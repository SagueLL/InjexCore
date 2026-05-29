"""Family 3 — physical ratios (cross-column, explicitly enumerated).

Each ratio is named in the policy with one of three operators:

* ``op: ratio``   ``a / b``  (defensive: ``|b| < eps`` becomes NaN)
* ``op: diff``    ``a - b``
* ``op: scale``   ``a * factor`` (unit canonicalisation, e.g. kWh/t → kWh/kg)

No auto-combinatorics: every ratio is one entry in
``configs/feature_engineering.yaml`` so the resulting feature set is
auditable and physically meaningful.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.feature_engineering.column_groups import ColumnGroups
from src.data.feature_engineering.policy import (
    FeatureEngineeringPolicy,
    RatioSpec,
)
from src.data.feature_engineering.reporting import Finding, Severity


def _required_columns(spec: RatioSpec) -> list[str]:
    cols = [spec.a]
    if spec.op != "scale" and spec.b is not None:
        cols.append(spec.b)
    return cols


def _missing(df: pd.DataFrame, spec: RatioSpec) -> list[str]:
    return [c for c in _required_columns(spec) if c not in df.columns]


def detect(
    df: pd.DataFrame,
    policy: FeatureEngineeringPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    p = policy.physical_ratios
    if not p.enabled:
        return [
            Finding(
                check="physical_ratios",
                severity=Severity.NORMAL,
                finding_type="skipped",
                action_taken="noop",
                evidence={"reason": "disabled"},
            )
        ]

    findings: list[Finding] = []
    for spec in p.ratios:
        missing = _missing(df, spec)
        if missing:
            findings.append(
                Finding(
                    check="physical_ratios",
                    severity=Severity.IMPORTANT,
                    finding_type="ratio_missing_input",
                    column=spec.name,
                    action_taken="skip",
                    evidence={
                        "name": spec.name,
                        "op": spec.op,
                        "missing": missing,
                    },
                )
            )
            continue
        findings.append(
            Finding(
                check="physical_ratios",
                severity=Severity.NORMAL,
                finding_type="ratio",
                column=spec.name,
                count=1,
                action_taken=f"add:{spec.name}",
                evidence={
                    "name": spec.name,
                    "op": spec.op,
                    "a": spec.a,
                    "b": spec.b,
                    "factor": spec.factor,
                    "epsilon": float(p.epsilon),
                    "nan_rate_warn": float(p.nan_rate_warn),
                },
            )
        )
    return findings


def _compute(
    df: pd.DataFrame, evidence: dict, eps: float,
) -> pd.Series:
    op = evidence["op"]
    a = df[evidence["a"]]
    if op == "scale":
        factor = float(evidence.get("factor") or 1.0)
        return a * factor
    b = df[evidence["b"]]
    if op == "diff":
        return a - b
    # ratio
    return pd.Series(
        np.where(b.abs() < eps, np.nan, a / b),
        index=a.index,
        dtype="float64",
    )


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: FeatureEngineeringPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    if not policy.physical_ratios.enabled:
        return df

    new_cols: dict[str, pd.Series] = {}
    extra_findings: list[Finding] = []
    for f in findings:
        if f.check != "physical_ratios" or f.finding_type != "ratio":
            continue
        ev = f.evidence
        if any(c not in df.columns for c in _required_columns(
            RatioSpec(name=ev["name"], op=ev["op"], a=ev["a"], b=ev.get("b"), factor=ev.get("factor")),
        )):
            continue
        eps = float(ev.get("epsilon", 1.0e-6))
        series = _compute(df, ev, eps)
        new_cols[ev["name"]] = series

        # Surface a high NaN fraction as an AWARE finding.
        nan_rate = float(series.isna().mean())
        if nan_rate > float(ev.get("nan_rate_warn", 1.0)):
            extra_findings.append(
                Finding(
                    check="physical_ratios",
                    severity=Severity.AWARE,
                    finding_type="ratio_high_nan_rate",
                    column=ev["name"],
                    action_taken="emit",
                    evidence={
                        "nan_rate": nan_rate,
                        "threshold": float(ev["nan_rate_warn"]),
                    },
                )
            )

    findings.extend(extra_findings)
    if not new_cols:
        return df
    return pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)
