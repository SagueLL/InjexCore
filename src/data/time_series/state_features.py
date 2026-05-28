"""Stage 4b — specialised features for ``{0, 1}`` state and alarm signals.

Generic rolling statistics on a binary flag would discard physical
meaning. This stage emits three interpretable families instead:

* ``<col>_runfrac_<W>``  fraction of the last ``W`` samples the flag was 1.
                          Only meaningful for running flags.
* ``<col>_tsla``         time-since-last-active in samples. ``0`` while the
                          flag is currently 1; integer count of samples
                          since the last 1 otherwise; ``NaN`` before the
                          first activation.
* ``<col>_edges_<W>``    number of rising edges (``0 → 1`` transitions) in
                          the last ``W`` samples. Surfaces alarm flapping
                          and rapid cycle restarts.

All rolling windows use ``closed='left'`` for leakage symmetry with
:mod:`src.data.time_series.rolling_windows`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.time_series.column_groups import ColumnGroups
from src.data.time_series.policy import TimeSeriesPolicy
from src.data.time_series.reporting import Finding, Severity


def _running_flag_columns(df: pd.DataFrame, groups: ColumnGroups) -> list[str]:
    return [c for c in df.columns if c in groups.running_flags]


def _alarm_flag_columns(df: pd.DataFrame, groups: ColumnGroups) -> list[str]:
    return [c for c in df.columns if c in groups.alarm_flags]


def detect(
    df: pd.DataFrame,
    policy: TimeSeriesPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    if not policy.state_features.enabled:
        return [
            Finding(
                check="state_features",
                severity=Severity.NORMAL,
                finding_type="skipped",
                action_taken="noop",
                evidence={"reason": "disabled"},
            )
        ]

    findings: list[Finding] = []
    running = _running_flag_columns(df, groups)
    alarms = _alarm_flag_columns(df, groups)

    for col in running:
        for w in policy.state_features.running_fraction_windows:
            findings.append(
                Finding(
                    check="state_features",
                    severity=Severity.NORMAL,
                    finding_type="runfrac",
                    column=col,
                    count=1,
                    action_taken=f"add:{col}_runfrac_{w}",
                    evidence={"window": int(w), "closed": "left", "category": "state_flag"},
                )
            )

    if policy.state_features.time_since_active:
        for col in running + alarms:
            category = "state_flag" if col in running else "alarm"
            findings.append(
                Finding(
                    check="state_features",
                    severity=Severity.NORMAL,
                    finding_type="tsla",
                    column=col,
                    count=1,
                    action_taken=f"add:{col}_tsla",
                    evidence={"category": category},
                )
            )

    for col in running + alarms:
        category = "state_flag" if col in running else "alarm"
        for w in policy.state_features.edge_count_windows:
            findings.append(
                Finding(
                    check="state_features",
                    severity=Severity.NORMAL,
                    finding_type="edges",
                    column=col,
                    count=1,
                    action_taken=f"add:{col}_edges_{w}",
                    evidence={"window": int(w), "closed": "left", "category": category},
                )
            )

    return findings


def _time_since_last_active(series: pd.Series) -> pd.Series:
    """Samples since the last ``1`` (``0`` while currently ``1``; NaN before
    the first activation)."""
    active = series.fillna(0).astype(bool)
    n = len(series)
    out = np.full(n, np.nan)
    counter = -1  # -1 means "no activation seen yet"
    for i in range(n):
        if active.iat[i]:
            counter = 0
        elif counter >= 0:
            counter += 1
        if counter >= 0:
            out[i] = counter
    return pd.Series(out, index=series.index, dtype="float64")


def _rising_edges(series: pd.Series) -> pd.Series:
    """1 at samples where the flag transitions ``0 → 1``, else 0."""
    flag = series.fillna(0).astype(float)
    edge = flag.diff().clip(lower=0).fillna(0)
    return edge


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: TimeSeriesPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    if not policy.state_features.enabled:
        return df
    relevant = [f for f in findings if f.check == "state_features" and f.column]
    if not relevant:
        return df

    new_cols: dict[str, pd.Series] = {}
    edge_cache: dict[str, pd.Series] = {}

    for f in relevant:
        col = f.column
        if col not in df.columns:
            continue
        source = df[col]

        if f.finding_type == "runfrac":
            w = int(f.evidence["window"])
            min_periods = max(1, w // 4)
            new_cols[f"{col}_runfrac_{w}"] = (
                source.fillna(0)
                .astype(float)
                .rolling(window=w, min_periods=min_periods, closed="left")
                .mean()
            )
        elif f.finding_type == "tsla":
            new_cols[f"{col}_tsla"] = _time_since_last_active(source)
        elif f.finding_type == "edges":
            if col not in edge_cache:
                edge_cache[col] = _rising_edges(source)
            edges = edge_cache[col]
            w = int(f.evidence["window"])
            min_periods = max(1, w // 4)
            new_cols[f"{col}_edges_{w}"] = edges.rolling(
                window=w, min_periods=min_periods, closed="left"
            ).sum()

    if not new_cols:
        return df
    return pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)
