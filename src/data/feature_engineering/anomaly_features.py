"""Family 6 — statistical anomaly features (univariate, no fitted models).

Multivariate scoring (Isolation Forest, LOF, Mahalanobis distance with a
covariance fit) belongs in :mod:`src.models.anomaly` per the CRISP-DM
boundary between preprocessing and modelling. This stage emits only
*statistical, parameter-free* anomaly scores so the engineered feature
matrix carries no model state.

* ``<col>_z_<W>``         rolling z-score
                          ``(x − rolling_mean_<W>) / rolling_std_<W>``.
                          Reuses upstream time-series columns if present.
* ``<col>_robust_z_<W>``  ``(x − rolling_median) / (1.4826 × rolling_MAD)``
                          — outlier-robust z-score.
* ``<col>_z_global``      global z-score against full-record mean / std.
                          Disabled by default — leaks future statistics
                          into past rows; acceptable for offline EDA only.

Routing is restricted to the ``categories`` whitelist (process sensors
by default). Setpoints / state / alarm flags are skipped.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.feature_engineering.column_groups import ColumnGroups
from src.data.feature_engineering.policy import FeatureEngineeringPolicy
from src.data.feature_engineering.reporting import Finding, Severity


def _min_periods(window: int) -> int:
    return max(2, window // 4)


def _columns_in_categories(
    df: pd.DataFrame, groups: ColumnGroups, allowed: list[str],
) -> list[str]:
    allowed_set = set(allowed)
    return [c for c in df.columns if groups.semantic_category(c) in allowed_set]


def detect(
    df: pd.DataFrame,
    policy: FeatureEngineeringPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    p = policy.anomaly_features
    if not p.enabled:
        return [
            Finding(
                check="anomaly_features",
                severity=Severity.NORMAL,
                finding_type="skipped",
                action_taken="noop",
                evidence={"reason": "disabled"},
            )
        ]

    findings: list[Finding] = []

    if p.rolling_z.enabled:
        cols = _columns_in_categories(df, groups, p.rolling_z.categories)
        for col in cols:
            for w in p.rolling_z.windows:
                findings.append(
                    Finding(
                        check="anomaly_features",
                        severity=Severity.NORMAL,
                        finding_type="rolling_z",
                        column=col,
                        count=1,
                        action_taken=f"add:{col}_z_{w}",
                        evidence={
                            "window": int(w),
                            "closed": p.rolling_z.closed,
                            "epsilon": float(p.rolling_z.epsilon),
                            "min_periods": _min_periods(int(w)),
                        },
                    )
                )

    if p.robust_z.enabled:
        cols = _columns_in_categories(df, groups, p.robust_z.categories)
        for col in cols:
            for w in p.robust_z.windows:
                findings.append(
                    Finding(
                        check="anomaly_features",
                        severity=Severity.NORMAL,
                        finding_type="robust_z",
                        column=col,
                        count=1,
                        action_taken=f"add:{col}_robust_z_{w}",
                        evidence={
                            "window": int(w),
                            "closed": p.robust_z.closed,
                            "epsilon": float(p.robust_z.epsilon),
                            "min_periods": _min_periods(int(w)),
                        },
                    )
                )

    if p.global_z.enabled:
        cols = _columns_in_categories(df, groups, p.global_z.categories)
        for col in cols:
            findings.append(
                Finding(
                    check="anomaly_features",
                    severity=Severity.AWARE,
                    finding_type="global_z",
                    column=col,
                    count=1,
                    action_taken=f"add:{col}_z_global",
                    evidence={
                        "epsilon": float(p.global_z.epsilon),
                        "leakage": "uses full-record mean/std",
                    },
                )
            )

    return findings


def _safe_div(num: pd.Series, denom: pd.Series, eps: float) -> pd.Series:
    return pd.Series(
        np.where(denom.abs() < eps, np.nan, num / denom),
        index=num.index,
        dtype="float64",
    )


def _rolling_z(
    s: pd.Series, w: int, closed: str, min_periods: int, eps: float,
) -> pd.Series:
    roll = s.rolling(window=w, min_periods=min_periods, closed=closed)
    return _safe_div(s - roll.mean(), roll.std(), eps)


def _rolling_robust_z(
    s: pd.Series, w: int, closed: str, min_periods: int, eps: float,
) -> pd.Series:
    roll = s.rolling(window=w, min_periods=min_periods, closed=closed)
    median = roll.median()
    mad = roll.apply(
        lambda arr: float(np.median(np.abs(arr - np.median(arr)))),
        raw=True,
    )
    return _safe_div(s - median, 1.4826 * mad, eps)


def _global_z(s: pd.Series, eps: float) -> pd.Series:
    mean = float(s.mean(skipna=True))
    std = float(s.std(skipna=True))
    if not np.isfinite(std) or std < eps:
        return pd.Series(np.nan, index=s.index, dtype="float64")
    return (s - mean) / std


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: FeatureEngineeringPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    if not policy.anomaly_features.enabled:
        return df

    new_cols: dict[str, pd.Series] = {}
    for f in findings:
        if f.check != "anomaly_features" or f.column is None:
            continue
        col = f.column
        if col not in df.columns:
            continue
        s = df[col]
        if f.finding_type == "rolling_z":
            w = int(f.evidence["window"])
            closed = f.evidence.get("closed", "left")
            min_periods = int(f.evidence.get("min_periods", _min_periods(w)))
            eps = float(f.evidence.get("epsilon", 1.0e-6))
            new_cols[f"{col}_z_{w}"] = _rolling_z(s, w, closed, min_periods, eps)
        elif f.finding_type == "robust_z":
            w = int(f.evidence["window"])
            closed = f.evidence.get("closed", "left")
            min_periods = int(f.evidence.get("min_periods", _min_periods(w)))
            eps = float(f.evidence.get("epsilon", 1.0e-6))
            new_cols[f"{col}_robust_z_{w}"] = _rolling_robust_z(
                s, w, closed, min_periods, eps,
            )
        elif f.finding_type == "global_z":
            eps = float(f.evidence.get("epsilon", 1.0e-6))
            new_cols[f"{col}_z_global"] = _global_z(s, eps)

    if not new_cols:
        return df
    return pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)
