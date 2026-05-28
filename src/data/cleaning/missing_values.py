"""Typed missing-value detection and remediation.

Runs LAST in the orchestrator so it can classify NaN cells produced by
upstream masking. Each NaN run is bucketed into one of six types
(machine_off, lost_communication, broken_sensor, maintenance_window,
missing_by_design, continuous_sensor) using the rules in the plan.

If a row's running flags are themselves NaN the row is critical → drop.
"""
from __future__ import annotations

import numpy as np
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
    findings.extend(_detect_undeterminable_rows(df, groups))
    findings.extend(_detect_nan_runs(df, policy, groups))
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
        if f.finding_type == "undeterminable_state" and f.evidence.get("rows"):
            drop_rows.update(int(r) for r in f.evidence["rows"])
    if drop_rows:
        out = out.drop(index=list(drop_rows)).reset_index(drop=True)

    out = _apply_to_runs(out, findings, policy)
    return out


def _detect_undeterminable_rows(
    df: pd.DataFrame, groups: ColumnGroups,
) -> list[Finding]:
    running_present = [c for c in groups.running_flags if c in df.columns]
    if not running_present:
        return []
    mask = df[running_present].isna().any(axis=1)
    if not mask.any():
        return []
    rows = [int(i) for i in mask[mask].index.tolist()]
    return [Finding(
        check="missing_values",
        severity=Severity.CRITICAL,
        finding_type="undeterminable_state",
        column=None,
        row_range=(rows[0], rows[-1]),
        count=len(rows),
        action_taken="drop",
        evidence={"rows": rows},
    )]


def _detect_nan_runs(
    df: pd.DataFrame, policy: CleaningPolicy, groups: ColumnGroups,
) -> list[Finding]:
    findings: list[Finding] = []
    process_set = set(groups.process)
    mbd = set(policy.missing_values.missing_by_design_columns)
    running_present = [c for c in groups.running_flags if c in df.columns]
    alarm_present = [c for c in groups.alarm_flags if c in df.columns]

    for col in df.columns:
        if col == "timestamp":
            continue
        nan_mask = df[col].isna()
        if not nan_mask.any():
            continue
        for start, end in _runs(nan_mask):
            findings.append(_classify_run(
                df, col, start, end, policy, groups,
                process_set, mbd, running_present, alarm_present,
            ))
    return findings


def _runs(mask: pd.Series) -> list[tuple[int, int]]:
    arr = mask.to_numpy()
    idx = mask.index.to_numpy()
    runs: list[tuple[int, int]] = []
    n = len(arr)
    i = 0
    while i < n:
        if not arr[i]:
            i += 1
            continue
        j = i
        while j < n and arr[j]:
            j += 1
        runs.append((int(idx[i]), int(idx[j - 1])))
        i = j
    return runs


def _classify_run(
    df: pd.DataFrame,
    col: str,
    start: int,
    end: int,
    policy: CleaningPolicy,
    groups: ColumnGroups,
    process_set: set[str],
    mbd: set[str],
    running_present: list[str],
    alarm_present: list[str],
) -> Finding:
    length = end - start + 1
    mv = policy.missing_values

    if col in mbd:
        return _finding(col, start, end, length, Severity.NORMAL,
                        "missing_by_design", "keep_nan")

    is_process = col in process_set

    if is_process and _machine_off(df, start, end, running_present):
        return _finding(col, start, end, length, Severity.AWARE,
                        "machine_off", "keep_nan")

    if is_process and _aligned_with_alarm(df, start, end, alarm_present,
                                          mv.alarm_alignment_window_min):
        return _finding(col, start, end, length, Severity.AWARE,
                        "maintenance_window", "keep_nan")

    if length > mv.broken_sensor_min_run and _any_running(df, start, end, running_present):
        return _finding(col, start, end, length, Severity.CRITICAL,
                        "broken_sensor", "tag_only")

    if length <= mv.interpolation_max_run and _any_running(df, start, end, running_present):
        return _finding(col, start, end, length, Severity.IMPORTANT,
                        "lost_communication", "interpolate_time")

    if length == 1 and is_process:
        return _finding(col, start, end, length, Severity.IMPORTANT,
                        "continuous_sensor", "forward_fill_1")

    return _finding(col, start, end, length, Severity.AWARE,
                    "unclassified_nan", "keep_nan")


def _finding(
    col: str, start: int, end: int, length: int,
    severity: Severity, finding_type: str, action: str,
) -> Finding:
    return Finding(
        check="missing_values",
        severity=severity,
        finding_type=finding_type,
        column=col,
        row_range=(start, end),
        count=length,
        action_taken=action,
    )


_MACHINE_OFF_FLAGS = ("granulator_g2_running", "feeder_al2_running")


def _machine_off(
    df: pd.DataFrame, start: int, end: int, running: list[str],
) -> bool:
    present = [c for c in _MACHINE_OFF_FLAGS if c in df.columns]
    if len(present) != len(_MACHINE_OFF_FLAGS):
        return False
    sub = df.loc[start:end, present]
    return bool((sub.fillna(1) == 0).all().all())


def _any_running(
    df: pd.DataFrame, start: int, end: int, running: list[str],
) -> bool:
    if not running:
        return False
    sub = df.loc[start:end, running]
    return bool((sub.fillna(0) == 1).any().any())


def _aligned_with_alarm(
    df: pd.DataFrame, start: int, end: int, alarm_cols: list[str], window_min: int,
) -> bool:
    if not alarm_cols:
        return False
    lo = max(0, start - window_min)
    hi = min(len(df) - 1, end + window_min)
    sub = df.loc[lo:hi, alarm_cols].fillna(0)
    if sub.empty:
        return False
    diff = sub.diff().fillna(0)
    has_rise = (diff == 1).any().any()
    has_fall = (diff == -1).any().any()
    return bool(has_rise and has_fall)


def _apply_to_runs(
    df: pd.DataFrame, findings: list[Finding], policy: CleaningPolicy,
) -> pd.DataFrame:
    out = df
    limit = policy.missing_values.interpolation_max_run
    for f in findings:
        if f.column is None or f.column not in out.columns or f.row_range is None:
            continue
        start, end = f.row_range
        if start not in out.index or end not in out.index:
            continue
        if f.action_taken == "forward_fill_1":
            out[f.column] = out[f.column].ffill(limit=1)
        elif f.action_taken == "interpolate_time":
            out = _interpolate_segment(out, f.column, start, end, limit)
    return out


def _interpolate_segment(
    df: pd.DataFrame, col: str, start: int, end: int, limit: int,
) -> pd.DataFrame:
    if "timestamp" not in df.columns:
        df[col] = df[col].interpolate(method="linear", limit=limit)
        return df
    ts_index = pd.DatetimeIndex(df["timestamp"])
    series = pd.Series(df[col].to_numpy(), index=ts_index)
    series = series.interpolate(method="time", limit=limit)
    df[col] = series.to_numpy()
    return df
