"""Sensor Health payload schemas.

Mirrors the frontend ``SensorHealthSummary`` type
(apps/dashboard/src/types/sensor-health.ts) with the contract's §3 delta:
``SensorIssueType`` widened to the 10 true rule families plus the computed
``low_coverage`` value (docs/dashboard/dashboard_api_contract.md §3; the
frontend union is widened in a later frontend slice).
"""

from __future__ import annotations

from typing import Literal

from src.api.schemas import CamelModel

SensorHealthStatus = Literal["healthy", "warning", "critical", "unknown"]
SensorIssueType = Literal[
    "flatline",
    "flatline_zero",
    "variance_collapse",
    "variance_explosion",
    "missingness_spike",
    "abrupt_offset",
    "saturation_low",
    "saturation_high",
    "counter_reset",
    "stale_signal",
    "low_coverage",
]


class SensorHealthKpi(CamelModel):
    """One sensor-health KPI; ``value`` carries raw numbers, never preformatted."""

    label: str
    value: int | float | str
    description: str | None = None


class SensorHealthDistributionItem(CamelModel):
    """Per-status sensor count; counts sum to the monitored-sensor total."""

    status: SensorHealthStatus
    label: str
    count: int


class SensorHealthSignal(CamelModel):
    """One problematic sensor (derived status warning, critical or unknown)."""

    sensor_id: str
    display_name: str
    status: SensorHealthStatus
    coverage_pct: float
    issue_types: list[SensorIssueType]
    recommendation: str


class SensorHealthInsight(CamelModel):
    """One curated sensor-health insight block."""

    title: str
    body: str


class SensorHealthSummary(CamelModel):
    """The sensor-health view payload served under the envelope's ``data`` field."""

    asset_name: str
    dataset_name: str
    period_start: str
    period_end: str
    summary_kpis: list[SensorHealthKpi]
    distribution: list[SensorHealthDistributionItem]
    problematic_signals: list[SensorHealthSignal]
    insights: list[SensorHealthInsight]
