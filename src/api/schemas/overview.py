"""Executive Overview payload schemas.

Mirrors the frontend ``DashboardSummary`` type
(apps/dashboard/src/types/dashboard.ts) plus the contract's only delta: an
optional ``statusReason`` that makes the status badge auditable
(docs/dashboard/dashboard_api_contract.md §3).
"""

from __future__ import annotations

from typing import Literal

from src.api.schemas import CamelModel

OperationalStatus = Literal["normal", "warning", "critical", "unknown"]


class DashboardKpi(CamelModel):
    """One overview KPI card; ``value`` carries raw numbers, never preformatted."""

    label: str
    value: int | float | str
    description: str | None = None
    helper_text: str | None = None


class ExecutiveInsight(CamelModel):
    """One curated executive insight block."""

    title: str
    body: str
    footer: str | None = None


class DashboardSummary(CamelModel):
    """The overview view payload served under the envelope's ``data`` field."""

    asset_name: str
    dataset_name: str
    period_start: str
    period_end: str
    total_records: int
    operational_status: OperationalStatus
    status_reason: str | None = None
    kpis: list[DashboardKpi]
    executive_insights: list[ExecutiveInsight]
    limitations: list[str]
