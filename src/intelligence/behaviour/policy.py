"""Pydantic policy schema for the Behaviour Intelligence stage.

Single source of truth for the sensor set, the leakage-safe fit window,
the operational-profile segmentation rules and the statistical-baseline
configuration. Materialised from ``configs/behaviour_intelligence.yaml``
at startup and passed read-only into every ``derive`` / ``fit`` function.

Every model inherits :class:`StrictModel` so a misspelled key in the YAML
raises a ``ValidationError`` instead of being silently dropped — the same
``extra="forbid"`` guarantee the data stages enforce.

Windows are in *samples*. The stage runs on the master dataset, which is
on the regular sample grid the cleaning stage enforced (60 s).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from src.preprocessing._common.models import StrictModel

# ---------------------------------------------------------------------------
# Sensor selection
# ---------------------------------------------------------------------------


class SensorSelectionPolicy(StrictModel):
    """Which columns baselines are computed over.

    ``process_sensor`` selects the ~17 raw process signals via the semantic
    catalogue (recommended; keeps baselines interpretable and avoids the
    566-column engineered explosion). ``explicit`` uses ``include_columns``
    verbatim. ``exclude_columns`` always applies.
    """

    source: Literal["process_sensor", "explicit"] = "process_sensor"
    include_columns: list[str] = Field(default_factory=list)
    exclude_columns: list[str] = Field(default_factory=list)
    min_non_null_fraction: float = Field(0.7, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Fit window (leakage guard)
# ---------------------------------------------------------------------------


class FitWindowPolicy(StrictModel):
    """Time-ordered slice every learned artifact is fitted on.

    ``fraction`` trains on the first ``train_fraction`` of rows (default).
    ``date_range`` trains on ``[start, end]``. ``all`` trains on the whole
    dataset — EDA only; leaks future statistics into the "normal" reference.
    """

    strategy: Literal["fraction", "all", "date_range"] = "fraction"
    train_fraction: float = Field(0.7, gt=0.0, le=1.0)
    start: str | None = None
    end: str | None = None


# ---------------------------------------------------------------------------
# Profile segmentation
# ---------------------------------------------------------------------------


class StartupPolicy(StrictModel):
    enabled: bool = True
    window_samples: int = Field(30, ge=1)


class ShutdownPolicy(StrictModel):
    enabled: bool = True
    window_samples: int = Field(30, ge=1)


class AlarmPolicy(StrictModel):
    enabled: bool = True
    any_alarm_column: str = "any_alarm_while_running"
    time_since_alarm_column: str = "time_since_any_alarm"
    window_samples: int = Field(30, ge=0)


class MaterialChangePolicy(StrictModel):
    """Material/recipe change is NOT a derivable regime.

    ``candidate_flag`` exposes it as a separate boolean column derived from
    ``batch_columns`` transitions (a proxy, explicitly captioned), never
    merged into the primary profile label. ``off`` disables it entirely.
    """

    mode: Literal["candidate_flag", "off"] = "candidate_flag"
    batch_columns: list[str] = Field(
        default_factory=lambda: ["batch_id", "batch_quality_id"]
    )


class ProfilesPolicy(StrictModel):
    enabled: bool = True
    running_column: str = "n_subsystems_running"
    production_column: str = "granulator_production_rate"
    # Two cut points → three production levels (low / mid / high).
    production_quantiles: list[float] = Field(default_factory=lambda: [0.33, 0.67])
    startup: StartupPolicy = Field(default_factory=StartupPolicy)
    shutdown: ShutdownPolicy = Field(default_factory=ShutdownPolicy)
    alarm: AlarmPolicy = Field(default_factory=AlarmPolicy)
    material_change: MaterialChangePolicy = Field(default_factory=MaterialChangePolicy)
    # Precedence among *running* rows; highest wins. ``stopped`` always
    # applies when the machine is off.
    precedence: list[str] = Field(
        default_factory=lambda: ["alarm", "startup", "shutdown", "production"]
    )
    min_samples_per_profile: int = Field(200, ge=1)
    # Requested regimes that the available signals cannot support. Surfaced
    # as AWARE findings instead of being fabricated.
    unsupported_regimes: list[str] = Field(
        default_factory=lambda: ["cleaning", "maintenance", "recipe_change"]
    )


# ---------------------------------------------------------------------------
# Statistical baselines
# ---------------------------------------------------------------------------


class BaselinesPolicy(StrictModel):
    """Per-(profile, sensor) statistics. ``count``, ``mean``, ``median``,
    ``std``, ``min``, ``max`` and ``iqr`` are always emitted; ``percentiles``
    add ``pNN`` columns on top."""

    enabled: bool = True
    percentiles: list[float] = Field(
        default_factory=lambda: [5.0, 25.0, 50.0, 75.0, 95.0]
    )


# ---------------------------------------------------------------------------
# Aggregate policy
# ---------------------------------------------------------------------------


class BehaviourPolicy(StrictModel):
    """Aggregate policy loaded from ``configs/behaviour_intelligence.yaml``."""

    sensors: SensorSelectionPolicy = Field(default_factory=SensorSelectionPolicy)
    fit_window: FitWindowPolicy = Field(default_factory=FitWindowPolicy)
    profiles: ProfilesPolicy = Field(default_factory=ProfilesPolicy)
    baselines: BaselinesPolicy = Field(default_factory=BaselinesPolicy)


def load_policy(yaml_path: Path) -> BehaviourPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Behaviour-intelligence policy not found at {yaml_path}"
        )
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return BehaviourPolicy.model_validate(raw)
