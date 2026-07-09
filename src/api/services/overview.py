"""Executive Overview view builder.

Assembles the dashboard-ready ``{meta, data}`` overview response.

The "Problematic sensors" KPI is **derived**, not pinned: it reads through the
sensor-health view's cached builder so the two views share one source of truth
for the §6 status precedence. A pinned copy of that number silently diverged from
the artifact (it held the monitored-sensor *total*, 17, where the artifact yields
13 problematic of 17) — exactly the contract §8 risk 2 failure mode. Consequently
this view now fails closed with ``ARTIFACT_UNREADABLE`` when the sensor-health
artifacts cannot be read: serving a stale pin instead would be a silent fallback.

The remaining values are still B1-verified canonical-run pins, guarded by the
real-run cross-view assertions in ``tests/api/test_dashboard_consistency.py``.
"""

from __future__ import annotations

from src.api.copy.notices import OVERVIEW_NOTICE_KEYS
from src.api.schemas.common import Envelope
from src.api.schemas.overview import DashboardKpi, DashboardSummary, ExecutiveInsight
from src.api.services.sensor_health import problematic_sensor_count
from src.api.services.view_meta import build_view_meta

# TODO(debt): B1-verified canonical-run pins (API contract §6–§8). Replace with
# startup-cached artifact readers (behaviour manifest, incidents run,
# scenario_anomaly_rate_comparison) in a later slice — "Problematic sensors" is
# already derived; these seven are cross-checked against the artifacts by
# tests/api/test_dashboard_consistency.py rather than at runtime.
_PERIOD_START = "2024-06-14"
_PERIOD_END = "2024-10-08"
_TOTAL_RECORDS = 167331
_CANDIDATE_EVENT_COUNT = 1038
_INCIDENT_COUNT = 88  # not the demo's 17 (contract §8 recopy)
_REVIEW_PACK_SIZE = 39
_CONTEXTUALISED_ANOMALIES = 30096
_NON_NORMAL_ROWS = 33186
_RESIDUAL_ANOMALY_BACKLOG = 1203
_RESIDUAL_WARNING_BACKLOG = 1887

# §5.3 forbidden framing: the quarantine is pending human approval — copy must
# never claim the channel was excluded from scoring.
_STATUS_REASON = (
    "The inlet_hopper_points quarantine proposal and the Reference v2 candidate "
    "are pending human review, and a residual review backlog of "
    f"{_RESIDUAL_ANOMALY_BACKLOG:,} anomaly and {_RESIDUAL_WARNING_BACKLOG:,} "
    "warning rows remains after interpretive contextualisation."
)

_LIMITATIONS = [
    "Offline historical analysis, not real-time monitoring.",
    "Anomalies are operational evidence, not guaranteed failures.",
    "Pelletizer data demonstrates the intelligence layer but is not yet the "
    "final commercial pilot cell.",
]


def _build_kpis(problematic_sensors: int) -> list[DashboardKpi]:
    return [
        DashboardKpi(
            label="Analysed records",
            value=_TOTAL_RECORDS,
            description="Rows in the master dataset over the full analysed period.",
            helper_text="Full coverage: 14 Jun – 8 Oct 2024.",
        ),
        DashboardKpi(
            label="Detected incidents",
            value=_INCIDENT_COUNT,
            description=(
                f"Aggregated from {_CANDIDATE_EVENT_COUNT:,} candidate events "
                "across sensor health, drift and anomaly evidence."
            ),
            helper_text=f"{_REVIEW_PACK_SIZE} incidents prioritized in the review pack.",
        ),
        DashboardKpi(
            label="Problematic sensors",
            value=problematic_sensors,
            description=(
                "Sensors with warning, faulty or unknown health rows over the period."
            ),
            helper_text=(
                "Includes one pending quarantine recommendation (inlet_hopper_points)."
            ),
        ),
        DashboardKpi(
            label="Contextualised anomalies",
            value=_CONTEXTUALISED_ANOMALIES,
            description=(
                "Non-normal rows attributed to the pending inlet_hopper_points "
                "instrumentation fault in the interpretive review view."
            ),
            helper_text=(
                f"90.7% of {_NON_NORMAL_ROWS:,} non-normal rows; original "
                "anomaly scores are unchanged."
            ),
        ),
    ]


def _build_insights(problematic_sensors: int) -> list[ExecutiveInsight]:
    return [
        ExecutiveInsight(
            title="Main operational finding",
            body=(
                f"Across {_TOTAL_RECORDS:,} records, {_CANDIDATE_EVENT_COUNT:,} "
                f"candidate events were aggregated into {_INCIDENT_COUNT} "
                f"distinct incidents, {_REVIEW_PACK_SIZE} of which are "
                "prioritized in the review pack. Incidents are anomaly evidence "
                "to guide maintenance triage, not guaranteed failures."
            ),
            footer="Period analysed: 14 Jun – 8 Oct 2024.",
        ),
        ExecutiveInsight(
            title="Sensor reliability matters",
            body=(
                f"{problematic_sensors} sensors show warning, faulty or "
                "unknown health rows, dominated by an inlet-hopper channel "
                "flatlined at zero since 17 Sep 2024. Its quarantine "
                "recommendation is pending human approval and has not been "
                "applied. In the interpretive review view, "
                f"{_CONTEXTUALISED_ANOMALIES:,} anomalies (about 91% of "
                "non-normal rows) are contextualised as dominated by that "
                "channel; original anomaly scores are unchanged and a residual "
                f"backlog of {_RESIDUAL_ANOMALY_BACKLOG:,} anomaly rows remains "
                "for review."
            ),
        ),
        ExecutiveInsight(
            title="Best current use",
            body=(
                "Offline forensic and triage aid: ranks incidents and sensors "
                "on operational evidence to support engineering judgement. It "
                "does not predict exact failures or their timing."
            ),
            footer=(
                "Offline historical analysis — decision support, not "
                "autonomous control."
            ),
        ),
    ]


def build_overview_summary() -> DashboardSummary:
    """Build the overview ``data`` payload.

    Raises ``ArtifactUnreadableError`` (propagated from the sensor-health builder)
    when the pinned sensor-health artifacts cannot be read.
    """
    problematic_sensors = problematic_sensor_count()
    return DashboardSummary(
        asset_name="Pelletizer line",
        dataset_name="Real industrial dataset",
        period_start=_PERIOD_START,
        period_end=_PERIOD_END,
        total_records=_TOTAL_RECORDS,
        # §6 status ladder: pending quarantine/reference proposals plus the
        # residual anomaly review backlog place the current run at "warning".
        operational_status="warning",
        status_reason=_STATUS_REASON,
        kpis=_build_kpis(problematic_sensors),
        executive_insights=_build_insights(problematic_sensors),
        limitations=list(_LIMITATIONS),
    )


def build_overview_response() -> Envelope[DashboardSummary]:
    """Build the full ``{meta, data}`` overview response."""
    return Envelope[DashboardSummary](
        meta=build_view_meta(OVERVIEW_NOTICE_KEYS),
        data=build_overview_summary(),
    )
