"""Operational Timeline view builder — the first real artifact reader.

Computes the per-UTC-day timeline from the pinned canonical run's persisted
anomaly scores, incidents and drift events (API contract §6). Artifacts are
read once at the first hit and the built response is cached in-process
(§8 risk 1 — the pinned run is immutable); no reads happen per request after
that. Raw parquet paths, run folders and model internals are never exposed.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache

import pandas as pd

from src.api.copy.notices import TIMELINE_NOTICE_KEYS
from src.api.errors import ArtifactUnreadableError
from src.api.schemas.common import Envelope
from src.api.schemas.timeline import (
    OperationalTimeline,
    TimelineEvent,
    TimelinePeriod,
    TimelinePoint,
    TimelineSeverity,
    TimelineStatus,
    TimelineSummaryKpi,
)
from src.api.services._series import daily_p95, day_statuses, overlaps
from src.api.services.view_meta import TRAIN_WINDOW_END, build_view_meta
from src.dashboard.contract import CANONICAL_RUN_ID
from src.intelligence._common.runs import resolve_run
from src.intelligence.anomaly import io as anomaly_io
from src.intelligence.drift import io as drift_io
from src.intelligence.incidents import io as incidents_io

# TODO(debt): pins on the canonical run (API contract §4/§8). The period
# boundaries mirror overview's pins (behaviour manifest coverage); the
# quarantine onset should later come from the sensor-health/reference
# artifacts.
_PERIOD_START = "2024-06-14"
_PERIOD_END = "2024-10-08"
_VALIDATION_START = "2024-09-04"
_PRE_QUARANTINE_END = "2024-09-16"
_QUARANTINE_ONSET = "2024-09-17"

_ASSET_NAME = "Pelletizer line"
_DATASET_NAME = "Real industrial dataset"

_SCORE_COLUMNS = ["timestamp", "combined_score", "severity"]

# §6 day-status ladder precedence, strongest first.
_STATUS_PRECEDENCE: tuple[TimelineStatus, ...] = (
    "critical",
    "drift",
    "warning",
    "normal",
)
# TimelineSeverity has no "drift" slot; drift-status anchors read as warning.
_STATUS_TO_EVENT_SEVERITY: dict[str, TimelineSeverity] = {
    "critical": "critical",
    "drift": "warning",
    "warning": "warning",
    "normal": "normal",
}


def _load_artifacts() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read (scores, unsuppressed incidents, drift events) from the pinned run."""
    try:
        anomaly_run = resolve_run(
            anomaly_io.ANOMALY_DIR,
            CANONICAL_RUN_ID,
            anomaly_io.MANIFEST_NAME,
            "anomaly",
        )
        incidents_run = resolve_run(
            incidents_io.INCIDENTS_DIR,
            CANONICAL_RUN_ID,
            incidents_io.MANIFEST_NAME,
            "incidents",
        )
        drift_run = resolve_run(
            drift_io.DRIFT_DIR, CANONICAL_RUN_ID, drift_io.MANIFEST_NAME, "drift"
        )
        scores = pd.read_parquet(
            anomaly_run / anomaly_io.SCORES_FILE, columns=_SCORE_COLUMNS
        )
        incidents = pd.read_parquet(incidents_run / incidents_io.INCIDENTS_FILE)
        suppressed = pd.read_parquet(incidents_run / incidents_io.SUPPRESSED_FILE)
        drift_events = pd.read_parquet(drift_run / drift_io.EVENTS_FILE)
    except (OSError, ValueError, KeyError) as exc:
        # Argument-less on purpose: resolve_run/pyarrow messages embed
        # filesystem paths the API must never expose.
        raise ArtifactUnreadableError() from exc
    # Filter suppression here so no consumer ever sees suppressed incidents.
    unsuppressed = incidents[
        ~incidents["incident_id"].isin(suppressed["suppressed_incident_id"])
    ].reset_index(drop=True)
    return scores, unsuppressed, drift_events


def _build_series(
    p95: pd.Series, incident_counts: list[int], statuses: list[str]
) -> list[TimelinePoint]:
    return [
        TimelinePoint(
            date=day.strftime("%Y-%m-%d"),
            deviation_score=float(score),
            incident_count=int(count),
            status=status,
        )
        for (day, score), count, status in zip(
            p95.items(), incident_counts, statuses, strict=True
        )
    ]


def _summary_kpis(
    series: list[TimelinePoint], incidents: pd.DataFrame, drift_events: pd.DataFrame
) -> list[TimelineSummaryKpi]:
    sustained = int(drift_events["status"].isin(["active", "persistent"]).sum())
    critical_days = sum(1 for point in series if point.status == "critical")
    return [
        TimelineSummaryKpi(
            label="Analysed days",
            value=len(series),
            description="UTC days with scored production records.",
        ),
        TimelineSummaryKpi(
            label="Incident windows",
            value=int(len(incidents)),
            description="Aggregated incidents overlapping the analysed period.",
        ),
        TimelineSummaryKpi(
            label="Sustained drift events",
            value=sustained,
            description="Drift events with active or persistent status.",
        ),
        TimelineSummaryKpi(
            label="Days with critical evidence",
            value=critical_days,
            description=(
                "Days overlapped by an anomaly- or critical-severity incident."
            ),
        ),
    ]


def _build_events(series: list[TimelinePoint]) -> list[TimelineEvent]:
    """Computed timeline anchors with templated titles (§6 — never narrative)."""
    events = [
        TimelineEvent(
            date=_PERIOD_START,
            type="baseline",
            severity="normal",
            title="Analysis window starts",
            description="First day covered by the analysed dataset.",
        ),
        TimelineEvent(
            date=TRAIN_WINDOW_END,
            type="baseline",
            severity="normal",
            title="Training baseline window ends",
            description=(
                "Behaviour baselines and detector references are fitted on data "
                "up to this day; later days are scored against them."
            ),
        ),
        TimelineEvent(
            date=_QUARANTINE_ONSET,
            type="review",
            severity="critical",
            title="Inlet hopper sensor fault onset",
            description=(
                "An inlet-hopper channel flatlines at zero from this day; its "
                "quarantine recommendation is pending human review and has not "
                "been applied."
            ),
        ),
    ]
    if series:
        # max() returns the first point at the maximum — deterministic tie-break.
        peak = max(series, key=lambda point: point.deviation_score)
        events.append(
            TimelineEvent(
                date=peak.date,
                type="incident",
                severity=_STATUS_TO_EVENT_SEVERITY[peak.status],
                title="Peak deviation evidence",
                description=(
                    "Highest daily deviation score of the analysed period "
                    f"({peak.deviation_score})."
                ),
            )
        )
    return sorted(events, key=lambda event: event.date)


def _modal_status(series: list[TimelinePoint], start: str, end: str) -> TimelineStatus:
    """Most frequent day status in [start, end]; ladder precedence breaks ties.

    Falls back to "normal" when no series days fall inside the range.
    """
    counts = Counter(point.status for point in series if start <= point.date <= end)
    if not counts:
        return "normal"
    best = max(counts.values())
    for status in _STATUS_PRECEDENCE:
        if counts.get(status) == best:
            return status
    return "normal"


def _build_periods(series: list[TimelinePoint]) -> list[TimelinePeriod]:
    """Anchored period ranges with the modal day status observed inside each."""
    ranges = [
        (
            "Training baseline window",
            _PERIOD_START,
            TRAIN_WINDOW_END,
            "Behaviour baselines and detector references are fitted on this "
            "window; later days are scored against it.",
        ),
        (
            "Post-training validation",
            _VALIDATION_START,
            _PRE_QUARANTINE_END,
            "Scored against the fitted baselines, before the inlet-hopper "
            "sensor fault onset.",
        ),
        (
            "Sensor fault under review",
            _QUARANTINE_ONSET,
            _PERIOD_END,
            "Window dominated by the inlet-hopper instrumentation fault; its "
            "quarantine recommendation is pending human review.",
        ),
    ]
    return [
        TimelinePeriod(
            title=title,
            start_date=start,
            end_date=end,
            status=_modal_status(series, start, end),
            description=description,
        )
        for title, start, end, description in ranges
    ]


def _build_timeline(
    scores: pd.DataFrame, incidents: pd.DataFrame, drift_events: pd.DataFrame
) -> OperationalTimeline:
    p95 = daily_p95(scores)
    days = pd.DatetimeIndex(p95.index)
    incident_counts = overlaps(days, incidents).sum(axis=1).tolist()
    statuses = day_statuses(days, p95, incidents, drift_events)
    series = _build_series(p95, incident_counts, statuses)
    return OperationalTimeline(
        asset_name=_ASSET_NAME,
        dataset_name=_DATASET_NAME,
        period_start=_PERIOD_START,
        period_end=_PERIOD_END,
        summary_kpis=_summary_kpis(series, incidents, drift_events),
        series=series,
        periods=_build_periods(series),
        events=_build_events(series),
    )


@lru_cache(maxsize=1)
def build_timeline_response() -> Envelope[OperationalTimeline]:
    """Build the ``{meta, data}`` timeline response; cached after the first hit.

    Exceptions are intentionally not cached by ``lru_cache``, so a transient
    read failure self-recovers on the next request.
    """
    scores, incidents, drift_events = _load_artifacts()
    return Envelope[OperationalTimeline](
        meta=build_view_meta(TIMELINE_NOTICE_KEYS),
        data=_build_timeline(scores, incidents, drift_events),
    )
