"""Stage 4 — rolling-window features for process sensors and control signals.

For each numeric signal column the stage emits:

* ``<col>_mean_<W>``   — rolling mean over the last ``W`` samples
* ``<col>_std_<W>``    — rolling std  over the last ``W`` samples
* ``<col>_trend_<W>``  — mean of ``Δx`` over the last ``W`` samples (slope proxy)

State flags and alarms are deliberately skipped here; their
specialised families live in :mod:`src.data.time_series.state_features`.

Leakage: by default each rolling window uses ``closed='left'`` so the
window at index ``t`` sees samples ``[t-W, t)`` only — never ``t``
itself. The setting is exposed in :class:`FeatureFamilySpec.closed` for
forecasting use-cases where this constraint can be relaxed.
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

_FAMILIES: tuple[str, ...] = ("rolling_mean", "rolling_std", "rolling_trend")
_SHORT: dict[str, str] = {
    "rolling_mean": "mean",
    "rolling_std": "std",
    "rolling_trend": "trend",
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


def _min_periods(window: int) -> int:
    return max(2, window // 4)


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
            for window in fs.windows:
                short = _SHORT[family]
                findings.append(
                    Finding(
                        check="rolling_windows",
                        severity=Severity.NORMAL,
                        finding_type=family,
                        column=col,
                        count=1,
                        action_taken=f"add:{col}_{short}_{window}",
                        evidence={
                            "window": int(window),
                            "closed": fs.closed,
                            "category": category,
                            "min_periods": _min_periods(int(window)),
                        },
                    )
                )
    return findings


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: TimeSeriesPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    relevant = [f for f in findings if f.check == "rolling_windows" and f.column]
    if not relevant:
        return df

    new_cols: dict[str, pd.Series] = {}
    for f in relevant:
        col = f.column
        if col not in df.columns:
            continue
        window = int(f.evidence["window"])
        closed = f.evidence.get("closed", "left")
        min_periods = int(f.evidence.get("min_periods", _min_periods(window)))
        source = df[col]
        roll = source.rolling(window=window, min_periods=min_periods, closed=closed)
        short = _SHORT[f.finding_type]
        name = f"{col}_{short}_{window}"
        if f.finding_type == "rolling_mean":
            new_cols[name] = roll.mean()
        elif f.finding_type == "rolling_std":
            new_cols[name] = roll.std()
        elif f.finding_type == "rolling_trend":
            new_cols[name] = (
                source.diff().rolling(window=window, min_periods=min_periods, closed=closed).mean()
            )

    if not new_cols:
        return df
    return pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)
