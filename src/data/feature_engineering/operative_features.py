"""Family 5 — operative features (cross-flag aggregations).

Per-flag operative statistics (``runfrac``, ``tsla``, ``edges``) already
live in :mod:`src.data.time_series.state_features`. This stage emits
*cross-flag* and *system-level* operative features that single-flag
statistics cannot express:

* ``time_since_machine_off``        samples since the last ``0 → 1`` edge
                                     on ``OR(running_flags)``. Captures
                                     full-machine restarts (not
                                     per-subsystem hand-offs).
* ``n_subsystems_running``           instantaneous count of active
                                     subsystems (sum of running flags).
* ``cumulative_starts``              lifetime count of rising edges on
                                     ``OR(running_flags)`` — restart
                                     counter.
* ``total_alarms_<W>``               sum of ``*_alarm`` edges across all
                                     alarms in a rolling window — system
                                     alarm pressure.
* ``time_since_any_alarm``           min ``tsla`` across alarms — samples
                                     since the most recent alarm anywhere.
* ``any_alarm_while_running``        boolean ``(any alarm) AND (any
                                     running)`` per sample — inconsistent
                                     operational state.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.feature_engineering.column_groups import ColumnGroups
from src.data.feature_engineering.policy import FeatureEngineeringPolicy
from src.data.feature_engineering.reporting import Finding, Severity


def _min_periods(window: int) -> int:
    return max(1, window // 4)


def _present(df: pd.DataFrame, cols: list[str]) -> list[str]:
    return [c for c in cols if c in df.columns]


def _any_flag(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """Element-wise OR of binary flag columns, NaN-safe."""
    if not cols:
        return pd.Series(0, index=df.index, dtype="int8")
    stacked = df[cols].fillna(0).astype(float).clip(lower=0, upper=1)
    return (stacked.sum(axis=1) > 0).astype("int8")


def _rising_edges(flag: pd.Series) -> pd.Series:
    return flag.diff().clip(lower=0).fillna(0)


def _time_since_last_active(flag: pd.Series) -> pd.Series:
    """Mirror of :func:`src.data.time_series.state_features._time_since_last_active`.

    Returns the number of samples since the last ``1`` in the flag.
    ``0`` while the flag is currently ``1``; NaN before the first
    activation.
    """
    active = flag.fillna(0).astype(bool)
    n = len(flag)
    out = np.full(n, np.nan)
    counter = -1
    for i in range(n):
        if active.iat[i]:
            counter = 0
        elif counter >= 0:
            counter += 1
        if counter >= 0:
            out[i] = counter
    return pd.Series(out, index=flag.index, dtype="float64")


def _time_since_last_rising_edge(flag: pd.Series) -> pd.Series:
    """Samples since the most recent ``0 → 1`` transition of ``flag``.

    ``0`` at the rising edge itself, then grows by 1 each sample until
    the next rising edge — regardless of whether the flag is still 1 or
    has dropped back to 0. ``NaN`` before the first edge.
    """
    f = flag.fillna(0).astype(float).clip(0, 1)
    rising = ((f.diff() > 0).fillna(False)).to_numpy().copy()
    # The very first sample is treated as a rising edge if the flag
    # starts at 1, so a record beginning with the machine already on
    # counts from sample 0.
    if len(f) > 0 and bool(f.iloc[0] > 0):
        rising[0] = True
    n = len(f)
    out = np.full(n, np.nan)
    counter = -1
    for i in range(n):
        if rising[i]:
            counter = 0
        elif counter >= 0:
            counter += 1
        if counter >= 0:
            out[i] = counter
    return pd.Series(out, index=flag.index, dtype="float64")


def detect(
    df: pd.DataFrame,
    policy: FeatureEngineeringPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    p = policy.operative_features
    if not p.enabled:
        return [
            Finding(
                check="operative_features",
                severity=Severity.NORMAL,
                finding_type="skipped",
                action_taken="noop",
                evidence={"reason": "disabled"},
            )
        ]

    findings: list[Finding] = []
    running_present = _present(df, p.running_flags)
    alarm_present = _present(df, p.alarm_flags)
    missing_running = [c for c in p.running_flags if c not in df.columns]
    missing_alarm = [c for c in p.alarm_flags if c not in df.columns]

    if missing_running:
        findings.append(
            Finding(
                check="operative_features",
                severity=Severity.AWARE,
                finding_type="running_flags_missing",
                action_taken="partial",
                evidence={"missing": missing_running},
            )
        )
    if missing_alarm:
        findings.append(
            Finding(
                check="operative_features",
                severity=Severity.AWARE,
                finding_type="alarm_flags_missing",
                action_taken="partial",
                evidence={"missing": missing_alarm},
            )
        )

    if p.time_since_machine_off and running_present:
        findings.append(
            Finding(
                check="operative_features",
                severity=Severity.NORMAL,
                finding_type="time_since_machine_off",
                count=1,
                action_taken="add:time_since_machine_off",
                evidence={"source_flags": running_present},
            )
        )

    if p.n_subsystems_running and running_present:
        findings.append(
            Finding(
                check="operative_features",
                severity=Severity.NORMAL,
                finding_type="n_subsystems_running",
                count=1,
                action_taken="add:n_subsystems_running",
                evidence={"source_flags": running_present},
            )
        )

    if p.cumulative_starts and running_present:
        findings.append(
            Finding(
                check="operative_features",
                severity=Severity.NORMAL,
                finding_type="cumulative_starts",
                count=1,
                action_taken="add:cumulative_starts",
                evidence={"source_flags": running_present},
            )
        )

    if p.total_alarms.enabled and alarm_present:
        for w in p.total_alarms.windows:
            findings.append(
                Finding(
                    check="operative_features",
                    severity=Severity.NORMAL,
                    finding_type="total_alarms",
                    count=1,
                    action_taken=f"add:total_alarms_{w}",
                    evidence={
                        "window": int(w),
                        "closed": p.total_alarms.closed,
                        "min_periods": _min_periods(int(w)),
                        "source_flags": alarm_present,
                    },
                )
            )

    if p.time_since_any_alarm and alarm_present:
        findings.append(
            Finding(
                check="operative_features",
                severity=Severity.NORMAL,
                finding_type="time_since_any_alarm",
                count=1,
                action_taken="add:time_since_any_alarm",
                evidence={"source_flags": alarm_present},
            )
        )

    if p.any_alarm_while_running and alarm_present and running_present:
        findings.append(
            Finding(
                check="operative_features",
                severity=Severity.NORMAL,
                finding_type="any_alarm_while_running",
                count=1,
                action_taken="add:any_alarm_while_running",
                evidence={
                    "running_flags": running_present,
                    "alarm_flags": alarm_present,
                },
            )
        )

    return findings


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: FeatureEngineeringPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    if not policy.operative_features.enabled:
        return df

    new_cols: dict[str, pd.Series] = {}
    or_running_cache: pd.Series | None = None
    or_alarm_cache: pd.Series | None = None
    any_alarm_edges_cache: pd.Series | None = None

    def _or_running() -> pd.Series:
        nonlocal or_running_cache
        if or_running_cache is None:
            or_running_cache = _any_flag(df, _present(df, policy.operative_features.running_flags))
        return or_running_cache

    def _or_alarm() -> pd.Series:
        nonlocal or_alarm_cache
        if or_alarm_cache is None:
            or_alarm_cache = _any_flag(df, _present(df, policy.operative_features.alarm_flags))
        return or_alarm_cache

    def _any_alarm_edges() -> pd.Series:
        nonlocal any_alarm_edges_cache
        if any_alarm_edges_cache is None:
            present = _present(df, policy.operative_features.alarm_flags)
            if not present:
                any_alarm_edges_cache = pd.Series(0.0, index=df.index)
            else:
                edges = pd.DataFrame(
                    {c: _rising_edges(df[c]) for c in present},
                    index=df.index,
                )
                any_alarm_edges_cache = edges.sum(axis=1)
        return any_alarm_edges_cache

    for f in findings:
        if f.check != "operative_features":
            continue
        ft = f.finding_type
        if ft == "time_since_machine_off":
            new_cols["time_since_machine_off"] = _time_since_last_rising_edge(_or_running())
        elif ft == "n_subsystems_running":
            present = _present(df, policy.operative_features.running_flags)
            if present:
                new_cols["n_subsystems_running"] = (
                    df[present].fillna(0).astype(float).clip(0, 1).sum(axis=1)
                )
        elif ft == "cumulative_starts":
            new_cols["cumulative_starts"] = _rising_edges(_or_running()).cumsum()
        elif ft == "total_alarms":
            w = int(f.evidence["window"])
            closed = f.evidence.get("closed", "left")
            min_periods = int(f.evidence.get("min_periods", _min_periods(w)))
            new_cols[f"total_alarms_{w}"] = _any_alarm_edges().rolling(
                window=w, min_periods=min_periods, closed=closed,
            ).sum()
        elif ft == "time_since_any_alarm":
            new_cols["time_since_any_alarm"] = _time_since_last_active(_or_alarm())
        elif ft == "any_alarm_while_running":
            new_cols["any_alarm_while_running"] = (
                ((_or_alarm() > 0) & (_or_running() > 0)).astype("int8")
            )

    if not new_cols:
        return df
    return pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)
