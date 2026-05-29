"""Family 2 — stability features.

Layered on top of the time-series engineering ``rolling_std``: this stage
emits semantically distinct stability indicators that the raw std
does not capture.

* ``<col>_cv_<W>``                 coefficient of variation
                                    ``rolling_std / |rolling_mean|`` —
                                    scale-free, comparable across °C /
                                    bar / %.
* ``<col>_stdratio_<S>_<L>``       short-window std divided by long-window
                                    std — surfaces *recent* instability
                                    against baseline. Reuses time-series
                                    columns when present, otherwise
                                    recomputes.
* ``<col>_range_<W>``              ``rolling_max - rolling_min``.
* ``<col>_mad_<W>``                rolling median absolute deviation
                                    (outlier-robust spread); restricted to
                                    the configured ``units`` whitelist.

Routing is constrained by the ``categories`` whitelist (process sensors
by default). Setpoints and state / alarm flags are never targeted.
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


def _columns_in_units(
    df: pd.DataFrame, groups: ColumnGroups, units: list[str], allowed: list[str],
) -> list[str]:
    """Subset of ``_columns_in_categories`` further filtered by ``Unity``."""
    cat_cols = set(_columns_in_categories(df, groups, allowed))
    classification = groups.classification
    return [
        c for c in df.columns
        if c in cat_cols
        and c in classification.index
        and classification.loc[c, "Unity"] in units
    ]


def detect(
    df: pd.DataFrame,
    policy: FeatureEngineeringPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    p = policy.stability
    if not p.enabled:
        return [
            Finding(
                check="stability",
                severity=Severity.NORMAL,
                finding_type="skipped",
                action_taken="noop",
                evidence={"reason": "disabled"},
            )
        ]

    findings: list[Finding] = []

    # --- coefficient of variation -----------------------------------------
    if p.cv.enabled:
        cols = _columns_in_categories(df, groups, p.cv.categories)
        for col in cols:
            for w in p.cv.windows:
                findings.append(
                    Finding(
                        check="stability",
                        severity=Severity.NORMAL,
                        finding_type="cv",
                        column=col,
                        count=1,
                        action_taken=f"add:{col}_cv_{w}",
                        evidence={
                            "window": int(w),
                            "closed": p.cv.closed,
                            "epsilon": float(p.cv.epsilon),
                            "min_periods": _min_periods(int(w)),
                        },
                    )
                )

    # --- std ratio (short / long) -----------------------------------------
    if p.std_ratio.enabled:
        cols = _columns_in_categories(df, groups, p.std_ratio.categories)
        for col in cols:
            findings.append(
                Finding(
                    check="stability",
                    severity=Severity.NORMAL,
                    finding_type="std_ratio",
                    column=col,
                    count=1,
                    action_taken=f"add:{col}_stdratio_{p.std_ratio.short}_{p.std_ratio.long}",
                    evidence={
                        "short": int(p.std_ratio.short),
                        "long": int(p.std_ratio.long),
                        "epsilon": float(p.std_ratio.epsilon),
                    },
                )
            )

    # --- rolling range ----------------------------------------------------
    if p.rolling_range.enabled:
        cols = _columns_in_categories(df, groups, p.rolling_range.categories)
        for col in cols:
            for w in p.rolling_range.windows:
                findings.append(
                    Finding(
                        check="stability",
                        severity=Severity.NORMAL,
                        finding_type="rolling_range",
                        column=col,
                        count=1,
                        action_taken=f"add:{col}_range_{w}",
                        evidence={
                            "window": int(w),
                            "closed": p.rolling_range.closed,
                            "min_periods": _min_periods(int(w)),
                        },
                    )
                )

    # --- MAD --------------------------------------------------------------
    if p.mad.enabled:
        cols = _columns_in_units(df, groups, p.mad.units, p.mad.categories)
        for col in cols:
            for w in p.mad.windows:
                findings.append(
                    Finding(
                        check="stability",
                        severity=Severity.NORMAL,
                        finding_type="mad",
                        column=col,
                        count=1,
                        action_taken=f"add:{col}_mad_{w}",
                        evidence={
                            "window": int(w),
                            "closed": p.mad.closed,
                            "min_periods": _min_periods(int(w)),
                        },
                    )
                )

    return findings


def _rolling_std(
    s: pd.Series, w: int, closed: str, min_periods: int,
) -> pd.Series:
    """Use the upstream time-series column if it is already present, else
    recompute. This avoids a noticeable cost on wide frames."""
    return s.rolling(window=w, min_periods=min_periods, closed=closed).std()


def _rolling_mean(
    s: pd.Series, w: int, closed: str, min_periods: int,
) -> pd.Series:
    return s.rolling(window=w, min_periods=min_periods, closed=closed).mean()


def _safe_div(num: pd.Series, denom: pd.Series, eps: float) -> pd.Series:
    return pd.Series(
        np.where(denom.abs() < eps, np.nan, num / denom),
        index=num.index,
        dtype="float64",
    )


def _rolling_mad(s: pd.Series, w: int, closed: str, min_periods: int) -> pd.Series:
    """Rolling median-absolute-deviation. Pandas has no built-in, so we
    feed a callable into ``rolling.apply``. Used only on units C / bar by
    default to keep cost contained."""
    def _mad(arr: np.ndarray) -> float:
        med = np.median(arr)
        return float(np.median(np.abs(arr - med)))
    return s.rolling(window=w, min_periods=min_periods, closed=closed).apply(
        _mad, raw=True,
    )


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: FeatureEngineeringPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    if not policy.stability.enabled:
        return df

    new_cols: dict[str, pd.Series] = {}
    for f in findings:
        if f.check != "stability" or f.column is None:
            continue
        col = f.column
        if col not in df.columns:
            continue
        s = df[col]

        if f.finding_type == "cv":
            w = int(f.evidence["window"])
            closed = f.evidence.get("closed", "left")
            min_periods = int(f.evidence.get("min_periods", _min_periods(w)))
            eps = float(f.evidence.get("epsilon", 1.0e-6))
            mean = _rolling_mean(s, w, closed, min_periods)
            std = _rolling_std(s, w, closed, min_periods)
            new_cols[f"{col}_cv_{w}"] = _safe_div(std, mean.abs(), eps)
        elif f.finding_type == "std_ratio":
            short = int(f.evidence["short"])
            long = int(f.evidence["long"])
            eps = float(f.evidence.get("epsilon", 1.0e-6))
            # Prefer upstream time-series std columns when available.
            short_col = f"{col}_std_{short}"
            long_col = f"{col}_std_{long}"
            if short_col in df.columns:
                short_std = df[short_col]
            else:
                short_std = _rolling_std(s, short, "left", _min_periods(short))
            if long_col in df.columns:
                long_std = df[long_col]
            else:
                long_std = _rolling_std(s, long, "left", _min_periods(long))
            new_cols[f"{col}_stdratio_{short}_{long}"] = _safe_div(
                short_std, long_std, eps,
            )
        elif f.finding_type == "rolling_range":
            w = int(f.evidence["window"])
            closed = f.evidence.get("closed", "left")
            min_periods = int(f.evidence.get("min_periods", _min_periods(w)))
            roll = s.rolling(window=w, min_periods=min_periods, closed=closed)
            new_cols[f"{col}_range_{w}"] = roll.max() - roll.min()
        elif f.finding_type == "mad":
            w = int(f.evidence["window"])
            closed = f.evidence.get("closed", "left")
            min_periods = int(f.evidence.get("min_periods", _min_periods(w)))
            new_cols[f"{col}_mad_{w}"] = _rolling_mad(s, w, closed, min_periods)

    if not new_cols:
        return df
    return pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)
