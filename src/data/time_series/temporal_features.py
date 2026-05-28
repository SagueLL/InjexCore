"""Stage 5 — generic shift-based temporal features.

For each signal column the stage emits:

* ``<col>_lag_<N>``       — ``df[col].shift(N)``
* ``<col>_pctchg_<N>``    — ``df[col].pct_change(N)``
* ``<col>_velocity_<N>``  — ``df[col].diff(N)``

State flags and alarms are handled by
:mod:`src.data.time_series.state_features`; setpoints / process / control
columns are configurable via :attr:`TimeSeriesPolicy.category_defaults`.

Lag values ``N >= 1`` are leak-safe by construction; the orchestrator
does not need to enforce additional guards.
"""
from __future__ import annotations

from typing import Iterator

import pandas as pd

from src.data.time_series.column_groups import ColumnGroups
from src.data.time_series.policy import (
    CategoryDefaults,
    FeatureFamilySpec,
    TimeSeriesPolicy,
)
from src.data.time_series.reporting import Finding, Severity

_FAMILIES: tuple[str, ...] = ("lag", "pct_change", "velocity")
_SHORT: dict[str, str] = {
    "lag": "lag",
    "pct_change": "pctchg",
    "velocity": "velocity",
}
_SKIP_CATEGORIES: frozenset[str] = frozenset({"state_flag", "alarm"})


def _iter_signal_columns(
    df: pd.DataFrame,
    groups: ColumnGroups,
) -> Iterator[tuple[str, str]]:
    for col in df.columns:
        category = groups.semantic_category(col)
        if category is None or category in _SKIP_CATEGORIES:
            continue
        yield col, category


def detect(
    df: pd.DataFrame,
    policy: TimeSeriesPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    findings: list[Finding] = []
    for col, category in _iter_signal_columns(df, groups):
        spec: CategoryDefaults = policy.resolve(category, col)
        for family in _FAMILIES:
            fs: FeatureFamilySpec = getattr(spec, family)
            if not fs.enabled:
                continue
            for n in fs.lags:
                short = _SHORT[family]
                findings.append(
                    Finding(
                        check="temporal_features",
                        severity=Severity.NORMAL,
                        finding_type=family,
                        column=col,
                        count=1,
                        action_taken=f"add:{col}_{short}_{n}",
                        evidence={"n": int(n), "category": category},
                    )
                )
    return findings


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: TimeSeriesPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    relevant = [f for f in findings if f.check == "temporal_features" and f.column]
    if not relevant:
        return df

    new_cols: dict[str, pd.Series] = {}
    for f in relevant:
        col = f.column
        if col not in df.columns:
            continue
        n = int(f.evidence["n"])
        short = _SHORT[f.finding_type]
        name = f"{col}_{short}_{n}"
        source = df[col]
        if f.finding_type == "lag":
            new_cols[name] = source.shift(n)
        elif f.finding_type == "pct_change":
            new_cols[name] = source.pct_change(n)
        elif f.finding_type == "velocity":
            new_cols[name] = source.diff(n)

    if not new_cols:
        return df
    return pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)
