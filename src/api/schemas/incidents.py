"""Incidents payload schemas.

Mirrors the frontend ``IncidentsSummary`` type
(apps/dashboard/src/types/incidents.ts) plus the §3 additive deltas only —
optional ``sourceSeverity`` / ``sourceStatus`` / ``reviewStatus`` /
``startTimestamp`` / ``endTimestamp`` (docs/dashboard/dashboard_api_contract.md
§3); ignored by the v1 UI, available for detail views later.
"""

from __future__ import annotations

from typing import Literal

from src.api.schemas import CamelModel

IncidentSeverity = Literal["normal", "warning", "critical"]
# "closed" is reserved and never emitted in v1: backend "resolved" means the
# evidence window ended, not that a human reviewed it (contract §5.3).
IncidentStatus = Literal["open", "in_review", "contextualised", "closed"]


class IncidentKpi(CamelModel):
    """One incidents KPI; ``value`` carries raw numbers, never preformatted."""

    label: str
    value: int | float | str
    description: str | None = None


class IncidentSeverityDistributionItem(CamelModel):
    """One severity bucket; two rows may share ``severity: "critical"``.

    The backend's 4-tier severity (info/warning/anomaly/critical) is preserved
    through the labels — "Anomaly evidence" and "Critical" both map to the UI
    ``critical`` tier (contract §5).
    """

    severity: IncidentSeverity
    label: str
    count: int


class IncidentRecord(CamelModel):
    """One grouped evidence window served for review (never a confirmed fault)."""

    id: str
    title: str
    severity: IncidentSeverity
    status: IncidentStatus
    start_date: str
    end_date: str
    affected_signals: list[str]
    evidence_summary: str
    recommendation: str
    # Contract §3 additive optional fields (always set by the service).
    source_severity: str | None = None
    source_status: str | None = None
    review_status: str | None = None
    start_timestamp: str | None = None
    end_timestamp: str | None = None


class IncidentInsight(CamelModel):
    """One curated insight with computed numbers interpolated (contract §6/§8)."""

    title: str
    body: str


class IncidentsSummary(CamelModel):
    """The incidents view payload served under the envelope's ``data`` field."""

    asset_name: str
    dataset_name: str
    period_start: str
    period_end: str
    summary_kpis: list[IncidentKpi]
    severity_distribution: list[IncidentSeverityDistributionItem]
    incidents: list[IncidentRecord]
    insights: list[IncidentInsight]
