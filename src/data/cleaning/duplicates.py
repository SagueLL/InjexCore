"""Duplicate detection: timestamps, payload windows, and PLC bursts."""
from __future__ import annotations

import pandas as pd

from src.data.cleaning.column_groups import ColumnGroups
from src.data.cleaning.policy import CleaningPolicy
from src.data.cleaning.reporting import Finding, Severity


def detect(
    df: pd.DataFrame,
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_detect_dup_timestamps(df))
    findings.extend(_detect_dup_payloads(df, policy, groups))
    findings.extend(_detect_plc_bursts(df, policy))
    return findings


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    out = df.copy()
    drop_rows: set[int] = set()
    for f in findings:
        if f.finding_type == "duplicate_timestamp" and f.evidence.get("drop_rows"):
            drop_rows.update(f.evidence["drop_rows"])
        elif f.finding_type == "plc_burst" and f.evidence.get("drop_rows"):
            drop_rows.update(f.evidence["drop_rows"])
    if drop_rows:
        out = out.drop(index=list(drop_rows)).reset_index(drop=True)
    return out


def _detect_dup_timestamps(df: pd.DataFrame) -> list[Finding]:
    dup_mask = df["timestamp"].duplicated(keep="first") & df["timestamp"].notna()
    if not dup_mask.any():
        return []
    drop_rows = dup_mask[dup_mask].index.tolist()
    return [
        Finding(
            check="duplicates",
            severity=Severity.IMPORTANT,
            finding_type="duplicate_timestamp",
            column="timestamp",
            row_range=(int(drop_rows[0]), int(drop_rows[-1])),
            count=len(drop_rows),
            action_taken="drop_keep_first",
            evidence={"drop_rows": [int(i) for i in drop_rows]},
        )
    ]


def _detect_dup_payloads(
    df: pd.DataFrame, policy: CleaningPolicy, groups: ColumnGroups,
) -> list[Finding]:
    signal_cols = [c for c in groups.signal_columns() if c in df.columns]
    if not signal_cols:
        return []
    window = policy.duplicates.payload_window_rows
    findings: list[Finding] = []
    sub = df[signal_cols]
    eq_prev = (sub == sub.shift(1)).all(axis=1)

    run_start: int | None = None
    for i, equal in eq_prev.items():
        if equal:
            if run_start is None:
                run_start = max(0, int(i) - 1)
        else:
            if run_start is not None:
                run_len = int(i) - run_start
                if run_len <= window and run_len >= 2:
                    findings.append(_payload_finding(run_start, int(i) - 1, run_len))
                run_start = None
    if run_start is not None:
        run_len = len(df) - run_start
        if run_len <= window and run_len >= 2:
            findings.append(_payload_finding(run_start, len(df) - 1, run_len))
    return findings


def _payload_finding(start: int, end: int, length: int) -> Finding:
    return Finding(
        check="duplicates",
        severity=Severity.AWARE,
        finding_type="duplicate_payload",
        row_range=(start, end),
        count=length,
        action_taken="tag_only",
    )


def _detect_plc_bursts(
    df: pd.DataFrame, policy: CleaningPolicy,
) -> list[Finding]:
    ts = df["timestamp"]
    deltas = ts.diff().dt.total_seconds()
    burst_member = deltas < policy.duplicates.burst_max_delta_s
    findings: list[Finding] = []

    n = len(df)
    i = 0
    while i < n:
        if i >= len(burst_member) or not bool(burst_member.iloc[i]):
            i += 1
            continue
        start = max(0, i - 1)
        j = i
        while j < n and bool(burst_member.iloc[j]):
            j += 1
        end = j - 1
        size = end - start + 1
        if size >= policy.duplicates.burst_min_rows:
            findings.append(_burst_finding(df, start, end))
        i = j
    return findings


def _burst_finding(df: pd.DataFrame, start: int, end: int) -> Finding:
    indices = list(range(start, end + 1))
    median_pos = indices[len(indices) // 2]
    drop_rows = [i for i in indices if i != median_pos]
    return Finding(
        check="duplicates",
        severity=Severity.IMPORTANT,
        finding_type="plc_burst",
        row_range=(start, end),
        count=len(indices),
        action_taken="keep_median_drop_neighbours",
        evidence={"drop_rows": [int(i) for i in drop_rows], "kept_row": int(median_pos)},
    )
