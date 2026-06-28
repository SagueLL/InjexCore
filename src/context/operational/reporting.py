"""Summaries, findings and the Markdown report for the Operational Context."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.context.operational.validation import CHECK
from src.preprocessing._common.reporting import Finding, Severity

SCOPE_STATEMENT = (
    "> **Scope:** the Operational Context Overlay enriches interpretation "
    "but does not modify existing model fitting or scoring. It never touches "
    "the master dataset, the BOM artifacts, or any Intelligence-Layer model."
)

#: Sustained-regime rule used in the report (stated wherever applied).
SUSTAINED_SHARE = 0.5
SUSTAINED_DAYS = 3


def dimension_summary(overlay: pd.DataFrame, column: str) -> pd.DataFrame:
    """Counts / share / train split / first-last seen per context value."""
    grouped = overlay.assign(_train=overlay["is_train"].astype(int)).groupby(
        column, dropna=False
    )
    out = pd.DataFrame(
        {
            "row_count": grouped.size(),
            "percentage": (grouped.size() / len(overlay) * 100.0).round(4),
            "n_train_rows": grouped["_train"].sum(),
            "first_seen": grouped["timestamp"].min(),
            "last_seen": grouped["timestamp"].max(),
        }
    )
    return out.reset_index().rename(columns={column: "value"}).assign(dimension=column)


def coverage_summary(overlay: pd.DataFrame) -> pd.DataFrame:
    """Long-form coverage across the four context dimensions."""
    dims = ["profile", "steam_context", "sensor_health_context", "bom_context_status"]
    frames = [dimension_summary(overlay, d) for d in dims]
    return pd.concat(frames, ignore_index=True)[
        ["dimension", "value", "row_count", "percentage", "n_train_rows"]
    ]


def daily_share(overlay: pd.DataFrame, column: str) -> pd.DataFrame:
    """Per-day composition of one context dimension (for plots + report)."""
    return (
        overlay.assign(day=overlay["timestamp"].dt.floor("D"))
        .groupby(["day", column])
        .size()
        .unstack(fill_value=0)
        .pipe(lambda f: f.div(f.sum(axis=1), axis=0))
        .reset_index()
    )


def first_sustained_day(daily: pd.DataFrame, column_value: str) -> pd.Timestamp | None:
    """First day whose share of ``column_value`` is ≥ SUSTAINED_SHARE for
    SUSTAINED_DAYS consecutive days (rule stated in the report)."""
    if column_value not in daily.columns:
        return None
    high = (daily[column_value] >= SUSTAINED_SHARE).to_numpy()
    run = 0
    for idx, flag in enumerate(high):
        run = run + 1 if flag else 0
        if run >= SUSTAINED_DAYS:
            return pd.Timestamp(daily["day"].iloc[idx - SUSTAINED_DAYS + 1])
    return None


def transitions_near(transitions: pd.DataFrame, day: str, hours: int) -> pd.DataFrame:
    center = pd.Timestamp(day)
    lo, hi = center - pd.Timedelta(hours=hours), center + pd.Timedelta(hours=hours)
    return transitions[
        (transitions["transition_timestamp"] >= lo)
        & (transitions["transition_timestamp"] < hi)
    ]


def build_findings(overlay: pd.DataFrame, transitions: pd.DataFrame) -> list[Finding]:
    findings: list[Finding] = []
    counts = overlay["sensor_health_context"].value_counts()
    if counts.get("sensor_faulty", 0):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="sensor_faulty_context_rows",
                count=int(counts["sensor_faulty"]),
                action_taken="reported_for_review",
            )
        )
    unknown_steam = int((overlay["steam_context"] == "unknown").sum())
    if unknown_steam:
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.AWARE,
                finding_type="steam_context_unknown_rows",
                count=unknown_steam,
                action_taken="reported_honestly",
            )
        )
    findings.append(
        Finding(
            check=CHECK,
            severity=Severity.NORMAL,
            finding_type="context_transitions_detected",
            count=int(len(transitions)),
            action_taken="persisted",
        )
    )
    return findings


def _share_table(summary: pd.DataFrame) -> list[str]:
    lines = [
        "| value | rows | % | train rows | first seen | last seen |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {r.value} | {r.row_count} | {r.percentage} | {r.n_train_rows} | "
        f"{r.first_seen} | {r.last_seen} |"
        for r in summary.itertuples(index=False)
    ]
    return lines


def render_report(
    overlay: pd.DataFrame,
    transitions: pd.DataFrame,
    summaries: dict[str, pd.DataFrame],
    manifest: dict[str, Any],
    candidate_dates: list[str],
    window_hours: int,
) -> str:
    """Markdown report answering the spec's operational-context questions."""
    steam_daily = daily_share(overlay, "steam_context")
    on_day = first_sustained_day(steam_daily, "steam_conditioning_on")
    health_first_faulty = overlay.loc[
        overlay["sensor_health_context"] == "sensor_faulty", "timestamp"
    ]
    lines = ["# Operational Context Report", "", SCOPE_STATEMENT, ""]
    lines += ["## Steam-conditioning context", ""]
    lines += _share_table(summaries["steam"])
    lines += [
        "",
        f"First day whose `steam_conditioning_on` share stays ≥ "
        f"{SUSTAINED_SHARE:.0%} for ≥ {SUSTAINED_DAYS} consecutive days: "
        f"**{on_day.date() if on_day is not None else 'not reached'}**. "
        "Note: row-level steam context tracks production activity — "
        "production rows classify as on even in the train window, so "
        "daily-median narratives are composition-sensitive. Check the "
        "steam-context × profile cross table below before interpreting "
        "regime shifts.",
        "",
        "### Steam context × profile (row counts)",
        "",
    ]
    cross = overlay.groupby(["steam_context", "profile"]).size().unstack(fill_value=0)
    lines += [
        "| steam_context | " + " | ".join(map(str, cross.columns)) + " |",
        "|" + "---|" * (len(cross.columns) + 1),
    ]
    lines += [
        f"| {idx} | " + " | ".join(str(v) for v in row) + " |"
        for idx, row in cross.iterrows()
    ]
    lines += [
        "",
        "## Sensor-health context",
        "",
    ]
    lines += _share_table(summaries["health"])
    lines += [
        "",
        f"First `sensor_faulty` timestamp: "
        f"**{health_first_faulty.min() if len(health_first_faulty) else 'none'}**.",
        "",
        "## BOM context coverage",
        "",
    ]
    lines += _share_table(summaries["bom"])
    lines += ["", "## Context transitions near the forensic candidate dates", ""]
    for day in candidate_dates:
        near = transitions_near(transitions, day, window_hours)
        types = (
            near["transition_types"].str.split("|").explode().value_counts().to_dict()
            if len(near)
            else {}
        )
        lines.append(
            f"- **{day}** (±{window_hours} h): {len(near)} transition row(s); types: {types or 'none'}"
        )
    lines += [
        "",
        "## Coincidence assessment (temporal association only)",
        "",
        "- Steam-context changes and BOM order changes are tracked "
        "independently; see the context addendum for whether the September "
        "inflections coincide with BOM events (the BOM addendum found no "
        "recipe/product change at the candidate dates).",
        "- The sensor-health failure (`inlet_hopper_points` flatline-zero) "
        "is an instrumentation observation; the BOM data records order "
        "activity, not sensor maintenance.",
        "",
        "## What remains unknown without plant records",
        "",
        "- Whether the sustained steam-on regime was an intentional "
        "operating-mode decision.",
        "- Whether the `inlet_hopper_points` channel was disconnected, "
        "failed, or decommissioned.",
        "- Clock alignment between the ERP (BOM) and the sensor historian.",
        "",
        f"Run: `{manifest.get('run_id')}` — timeline rows: "
        f"{manifest.get('timeline_row_count')}.",
        "",
    ]
    return "\n".join(lines)
