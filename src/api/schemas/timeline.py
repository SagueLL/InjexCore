"""Operational Timeline payload schemas.

Mirrors the frontend ``OperationalTimeline`` type
(apps/dashboard/src/types/timeline.ts) exactly — the only view with zero type
deltas (docs/dashboard/dashboard_api_contract.md §3); ``series`` / ``periods``
/ ``events`` are backend-computed per §6.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.api.schemas import CamelModel

TimelineStatus = Literal["normal", "warning", "drift", "critical"]
TimelineEventType = Literal["baseline", "warning", "drift", "incident", "review"]
TimelineSeverity = Literal["normal", "warning", "critical"]


class TimelineSummaryKpi(CamelModel):
    """One timeline KPI; ``value`` carries raw numbers, never preformatted."""

    label: str
    value: int | float | str
    description: str | None = None


class TimelinePoint(CamelModel):
    """One UTC day of the evidence series (days without scored rows are omitted).

    ``evidence_share`` is the fraction of the day's scored rows carrying warning or
    anomaly evidence — a rate in [0, 1], not a model score. ``incident_count``
    counts *episodic* incidents overlapping the day; recurring-pattern envelopes
    span most of the period and are excluded (see ``services/_series.py``).
    """

    date: str
    evidence_share: float = Field(ge=0.0, le=1.0)
    incident_count: int
    status: TimelineStatus


class TimelineEvent(CamelModel):
    """A dated timeline anchor (computed, never hand-written narrative)."""

    date: str
    type: TimelineEventType
    severity: TimelineSeverity
    title: str
    description: str


class TimelinePeriod(CamelModel):
    """A labelled date range with the modal day status observed inside it."""

    title: str
    start_date: str
    end_date: str
    status: TimelineStatus
    description: str


class OperationalTimeline(CamelModel):
    """The timeline view payload served under the envelope's ``data`` field."""

    asset_name: str
    dataset_name: str
    period_start: str
    period_end: str
    summary_kpis: list[TimelineSummaryKpi]
    series: list[TimelinePoint]
    periods: list[TimelinePeriod]
    events: list[TimelineEvent]
