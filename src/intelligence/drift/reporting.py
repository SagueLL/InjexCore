"""Findings + Markdown report for Drift Intelligence."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.intelligence._common.reporting import Finding, Severity
from src.intelligence.drift.policy import DriftPolicy
from src.intelligence.drift.validation import CHECK

_FINDING_SEVERITY = {
    "info": Severity.NORMAL,
    "warning": Severity.AWARE,
    "anomaly": Severity.IMPORTANT,
    "critical": Severity.CRITICAL,
}


def build_profile_summary(scored: pd.DataFrame, policy: DriftPolicy) -> pd.DataFrame:
    """Per-(profile, view) drift aggregate across sensor-scope windows."""
    columns = [
        "profile",
        "view",
        "n_windows",
        "mean_drift_score",
        "max_drift_score",
        "n_active_windows",
    ]
    subset = scored[(scored["scope"] == "sensor") & (scored["profile"] != "__global__")]
    if not len(subset):
        return pd.DataFrame(columns=columns)
    threshold = policy.events.active_score_threshold
    rows: list[dict[str, Any]] = []
    for (profile, view), group in subset.groupby(["profile", "view"]):
        rows.append(
            {
                "profile": profile,
                "view": view,
                "n_windows": int(len(group)),
                "mean_drift_score": float(group["drift_score"].mean()),
                "max_drift_score": float(group["drift_score"].max()),
                "n_active_windows": int((group["drift_score"] >= threshold).sum()),
            }
        )
    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values("max_drift_score", ascending=False, kind="stable")
        .reset_index(drop=True)
    )


def build_findings(
    events: pd.DataFrame,
    comparison: pd.DataFrame,
    unsupported: pd.DataFrame,
) -> list[Finding]:
    """One finding per drift event (severity-mapped) + aggregate findings."""
    findings: list[Finding] = []
    for event in events.itertuples(index=False):
        findings.append(
            Finding(
                check=CHECK,
                severity=_FINDING_SEVERITY.get(str(event.severity), Severity.AWARE),
                finding_type=f"drift_event_{event.drift_type}",
                column=str(event.affected_sensors) or None,
                action_taken="pending_review",
                evidence={
                    "drift_event_id": str(event.drift_event_id),
                    "scope": str(event.scope),
                    "view": str(event.view),
                    "temporal_shape": str(event.temporal_shape),
                    "status": str(event.status),
                    "start": str(event.start_timestamp),
                    "end": str(event.end_timestamp),
                },
            )
        )
    residual = comparison[
        comparison["residual_drift"] & (comparison["scope"] == "sensor")
    ]
    if len(residual):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="healthy_only_residual_drift",
                count=int(len(residual)),
                action_taken="pending_review",
                evidence={
                    "entities": sorted(residual["entity"].astype(str).unique())[:10]
                },
            )
        )
    if len(unsupported):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.AWARE,
                finding_type="unsupported_scopes",
                count=int(len(unsupported)),
                action_taken="documented_as_gap",
            )
        )
    return findings


def _events_section(events: pd.DataFrame) -> list[str]:
    lines = ["## Drift events", ""]
    if not len(events):
        lines.append("No drift events were detected.")
        lines.append("")
        return lines
    lines.append(
        f"**Total events:** {len(events)} "
        f"({int(events['is_persistent'].sum())} persistent)"
    )
    lines.append("")
    by_type = events.groupby(["drift_type", "view"]).size()
    lines.append("| Drift type | View | Events |")
    lines.append("|---|---|---|")
    for (dtype, view), count in by_type.items():
        lines.append(f"| {dtype} | {view} | {count} |")
    lines.append("")
    lines.append("Top events by severity / duration:")
    lines.append("")
    lines.append("| Event | Type | Shape | Status | Severity | Start | End | Sensors |")
    lines.append("|---|---|---|---|---|---|---|---|")
    severity_rank = {"critical": 0, "anomaly": 1, "warning": 2, "info": 3}
    ordered = events.copy()
    ordered["rank"] = ordered["severity"].map(severity_rank).fillna(9)
    ordered = ordered.sort_values(
        ["rank", "duration_seconds"], ascending=[True, False], kind="stable"
    ).head(15)
    for e in ordered.itertuples(index=False):
        lines.append(
            f"| {e.drift_event_id} | {e.drift_type} | {e.temporal_shape} "
            f"| {e.status} | {e.severity} | {e.start_timestamp} "
            f"| {e.end_timestamp} | {e.affected_sensors} |"
        )
    lines.append("")
    return lines


def _comparison_section(comparison: pd.DataFrame) -> list[str]:
    lines = ["## Raw vs healthy-only", ""]
    lines.append(
        "The healthy-only view is an *analytical interpretation*: sensors "
        "flagged faulty or quarantine-recommended are excluded in memory for "
        "the affected timestamps. No upstream model was refitted, no anomaly "
        "score was mutated, and no sensor was excluded from production "
        "scoring. The optional multivariate proxy is labeled "
        "`healthy_only_proxy` and is not a rescoring."
    )
    lines.append("")
    sensor_rows = comparison[comparison["scope"] == "sensor"].dropna(
        subset=["drift_score_raw", "drift_score_healthy_only"]
    )
    if len(sensor_rows):
        lines.append(
            f"Sensor windows compared: {len(sensor_rows)}; mean raw score "
            f"{sensor_rows['drift_score_raw'].mean():.3f} vs healthy-only "
            f"{sensor_rows['drift_score_healthy_only'].mean():.3f}; residual "
            f"drift windows: {int(sensor_rows['residual_drift'].sum())}."
        )
        lines.append("")
    dominated = comparison[comparison["exclusion_reason"] != ""]
    if len(dominated):
        lines.append(
            f"Multivariate windows dominated by faulty/quarantined sensor "
            f"evidence (Level-A exclusion): {len(dominated)}."
        )
        lines.append("")
    return lines


def render_report(
    events: pd.DataFrame,
    comparison: pd.DataFrame,
    context_shift: pd.DataFrame,
    correlation_summary: pd.DataFrame,
    unsupported: pd.DataFrame,
    manifest: dict[str, Any],
) -> str:
    """Human-readable Markdown report for one drift run."""
    lines = [
        "# Drift Intelligence Report",
        "",
        f"Run `{manifest['run_id']}` — {manifest['fit_timestamp']}",
        "",
        f"Train window: {manifest['fit_window']['train_start']} → "
        f"{manifest['fit_window']['train_end']} "
        f"({manifest['fit_window']['n_train']} rows of "
        f"{manifest['fit_window']['n_total']}).",
        "",
        "Reference statistics are fitted on the behaviour train window only; "
        "nothing was refitted on validation data and no upstream artifact "
        "was modified.",
        "",
    ]
    lines += _events_section(events)
    lines += _comparison_section(comparison)

    lines += ["## Context composition", ""]
    if len(context_shift):
        worst = context_shift.sort_values(
            "categorical_psi", ascending=False, kind="stable"
        ).head(10)
        lines.append("| Window | Column | PSI | Total variation |")
        lines.append("|---|---|---|---|")
        for row in worst.itertuples(index=False):
            lines.append(
                f"| {row.window_start} | {row.column} "
                f"| {row.categorical_psi:.3f} | {row.total_variation:.3f} |"
            )
    else:
        lines.append("No context composition shifts were computed.")
    lines.append("")

    lines += ["## Correlation drift", ""]
    if len(correlation_summary):
        breaks = correlation_summary[
            correlation_summary["classification"] == "process_correlation_break"
        ]
        sensor_evidence = correlation_summary[
            correlation_summary["classification"] == "sensor_drift_evidence"
        ]
        lines.append(
            f"Shifted pairs: {len(correlation_summary)} "
            f"({len(breaks)} process breaks, {len(sensor_evidence)} classified "
            "as sensor-drift evidence)."
        )
        lines.append(
            "Validation Spearman values are not persisted upstream — Spearman "
            "*changes* are an upstream limitation, not computed here."
        )
    else:
        lines.append("No material correlation shifts.")
    lines.append("")

    lines += ["## Unsupported scopes", ""]
    lines.append(f"{len(unsupported)} (scope, entity, profile) gaps documented.")
    lines.append("")
    return "\n".join(lines)
