"""Pydantic policy schema for all six cleaning modules.

Single source of truth for thresholds and per-variable physical bounds.
The full policy is materialised from ``configs/cleaning.yaml`` at startup
and passed read-only into every detect/apply function.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass


class TimestampsPolicy(BaseModel):
    expected_period_s: float = 60.0
    gap_factor: float = 2.0
    max_legal_jump_s: float = 3600.0


class DuplicatesPolicy(BaseModel):
    payload_window_rows: int = 5
    burst_max_delta_s: float = 1.0
    burst_min_rows: int = 3


class FrozenSensorsPolicy(BaseModel):
    frozen_min_minutes: int = 120
    epsilon_rate_cols: list[str] = Field(default_factory=list)
    epsilon: float = 1e-6
    skip_columns: list[str] = Field(default_factory=list)


class MissingValuesPolicy(BaseModel):
    broken_sensor_min_run: int = 30
    interpolation_max_run: int = 5
    alarm_alignment_window_min: int = 10
    missing_by_design_columns: list[str] = Field(default_factory=list)


class Bound(BaseModel):
    min: float
    max: float
    severity: str = "important"
    integer: bool = False


class PhysicalRangesPolicy(BaseModel):
    clip_soft_violations: bool = False
    bounds: dict[str, Bound] = Field(default_factory=dict)


class StateConsistencyPolicy(BaseModel):
    min_production_kgmin: float = 0.1
    min_power_pct: float = 1.0
    alarm_shutdown_window_min: int = 10
    sp_pv_max_drift_pct: float = 20.0
    sp_pv_drift_min_minutes: int = 30
    hot_temperature_threshold_c: float = 200.0


class CleaningPolicy(BaseModel):
    """Aggregate policy loaded from ``configs/cleaning.yaml``."""

    timestamps: TimestampsPolicy = Field(default_factory=TimestampsPolicy)
    duplicates: DuplicatesPolicy = Field(default_factory=DuplicatesPolicy)
    frozen_sensors: FrozenSensorsPolicy = Field(default_factory=FrozenSensorsPolicy)
    missing_values: MissingValuesPolicy = Field(default_factory=MissingValuesPolicy)
    physical_ranges: PhysicalRangesPolicy = Field(default_factory=PhysicalRangesPolicy)
    state_consistency: StateConsistencyPolicy = Field(
        default_factory=StateConsistencyPolicy
    )


def load_policy(yaml_path: Path) -> CleaningPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Cleaning policy not found at {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return CleaningPolicy.model_validate(raw)
