"""Family 4 — energetic features.

Outputs (assuming a regular sample grid of ``sample_period_s`` seconds):

* ``<power>_cumkwh``         lifetime cumulative energy
                              ``cumsum(power * dt / 3600)`` for each
                              configured power column.
* ``<power>_cumkwh_day``     same with daily reset
                              (``groupby(index.normalize())``).
* ``<power>_energy_per_kg_<W>``
                              rolling ``Σpower / Σproduction`` over ``W``
                              samples — windowed kWh-per-kg avoids the
                              per-row divide-by-zero pathology of
                              ``power / production`` near idle.

Per-cycle aggregations are out of scope until a cycle marker column
exists on the dataset (``per_cycle.enabled: false`` by default).

Notes on units: the power columns in the InjexCore dictionary are
recorded as ``%`` of nominal load, not kW. Treating them as kW for the
purposes of ``cumkwh`` therefore yields ``%·h`` rather than physical
kilowatt-hours. The feature is still useful as a *load-time integral* —
downstream code that needs physical units can multiply by the nominal
rating. This caveat is documented in ``docs/feature_engineering.md``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.feature_engineering.column_groups import ColumnGroups
from src.data.feature_engineering.policy import FeatureEngineeringPolicy
from src.data.feature_engineering.reporting import Finding, Severity


def _min_periods(window: int) -> int:
    return max(2, window // 4)


def detect(
    df: pd.DataFrame,
    policy: FeatureEngineeringPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    p = policy.energetic_features
    if not p.enabled:
        return [
            Finding(
                check="energetic_features",
                severity=Severity.NORMAL,
                finding_type="skipped",
                action_taken="noop",
                evidence={"reason": "disabled"},
            )
        ]

    findings: list[Finding] = []
    dt_hours = float(p.sample_period_s) / 3600.0

    # --- cumulative energy -----------------------------------------------
    if p.cumulative.enabled:
        for col in p.power_columns:
            if col not in df.columns:
                findings.append(
                    Finding(
                        check="energetic_features",
                        severity=Severity.IMPORTANT,
                        finding_type="cumulative_energy_missing_input",
                        column=col,
                        action_taken="skip",
                        evidence={"missing": col},
                    )
                )
                continue
            findings.append(
                Finding(
                    check="energetic_features",
                    severity=Severity.NORMAL,
                    finding_type="cumulative_energy",
                    column=col,
                    count=1,
                    action_taken=f"add:{col}_cumkwh",
                    evidence={"dt_hours": dt_hours, "reset": "none"},
                )
            )
            if p.cumulative.daily_reset:
                findings.append(
                    Finding(
                        check="energetic_features",
                        severity=Severity.NORMAL,
                        finding_type="cumulative_energy",
                        column=col,
                        count=1,
                        action_taken=f"add:{col}_cumkwh_day",
                        evidence={"dt_hours": dt_hours, "reset": "daily"},
                    )
                )

    # --- energy per kg over rolling window --------------------------------
    if p.energy_per_kg.enabled:
        prod = p.production_column
        if prod is None or prod not in df.columns:
            findings.append(
                Finding(
                    check="energetic_features",
                    severity=Severity.IMPORTANT,
                    finding_type="energy_per_kg_missing_input",
                    column=prod,
                    action_taken="skip",
                    evidence={"missing": prod or "<unset>"},
                )
            )
        else:
            for col in p.power_columns:
                if col not in df.columns:
                    continue
                for w in p.energy_per_kg.windows:
                    findings.append(
                        Finding(
                            check="energetic_features",
                            severity=Severity.NORMAL,
                            finding_type="energy_per_kg",
                            column=col,
                            count=1,
                            action_taken=f"add:{col}_energy_per_kg_{w}",
                            evidence={
                                "window": int(w),
                                "closed": p.energy_per_kg.closed,
                                "min_periods": _min_periods(int(w)),
                                "production_col": prod,
                                "dt_hours": dt_hours,
                                "epsilon": float(p.energy_per_kg.epsilon),
                            },
                        )
                    )

    # --- per-cycle (disabled until a cycle marker exists) ----------------
    if p.per_cycle.enabled:
        findings.append(
            Finding(
                check="energetic_features",
                severity=Severity.AWARE,
                finding_type="per_cycle_enabled",
                action_taken="noop",
                evidence={
                    "note": "per-cycle features requested but not implemented "
                            "for this dataset (no cycle marker)",
                    "cycle_id_column": p.per_cycle.cycle_id_column,
                },
            )
        )

    return findings


def _cumulative_energy(power: pd.Series, dt_hours: float) -> pd.Series:
    return (power.fillna(0).astype(float) * dt_hours).cumsum()


def _cumulative_energy_daily(power: pd.Series, dt_hours: float) -> pd.Series:
    if not isinstance(power.index, pd.DatetimeIndex):
        # Fall back to lifetime cumulation if the index is not datetime —
        # daily grouping is meaningless without timestamps.
        return _cumulative_energy(power, dt_hours)
    per_sample = power.fillna(0).astype(float) * dt_hours
    day = power.index.normalize()
    return per_sample.groupby(day).cumsum()


def _rolling_energy_per_kg(
    power: pd.Series,
    production: pd.Series,
    window: int,
    closed: str,
    min_periods: int,
    dt_hours: float,
    eps: float,
) -> pd.Series:
    # Power in % or kW × dt(h) → kWh per sample. Sum over the window.
    power_sum = (power.fillna(0).astype(float)).rolling(
        window=window, min_periods=min_periods, closed=closed,
    ).sum() * dt_hours
    # production_rate is kg/min; per-sample kg = production × (dt_hours × 60).
    sample_period_min = dt_hours * 60.0
    prod_kg = production.fillna(0).astype(float) * sample_period_min
    prod_sum = prod_kg.rolling(
        window=window, min_periods=min_periods, closed=closed,
    ).sum()
    return pd.Series(
        np.where(prod_sum.abs() < eps, np.nan, power_sum / prod_sum),
        index=power.index,
        dtype="float64",
    )


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: FeatureEngineeringPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    if not policy.energetic_features.enabled:
        return df

    new_cols: dict[str, pd.Series] = {}
    for f in findings:
        if f.check != "energetic_features":
            continue
        if f.finding_type == "cumulative_energy":
            col = f.column
            if col is None or col not in df.columns:
                continue
            dt_hours = float(f.evidence["dt_hours"])
            reset = f.evidence.get("reset", "none")
            if reset == "daily":
                new_cols[f"{col}_cumkwh_day"] = _cumulative_energy_daily(
                    df[col], dt_hours,
                )
            else:
                new_cols[f"{col}_cumkwh"] = _cumulative_energy(df[col], dt_hours)
        elif f.finding_type == "energy_per_kg":
            col = f.column
            prod_col = f.evidence["production_col"]
            if col is None or col not in df.columns or prod_col not in df.columns:
                continue
            w = int(f.evidence["window"])
            closed = f.evidence.get("closed", "left")
            min_periods = int(f.evidence.get("min_periods", _min_periods(w)))
            dt_hours = float(f.evidence["dt_hours"])
            eps = float(f.evidence.get("epsilon", 1.0e-6))
            new_cols[f"{col}_energy_per_kg_{w}"] = _rolling_energy_per_kg(
                df[col], df[prod_col], w, closed, min_periods, dt_hours, eps,
            )

    if not new_cols:
        return df
    return pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)
