"""Family 1 — temporal derivatives.

Adds three feature families that are *not* covered by the time-series
engineering stage (which already emits ``pct_change`` / ``velocity``):

* ``<col>_accel_<L>``        second-order change ``diff(L).diff(L)``.
* ``<col>_signchanges_<W>``  count of ``sign(diff)`` flips in a rolling
                              window — surfaces oscillation around a
                              setpoint that ``rolling_std`` averages out.
* ``<pv>_minus_<sp>``        SP–PV deviation for each explicit
                              (setpoint, process variable) pair.

All rolling windows use ``closed='left'`` for leakage symmetry with the
upstream rolling features. Routing for ``accel`` and ``signchanges`` is
restricted to the ``categories`` whitelist in the policy (process sensors
by default); state / alarm flags and setpoints are skipped.
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
    return [
        c for c in df.columns
        if groups.semantic_category(c) in allowed_set
    ]


def detect(
    df: pd.DataFrame,
    policy: FeatureEngineeringPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    p = policy.temporal_derivatives
    if not p.enabled:
        return [
            Finding(
                check="temporal_derivatives",
                severity=Severity.NORMAL,
                finding_type="skipped",
                action_taken="noop",
                evidence={"reason": "disabled"},
            )
        ]

    findings: list[Finding] = []

    # --- acceleration ------------------------------------------------------
    if p.acceleration.enabled:
        cols = _columns_in_categories(df, groups, p.acceleration.categories)
        for col in cols:
            for lag in p.acceleration.lags:
                findings.append(
                    Finding(
                        check="temporal_derivatives",
                        severity=Severity.NORMAL,
                        finding_type="acceleration",
                        column=col,
                        count=1,
                        action_taken=f"add:{col}_accel_{lag}",
                        evidence={"lag": int(lag)},
                    )
                )

    # --- sign-change rate -------------------------------------------------
    if p.sign_change_rate.enabled:
        cols = _columns_in_categories(df, groups, p.sign_change_rate.categories)
        for col in cols:
            for w in p.sign_change_rate.windows:
                findings.append(
                    Finding(
                        check="temporal_derivatives",
                        severity=Severity.NORMAL,
                        finding_type="sign_change_rate",
                        column=col,
                        count=1,
                        action_taken=f"add:{col}_signchanges_{w}",
                        evidence={
                            "window": int(w),
                            "closed": p.sign_change_rate.closed,
                            "min_periods": _min_periods(int(w)),
                        },
                    )
                )

    # --- SP–PV deviation --------------------------------------------------
    if p.sp_pv_deviation.enabled:
        for sp_col, pv_col in p.sp_pv_deviation.pairs.items():
            missing = [c for c in (sp_col, pv_col) if c not in df.columns]
            if missing:
                findings.append(
                    Finding(
                        check="temporal_derivatives",
                        severity=Severity.IMPORTANT,
                        finding_type="sp_pv_deviation_missing",
                        column=sp_col,
                        action_taken="skip",
                        evidence={"sp": sp_col, "pv": pv_col, "missing": missing},
                    )
                )
                continue
            findings.append(
                Finding(
                    check="temporal_derivatives",
                    severity=Severity.NORMAL,
                    finding_type="sp_pv_deviation",
                    column=pv_col,
                    count=1,
                    action_taken=f"add:{pv_col}_minus_{sp_col}",
                    evidence={"sp": sp_col, "pv": pv_col},
                )
            )

    return findings


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: FeatureEngineeringPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    if not policy.temporal_derivatives.enabled:
        return df

    new_cols: dict[str, pd.Series] = {}
    for f in findings:
        if f.check != "temporal_derivatives":
            continue
        if f.finding_type == "acceleration":
            col = f.column
            if col is None or col not in df.columns:
                continue
            lag = int(f.evidence["lag"])
            new_cols[f"{col}_accel_{lag}"] = df[col].diff(lag).diff(lag)
        elif f.finding_type == "sign_change_rate":
            col = f.column
            if col is None or col not in df.columns:
                continue
            w = int(f.evidence["window"])
            closed = f.evidence.get("closed", "left")
            min_periods = int(f.evidence.get("min_periods", _min_periods(w)))
            d = df[col].diff()
            sign_change = (np.sign(d) * np.sign(d.shift(1)) < 0).astype(float)
            new_cols[f"{col}_signchanges_{w}"] = sign_change.rolling(
                window=w, min_periods=min_periods, closed=closed,
            ).sum()
        elif f.finding_type == "sp_pv_deviation":
            sp_col = f.evidence["sp"]
            pv_col = f.evidence["pv"]
            if sp_col not in df.columns or pv_col not in df.columns:
                continue
            new_cols[f"{pv_col}_minus_{sp_col}"] = df[pv_col] - df[sp_col]

    if not new_cols:
        return df
    return pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)
