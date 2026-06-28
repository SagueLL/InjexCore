"""Findings, summaries and Markdown report for Incident Aggregation."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.intelligence._common.reporting import Finding, Severity
from src.intelligence.incidents.validation import CHECK

_FINDING_SEVERITY = {
    "info": Severity.NORMAL,
    "warning": Severity.AWARE,
    "anomaly": Severity.IMPORTANT,
    "critical": Severity.CRITICAL,
}


def incident_summary(incidents: pd.DataFrame) -> pd.DataFrame:
    """Per-type aggregate: counts, severity breakdown, durations."""
    columns = [
        "incident_type",
        "n_incidents",
        "n_persistent",
        "n_critical",
        "n_anomaly",
        "n_warning",
        "n_info",
        "mean_duration_seconds",
        "max_duration_seconds",
    ]
    if not len(incidents):
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for incident_type, group in incidents.groupby("incident_type"):
        severity_counts = group["severity"].value_counts()
        rows.append(
            {
                "incident_type": incident_type,
                "n_incidents": int(len(group)),
                "n_persistent": int(group["is_persistent"].sum()),
                "n_critical": int(severity_counts.get("critical", 0)),
                "n_anomaly": int(severity_counts.get("anomaly", 0)),
                "n_warning": int(severity_counts.get("warning", 0)),
                "n_info": int(severity_counts.get("info", 0)),
                "mean_duration_seconds": float(group["duration_seconds"].mean()),
                "max_duration_seconds": float(group["duration_seconds"].max()),
            }
        )
    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values("n_incidents", ascending=False, kind="stable")
        .reset_index(drop=True)
    )


def incident_timeline(incidents: pd.DataFrame) -> pd.DataFrame:
    """Daily counts of incidents in effect, by type and severity."""
    columns = ["date", "incident_type", "severity", "n_incidents"]
    if not len(incidents):
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for _, incident in incidents.iterrows():
        days = pd.date_range(
            pd.Timestamp(incident["start_timestamp"]).floor("1D"),
            pd.Timestamp(incident["end_timestamp"]).floor("1D"),
            freq="1D",
        )
        for day in days:
            rows.append(
                {
                    "date": day,
                    "incident_type": str(incident["incident_type"]),
                    "severity": str(incident["severity"]),
                }
            )
    frame = pd.DataFrame(rows)
    return (
        frame.groupby(["date", "incident_type", "severity"])
        .size()
        .rename("n_incidents")
        .reset_index()
    )


def build_findings(
    incidents: pd.DataFrame,
    suppressed: pd.DataFrame,
    relationships: pd.DataFrame,
) -> list[Finding]:
    """One finding per incident + aggregates for suppression/relationships."""
    findings: list[Finding] = []
    for incident in incidents.itertuples(index=False):
        findings.append(
            Finding(
                check=CHECK,
                severity=_FINDING_SEVERITY.get(str(incident.severity), Severity.AWARE),
                finding_type=f"incident_{incident.incident_type}",
                column=str(incident.affected_sensors) or None,
                action_taken="pending_review",
                evidence={
                    "incident_id": str(incident.incident_id),
                    "status": str(incident.status),
                    "start": str(incident.start_timestamp),
                    "end": str(incident.end_timestamp),
                    "sources": str(incident.sources),
                },
            )
        )
    if len(suppressed):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.AWARE,
                finding_type="suppressed_duplicate_events",
                count=int(len(suppressed)),
                action_taken="recorded_transparently",
            )
        )
    if len(relationships):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.NORMAL,
                finding_type="incident_relationships",
                count=int(len(relationships)),
                action_taken="causality_status_unknown",
            )
        )
    return findings


def render_report(
    incidents: pd.DataFrame,
    summary: pd.DataFrame,
    suppressed: pd.DataFrame,
    relationships: pd.DataFrame,
    review_pack: pd.DataFrame,
    manifest: dict[str, Any],
) -> str:
    """Human-readable Markdown report for one incidents run."""
    lines = [
        "# Incident Aggregation Report",
        "",
        f"Run `{manifest['run_id']}` — {manifest['created_at']}",
        "",
        "Incident relationships are associative and temporal; they do not "
        "establish causality (`causality_status = unknown` on every row). "
        "No upstream artifact was modified; no sensor was excluded; no "
        "quarantine recommendation was approved.",
        "",
        "## Incidents",
        "",
        f"**Total:** {len(incidents)} "
        f"({int(incidents['is_persistent'].sum()) if len(incidents) else 0} "
        f"persistent); suppressed duplicates: {len(suppressed)}; "
        f"relationships: {len(relationships)}; review pack: {len(review_pack)} "
        "rows.",
        "",
    ]
    if len(summary):
        lines.append("| Type | Incidents | Persistent | Critical | Anomaly | Warning |")
        lines.append("|---|---|---|---|---|---|")
        for row in summary.itertuples(index=False):
            lines.append(
                f"| {row.incident_type} | {row.n_incidents} | {row.n_persistent} "
                f"| {row.n_critical} | {row.n_anomaly} | {row.n_warning} |"
            )
        lines.append("")
    if len(review_pack):
        lines.append("## Top review-pack entries")
        lines.append("")
        lines.append("| Incident | Type | Status | Severity | Start | Sensors |")
        lines.append("|---|---|---|---|---|---|")
        for row in review_pack.head(10).itertuples(index=False):
            lines.append(
                f"| {row.incident_id} | {row.incident_type} | {row.status} "
                f"| {row.severity} | {row.start_timestamp} "
                f"| {row.affected_sensors} |"
            )
        lines.append("")
    return "\n".join(lines)
