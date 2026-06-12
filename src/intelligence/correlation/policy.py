"""Pydantic policy schema for the Correlation Intelligence component.

Materialised from ``configs/correlation_intelligence.yaml``. Composes the
shared feature-selection and profile-gate fragments so eligibility behaves
identically across Iteration B components. Every model inherits
:class:`StrictModel` — a misspelled YAML key raises instead of being
silently dropped.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field

from src.intelligence._common.policy import (
    FeatureSelectionPolicy,
    ProfileGatePolicy,
)
from src.preprocessing._common.models import StrictModel


class CorrelationThresholdsPolicy(StrictModel):
    """Eligibility and reporting thresholds.

    ``min_valid_observations`` is the pairwise ``min_periods`` — a cell with
    fewer joint non-null observations is NaN, never a guess. Features whose
    training std falls below ``near_constant_std`` or whose missing fraction
    exceeds ``max_missing_fraction`` are excluded with a recorded reason.
    """

    min_valid_observations: int = Field(200, ge=2)
    near_constant_std: float = Field(1e-9, ge=0.0)
    strong_threshold: float = Field(0.8, ge=0.0, le=1.0)
    redundancy_threshold: float = Field(0.95, ge=0.0, le=1.0)
    max_missing_fraction: float = Field(0.3, ge=0.0, le=1.0)


class CorrelationShiftPolicy(StrictModel):
    """Train-vs-validation shift diagnostics — diagnostics only, no alerts.

    Pairs whose |Pearson(train) - Pearson(validation)| exceeds
    ``delta_threshold`` are surfaced as AWARE findings (at most ``top_k``).
    """

    enabled: bool = True
    top_k: int = Field(20, ge=1)
    delta_threshold: float = Field(0.2, ge=0.0, le=2.0)


class CorrelationPolicy(StrictModel):
    """Aggregate policy loaded from ``configs/correlation_intelligence.yaml``."""

    features: FeatureSelectionPolicy = Field(default_factory=FeatureSelectionPolicy)
    profiles: ProfileGatePolicy = Field(default_factory=ProfileGatePolicy)
    thresholds: CorrelationThresholdsPolicy = Field(
        default_factory=CorrelationThresholdsPolicy
    )
    shift: CorrelationShiftPolicy = Field(default_factory=CorrelationShiftPolicy)


def load_policy(yaml_path: Path) -> CorrelationPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Correlation-intelligence policy not found at {yaml_path}"
        )
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return CorrelationPolicy.model_validate(raw)
