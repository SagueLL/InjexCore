"""Per-variable physical bound enforcement.

For each column in ``policy.physical_ranges.bounds`` we flag any row where
the value escapes ``[min, max]``. Severity of the bound entry decides the
action: ``critical`` always masks the cell; ``important`` clips when
``clip_soft_violations`` is true, else masks; ``aware`` tags only.
Bounds marked ``integer: true`` additionally flag fractional numerics.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.cleaning.column_groups import ColumnGroups
from src.data.cleaning.policy import Bound, CleaningPolicy
from src.data.cleaning.reporting import Finding, Severity


def detect(
    df: pd.DataFrame,
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    findings: list[Finding] = []
    for col, bound in policy.physical_ranges.bounds.items():
        if col not in df.columns:
            continue
        findings.extend(_detect_one_column(df, col, bound, policy))
    return findings


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    out = df.copy()
    for f in findings:
        if f.column is None or f.column not in out.columns:
            continue
        rows = f.evidence.get("rows")
        if not rows:
            continue
        if f.action_taken == "mask_nan":
            out.loc[rows, f.column] = np.nan
        elif f.action_taken == "clip":
            bmin = f.evidence.get("min")
            bmax = f.evidence.get("max")
            out.loc[rows, f.column] = out.loc[rows, f.column].clip(lower=bmin, upper=bmax)
    return out


def _detect_one_column(
    df: pd.DataFrame, col: str, bound: Bound, policy: CleaningPolicy,
) -> list[Finding]:
    series = pd.to_numeric(df[col], errors="coerce")
    findings: list[Finding] = []

    oob_mask = (series < bound.min) | (series > bound.max)
    oob_mask = oob_mask & series.notna()
    if oob_mask.any():
        findings.append(_oob_finding(col, bound, oob_mask, series, policy))

    if bound.integer:
        frac_mask = series.notna() & (series != series.round())
        frac_mask = frac_mask & ~oob_mask
        if frac_mask.any():
            findings.append(_fractional_finding(col, bound, frac_mask))
    return findings


def _oob_finding(
    col: str, bound: Bound, mask: pd.Series, series: pd.Series, policy: CleaningPolicy,
) -> Finding:
    rows = [int(i) for i in mask[mask].index.tolist()]
    severity = Severity(bound.severity)
    action = _action_for(bound, policy)
    sample = series.loc[rows[: min(5, len(rows))]].tolist()
    return Finding(
        check="physical_ranges",
        severity=severity,
        finding_type="out_of_range",
        column=col,
        row_range=(rows[0], rows[-1]),
        count=len(rows),
        action_taken=action,
        evidence={
            "rows": rows,
            "min": bound.min,
            "max": bound.max,
            "sample_values": sample,
        },
    )


def _fractional_finding(
    col: str, bound: Bound, mask: pd.Series,
) -> Finding:
    rows = [int(i) for i in mask[mask].index.tolist()]
    return Finding(
        check="physical_ranges",
        severity=Severity(bound.severity),
        finding_type="non_integer_in_integer_column",
        column=col,
        row_range=(rows[0], rows[-1]),
        count=len(rows),
        action_taken="mask_nan",
        evidence={"rows": rows},
    )


def _action_for(bound: Bound, policy: CleaningPolicy) -> str:
    severity = Severity(bound.severity)
    if severity == Severity.CRITICAL:
        return "mask_nan"
    if severity == Severity.IMPORTANT:
        return "clip" if policy.physical_ranges.clip_soft_violations else "mask_nan"
    return "tag_only"
