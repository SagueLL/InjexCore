"""Drift & Anomaly payload schemas.

Mirrors the frontend ``DriftAnomalySummary`` type
(apps/dashboard/src/types/drift-anomaly.ts) with the §3 delta
(docs/dashboard/dashboard_api_contract.md): the ``DetectionMethod`` union is
replaced with the real backend detectors — ``pca_q`` is served as
``pca_residual`` (Q/SPE is the residual distance), ``pca_t2`` stays separate
(in-model distance), and the demo-only ``lof`` / ``ocsvm`` methods are removed
because they do not exist in the backend (serving them would be fabrication).
``context_overlay`` is an interpretive review overlay row, not a detector.
"""

from __future__ import annotations

from typing import Literal

from src.api.schemas import CamelModel

DriftAnomalySeverity = Literal["normal", "warning", "critical"]
DetectionMethod = Literal[
    "statistical",
    "mahalanobis",
    "pca_t2",
    "pca_residual",
    "isolation_forest",
    "context_overlay",
]
ContributionLevel = Literal["low", "medium", "high"]


class DriftAnomalyKpi(CamelModel):
    """One funnel KPI; ``value`` carries raw numbers, never preformatted."""

    label: str
    value: int | float | str
    description: str | None = None


class AnomalyEvidencePoint(CamelModel):
    """One UTC day of anomaly evidence (days without scored rows are omitted)."""

    date: str
    anomaly_score: float
    anomaly_count: int
    residual_count: int
    severity: DriftAnomalySeverity


class DetectionMethodSummary(CamelModel):
    """One detection method (or the interpretive context overlay) with its evidence."""

    method: DetectionMethod
    label: str
    evidence_count: int
    description: str


class AffectedSignal(CamelModel):
    """One sensor ranked by its share of the residual review evidence."""

    sensor_id: str
    display_name: str
    contribution: ContributionLevel
    severity: DriftAnomalySeverity
    interpretation: str


class DriftAnomalyInsight(CamelModel):
    """A curated insight block; numbers are interpolated from artifacts."""

    title: str
    body: str


class DriftAnomalySummary(CamelModel):
    """The drift-anomaly view payload served under the envelope's ``data`` field."""

    asset_name: str
    dataset_name: str
    period_start: str
    period_end: str
    summary_kpis: list[DriftAnomalyKpi]
    evidence_series: list[AnomalyEvidencePoint]
    detection_methods: list[DetectionMethodSummary]
    affected_signals: list[AffectedSignal]
    insights: list[DriftAnomalyInsight]
