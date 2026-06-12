"""Pydantic policy schema for the Sensor Health Intelligence component.

Materialised from ``configs/sensor_health_intelligence.yaml``. One sub-policy
per rule family plus scoring/event/quarantine policies and per-sensor
metadata (defaults + optional overrides). Every model inherits
:class:`StrictModel` — a misspelled YAML key raises.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from src.intelligence._common.policy import (
    FeatureSelectionPolicy,
    ProfileGatePolicy,
)
from src.preprocessing._common.models import StrictModel

#: Closed vocabulary of rule families (the contract, not a tunable).
ISSUE_TYPES = (
    "flatline",
    "flatline_zero",
    "variance_collapse",
    "variance_explosion",
    "missingness_spike",
    "abrupt_offset",
    "saturation_low",
    "saturation_high",
    "counter_reset",
    "stale_signal",
)

HEALTH_STATUSES = ("healthy", "warning", "faulty", "unknown")


class FlatlinePolicy(StrictModel):
    """Constant-value runs (non-zero values; zeros belong to flatline_zero)."""

    enabled: bool = True
    eps: float = Field(0.0, ge=0.0)  # exact equality (PLC-quantized values)
    min_run_rows: int = Field(60, ge=1)
    train_run_multiplier: float = Field(1.5, gt=0.0)


class FlatlineZeroPolicy(StrictModel):
    """Persistent exact-zero runs — the inlet_hopper_points failure mode."""

    enabled: bool = True
    zero_eps: float = Field(1.0e-9, ge=0.0)
    min_run_rows: int = Field(30, ge=1)
    min_run_rows_abnormal: int = Field(15, ge=1)
    abnormal_train_zero_fraction: float = Field(0.001, ge=0.0, le=1.0)
    train_run_multiplier: float = Field(1.5, gt=0.0)


class VarianceCollapsePolicy(StrictModel):
    """Rolling variance below both the baseline ratio AND the train floor.

    ``train_min_factor`` self-calibrates: a row only flags when its rolling
    std is below ``train_min_factor x`` the *quietest* profile-pure rolling
    std the train window ever showed for that (profile, sensor) — so the
    rule cannot contradict its own reference data.
    """

    enabled: bool = True
    window_rows: int = Field(60, ge=2)
    collapse_ratio: float = Field(0.05, gt=0.0)
    train_min_factor: float = Field(0.5, gt=0.0, le=1.0)
    require_profile_pure_window: bool = True


class VarianceExplosionPolicy(StrictModel):
    enabled: bool = True
    window_rows: int = Field(60, ge=2)
    explosion_ratio: float = Field(6.0, gt=1.0)
    require_profile_pure_window: bool = True


class MissingnessSpikePolicy(StrictModel):
    """Abrupt rise of the rolling NaN fraction over the train reference.

    The threshold self-calibrates against the *worst* rolling missingness
    observed in train (``train_max_margin`` headroom on top): sensors with
    routine full outage blocks (weekend gaps) never spike on the same
    pattern, while a never-missing sensor fires at the absolute floor.
    """

    enabled: bool = True
    window_rows: int = Field(240, ge=2)
    spike_margin: float = Field(0.25, ge=0.0, le=1.0)
    absolute_floor: float = Field(0.5, ge=0.0, le=1.0)
    train_max_margin: float = Field(0.05, ge=0.0, le=1.0)


class AbruptOffsetPolicy(StrictModel):
    """Persistent step in level — warning-capped (corroboration escalates)."""

    enabled: bool = True
    window_rows: int = Field(60, ge=2)
    jump_z_threshold: float = Field(8.0, gt=0.0)
    persistence_rows: int = Field(30, ge=1)


class SaturationPolicy(StrictModel):
    """Stuck at a configured physical bound (no train-minmax fallback)."""

    enabled: bool = True
    rel_tolerance: float = Field(1.0e-6, ge=0.0)
    abs_tolerance: float = Field(1.0e-9, ge=0.0)
    min_run_rows: int = Field(30, ge=1)


class CounterResetPolicy(StrictModel):
    """Drop-magnitude reset semantics for oscillating counter signals."""

    enabled: bool = True
    drop_fraction: float = Field(0.9, gt=0.0, le=1.0)
    low_ceiling_fraction: float = Field(0.01, gt=0.0, le=1.0)
    detect_window_rows: int = Field(5, ge=1)
    recovery_floor_fraction: float = Field(0.5, gt=0.0, le=1.0)
    recovery_window_rows: int = Field(60, ge=1)
    persistent_zero_rows: int = Field(240, ge=1)


class StaleSignalPolicy(StrictModel):
    """Almost-frozen signals (distinct-value collapse); weak corroborator.

    ``train_min_factor`` self-calibrates like variance_collapse: only rows
    whose unique-value fraction is below ``factor x`` the train minimum can
    flag — a sensor that already plateaus in train never re-flags the same
    plateau (full freezes belong to flatline anyway).
    """

    enabled: bool = True
    window_rows: int = Field(120, ge=2)
    max_unique_fraction: float = Field(0.05, gt=0.0, le=1.0)
    train_min_factor: float = Field(0.999, gt=0.0, le=1.0)


class RulesPolicy(StrictModel):
    flatline: FlatlinePolicy = Field(default_factory=FlatlinePolicy)
    flatline_zero: FlatlineZeroPolicy = Field(default_factory=FlatlineZeroPolicy)
    variance_collapse: VarianceCollapsePolicy = Field(
        default_factory=VarianceCollapsePolicy
    )
    variance_explosion: VarianceExplosionPolicy = Field(
        default_factory=VarianceExplosionPolicy
    )
    missingness_spike: MissingnessSpikePolicy = Field(
        default_factory=MissingnessSpikePolicy
    )
    abrupt_offset: AbruptOffsetPolicy = Field(default_factory=AbruptOffsetPolicy)
    saturation: SaturationPolicy = Field(default_factory=SaturationPolicy)
    counter_reset: CounterResetPolicy = Field(default_factory=CounterResetPolicy)
    stale_signal: StaleSignalPolicy = Field(default_factory=StaleSignalPolicy)


def _default_base_scores() -> dict[str, float]:
    return {
        "flatline_zero": 0.9,
        "counter_reset": 0.9,
        "counter_reset_recovered": 0.4,
        "flatline": 0.7,
        "saturation_low": 0.7,
        "saturation_high": 0.7,
        "missingness_spike": 0.7,
        "variance_collapse": 0.5,
        "variance_explosion": 0.5,
        "abrupt_offset": 0.4,
        "stale_signal": 0.3,
    }


class ScoringPolicy(StrictModel):
    """How rule activations become health_score + status (kept explainable)."""

    rule_base_scores: dict[str, float] = Field(default_factory=_default_base_scores)
    strong_rule_min_base: float = Field(0.7, gt=0.0, le=1.0)
    corroboration_bonus: float = Field(0.1, ge=0.0, le=1.0)
    persistent_min_rows: int = Field(120, ge=1)
    unknown_availability_window_rows: int = Field(60, ge=1)
    unknown_min_valid_fraction: float = Field(0.3, ge=0.0, le=1.0)


class EventsPolicy(StrictModel):
    gap_merge_rows: int = Field(5, ge=0)
    persistent_event_rows: int = Field(240, ge=1)


class QuarantinePolicy(StrictModel):
    """Recommendation only — approval_required/approved are hardcoded."""

    trigger_issue_types: list[str] = Field(
        default_factory=lambda: [
            "flatline_zero",
            "counter_reset",
            "saturation_low",
            "saturation_high",
            "missingness_spike",
        ]
    )
    require_persistent: bool = True


class SensorMeta(StrictModel):
    """Effective per-sensor metadata (defaults merged with overrides)."""

    kind: Literal["process", "counter"] = "process"
    expected_zero_during_profiles: list[str] = Field(default_factory=list)
    allow_flatline_profiles: list[str] = Field(
        default_factory=lambda: ["stopped", "shutdown"]
    )
    physical_min: float | None = None
    physical_max: float | None = None
    disabled_rules: list[str] = Field(default_factory=list)


class SensorMetaOverride(StrictModel):
    """Partial override; ``None`` fields inherit from the defaults."""

    kind: Literal["process", "counter"] | None = None
    expected_zero_during_profiles: list[str] | None = None
    allow_flatline_profiles: list[str] | None = None
    physical_min: float | None = None
    physical_max: float | None = None
    disabled_rules: list[str] | None = None


class SensorsPolicy(StrictModel):
    defaults: SensorMeta = Field(default_factory=SensorMeta)
    overrides: dict[str, SensorMetaOverride] = Field(default_factory=dict)


class SensorHealthPolicy(StrictModel):
    """Aggregate policy loaded from ``configs/sensor_health_intelligence.yaml``."""

    features: FeatureSelectionPolicy = Field(default_factory=FeatureSelectionPolicy)
    profiles: ProfileGatePolicy = Field(default_factory=ProfileGatePolicy)
    rules: RulesPolicy = Field(default_factory=RulesPolicy)
    scoring: ScoringPolicy = Field(default_factory=ScoringPolicy)
    events: EventsPolicy = Field(default_factory=EventsPolicy)
    quarantine: QuarantinePolicy = Field(default_factory=QuarantinePolicy)
    sensors: SensorsPolicy = Field(default_factory=SensorsPolicy)


def resolve_sensor_meta(policy: SensorHealthPolicy, sensor: str) -> SensorMeta:
    """Defaults merged with the sensor's override (non-None fields win)."""
    meta = policy.sensors.defaults.model_copy(deep=True)
    override = policy.sensors.overrides.get(sensor)
    if override is None:
        return meta
    updates = {k: v for k, v in override.model_dump().items() if v is not None}
    return meta.model_copy(update=updates)


def load_policy(yaml_path: Path) -> SensorHealthPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Sensor-health policy not found at {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return SensorHealthPolicy.model_validate(raw)
