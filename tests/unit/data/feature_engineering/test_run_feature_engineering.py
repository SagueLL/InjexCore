"""Orchestrator smoke test: the feature engineering pipeline produces an
engineered matrix and a report."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.data.feature_engineering import run_feature_engineering
from src.data.time_series import run_ts_engineering


@pytest.fixture
def features_parquet(tiny_frame_factory, project_root, tmp_path: Path) -> Path:
    """Run the time-series engineering stage on a tiny clean frame and
    persist the resulting feature parquet for the feature engineering
    stage to consume."""
    clean = tmp_path / "clean.csv"
    df = tiny_frame_factory(n_rows=80, period_s=60.0)
    df.to_csv(clean, index=False)

    out_parquet = tmp_path / "features.parquet"
    rc = run_ts_engineering.main(
        [
            "--clean", str(clean),
            "--classification", str(project_root / "data" / "features" / "variable_classification.csv"),
            "--policy", str(project_root / "configs" / "time_series.yaml"),
            "--out-parquet", str(out_parquet),
            "--out-json", str(tmp_path / "ts_report.json"),
            "--out-md", str(tmp_path / "ts_report.md"),
        ]
    )
    assert rc == 0
    assert out_parquet.exists()
    return out_parquet


def test_run_produces_expected_schema(features_parquet, project_root):
    df, findings = run_feature_engineering.run(
        features_path=features_parquet,
        classification=project_root / "data" / "features" / "variable_classification.csv",
        policy_path=project_root / "configs" / "feature_engineering.yaml",
    )

    # Index is the timestamp.
    assert isinstance(df.index, pd.DatetimeIndex)

    # Representative columns from each family.
    for name in (
        # Family 1 — temporal derivatives
        "granulator_power_accel_1",
        "granulator_power_signchanges_15",
        "granulator_power_minus_granulator_power_sp",
        # Family 2 — stability
        "granulator_power_cv_60",
        "granulator_power_range_15",
        "granulator_power_stdratio_5_60",
        # Family 3 — physical ratios
        "granulator_kwh_per_kg",
        "temp_rise_conditioner",
        "extruder_kwh_per_kg",
        # Family 4 — energetic
        "granulator_power_cumkwh",
        "granulator_power_cumkwh_day",
        "granulator_power_energy_per_kg_60",
        # Family 5 — operative
        "time_since_machine_off",
        "n_subsystems_running",
        "cumulative_starts",
        "total_alarms_60",
        "any_alarm_while_running",
        # Family 6 — anomaly
        "granulator_power_z_60",
        "granulator_power_robust_z_60",
    ):
        assert name in df.columns, f"missing engineered feature {name!r}"

    # Findings list non-empty and dominated by NORMAL audit records.
    assert findings
    normal_pct = sum(1 for f in findings if f.severity.value == "normal") / len(findings)
    assert normal_pct > 0.8


def test_main_writes_artifacts(features_parquet, project_root, tmp_path):
    out_parquet = tmp_path / "engineered.parquet"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"

    rc = run_feature_engineering.main(
        [
            "--features", str(features_parquet),
            "--classification", str(project_root / "data" / "features" / "variable_classification.csv"),
            "--policy", str(project_root / "configs" / "feature_engineering.yaml"),
            "--out-parquet", str(out_parquet),
            "--out-json", str(out_json),
            "--out-md", str(out_md),
        ]
    )
    assert rc == 0
    assert out_parquet.exists()
    assert out_json.exists()
    assert out_md.exists()

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    for stage in (
        "temporal_derivatives",
        "stability",
        "physical_ratios",
        "energetic_features",
        "operative_features",
        "anomaly_features",
    ):
        assert stage in payload["findings_by_check"], f"missing stage {stage}"

    md_text = out_md.read_text(encoding="utf-8")
    assert md_text.startswith("# Feature Engineering Report")


def test_no_write_skips_parquet(features_parquet, project_root, tmp_path):
    out_parquet = tmp_path / "engineered.parquet"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"

    rc = run_feature_engineering.main(
        [
            "--features", str(features_parquet),
            "--classification", str(project_root / "data" / "features" / "variable_classification.csv"),
            "--policy", str(project_root / "configs" / "feature_engineering.yaml"),
            "--out-parquet", str(out_parquet),
            "--out-json", str(out_json),
            "--out-md", str(out_md),
            "--no-write",
        ]
    )
    assert rc == 0
    assert not out_parquet.exists()
    assert out_json.exists()
    assert out_md.exists()
