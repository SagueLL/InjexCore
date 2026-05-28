"""Stuck-value detection on Process columns.

Scans each Process column for runs of consecutive equal samples whose
length reaches ``policy.frozen_sensors.frozen_min_minutes`` (interpreted
as samples at the configured 1-min cadence). Equality is exact except
for columns listed in ``epsilon_rate_cols``, which use ``|Δ| < epsilon``.

Severity rules:
- critical → column is a temperature_forecasting / pressure_forecasting
  potential objective (read from ``groups.classification``).
- aware    → all running flags are zero during the run.
- important → any other process column.

Apply masks only critical findings (re-classified later by missing_values).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.cleaning.column_groups import ColumnGroups
from src.data.cleaning.policy import CleaningPolicy
from src.data.cleaning.reporting import Finding, Severity

_FORECAST_OBJECTIVES = {"temperature_forecasting", "pressure_forecasting"}


def detect(
    df: pd.DataFrame,
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    findings: list[Finding] = []
    skip = set(policy.frozen_sensors.skip_columns)
    min_run = policy.frozen_sensors.frozen_min_minutes
    eps_cols = set(policy.frozen_sensors.epsilon_rate_cols)
    eps = policy.frozen_sensors.epsilon

    running_present = [c for c in groups.running_flags if c in df.columns]

    for col in groups.process:
        if col in skip or col not in df.columns:
            continue
        use_eps = col in eps_cols
        for start, end in _frozen_runs(df[col], min_run, eps if use_eps else None):
            findings.append(_make_finding(
                df, col, start, end, groups, running_present,
            ))
    return findings


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    out = df.copy()
    for f in findings:
        if f.severity != Severity.CRITICAL or f.column is None:
            continue
        if f.row_range is None or f.column not in out.columns:
            continue
        start, end = f.row_range
        out.loc[start:end, f.column] = np.nan
    return out


def _frozen_runs(
    series: pd.Series, min_len: int, eps: float | None,
) -> list[tuple[int, int]]:
    values = series.to_numpy()
    n = len(values)
    runs: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if not _is_finite(values[i]):
            i += 1
            continue
        j = i + 1
        while j < n and _is_finite(values[j]) and _equal(values[i], values[j], eps):
            j += 1
        run_len = j - i
        if run_len >= min_len:
            runs.append((int(series.index[i]), int(series.index[j - 1])))
        i = j
    return runs


def _is_finite(v: float) -> bool:
    return v is not None and not (isinstance(v, float) and np.isnan(v))


def _equal(a: float, b: float, eps: float | None) -> bool:
    if eps is None:
        return bool(a == b)
    return bool(abs(a - b) < eps)


def _make_finding(
    df: pd.DataFrame,
    col: str,
    start: int,
    end: int,
    groups: ColumnGroups,
    running_present: list[str],
) -> Finding:
    severity = _severity_for(col, df, start, end, groups, running_present)
    action = "mask_nan" if severity == Severity.CRITICAL else "tag_only"
    value = df.at[start, col]
    return Finding(
        check="frozen_sensors",
        severity=severity,
        finding_type="frozen_run",
        column=col,
        row_range=(start, end),
        count=end - start + 1,
        action_taken=action,
        evidence={"value": _scalar(value), "length": end - start + 1},
    )


def _severity_for(
    col: str,
    df: pd.DataFrame,
    start: int,
    end: int,
    groups: ColumnGroups,
    running_present: list[str],
) -> Severity:
    objective = _objective_for(col, groups)
    if objective in _FORECAST_OBJECTIVES:
        return Severity.CRITICAL
    if running_present and _all_flags_off(df, running_present, start, end):
        return Severity.AWARE
    return Severity.IMPORTANT


def _objective_for(col: str, groups: ColumnGroups) -> str | None:
    cls = groups.classification
    if col not in cls.index or "Potential_Objective" not in cls.columns:
        return None
    val = cls.loc[col, "Potential_Objective"]
    return str(val) if pd.notna(val) else None


def _all_flags_off(
    df: pd.DataFrame, flags: list[str], start: int, end: int,
) -> bool:
    sub = df.loc[start:end, flags]
    return bool((sub.fillna(0) == 0).all().all())


def _scalar(v: object) -> float | None:
    try:
        f = float(v)  # type: ignore[arg-type]
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None
