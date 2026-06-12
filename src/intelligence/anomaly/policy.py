"""Pydantic policy schema for the Anomaly Intelligence component.

Materialised from ``configs/anomaly_intelligence.yaml``. One sub-policy per
detector plus the combination/severity rule. Every model inherits
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


class StatisticalDetectorPolicy(StrictModel):
    """Detector A — baselines-driven, model-free.

    ``lower/upper_percentile`` name baseline columns (``p05``/``p95`` by
    default) used for breach flags. The robust z denominator is
    ``iqr / 1.349`` (≈σ under normality), falling back to ``std`` for
    profiles where the IQR collapses.
    """

    enabled: bool = True
    lower_percentile: str = "p05"
    upper_percentile: str = "p95"
    robust_z_threshold: float = Field(3.5, gt=0.0)
    top_k_variables: int = Field(3, ge=1)


class MahalanobisPolicy(StrictModel):
    """Detector B — regularized multivariate distance."""

    enabled: bool = True
    estimator: Literal["ledoit_wolf", "shrunk"] = "ledoit_wolf"
    shrinkage: float = Field(0.1, ge=0.0, le=1.0)  # only for estimator="shrunk"
    top_k_variables: int = Field(3, ge=1)


class PcaDetectorPolicy(StrictModel):
    """Detector C — consumes the persisted PCA Intelligence run.

    Thresholds are empirical training-score percentiles, NOT parametric
    (F-distribution) limits: the data is autocorrelated and non-normal, and
    parametric thresholds would be false precision.
    """

    enabled: bool = True
    t2_threshold_percentile: float = Field(99.0, gt=50.0, lt=100.0)
    q_threshold_percentile: float = Field(99.0, gt=50.0, lt=100.0)
    top_k_variables: int = Field(3, ge=1)


class IsolationForestPolicy(StrictModel):
    """Detector D — Isolation Forest, deterministic and transparent.

    ``contamination`` is intentionally not exposed: triggering comes from
    the train-score ECDF like every other detector, not from sklearn's
    internal offset.
    """

    enabled: bool = True
    n_estimators: int = Field(200, ge=10)
    max_samples: int | Literal["auto"] = "auto"
    random_state: int = 42


class CombinePolicy(StrictModel):
    """Score combination + severity rule — simple and documented.

    ``max`` (default) is the conservative rule: the combined score is the
    worst normalized detector score. ``weighted_mean`` averages available
    detectors with ``weights``. Severity thresholds are percentiles of the
    *training* combined score per profile.
    """

    method: Literal["max", "weighted_mean"] = "max"
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "statistical": 1.0,
            "mahalanobis": 1.0,
            "pca_q": 1.0,
            "pca_t2": 1.0,
            "isolation_forest": 1.0,
        }
    )
    trigger_percentile: float = Field(99.0, gt=50.0, lt=100.0)
    warning_percentile: float = Field(99.0, gt=50.0, lt=100.0)
    anomaly_percentile: float = Field(99.9, gt=50.0, lt=100.0)


class SummariesPolicy(StrictModel):
    """Operational summary reports."""

    top_events: int = Field(50, ge=1)
    timeline_freq: str = "1h"


class AnomalyPolicy(StrictModel):
    """Aggregate policy loaded from ``configs/anomaly_intelligence.yaml``."""

    features: FeatureSelectionPolicy = Field(default_factory=FeatureSelectionPolicy)
    profiles: ProfileGatePolicy = Field(default_factory=ProfileGatePolicy)
    statistical: StatisticalDetectorPolicy = Field(
        default_factory=StatisticalDetectorPolicy
    )
    mahalanobis: MahalanobisPolicy = Field(default_factory=MahalanobisPolicy)
    pca_detector: PcaDetectorPolicy = Field(default_factory=PcaDetectorPolicy)
    isolation_forest: IsolationForestPolicy = Field(
        default_factory=IsolationForestPolicy
    )
    combine: CombinePolicy = Field(default_factory=CombinePolicy)
    summaries: SummariesPolicy = Field(default_factory=SummariesPolicy)


def load_policy(yaml_path: Path) -> AnomalyPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Anomaly-intelligence policy not found at {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return AnomalyPolicy.model_validate(raw)
