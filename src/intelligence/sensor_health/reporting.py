"""Summary table, findings and Markdown report for Sensor Health."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from src.intelligence._common.reporting import Finding, Severity
from src.intelligence.sensor_health.policy import (
    SensorHealthPolicy,
    resolve_sensor_meta,
)
from src.intelligence.sensor_health.rules import CHECK
from src.intelligence.sensor_health.scoring import SensorScore

SCOPE_STATEMENT = (
    "> **Scope:** Sensor Health Intelligence recommends quarantine but never "
    "excludes sensors automatically. It does not refit models, does not "
    "change anomaly thresholds, and does not modify any upstream artifact."
)


def build_summary(
    per_sensor: dict[str, SensorScore],
    train_mask: np.ndarray,
    events: pd.DataFrame,
    quarantine: pd.DataFrame,
    policy: SensorHealthPolicy,
) -> pd.DataFrame:
    """One row per sensor: status counts (train/validation), events, flags."""
    quarantined = set(quarantine["sensor"]) if len(quarantine) else set()
    rows: list[dict[str, Any]] = []
    for sensor in sorted(per_sensor):
        s = per_sensor[sensor]
        sensor_events = events[events["sensor"] == sensor] if len(events) else events
        issue_rows: dict[str, int] = {}
        for tokens in s.issue_types[s.issue_types != ""]:
            for t in tokens.split("|"):
                issue_rows[t] = issue_rows.get(t, 0) + 1
        faulty_rows = np.flatnonzero(s.status == "faulty")
        rows.append(
            {
                "sensor": sensor,
                "kind": resolve_sensor_meta(policy, sensor).kind,
                "n_rows": len(s.status),
                "n_healthy": int((s.status == "healthy").sum()),
                "n_warning": int((s.status == "warning").sum()),
                "n_faulty": int((s.status == "faulty").sum()),
                "n_unknown": int((s.status == "unknown").sum()),
                "n_warning_train": int((s.status[train_mask] == "warning").sum()),
                "n_faulty_train": int((s.status[train_mask] == "faulty").sum()),
                "issue_row_counts": json.dumps(issue_rows, sort_keys=True),
                "n_events": int(len(sensor_events)),
                "n_persistent_events": int(sensor_events["is_persistent"].sum())
                if len(sensor_events)
                else 0,
                "first_faulty_row": int(faulty_rows[0]) if len(faulty_rows) else None,
                "quarantine_recommended": sensor in quarantined,
            }
        )
    return pd.DataFrame(rows)


def build_findings(
    summary: pd.DataFrame,
    events: pd.DataFrame,
    quarantine: pd.DataFrame,
    unsupported: pd.DataFrame,
) -> list[Finding]:
    """Structured findings mirroring the report's headline facts."""
    findings: list[Finding] = []
    for row in summary.itertuples(index=False):
        if row.n_faulty:
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.IMPORTANT,
                    finding_type="sensor_faulty_rows",
                    column=row.sensor,
                    count=row.n_faulty,
                    action_taken="reported_for_review",
                    evidence={"issue_row_counts": json.loads(row.issue_row_counts)},
                )
            )
        elif row.n_warning:
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.AWARE,
                    finding_type="sensor_warning_rows",
                    column=row.sensor,
                    count=row.n_warning,
                    action_taken="reported_for_review",
                )
            )
    for rec in quarantine.itertuples(index=False):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="quarantine_recommended",
                column=rec.sensor,
                action_taken="recommendation_only_no_exclusion",
                evidence={
                    "issue_types": rec.issue_types,
                    "approval_required": True,
                    "approved": False,
                },
            )
        )
    if len(unsupported):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.AWARE,
                finding_type="unsupported_profile_sensor_pairs",
                count=len(unsupported),
                action_taken="per_profile_rules_inactive",
                evidence={"pairs": unsupported.head(20).to_dict(orient="records")},
            )
        )
    return findings


def _events_table(events: pd.DataFrame, max_rows: int = 25) -> list[str]:
    if events.empty:
        return ["_none_"]
    cols = [
        "sensor_health_event_id",
        "status",
        "issue_types",
        "start_timestamp",
        "end_timestamp",
        "is_persistent",
        "recommended_action",
    ]
    shown = events.sort_values("duration_rows", ascending=False).head(max_rows)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += [
        "| " + " | ".join(str(getattr(r, c)) for c in cols) + " |"
        for r in shown.itertuples(index=False)
    ]
    return lines


def render_report(
    summary: pd.DataFrame,
    events: pd.DataFrame,
    quarantine: pd.DataFrame,
    unsupported: pd.DataFrame,
    manifest: dict[str, Any],
) -> str:
    """Markdown report answering the spec's review questions."""
    flagged = summary[(summary["n_faulty"] > 0) | (summary["n_warning"] > 0)]
    lines = ["# Sensor Health Intelligence Report", "", SCOPE_STATEMENT, ""]
    lines += [
        "## Flagged sensors",
        "",
        "| sensor | kind | faulty rows | warning rows | unknown rows | events | quarantine |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {r.sensor} | {r.kind} | {r.n_faulty} | {r.n_warning} | "
        f"{r.n_unknown} | {r.n_events} | {r.quarantine_recommended} |"
        for r in summary.itertuples(index=False)
    ]
    lines += ["", "## Events (largest first, pending_review)", ""]
    lines += _events_table(events)
    lines += ["", "## Quarantine recommendations", ""]
    if quarantine.empty:
        lines += ["_none_"]
    else:
        lines += [
            f"- **{r.sensor}** — {r.reason} (approval_required={r.approval_required}, "
            f"approved={r.approved})"
            for r in quarantine.itertuples(index=False)
        ]
    lines += [
        "",
        "## Profile-aware suppression",
        "",
        "Zero/flatline candidates inside each sensor's allowed profiles are "
        "suppressed before thresholding and surviving segments are re-measured "
        "independently — stopped-state zeros on power/flow sensors do not "
        "produce events. Zeros during `alarm` are intentionally not "
        "suppressed and surface as reviewable warnings.",
        "",
        "## Unsupported (profile, sensor) pairs",
        "",
        f"{len(unsupported)} pairs have no usable behaviour baseline; "
        "per-profile rules are inactive there (see "
        "unsupported_sensors.parquet).",
        "",
        "## Limitations",
        "",
        "- Rules are reference-based on the train window; a fault present "
        "throughout training would calibrate the references and go unseen.",
        "- `abrupt_offset` is warning-capped: steps cannot be separated from "
        "legitimate setpoint changes without plant records.",
        "- Health statuses describe instrumentation plausibility, not process "
        "quality; review statuses start at `pending_review` and require a "
        "human decision.",
        "",
        f"Run: `{manifest.get('run_id')}` — sensors evaluated: "
        f"{len(summary)}; flagged: {len(flagged)}.",
        "",
    ]
    return "\n".join(lines)
