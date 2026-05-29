"""Promote the engineered parquet to a canonical ``master_dataset``.

The engineered matrix already went through cleaning → time-series →
feature-engineering. The master step performs a final integrity pass
before the dataset becomes the **single source of truth** for every
downstream model family:

* Timestamp monotonicity & uniqueness (re-validates the cleaning
  invariant after upstream feature joins).
* NaN budget per column (configurable
  ``max_nan_fraction_per_column``); breaches surface as ``IMPORTANT``
  findings so downstream selectors can decide whether to drop the
  column.
* Optional schema lock: when ``schema_lock`` is true and a
  ``schema_lock.json`` snapshot exists next to the master parquet,
  added / removed columns and dtype changes are reported as ``AWARE``.
* Optional drop list (e.g. ``drift`` from the synthetic generator).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.data.datasets.column_groups import ColumnGroups
from src.data.datasets.policy import SpecializedDatasetsPolicy
from src.data.datasets.reporting import Finding, Severity

CHECK_NAME = "master_validation"


def _check_timestamps(
    df: pd.DataFrame, *, require_monotonic: bool, require_unique: bool,
) -> list[Finding]:
    findings: list[Finding] = []
    if isinstance(df.index, pd.DatetimeIndex):
        ts = df.index
    elif "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        findings.append(
            Finding(
                check=CHECK_NAME,
                severity=Severity.IMPORTANT,
                finding_type="missing_timestamp",
                action_taken="none",
                evidence={"reason": "no timestamp index or column"},
            )
        )
        return findings

    n_nat = int(pd.isna(ts).sum())
    if n_nat:
        findings.append(
            Finding(
                check=CHECK_NAME,
                severity=Severity.IMPORTANT,
                finding_type="timestamp_nat",
                count=n_nat,
                action_taken="flag",
                evidence={"nat_rows": n_nat},
            )
        )

    if require_monotonic and not ts.is_monotonic_increasing:
        findings.append(
            Finding(
                check=CHECK_NAME,
                severity=Severity.IMPORTANT,
                finding_type="non_monotonic_timestamps",
                action_taken="flag",
                evidence={"reason": "timestamps are not monotonically increasing"},
            )
        )

    if require_unique:
        # Compatible with both DatetimeIndex and Series.
        duplicated = pd.Index(ts).duplicated()
        n_dup = int(duplicated.sum())
        if n_dup:
            findings.append(
                Finding(
                    check=CHECK_NAME,
                    severity=Severity.IMPORTANT,
                    finding_type="duplicate_timestamps",
                    count=n_dup,
                    action_taken="flag",
                    evidence={"duplicate_rows": n_dup},
                )
            )
    return findings


def _check_nan_budget(
    df: pd.DataFrame, max_fraction: float,
) -> list[Finding]:
    if df.empty:
        return []
    fractions = df.isna().mean(numeric_only=False)
    findings: list[Finding] = []
    for col, frac in fractions.items():
        f = float(frac)
        if f > max_fraction:
            findings.append(
                Finding(
                    check=CHECK_NAME,
                    severity=Severity.IMPORTANT,
                    finding_type="nan_budget_breach",
                    column=str(col),
                    action_taken="flag",
                    evidence={
                        "nan_fraction": round(f, 6),
                        "threshold": float(max_fraction),
                    },
                )
            )
    return findings


def _drop_columns(
    df: pd.DataFrame, drop: list[str],
) -> tuple[pd.DataFrame, list[Finding]]:
    findings: list[Finding] = []
    if not drop:
        return df, findings
    present = [c for c in drop if c in df.columns]
    missing = [c for c in drop if c not in df.columns]
    if present:
        df = df.drop(columns=present)
        findings.append(
            Finding(
                check=CHECK_NAME,
                severity=Severity.NORMAL,
                finding_type="dropped_columns",
                count=len(present),
                action_taken=f"drop:{len(present)}",
                evidence={"columns": present},
            )
        )
    for name in missing:
        findings.append(
            Finding(
                check=CHECK_NAME,
                severity=Severity.NORMAL,
                finding_type="drop_skipped",
                column=name,
                action_taken="skip",
                evidence={"reason": "column not present"},
            )
        )
    return df, findings


def _check_schema_lock(
    df: pd.DataFrame, schema_path: Path,
) -> list[Finding]:
    if not schema_path.exists():
        return [
            Finding(
                check=CHECK_NAME,
                severity=Severity.NORMAL,
                finding_type="schema_lock_missing",
                action_taken="bootstrap",
                evidence={"path": str(schema_path)},
            )
        ]
    snapshot = json.loads(schema_path.read_text(encoding="utf-8"))
    expected = snapshot.get("columns", {})
    current = {c: str(df[c].dtype) for c in df.columns}

    added = sorted(set(current) - set(expected))
    removed = sorted(set(expected) - set(current))
    dtype_changes = {
        c: {"expected": expected[c], "actual": current[c]}
        for c in set(current) & set(expected)
        if expected[c] != current[c]
    }

    findings: list[Finding] = []
    if added:
        findings.append(
            Finding(
                check=CHECK_NAME,
                severity=Severity.AWARE,
                finding_type="schema_added_columns",
                count=len(added),
                action_taken="flag",
                evidence={"columns": added},
            )
        )
    if removed:
        findings.append(
            Finding(
                check=CHECK_NAME,
                severity=Severity.AWARE,
                finding_type="schema_removed_columns",
                count=len(removed),
                action_taken="flag",
                evidence={"columns": removed},
            )
        )
    if dtype_changes:
        findings.append(
            Finding(
                check=CHECK_NAME,
                severity=Severity.AWARE,
                finding_type="schema_dtype_drift",
                count=len(dtype_changes),
                action_taken="flag",
                evidence={"changes": dtype_changes},
            )
        )
    if not (added or removed or dtype_changes):
        findings.append(
            Finding(
                check=CHECK_NAME,
                severity=Severity.NORMAL,
                finding_type="schema_lock_match",
                action_taken="noop",
                evidence={"columns": len(current)},
            )
        )
    return findings


def run(
    df: pd.DataFrame,
    policy: SpecializedDatasetsPolicy,
    groups: ColumnGroups,
    *,
    schema_lock_path: Path | None = None,
) -> tuple[pd.DataFrame, list[Finding]]:
    """Run the master integrity pass on the engineered DataFrame.

    Returns the master DataFrame (engineered minus the configured
    ``drop_columns``) plus a flat findings list. ``groups`` is accepted
    for signature symmetry with the projection modules even though it
    is not consumed today.
    """
    del groups  # reserved for future per-category integrity checks
    p = policy.master_validation
    if not p.enabled:
        return df, [
            Finding(
                check=CHECK_NAME,
                severity=Severity.NORMAL,
                finding_type="skipped",
                action_taken="noop",
                evidence={"reason": "disabled"},
            )
        ]

    findings: list[Finding] = []

    df, drop_findings = _drop_columns(df, list(p.drop_columns))
    findings.extend(drop_findings)

    findings.extend(
        _check_timestamps(
            df,
            require_monotonic=p.require_monotonic_timestamps,
            require_unique=p.require_unique_timestamps,
        )
    )
    findings.extend(_check_nan_budget(df, p.max_nan_fraction_per_column))

    if p.schema_lock and schema_lock_path is not None:
        findings.extend(_check_schema_lock(df, schema_lock_path))

    findings.append(
        Finding(
            check=CHECK_NAME,
            severity=Severity.NORMAL,
            finding_type="master_summary",
            count=df.shape[1],
            action_taken=f"promote:{df.shape[1]}",
            evidence={
                "rows": int(df.shape[0]),
                "columns": int(df.shape[1]),
            },
        )
    )
    return df, findings
