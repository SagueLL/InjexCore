"""Master-validation integrity pass."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.datasets import master_validation
from src.data.datasets.policy import (
    MasterValidationPolicy,
    SpecializedDatasetsPolicy,
)
from src.data.datasets.reporting import Severity


def _policy(**overrides) -> SpecializedDatasetsPolicy:
    return SpecializedDatasetsPolicy(
        master_validation=MasterValidationPolicy(**overrides)
    )


def _frame(n: int = 10) -> pd.DataFrame:
    ts = pd.date_range("2025-01-01", periods=n, freq="min")
    return pd.DataFrame({"x": range(n)}, index=pd.DatetimeIndex(ts, name="timestamp"))


def test_clean_frame_emits_only_normal_findings(groups):
    df = _frame()
    policy = _policy(schema_lock=False)
    out, findings = master_validation.run(df, policy, groups)
    assert out.shape == df.shape
    assert all(f.severity is Severity.NORMAL for f in findings), findings


def test_non_monotonic_timestamps_flagged(groups):
    df = _frame()
    # Swap two consecutive timestamps to break monotonicity.
    idx = df.index.tolist()
    idx[3], idx[4] = idx[4], idx[3]
    df.index = pd.DatetimeIndex(idx, name="timestamp")
    out, findings = master_validation.run(df, _policy(schema_lock=False), groups)
    types = {f.finding_type for f in findings}
    assert "non_monotonic_timestamps" in types


def test_duplicate_timestamps_flagged(groups):
    df = _frame()
    idx = df.index.tolist()
    idx[5] = idx[4]
    df.index = pd.DatetimeIndex(idx, name="timestamp")
    out, findings = master_validation.run(df, _policy(schema_lock=False), groups)
    types = {f.finding_type for f in findings}
    assert "duplicate_timestamps" in types


def test_nan_budget_breach_per_column(groups):
    df = _frame()
    # 5 NaNs out of 10 = 0.50 > default 0.30 threshold.
    df.loc[df.index[:5], "x"] = np.nan
    out, findings = master_validation.run(df, _policy(schema_lock=False), groups)
    breaches = [f for f in findings if f.finding_type == "nan_budget_breach"]
    assert len(breaches) == 1
    assert breaches[0].column == "x"
    assert breaches[0].severity is Severity.IMPORTANT


def test_drop_columns_removes_listed_names(groups):
    df = _frame()
    df["drift"] = 1.0
    out, findings = master_validation.run(
        df, _policy(schema_lock=False, drop_columns=["drift", "missing"]), groups,
    )
    assert "drift" not in out.columns
    drop_finding = next(
        f for f in findings if f.finding_type == "dropped_columns"
    )
    assert drop_finding.evidence["columns"] == ["drift"]
    skip = [f for f in findings if f.finding_type == "drop_skipped"]
    assert skip and skip[0].column == "missing"


def test_schema_lock_bootstraps_when_missing(groups, tmp_path: Path):
    df = _frame()
    snapshot = tmp_path / "schema_lock.json"
    out, findings = master_validation.run(
        df, _policy(schema_lock=True), groups,
        schema_lock_path=snapshot,
    )
    types = {f.finding_type for f in findings}
    assert "schema_lock_missing" in types


def test_schema_lock_detects_drift(groups, tmp_path: Path):
    df = _frame()
    snapshot = tmp_path / "schema_lock.json"
    snapshot.write_text(
        json.dumps({"columns": {"x": str(df["x"].dtype), "removed_col": "float64"}}),
        encoding="utf-8",
    )
    df["added_col"] = 1.0
    df["x"] = df["x"].astype("float64")
    _, findings = master_validation.run(
        df, _policy(schema_lock=True), groups,
        schema_lock_path=snapshot,
    )
    types = {f.finding_type for f in findings}
    assert "schema_added_columns" in types
    assert "schema_removed_columns" in types


def test_disabled_pass_returns_frame_unchanged(groups):
    df = _frame()
    df["drift"] = 1.0
    out, findings = master_validation.run(
        df, _policy(enabled=False, drop_columns=["drift"]), groups,
    )
    assert "drift" in out.columns
    assert len(findings) == 1 and findings[0].finding_type == "skipped"
