"""Temporal integrity checks for the cleaning pipeline.

Detects unparseable timestamps, non-monotonic rows, gaps that exceed
``gap_factor * expected_period_s``, and forward jumps beyond
``max_legal_jump_s`` (DST / TZ artefacts).
"""
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
    findings.extend(_detect_unparseable(df))
    findings.extend(_detect_non_monotonic(df))
    findings.extend(_detect_gaps_and_jumps(df, policy))
    return findings


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    out = df.copy()
    nat_mask = out["timestamp"].isna()
    if nat_mask.any():
        out = out.loc[~nat_mask].reset_index(drop=True)

    if not out["timestamp"].is_monotonic_increasing:
        out = out.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    return out


def _detect_unparseable(df: pd.DataFrame) -> list[Finding]:
    mask = df["timestamp"].isna()
    if not mask.any():
        return []
    idx = mask[mask].index.tolist()
    return [
        Finding(
            check="timestamps",
            severity=Severity.CRITICAL,
            finding_type="unparseable_timestamp",
            column="timestamp",
            row_range=(int(idx[0]), int(idx[-1])),
            count=int(mask.sum()),
            action_taken="drop",
        )
    ]


def _detect_non_monotonic(df: pd.DataFrame) -> list[Finding]:
    ts = df["timestamp"]
    valid = ts.notna()
    deltas = ts[valid].diff()
    bad = deltas < pd.Timedelta(0)
    if not bad.any():
        return []
    bad_idx = bad[bad].index.tolist()
    return [
        Finding(
            check="timestamps",
            severity=Severity.CRITICAL,
            finding_type="non_monotonic",
            column="timestamp",
            row_range=(int(bad_idx[0]), int(bad_idx[-1])),
            count=int(bad.sum()),
            action_taken="sort",
        )
    ]


def _detect_gaps_and_jumps(
    df: pd.DataFrame, policy: CleaningPolicy,
) -> list[Finding]:
    ts = df["timestamp"]
    valid = ts.notna()
    deltas = ts[valid].diff().dt.total_seconds()
    findings: list[Finding] = []

    gap_threshold = policy.timestamps.gap_factor * policy.timestamps.expected_period_s
    gap_mask = deltas > gap_threshold
    jump_mask = deltas > policy.timestamps.max_legal_jump_s

    for idx, delta in deltas[gap_mask & ~jump_mask].items():
        findings.append(Finding(
            check="timestamps",
            severity=Severity.IMPORTANT,
            finding_type="gap",
            column="timestamp",
            row_range=(int(idx) - 1, int(idx)),
            count=1,
            action_taken="tag_only",
            evidence={"delta_s": float(delta), "threshold_s": gap_threshold},
        ))

    for idx, delta in deltas[jump_mask].items():
        findings.append(Finding(
            check="timestamps",
            severity=Severity.IMPORTANT,
            finding_type="dst_jump",
            column="timestamp",
            row_range=(int(idx) - 1, int(idx)),
            count=1,
            action_taken="tag_only",
            evidence={"delta_s": float(delta)},
        ))
    return findings
