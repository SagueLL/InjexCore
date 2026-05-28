"""Pydantic policy schema for the time-series engineering pipeline.

Single source of truth for stage toggles, per-category feature defaults
and per-column overrides. Materialised from ``configs/time_series.yaml``
at startup and passed read-only into every detect/apply function.

Window sizes and lag depths are expressed in *samples*, not seconds — the
resampling stage (when enabled) makes the sample period predictable.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Stage policies
# ---------------------------------------------------------------------------


class TemporalConversionPolicy(BaseModel):
    enabled: bool = True
    timestamp_col: str = "timestamp"


class TemporalIndexPolicy(BaseModel):
    enabled: bool = True
    drop_duplicates_on_index: bool = True


class ResamplingPolicy(BaseModel):
    enabled: bool = False
    rule: str = "1min"
    aggregations: dict[str, str] = Field(
        default_factory=lambda: {
            "process_sensor": "mean",
            "setpoint": "last",
            "state_flag": "max",
            "alarm": "max",
            "control": "mean",
        }
    )


class StateFeaturesPolicy(BaseModel):
    enabled: bool = True
    running_fraction_windows: list[int] = Field(default_factory=lambda: [15, 60, 240])
    time_since_active: bool = True
    edge_count_windows: list[int] = Field(default_factory=lambda: [60, 240])


# ---------------------------------------------------------------------------
# Generic feature families (Stage 4 + Stage 5)
# ---------------------------------------------------------------------------


class FeatureFamilySpec(BaseModel):
    """One generic feature family for one semantic category.

    Rolling families use ``windows`` (samples); shift-based families
    (``lag``, ``pct_change``, ``velocity``) use ``lags`` (samples).
    The ``closed`` setting only applies to rolling families; for shift
    families it is ignored.
    """

    enabled: bool = True
    windows: list[int] = Field(default_factory=lambda: [5, 15, 60])
    lags: list[int] = Field(default_factory=lambda: [1, 5, 15])
    closed: str = "left"


class CategoryDefaults(BaseModel):
    """Per-semantic-category default feature families."""

    rolling_mean: FeatureFamilySpec = Field(default_factory=FeatureFamilySpec)
    rolling_std: FeatureFamilySpec = Field(default_factory=FeatureFamilySpec)
    rolling_trend: FeatureFamilySpec = Field(default_factory=FeatureFamilySpec)
    lag: FeatureFamilySpec = Field(default_factory=FeatureFamilySpec)
    pct_change: FeatureFamilySpec = Field(default_factory=FeatureFamilySpec)
    velocity: FeatureFamilySpec = Field(default_factory=FeatureFamilySpec)


class ColumnOverride(BaseModel):
    """Optional per-column overrides applied on top of category defaults."""

    disable_families: list[str] = Field(default_factory=list)
    enable_families: list[str] = Field(default_factory=list)
    windows: list[int] | None = None
    lags: list[int] | None = None


# ---------------------------------------------------------------------------
# Aggregate policy
# ---------------------------------------------------------------------------


class TimeSeriesPolicy(BaseModel):
    """Aggregate policy loaded from ``configs/time_series.yaml``."""

    temporal_conversion: TemporalConversionPolicy = Field(
        default_factory=TemporalConversionPolicy
    )
    temporal_index: TemporalIndexPolicy = Field(default_factory=TemporalIndexPolicy)
    resampling: ResamplingPolicy = Field(default_factory=ResamplingPolicy)
    state_features: StateFeaturesPolicy = Field(default_factory=StateFeaturesPolicy)
    category_defaults: dict[str, CategoryDefaults] = Field(default_factory=dict)
    overrides: dict[str, ColumnOverride] = Field(default_factory=dict)

    def resolve(self, category: str, column: str) -> CategoryDefaults:
        """Return the effective :class:`CategoryDefaults` for ``column``.

        Starts from the category defaults and applies the column override
        (if any): ``windows`` / ``lags`` replace the values on every
        family, then ``disable_families`` / ``enable_families`` toggle
        the ``enabled`` flag.
        """
        base = self.category_defaults.get(category)
        if base is None:
            base = CategoryDefaults()
        override = self.overrides.get(column)
        if override is None:
            return base

        merged = base.model_copy(deep=True)
        for fam_name in (
            "rolling_mean",
            "rolling_std",
            "rolling_trend",
            "lag",
            "pct_change",
            "velocity",
        ):
            fam: FeatureFamilySpec = getattr(merged, fam_name)
            if override.windows is not None:
                fam.windows = list(override.windows)
            if override.lags is not None:
                fam.lags = list(override.lags)
            if fam_name in override.disable_families:
                fam.enabled = False
            if fam_name in override.enable_families:
                fam.enabled = True
        return merged


def load_policy(yaml_path: Path) -> TimeSeriesPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Time-series policy not found at {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return TimeSeriesPolicy.model_validate(raw)
