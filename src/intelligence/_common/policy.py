"""Reusable pydantic policy fragments shared by Iteration B components.

Each component's aggregate policy (``CorrelationPolicy``, ``PcaPolicy``,
``AnomalyPolicy``) composes these fragments so feature eligibility and
profile gating behave identically across the layer. Everything inherits
:class:`StrictModel` (``extra="forbid"``) — a misspelled YAML key raises.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.preprocessing._common.models import StrictModel

# Pseudo-profile name used when ``global_fallback`` pools all rows.
GLOBAL_PROFILE = "__global__"


class FeatureSelectionPolicy(StrictModel):
    """Which columns a component analyses.

    ``process_sensor`` selects the ~17 raw process signals via the semantic
    catalogue (default; keeps matrices, loadings and anomaly evidence
    interpretable). ``explicit`` uses ``include_columns`` verbatim — the
    opt-in route to engineered features. ``exclude_columns`` always applies.
    """

    source: Literal["process_sensor", "explicit"] = "process_sensor"
    include_columns: list[str] = Field(default_factory=list)
    exclude_columns: list[str] = Field(default_factory=list)
    min_non_null_fraction: float = Field(0.7, ge=0.0, le=1.0)


class ProfileGatePolicy(StrictModel):
    """Per-profile support gate.

    Profiles with fewer than ``min_samples_per_profile`` training rows are
    skipped and reported, never silently fitted. ``global_fallback`` pools
    every row into a single ``__global__`` pseudo-profile *in addition to*
    the per-profile fits — disabled by default because it mixes operational
    regimes; enable only as an explicit, documented choice.
    """

    min_samples_per_profile: int = Field(200, ge=1)
    exclude_profiles: list[str] = Field(default_factory=lambda: ["unknown"])
    global_fallback: bool = False
