"""Pydantic policy schema for the PCA Intelligence component.

Materialised from ``configs/pca_intelligence.yaml``. Composes the shared
feature-selection and profile-gate fragments. Every model inherits
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


class PcaModelPolicy(StrictModel):
    """Per-profile scaling + PCA fitting knobs.

    ``explained_variance_target`` picks the smallest component count whose
    cumulative explained variance reaches the target (optionally capped by
    ``max_components``). ``robust`` scaling (median/IQR) is the default —
    industrial sensors carry outliers that would distort a mean/std scaler.
    ``median_impute`` fills gaps with the *training* median (leakage-safe);
    ``drop_rows`` drops incomplete rows instead.
    """

    explained_variance_target: float = Field(0.95, gt=0.0, le=1.0)
    max_components: int | None = Field(None, ge=1)
    min_features: int = Field(3, ge=2)
    scaler: Literal["robust", "standard"] = "robust"
    missing_policy: Literal["median_impute", "drop_rows"] = "median_impute"
    max_missing_fraction: float = Field(0.3, ge=0.0, le=1.0)
    near_constant_std: float = Field(1e-9, ge=0.0)
    random_state: int = 42


class PcaPolicy(StrictModel):
    """Aggregate policy loaded from ``configs/pca_intelligence.yaml``."""

    features: FeatureSelectionPolicy = Field(default_factory=FeatureSelectionPolicy)
    profiles: ProfileGatePolicy = Field(default_factory=ProfileGatePolicy)
    model: PcaModelPolicy = Field(default_factory=PcaModelPolicy)


def load_policy(yaml_path: Path) -> PcaPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"PCA-intelligence policy not found at {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return PcaPolicy.model_validate(raw)
