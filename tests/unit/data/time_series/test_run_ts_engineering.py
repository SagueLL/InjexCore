"""Orchestrator smoke test: pipeline produces a feature matrix and report."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.data.time_series import run_ts_engineering


@pytest.fixture
def cleaned_csv(tiny_frame_factory, tmp_path: Path) -> Path:
    """Persist a tiny frame in the same shape cleaning would produce."""
    df = tiny_frame_factory(n_rows=80, period_s=60.0)
    out = tmp_path / "clean.csv"
    df.to_csv(out, index=False)
    return out


def test_run_produces_expected_schema(cleaned_csv, project_root, tmp_path):
    df, findings = run_ts_engineering.run(
        clean_csv=cleaned_csv,
        classification=project_root / "data" / "features" / "variable_classification.csv",
        policy_path=project_root / "configs" / "time_series.yaml",
    )

    # Index is the timestamp.
    assert isinstance(df.index, pd.DatetimeIndex)

    # Process sensor → full generic set.
    for name in (
        "granulator_power_mean_60",
        "granulator_power_std_60",
        "granulator_power_trend_60",
        "granulator_power_lag_1",
        "granulator_power_pctchg_1",
        "granulator_power_velocity_1",
    ):
        assert name in df.columns, f"missing process_sensor feature {name!r}"

    # Setpoint → lag only.
    assert "granulator_power_sp_lag_1" in df.columns
    assert "granulator_power_sp_mean_60" not in df.columns

    # Alarm flag → specialised families, NOT generic rolling.
    assert "granulator_g2_alarm_tsla" in df.columns
    assert "granulator_g2_alarm_edges_60" in df.columns
    assert "granulator_g2_alarm_mean_60" not in df.columns

    # Findings list is non-empty and dominated by NORMAL audit records.
    assert findings
    normal_pct = sum(1 for f in findings if f.severity.value == "normal") / len(findings)
    assert normal_pct > 0.8


def test_main_writes_artifacts(cleaned_csv, project_root, tmp_path):
    out_parquet = tmp_path / "features.parquet"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"

    rc = run_ts_engineering.main(
        [
            "--clean", str(cleaned_csv),
            "--classification", str(project_root / "data" / "features" / "variable_classification.csv"),
            "--policy", str(project_root / "configs" / "time_series.yaml"),
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
    assert "summary" in payload
    assert "findings_by_check" in payload
    # Every stage should have at least one finding.
    for stage in (
        "temporal_conversion",
        "temporal_index",
        "resampling",
        "rolling_windows",
        "temporal_features",
        "state_features",
    ):
        assert stage in payload["findings_by_check"], f"missing stage {stage}"

    # Markdown carries the TS-specific title.
    md_text = out_md.read_text(encoding="utf-8")
    assert md_text.startswith("# Time-Series Engineering Report")
