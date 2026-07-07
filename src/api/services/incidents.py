"""Incidents view builder.

Serves ALL canonical-run incidents — never just the review pack (API contract
§1: serving only the 39-row pack while KPIs say 88 would be silently lossy) —
sorted by review-pack priority, then source severity, then start date.
Artifacts are read once at the first hit and the built response is cached
in-process (§8 risk 1 — the pinned run is immutable). Raw parquet paths, run
folders and model internals are never exposed. All copy is composed from
curated templates with computed numbers interpolated (§6/§8): incidents are
grouped evidence windows for review, never confirmed failures, and quarantine
stays pending human approval.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from src.api.copy.notices import INCIDENTS_NOTICE_KEYS
from src.api.errors import ArtifactUnreadableError
from src.api.schemas.common import Envelope
from src.api.schemas.incidents import (
    IncidentInsight,
    IncidentKpi,
    IncidentRecord,
    IncidentSeverity,
    IncidentSeverityDistributionItem,
    IncidentsSummary,
    IncidentStatus,
)
from src.api.services.view_meta import build_view_meta
from src.dashboard.contract import CANONICAL_RUN_ID
from src.intelligence._common.runs import resolve_run
from src.intelligence.incidents import io as incidents_io

# TODO(debt): pins on the canonical run (API contract §4/§8). The period
# boundaries mirror overview's pins (behaviour manifest coverage); the
# quarantine-pending channel should later come from the reference /
# scoring-experiment artifacts instead of a literal.
_PERIOD_START = "2024-06-14"
_PERIOD_END = "2024-10-08"
_QUARANTINE_PENDING_CHANNEL = "inlet_hopper_points"

_ASSET_NAME = "Pelletizer line"
_DATASET_NAME = "Real industrial dataset"

# "Critical evidence windows" KPI counts the UI-critical tier (anomaly +
# critical) so the card matches the critical badges visible in the list.
_CRITICAL_KPI_SEVERITIES: tuple[str, ...] = ("anomaly", "critical")

# §5 severity mapping: backend 4-tier -> UI 3-tier. info is series colouring
# only ("normal"); anomaly and critical both badge as "critical" — the 4-tier
# truth survives in sourceSeverity and the distribution labels.
_SEVERITY_TO_UI: dict[str, IncidentSeverity] = {
    "info": "normal",
    "warning": "warning",
    "anomaly": "critical",
    "critical": "critical",
}
# Contract 4-tier ranking on SOURCE severity, strongest first.
_SEVERITY_RANK = {"critical": 0, "anomaly": 1, "warning": 2, "info": 3}

# §5 severityDistribution: four rows in fixed order; "Anomaly evidence" and
# "Critical" both carry severity "critical" to preserve the backend tiers.
_DISTRIBUTION_ROWS: tuple[tuple[str, IncidentSeverity, str], ...] = (
    ("info", "normal", "Normal"),
    ("warning", "warning", "Warning"),
    ("anomaly", "critical", "Anomaly evidence"),
    ("critical", "critical", "Critical"),
)

_ACTION_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
_QUARANTINE_ACTION = "quarantine_from_process_scoring"

_TITLE_TEMPLATES: dict[str, str] = {
    "sensor_warning": "Sensor warning evidence window",
    "process_drift": "Process drift evidence window",
    "anomaly_burst": "Anomaly burst evidence window",
    "multivariate_shift": "Multivariate shift evidence window",
    "context_shift": "Operating-context shift evidence window",
    "sensor_fault": "Sensor fault evidence window",
    "correlation_break": "Correlation break evidence window",
    "data_quality_issue": "Data quality evidence window",
}
_DEFAULT_TITLE = "Grouped evidence window"

_TYPE_LABELS: dict[str, str] = {
    "sensor_warning": "Sensor warning evidence",
    "process_drift": "Process drift evidence",
    "anomaly_burst": "A burst of anomaly evidence",
    "multivariate_shift": "Multivariate shift evidence",
    "context_shift": "Operating-context shift evidence",
    "sensor_fault": "Sensor fault evidence",
    "correlation_break": "Correlation break evidence",
    "data_quality_issue": "Data quality evidence",
}
_DEFAULT_TYPE_LABEL = "Grouped evidence"

_SOURCE_LABELS = {
    "sensor_health": "sensor health",
    "bom_context": "BOM context",
    "drift": "drift",
    "anomaly": "anomaly",
    "operational_context": "operational context",
}

# One cautious operational phrase per persisted action name. The quarantine
# phrase is the approved §5.3 pending-approval copy — it must keep "pending"
# and must never claim the channel was excluded automatically.
_ACTION_RECOMMENDATIONS: dict[str, str] = {
    "inspect_sensor_channel": (
        "Inspect the affected sensor channel and its acquisition path before "
        "interpreting this window as process behaviour."
    ),
    "review_maintenance_log": (
        "Review the maintenance log for work overlapping this window before "
        "drawing conclusions."
    ),
    "compare_healthy_only_drift": (
        "Compare against the healthy-only drift view to check whether the "
        "pattern persists without the affected channel."
    ),
    "review_setpoint_changes": (
        "Review recorded setpoint changes around this window; the evidence "
        "may reflect an intended operating change."
    ),
    "inspect_product_recipe_context": (
        "Check the product and recipe context active during this window; "
        "recipe changes can explain grouped deviations."
    ),
    "review_operator_notes": (
        "Review operator notes for this window to add plant context the "
        "detectors cannot see."
    ),
    "review_historian_mapping": (
        "Verify the historian tag mapping for the affected signals; mapping "
        "issues can look like process deviations."
    ),
    _QUARANTINE_ACTION: (
        "Quarantine of the affected channel is pending review and human "
        "approval — the channel is not excluded automatically."
    ),
}
_DEFAULT_RECOMMENDATION = (
    "Review against plant records and operator context before any action; "
    "treat this window as review evidence only."
)


def _load_artifacts() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read (unsuppressed incidents, review pack, actions) from the pinned run."""
    try:
        incidents_run = resolve_run(
            incidents_io.INCIDENTS_DIR,
            CANONICAL_RUN_ID,
            incidents_io.MANIFEST_NAME,
            "incidents",
        )
        incidents = pd.read_parquet(incidents_run / incidents_io.INCIDENTS_FILE)
        review_pack = pd.read_parquet(incidents_run / incidents_io.REVIEW_PACK_FILE)
        suppressed = pd.read_parquet(incidents_run / incidents_io.SUPPRESSED_FILE)
        actions = pd.read_parquet(incidents_run / incidents_io.ACTIONS_FILE)
    except (OSError, ValueError, KeyError) as exc:
        # Argument-less on purpose: resolve_run/pyarrow messages embed
        # filesystem paths the API must never expose.
        raise ArtifactUnreadableError() from exc
    # Filter suppression here so no consumer ever sees suppressed incidents.
    unsuppressed = incidents[
        ~incidents["incident_id"].isin(suppressed["suppressed_incident_id"])
    ].reset_index(drop=True)
    return unsuppressed, review_pack, actions


def _split_pipe(value: object) -> list[str]:
    """Split a ``|``-delimited artifact string; empty/NaN values become []."""
    if not isinstance(value, str) or not value.strip():
        return []
    return [token.strip() for token in value.split("|") if token.strip()]


def _humanize_signal(channel: str) -> str:
    # TODO(debt): swap for the curated per-sensor display-name registry once
    # it exists; deterministic humanization is enough for v1.
    return channel.replace("_", " ").capitalize()


def _map_severity(source: str) -> IncidentSeverity:
    # .get with a visible fallback: an unknown future severity degrades to a
    # reviewable "warning" instead of failing the whole response.
    return _SEVERITY_TO_UI.get(source, "warning")


def _map_status(
    incident_id: str, raw_sensors: list[str], pack_ids: frozenset[str]
) -> IncidentStatus:
    """§5 deterministic status ladder; "closed" is unreachable by construction.

    Backend "resolved" only means the evidence window ended — emitting
    "closed" would assert human review closure that never happened.
    """
    if _QUARANTINE_PENDING_CHANNEL in raw_sensors:
        return "contextualised"
    if incident_id in pack_ids:
        return "in_review"
    return "open"


def _pack_rank(review_pack: pd.DataFrame) -> dict[str, int]:
    """Review-pack priority: the pack has no priority column, row order IS it."""
    return {
        str(incident_id): position
        for position, incident_id in enumerate(review_pack["incident_id"])
    }


def _sort_incidents(incidents: pd.DataFrame, pack_rank: dict[str, int]) -> pd.DataFrame:
    """§1 sort: review-pack priority, then source severity, then start date."""
    sentinel = len(pack_rank)
    ordered = incidents.assign(
        _pack=incidents["incident_id"].map(lambda iid: pack_rank.get(iid, sentinel)),
        _sev=incidents["severity"].map(
            lambda sev: _SEVERITY_RANK.get(sev, len(_SEVERITY_RANK))
        ),
    ).sort_values(["_pack", "_sev", "start_timestamp"], kind="stable")
    return ordered.drop(columns=["_pack", "_sev"]).reset_index(drop=True)


def _plural(count: int, unit: str) -> str:
    return f"{count} {unit}" if count == 1 else f"{count} {unit}s"


def _format_duration(seconds: float) -> str:
    """Largest two units, floored to whole minutes (minimum "1 minute")."""
    total_minutes = max(int(seconds // 60), 1)
    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    if days:
        parts = [_plural(days, "day")] + ([_plural(hours, "hour")] if hours else [])
    elif hours:
        parts = [_plural(hours, "hour")] + (
            [_plural(minutes, "minute")] if minutes else []
        )
    else:
        parts = [_plural(minutes, "minute")]
    return " ".join(parts)


def _compose_title(incident_type: str, signals: list[str]) -> str:
    template = _TITLE_TEMPLATES.get(incident_type, _DEFAULT_TITLE)
    if not signals:
        return template
    title = f"{template} — {signals[0]}"
    if len(signals) > 1:
        title += f" +{len(signals) - 1} more"
    return title


def _compose_evidence_summary(
    incident_type: str,
    sources: list[str],
    n_members: int,
    duration_seconds: float,
    signals: list[str],
) -> str:
    """Compose from scalar columns only — the ``evidence`` JSON is never parsed.

    TODO(debt): richer summaries from the evidence payload can slot in here
    later; skipping the parse removes that whole failure class for v1.
    """
    type_label = _TYPE_LABELS.get(incident_type, _DEFAULT_TYPE_LABEL)
    source_labels = [
        _SOURCE_LABELS.get(source, source.replace("_", " ")) for source in sources
    ]
    origin = f" from {', '.join(source_labels)} evidence" if source_labels else ""
    summary = (
        f"{type_label} grouping {_plural(n_members, 'source event')}{origin} "
        f"over {_format_duration(duration_seconds)}."
    )
    if signals:
        summary += f" Affected signals: {', '.join(signals)}."
    return summary + (
        " Grouped for review; this window is evidence to contextualise, not a "
        "conclusion about equipment condition."
    )


def _compose_recommendation(incident_actions: pd.DataFrame | None) -> str:
    """Top two persisted actions by priority; the quarantine phrase always kept."""
    if incident_actions is None or incident_actions.empty:
        return _DEFAULT_RECOMMENDATION
    ordered = incident_actions.sort_values(
        "priority",
        key=lambda column: column.map(_ACTION_PRIORITY_RANK).fillna(
            len(_ACTION_PRIORITY_RANK)
        ),
        kind="stable",
    )
    phrases: list[str] = []
    for action in ordered["recommended_action"]:
        phrase = _ACTION_RECOMMENDATIONS.get(action)
        if phrase is not None and phrase not in phrases:
            phrases.append(phrase)
    if not phrases:
        return _DEFAULT_RECOMMENDATION
    selected = phrases[:2]
    quarantine = _ACTION_RECOMMENDATIONS[_QUARANTINE_ACTION]
    if quarantine in phrases and quarantine not in selected:
        selected = [quarantine, *selected][:2]
    return " ".join(selected)


def _build_records(
    incidents: pd.DataFrame, pack_rank: dict[str, int], actions: pd.DataFrame
) -> list[IncidentRecord]:
    ordered = _sort_incidents(incidents, pack_rank)
    actions_by_incident = dict(tuple(actions.groupby("incident_id")))
    pack_ids = frozenset(pack_rank)
    records: list[IncidentRecord] = []
    for row in ordered.itertuples():
        incident_id = str(row.incident_id)
        raw_sensors = _split_pipe(row.affected_sensors)
        signals = [_humanize_signal(sensor) for sensor in raw_sensors]
        records.append(
            IncidentRecord(
                id=incident_id,
                title=_compose_title(row.incident_type, signals),
                severity=_map_severity(row.severity),
                status=_map_status(incident_id, raw_sensors, pack_ids),
                start_date=row.start_timestamp.strftime("%Y-%m-%d"),
                end_date=row.end_timestamp.strftime("%Y-%m-%d"),
                affected_signals=signals,
                evidence_summary=_compose_evidence_summary(
                    row.incident_type,
                    _split_pipe(row.sources),
                    int(row.n_members),
                    float(row.duration_seconds),
                    signals,
                ),
                recommendation=_compose_recommendation(
                    actions_by_incident.get(incident_id)
                ),
                source_severity=str(row.severity),
                source_status=str(row.status),
                review_status=str(row.review_status),
                start_timestamp=row.start_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                end_timestamp=row.end_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )
    return records


def _build_kpis(records: list[IncidentRecord]) -> list[IncidentKpi]:
    critical = sum(
        1 for record in records if record.source_severity in _CRITICAL_KPI_SEVERITIES
    )
    in_review = sum(1 for record in records if record.status == "in_review")
    contextualised = sum(1 for record in records if record.status == "contextualised")
    return [
        IncidentKpi(
            label="Total incidents",
            value=len(records),
            description="Grouped evidence windows raised for review.",
        ),
        IncidentKpi(
            label="Critical evidence windows",
            value=critical,
            description="Highest-priority evidence windows to review first.",
        ),
        IncidentKpi(
            label="In review",
            value=in_review,
            description=(
                "Prioritised in the review pack, awaiting operator and "
                "production context."
            ),
        ),
        IncidentKpi(
            label="Contextualised",
            value=contextualised,
            description=(
                "Overlapping a known instrumentation fault; interpretation "
                "adjusted, scores unchanged."
            ),
        ),
    ]


def _build_severity_distribution(
    incidents: pd.DataFrame,
) -> list[IncidentSeverityDistributionItem]:
    counts = incidents["severity"].value_counts()
    return [
        IncidentSeverityDistributionItem(
            severity=ui_severity, label=label, count=int(counts.get(source, 0))
        )
        for source, ui_severity, label in _DISTRIBUTION_ROWS
    ]


def _build_insights(
    records: list[IncidentRecord],
    incidents: pd.DataFrame,
    review_pack: pd.DataFrame,
    actions: pd.DataFrame,
) -> list[IncidentInsight]:
    total = len(records)
    n_types = int(incidents["incident_type"].nunique())
    # Literal pair (not the KPI constant): the sentence names both severities.
    n_evidence = sum(
        1 for record in records if record.source_severity in ("anomaly", "critical")
    )
    n_pack = len(review_pack)
    n_contextualised = sum(1 for record in records if record.status == "contextualised")
    n_quarantine = int(
        actions.loc[
            actions["recommended_action"] == _QUARANTINE_ACTION, "incident_id"
        ].nunique()
    )
    return [
        IncidentInsight(
            title="Incidents are reviewable evidence windows",
            body=(
                f"This run groups source events into {total} reviewable "
                f"evidence windows across {_plural(n_types, 'incident type')}, "
                "so review starts from consolidated episodes instead of raw "
                "readings."
            ),
        ),
        IncidentInsight(
            title="Severity ranks review priority",
            body=(
                f"{n_evidence} of {total} windows carry anomaly- or "
                f"critical-severity evidence and {n_pack} are prioritised in "
                "the review pack. Severity orders where to look first; it does "
                "not assert equipment condition."
            ),
        ),
        IncidentInsight(
            title="Context is required before action",
            body=(
                f"Contextualised windows ({n_contextualised} of {total}) "
                "overlap the known instrumentation fault, and "
                f"{_plural(n_quarantine, 'quarantine recommendation')} "
                f"remain{'s' if n_quarantine == 1 else ''} pending human "
                "review and approval — the affected channel is not excluded "
                "automatically. Incident relationships are associative, not "
                "causal."
            ),
        ),
    ]


def _build_summary(
    incidents: pd.DataFrame, review_pack: pd.DataFrame, actions: pd.DataFrame
) -> IncidentsSummary:
    pack_rank = _pack_rank(review_pack)
    records = _build_records(incidents, pack_rank, actions)
    return IncidentsSummary(
        asset_name=_ASSET_NAME,
        dataset_name=_DATASET_NAME,
        period_start=_PERIOD_START,
        period_end=_PERIOD_END,
        summary_kpis=_build_kpis(records),
        severity_distribution=_build_severity_distribution(incidents),
        incidents=records,
        insights=_build_insights(records, incidents, review_pack, actions),
    )


@lru_cache(maxsize=1)
def build_incidents_response() -> Envelope[IncidentsSummary]:
    """Build the ``{meta, data}`` incidents response; cached after the first hit.

    Exceptions are intentionally not cached by ``lru_cache``, so a transient
    read failure self-recovers on the next request.
    """
    incidents, review_pack, actions = _load_artifacts()
    return Envelope[IncidentsSummary](
        meta=build_view_meta(INCIDENTS_NOTICE_KEYS),
        data=_build_summary(incidents, review_pack, actions),
    )
