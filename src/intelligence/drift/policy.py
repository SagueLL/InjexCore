"""Pydantic policy schema for the Drift Intelligence component.

Materialised from ``configs/drift_intelligence.yaml``. The drift taxonomies
(scope, drift type, temporal shape, status, severity, view) are the contract
and live here as closed vocabularies — tunables (windows, caps, weights,
thresholds) live in the policy models. Every model inherits
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

#: Closed vocabularies (the contract, not tunables).
SCOPES = ("sensor", "profile", "context", "correlation", "multivariate", "global")
DRIFT_TYPES = (
    "sensor_drift",
    "process_drift",
    "context_shift",
    "correlation_shift",
    "multivariate_shift",
    "profile_composition_shift",
    "unknown_shift",
)
TEMPORAL_SHAPES = (
    "abrupt",
    "progressive",
    "episodic",
    "persistent",
    "transient",
    "unknown",
)
EVENT_STATUSES = (
    "candidate",
    "active",
    "persistent",
    "resolved",
    "dismissed",
    "pending_review",
)
#: Drift severity vocabulary — deliberately distinct from the Finding
#: ``Severity`` enum (report severities) to avoid conflating the two.
DRIFT_SEVERITIES = ("info", "warning", "anomaly", "critical")
VIEWS = ("raw", "healthy_only")

#: Pseudo-profile key for metrics computed over all rows regardless of profile.
GLOBAL_SCOPE_KEY = "__global__"

UNIVARIATE_METRICS = (
    "mean_shift",
    "median_shift",
    "std_shift",
    "iqr_shift",
    "zero_rate_shift",
    "missingness_shift",
    "unique_value_collapse",
    "psi",
    "ks_statistic",
    "wasserstein_distance",
)

#: Honest label for the optional Level-B multivariate approximation — this is
#: an interpretive proxy computed from persisted per-feature contributions,
#: never a rescoring of upstream models.
HEALTHY_ONLY_PROXY_LABEL = "healthy_only_proxy"


class UpstreamRunsPolicy(StrictModel):
    """Upstream artifact locations + run pins.

    Behaviour artifacts are fixed paths (Iteration A is not run-versioned);
    everything else is run-versioned and resolved via the completed-run
    convention (``latest`` supported, or a pinned id for reproducibility).
    """

    profile_labels_path: str = (
        "data/intelligence/behaviour/profiles/profile_labels.parquet"
    )
    behaviour_manifest_path: str = (
        "data/intelligence/behaviour/behaviour_fit_manifest.json"
    )
    anomaly_root: str = "data/intelligence/anomaly"
    anomaly_run: str = "latest"
    pca_root: str = "data/intelligence/pca"
    pca_run: str = "latest"
    correlation_root: str = "data/intelligence/correlation"
    correlation_run: str = "latest"
    sensor_health_root: str = "data/intelligence/sensor_health"
    sensor_health_run: str = "latest"
    operational_root: str = "data/context/operational"
    operational_run: str = "latest"


class WindowsPolicy(StrictModel):
    """Tumbling observation windows for drift metrics.

    ``daily`` keeps the distribution metrics (PSI/KS/W1) to ~120 windows over
    the four-month span — seconds of compute. ``hourly`` is supported but
    multiplies the metric loops ~24x; use deliberately.
    """

    granularity: Literal["hourly", "daily"] = "daily"
    min_rows_per_window: int = Field(30, ge=1)
    min_valid_fraction: float = Field(0.3, ge=0.0, le=1.0)


class UnivariatePolicy(StrictModel):
    enabled_metrics: list[str] = Field(default_factory=lambda: list(UNIVARIATE_METRICS))
    per_profile: bool = True
    psi_bins: int = Field(10, ge=2)
    psi_smoothing: float = Field(1.0e-4, gt=0.0)
    max_reference_sample: int = Field(5000, ge=100)
    unique_collapse_train_factor: float = Field(0.5, gt=0.0, le=1.0)
    zero_eps: float = Field(1.0e-9, ge=0.0)


class MultivariatePolicy(StrictModel):
    """Distribution shifts of *persisted* scores — nothing is recomputed."""

    enabled: bool = True
    anomaly_score_columns: list[str] = Field(
        default_factory=lambda: [
            "statistical_score",
            "mahalanobis_score",
            "pca_q_score",
            "pca_t2_score",
            "isolation_forest_score",
            "combined_score",
        ]
    )
    pca_score_columns: list[str] = Field(
        default_factory=lambda: ["t2", "q_spe", "reconstruction_error"]
    )
    severity_rate: bool = True
    detector_agreement: bool = True


class CorrelationDriftPolicy(StrictModel):
    """Classification of the persisted correlation train-vs-validation shift.

    The correlation run persists one Pearson delta per (profile, pair) —
    windowed correlation recomputation is out of scope here. Validation
    Spearman values are not persisted upstream, so Spearman *changes* are
    reported as an upstream limitation, not fabricated.
    """

    enabled: bool = True
    top_k_pairs: int = Field(20, ge=1)
    strong_threshold: float = Field(0.7, ge=0.0, le=1.0)
    weak_threshold: float = Field(0.3, ge=0.0, le=1.0)
    sign_flip_min_abs: float = Field(0.3, ge=0.0, le=1.0)
    material_delta: float = Field(0.3, ge=0.0, le=2.0)
    min_material_pairs_for_event: int = Field(3, ge=1)


class ContextDriftPolicy(StrictModel):
    enabled: bool = True
    columns: list[str] = Field(
        default_factory=lambda: [
            "profile",
            "steam_context",
            "sensor_health_context",
            "product_code",
            "recipe_context_key",
            "bom_context_status",
        ]
    )
    psi_smoothing: float = Field(1.0e-4, gt=0.0)


class HealthyViewPolicy(StrictModel):
    """Analytical healthy-only view — interpretation only, never mutation."""

    enabled: bool = True
    exclude_statuses: list[str] = Field(
        default_factory=lambda: ["faulty", "quarantine_recommended"]
    )
    evidence_dominance_fraction: float = Field(0.6, gt=0.0, le=1.0)
    multivariate_proxy: bool = True


class SensorHealthOverridePolicy(StrictModel):
    """Instrumentation events trump process interpretation (spec §7.5)."""

    enabled: bool = True
    strong_issue_families: list[str] = Field(
        default_factory=lambda: ["flatline_zero", "counter_reset", "missingness_spike"]
    )
    min_overlap_fraction: float = Field(0.5, gt=0.0, le=1.0)
    promote_faulty_events: bool = True


def _default_metric_caps() -> dict[str, float]:
    return {
        "mean_shift": 3.0,
        "median_shift": 3.0,
        "std_shift": 1.5,
        "iqr_shift": 1.5,
        "zero_rate_shift": 0.5,
        "missingness_shift": 0.5,
        "unique_value_collapse": 1.0,
        "psi": 0.5,
        "ks_statistic": 0.5,
        "wasserstein_distance": 3.0,
        "severity_rate_shift": 0.5,
        "detector_agreement_shift": 2.0,
        "categorical_psi": 0.5,
        "total_variation": 0.5,
    }


def _default_metric_weights() -> dict[str, float]:
    return {
        "mean_shift": 0.5,
        "median_shift": 0.5,
        "std_shift": 0.5,
        "iqr_shift": 0.5,
        "zero_rate_shift": 1.0,
        "missingness_shift": 1.0,
        "unique_value_collapse": 1.0,
        "psi": 1.0,
        "ks_statistic": 1.0,
        "wasserstein_distance": 1.0,
        "severity_rate_shift": 1.0,
        "detector_agreement_shift": 0.5,
        "categorical_psi": 1.0,
        "total_variation": 1.0,
    }


def _default_severity_thresholds() -> dict[str, float]:
    return {"info": 0.0, "warning": 0.4, "anomaly": 0.6, "critical": 0.8}


class DriftScoringPolicy(StrictModel):
    """Normalized metrics -> weighted score -> calibration -> severity.

    Train-window self-calibration mirrors the sensor-health idiom: a window
    only counts as drifting when its weighted evidence exceeds the in-control
    envelope (``train_calibration_quantile``) that the train period itself
    produced for the same (scope, entity, profile) — small-window sampling
    noise and naturally variable context mixes cancel out instead of flagging.
    """

    metric_caps: dict[str, float] = Field(default_factory=_default_metric_caps)
    metric_weights: dict[str, float] = Field(default_factory=_default_metric_weights)
    train_calibration: bool = True
    train_calibration_quantile: float = Field(0.95, gt=0.5, le=1.0)
    train_calibration_min_windows: int = Field(5, ge=1)
    excess_cap: float = Field(0.3, gt=0.0, le=1.0)
    persistence_bonus: float = Field(0.1, ge=0.0, le=0.5)
    persistence_min_windows: int = Field(3, ge=1)
    severity_thresholds: dict[str, float] = Field(
        default_factory=_default_severity_thresholds
    )


class DriftEventsPolicy(StrictModel):
    active_score_threshold: float = Field(0.5, ge=0.0, le=1.0)
    gap_merge_windows: int = Field(1, ge=0)
    candidate_max_windows: int = Field(1, ge=1)
    persistent_min_windows: int = Field(7, ge=1)
    abrupt_onset_max_windows: int = Field(2, ge=1)
    progressive_min_onset_windows: int = Field(4, ge=2)
    episodic_min_segments: int = Field(3, ge=2)
    promoted_event_absorb_coverage: float = Field(0.7, gt=0.0, le=1.0)


class DriftPolicy(StrictModel):
    """Aggregate policy loaded from ``configs/drift_intelligence.yaml``."""

    features: FeatureSelectionPolicy = Field(default_factory=FeatureSelectionPolicy)
    profiles: ProfileGatePolicy = Field(default_factory=ProfileGatePolicy)
    upstream: UpstreamRunsPolicy = Field(default_factory=UpstreamRunsPolicy)
    windows: WindowsPolicy = Field(default_factory=WindowsPolicy)
    univariate: UnivariatePolicy = Field(default_factory=UnivariatePolicy)
    multivariate: MultivariatePolicy = Field(default_factory=MultivariatePolicy)
    correlation: CorrelationDriftPolicy = Field(default_factory=CorrelationDriftPolicy)
    context: ContextDriftPolicy = Field(default_factory=ContextDriftPolicy)
    healthy_view: HealthyViewPolicy = Field(default_factory=HealthyViewPolicy)
    sensor_health_override: SensorHealthOverridePolicy = Field(
        default_factory=SensorHealthOverridePolicy
    )
    scoring: DriftScoringPolicy = Field(default_factory=DriftScoringPolicy)
    events: DriftEventsPolicy = Field(default_factory=DriftEventsPolicy)


def severity_from_score(score: float, thresholds: dict[str, float]) -> str:
    """Map a drift score in [0, 1] onto the drift-severity vocabulary."""
    severity = "info"
    for name in DRIFT_SEVERITIES:
        cut = thresholds.get(name)
        if cut is not None and score >= cut:
            severity = name
    return severity


def load_policy(yaml_path: Path) -> DriftPolicy:
    """Read the YAML config and validate it against the schema."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Drift policy not found at {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return DriftPolicy.model_validate(raw)
