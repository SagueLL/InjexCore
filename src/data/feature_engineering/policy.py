"""Pydantic policy schema for the feature engineering pipeline.

Single source of truth for per-family enablement, windows / lags,
explicit cross-column pairs and ratios. Materialised from
``configs/feature_engineering.yaml`` at startup and passed read-only
into every detect / apply function.

Windows and lags are in *samples*. The pipeline runs on the
time-series engineering output, which is assumed to be on a regular
sample grid (cleaning enforces 60 s; ts resampling is optional).
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Family 1 — temporal derivatives
# ---------------------------------------------------------------------------


class AccelerationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    lags: list[int] = Field(default_factory=lambda: [1, 5])
    categories: list[str] = Field(default_factory=lambda: ["process_sensor"])


class SignChangeRatePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    windows: list[int] = Field(default_factory=lambda: [15, 60])
    categories: list[str] = Field(default_factory=lambda: ["process_sensor"])
    closed: str = "left"


class SpPvDeviationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    # Map setpoint column -> process-variable column.
    pairs: dict[str, str] = Field(default_factory=dict)


class TemporalDerivativesPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    acceleration: AccelerationPolicy = Field(default_factory=AccelerationPolicy)
    sign_change_rate: SignChangeRatePolicy = Field(
        default_factory=SignChangeRatePolicy
    )
    sp_pv_deviation: SpPvDeviationPolicy = Field(default_factory=SpPvDeviationPolicy)


# ---------------------------------------------------------------------------
# Family 2 — stability
# ---------------------------------------------------------------------------


class CvPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    windows: list[int] = Field(default_factory=lambda: [15, 60])
    categories: list[str] = Field(default_factory=lambda: ["process_sensor"])
    epsilon: float = 1.0e-6
    closed: str = "left"


class StdRatioPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    short: int = 5
    long: int = 60
    categories: list[str] = Field(default_factory=lambda: ["process_sensor"])
    epsilon: float = 1.0e-6


class RollingRangePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    windows: list[int] = Field(default_factory=lambda: [15, 60])
    categories: list[str] = Field(default_factory=lambda: ["process_sensor"])
    closed: str = "left"


class MadPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    windows: list[int] = Field(default_factory=lambda: [60])
    categories: list[str] = Field(default_factory=lambda: ["process_sensor"])
    units: list[str] = Field(default_factory=lambda: ["C", "bar"])
    closed: str = "left"


class StabilityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    cv: CvPolicy = Field(default_factory=CvPolicy)
    std_ratio: StdRatioPolicy = Field(default_factory=StdRatioPolicy)
    rolling_range: RollingRangePolicy = Field(default_factory=RollingRangePolicy)
    mad: MadPolicy = Field(default_factory=MadPolicy)


# ---------------------------------------------------------------------------
# Family 3 — physical ratios
# ---------------------------------------------------------------------------


class RatioSpec(BaseModel):
    """One explicit cross-column ratio / difference / scale feature."""

    model_config = ConfigDict(extra="forbid")
    name: str
    op: Literal["ratio", "diff", "scale"] = "ratio"
    a: str
    b: str | None = None
    factor: float | None = None


class PhysicalRatiosPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    epsilon: float = 1.0e-6
    nan_rate_warn: float = 0.50
    ratios: list[RatioSpec] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Family 4 — energetic features
# ---------------------------------------------------------------------------


class CumulativeEnergyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    daily_reset: bool = True


class EnergyPerKgPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    windows: list[int] = Field(default_factory=lambda: [60, 240])
    epsilon: float = 1.0e-6
    closed: str = "left"


class PerCyclePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Disabled by default until a cycle marker column exists.
    enabled: bool = False
    cycle_id_column: str | None = None


class EnergeticFeaturesPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    sample_period_s: float = 60.0
    power_columns: list[str] = Field(default_factory=list)
    production_column: str | None = None
    cumulative: CumulativeEnergyPolicy = Field(default_factory=CumulativeEnergyPolicy)
    energy_per_kg: EnergyPerKgPolicy = Field(default_factory=EnergyPerKgPolicy)
    per_cycle: PerCyclePolicy = Field(default_factory=PerCyclePolicy)


# ---------------------------------------------------------------------------
# Family 5 — operative features
# ---------------------------------------------------------------------------


class TotalAlarmsPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    windows: list[int] = Field(default_factory=lambda: [60, 240])
    closed: str = "left"


class OperativeFeaturesPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    running_flags: list[str] = Field(default_factory=list)
    alarm_flags: list[str] = Field(default_factory=list)
    time_since_machine_off: bool = True
    n_subsystems_running: bool = True
    cumulative_starts: bool = True
    total_alarms: TotalAlarmsPolicy = Field(default_factory=TotalAlarmsPolicy)
    time_since_any_alarm: bool = True
    any_alarm_while_running: bool = True


# ---------------------------------------------------------------------------
# Family 6 — statistical anomaly features
# ---------------------------------------------------------------------------


class RollingZPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    windows: list[int] = Field(default_factory=lambda: [60, 240])
    categories: list[str] = Field(default_factory=lambda: ["process_sensor"])
    epsilon: float = 1.0e-6
    closed: str = "left"


class RobustZPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    windows: list[int] = Field(default_factory=lambda: [60])
    categories: list[str] = Field(default_factory=lambda: ["process_sensor"])
    epsilon: float = 1.0e-6
    closed: str = "left"


class GlobalZPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # OFF by default — leaks future statistics into past rows.
    enabled: bool = False
    categories: list[str] = Field(default_factory=lambda: ["process_sensor"])
    epsilon: float = 1.0e-6


class AnomalyFeaturesPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    rolling_z: RollingZPolicy = Field(default_factory=RollingZPolicy)
    robust_z: RobustZPolicy = Field(default_factory=RobustZPolicy)
    global_z: GlobalZPolicy = Field(default_factory=GlobalZPolicy)


# ---------------------------------------------------------------------------
# Aggregate policy
# ---------------------------------------------------------------------------


class FeatureEngineeringPolicy(BaseModel):
    """Aggregate policy loaded from ``configs/feature_engineering.yaml``."""

    model_config = ConfigDict(extra="forbid")

    temporal_derivatives: TemporalDerivativesPolicy = Field(
        default_factory=TemporalDerivativesPolicy
    )
    stability: StabilityPolicy = Field(default_factory=StabilityPolicy)
    physical_ratios: PhysicalRatiosPolicy = Field(default_factory=PhysicalRatiosPolicy)
    energetic_features: EnergeticFeaturesPolicy = Field(
        default_factory=EnergeticFeaturesPolicy
    )
    operative_features: OperativeFeaturesPolicy = Field(
        default_factory=OperativeFeaturesPolicy
    )
    anomaly_features: AnomalyFeaturesPolicy = Field(
        default_factory=AnomalyFeaturesPolicy
    )


def load_policy(yaml_path: Path) -> FeatureEngineeringPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Feature engineering policy not found at {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return FeatureEngineeringPolicy.model_validate(raw)
