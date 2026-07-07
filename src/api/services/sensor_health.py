"""Sensor Health view builder.

Serves per-sensor instrumentation health from the pinned run's 17-row
``sensor_health_summary`` plus the contract-mandated coverage computation over
the master dataset (API contract §6: ``coveragePct`` = 100 × per-sensor
non-null share over the full period, computed once and cached — the summary
has no coverage column, and ``health_score`` / ``n_unknown``-based proxies are
explicitly forbidden). The 2.84M-row sensor-health scores table is never read
(§8). Artifacts are read once at first hit and the built response is cached
in-process; no paths, run folders or model internals are exposed.
"""

from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache

import pandas as pd

from src.api.copy.notices import SENSOR_HEALTH_NOTICE_KEYS
from src.api.copy.sensors import display_name_for
from src.api.errors import ArtifactUnreadableError
from src.api.schemas.common import Envelope
from src.api.schemas.sensor_health import (
    SensorHealthDistributionItem,
    SensorHealthInsight,
    SensorHealthKpi,
    SensorHealthSignal,
    SensorHealthSummary,
)
from src.api.services.view_meta import build_view_meta
from src.dashboard.contract import CANONICAL_RUN_ID
from src.intelligence._common.runs import resolve_run
from src.intelligence.sensor_health import io as sensor_health_io
from src.intelligence.sensor_health.io import DEFAULT_MASTER_IN

# TODO(debt): pins on the canonical run (API contract §4/§8). Period boundaries
# mirror overview/timeline; the quarantine onset should later come from the
# sensor-health/reference artifacts; the low-coverage threshold is a
# calibration pin (on the pinned run it fires only for the ~30%-coverage
# expander hydraulic-pressure channel).
_PERIOD_START = "2024-06-14"
_PERIOD_END = "2024-10-08"
_QUARANTINE_ONSET = "2024-09-17"
_LOW_COVERAGE_THRESHOLD_PCT = 90.0

_ASSET_NAME = "Pelletizer line"
_DATASET_NAME = "Real industrial dataset"

# Problematic-signal display order (§6 population, strongest first) and the
# summary column that quantifies each derived status.
_STATUS_ORDER = {"critical": 0, "warning": 1, "unknown": 2}
_AFFECTED_COLUMN = {
    "critical": "n_faulty",
    "warning": "n_warning",
    "unknown": "n_unknown",
}
_DISTRIBUTION_ORDER = (
    ("healthy", "Healthy"),
    ("warning", "Warning"),
    ("critical", "Critical"),
    ("unknown", "Unknown"),
)


def _parse_issue_counts(raw: str) -> dict[str, int]:
    """Parse one ``issue_row_counts`` JSON cell; raises ValueError when malformed."""
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("issue_row_counts cell is not a JSON object")
    return {str(key): int(value) for key, value in parsed.items()}


def _load_artifacts() -> tuple[pd.DataFrame, dict[str, float]]:
    """Read the per-sensor summary (+ parsed issues) and master-based coverage."""
    try:
        run = resolve_run(
            sensor_health_io.SENSOR_HEALTH_DIR,
            CANONICAL_RUN_ID,
            sensor_health_io.MANIFEST_NAME,
            "sensor_health",
        )
        summary = pd.read_parquet(run / sensor_health_io.SUMMARY_FILE)
        # A corrupt JSON cell is artifact corruption: fail closed with the
        # ARTIFACT_UNREADABLE envelope, never a bare 500.
        summary["issue_counts"] = summary["issue_row_counts"].map(_parse_issue_counts)
        # §6: coverage comes from the master's non-null share only. Direct
        # column-projected read: a missing sensor column must fail closed
        # (ArrowInvalid ⊂ ValueError), not be silently dropped.
        master = pd.read_parquet(DEFAULT_MASTER_IN, columns=summary["sensor"].tolist())
    except (OSError, ValueError, KeyError) as exc:
        # Argument-less on purpose: underlying messages embed filesystem paths.
        raise ArtifactUnreadableError() from exc
    coverage = {
        str(sensor): float(round(share * 100, 1))
        for sensor, share in master.notna().mean().items()
    }
    return summary, coverage


def _derive_status(
    n_faulty: int, n_warning: int, n_unknown: int, quarantine_recommended: bool
) -> str:
    """§6 status precedence; backend ``faulty`` is served as UI ``critical`` (§5)."""
    if n_faulty > 0 or quarantine_recommended:
        return "critical"
    if n_warning > 0:
        return "warning"
    if n_unknown > 0:
        return "unknown"
    return "healthy"


def _statuses(summary: pd.DataFrame) -> list[str]:
    return [
        _derive_status(
            int(row.n_faulty),
            int(row.n_warning),
            int(row.n_unknown),
            bool(row.quarantine_recommended),
        )
        for row in summary.itertuples()
    ]


def _issue_types(issue_counts: dict[str, int], coverage_pct: float) -> list[str]:
    """Rule families by affected rows desc (name tiebreak) + computed low_coverage.

    Keys outside the SensorIssueType union fail loud in pydantic validation:
    the pinned run is probe-verified in-union, and silently dropping unknown
    families would hide contract drift.
    """
    families = sorted(issue_counts, key=lambda name: (-issue_counts[name], name))
    if coverage_pct < _LOW_COVERAGE_THRESHOLD_PCT:
        families.append("low_coverage")
    return families


def _recommendation(status: str, quarantine: bool, coverage_pct: float) -> str:
    if quarantine:
        return (
            "A quarantine recommendation for this channel is pending human "
            "review and has not been applied; corroborate process conclusions "
            "against redundant signals meanwhile."
        )
    if status == "critical":
        return (
            "Faulty rows detected; inspect the instrumentation before relying "
            "on this signal in process interpretation."
        )
    if status == "warning":
        return (
            "Reliability warnings observed; corroborate with redundant signals "
            "before drawing process conclusions."
        )
    if coverage_pct < _LOW_COVERAGE_THRESHOLD_PCT:
        return (
            f"Records data for only {coverage_pct}% of the analysed period, so "
            "no reliable baseline could be fitted; interpret readings with "
            "caution."
        )
    return (
        "No fitted baseline covers part of the period; interpret readings with "
        "caution rather than as a fault."
    )


def _problematic_signals(
    summary: pd.DataFrame, coverage: dict[str, float], statuses: list[str]
) -> list[SensorHealthSignal]:
    keyed = []
    for row, status in zip(summary.itertuples(), statuses, strict=True):
        if status == "healthy":
            continue
        sensor_id = str(row.sensor)
        coverage_pct = coverage[sensor_id]
        affected = int(getattr(row, _AFFECTED_COLUMN[status]))
        signal = SensorHealthSignal(
            sensor_id=sensor_id,
            display_name=display_name_for(sensor_id),
            status=status,
            coverage_pct=coverage_pct,
            issue_types=_issue_types(row.issue_counts, coverage_pct),
            recommendation=_recommendation(
                status, bool(row.quarantine_recommended), coverage_pct
            ),
        )
        keyed.append(((_STATUS_ORDER[status], -affected, sensor_id), signal))
    keyed.sort(key=lambda item: item[0])
    return [signal for _, signal in keyed]


def _distribution(statuses: list[str]) -> list[SensorHealthDistributionItem]:
    counts = Counter(statuses)
    return [
        SensorHealthDistributionItem(
            status=status, label=label, count=int(counts.get(status, 0))
        )
        for status, label in _DISTRIBUTION_ORDER
    ]


def _summary_kpis(
    distribution: list[SensorHealthDistributionItem],
) -> list[SensorHealthKpi]:
    counts = {item.status: item.count for item in distribution}
    return [
        SensorHealthKpi(
            label="Healthy signals",
            value=counts["healthy"],
            description="Signals with no reliability findings over the period.",
        ),
        SensorHealthKpi(
            label="Warning signals",
            value=counts["warning"],
            description="Signals with reliability warnings to monitor.",
        ),
        SensorHealthKpi(
            label="Critical signals",
            value=counts["critical"],
            description=(
                "Signals with faulty rows or a pending quarantine "
                "recommendation; not decision-grade alone."
            ),
        ),
        SensorHealthKpi(
            label="Review required",
            value=counts["warning"] + counts["critical"] + counts["unknown"],
            description="Signals flagged warning, critical or unknown.",
        ),
    ]


def _insights(
    summary: pd.DataFrame, coverage: dict[str, float]
) -> list[SensorHealthInsight]:
    quarantine_faulty_rows = int(
        summary.loc[summary["quarantine_recommended"], "n_faulty"].sum()
    )
    n_events = int(summary["n_events"].sum())
    min_sensor, min_pct = min(coverage.items(), key=lambda item: item[1])
    return [
        SensorHealthInsight(
            title="Signal reliability shapes anomaly interpretation",
            body=(
                "An inlet-hopper counter channel has been flatlined at zero "
                f"since {_QUARANTINE_ONSET}; its {quarantine_faulty_rows:,} "
                "faulty rows drive most of the contextualised anomaly "
                "evidence. Its quarantine recommendation is pending human "
                "review and has not been applied."
            ),
        ),
        SensorHealthInsight(
            title="Low coverage is a data gap, not a machine fault",
            body=(
                f"{display_name_for(min_sensor)} records data for only "
                f"{min_pct}% of the analysed period, so no reliable baseline "
                "could be fitted; its unknown status reflects missing coverage "
                "rather than a detected failure."
            ),
        ),
        SensorHealthInsight(
            title="Instrumentation findings stay separate from process anomalies",
            body=(
                f"{n_events} sensor-health events over the period are pending "
                "review. Sensor health recommends actions for human review; it "
                "never changes anomaly scores or removes signals on its own."
            ),
        ),
    ]


def _build_summary(
    summary: pd.DataFrame, coverage: dict[str, float]
) -> SensorHealthSummary:
    statuses = _statuses(summary)
    distribution = _distribution(statuses)
    return SensorHealthSummary(
        asset_name=_ASSET_NAME,
        dataset_name=_DATASET_NAME,
        period_start=_PERIOD_START,
        period_end=_PERIOD_END,
        summary_kpis=_summary_kpis(distribution),
        distribution=distribution,
        problematic_signals=_problematic_signals(summary, coverage, statuses),
        insights=_insights(summary, coverage),
    )


@lru_cache(maxsize=1)
def build_sensor_health_response() -> Envelope[SensorHealthSummary]:
    """Build the ``{meta, data}`` sensor-health response; cached after first hit.

    Exceptions are intentionally not cached by ``lru_cache``, so a transient
    read failure self-recovers on the next request.
    """
    summary, coverage = _load_artifacts()
    return Envelope[SensorHealthSummary](
        meta=build_view_meta(SENSOR_HEALTH_NOTICE_KEYS),
        data=_build_summary(summary, coverage),
    )
