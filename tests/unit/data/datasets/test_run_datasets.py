"""Orchestrator smoke test: the specialized-datasets stage produces a
master + three projections and a report for each."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.data.datasets import run_datasets
from src.data.feature_engineering import run_feature_engineering
from src.data.time_series import run_ts_engineering


@pytest.fixture
def engineered_parquet(tiny_frame_factory, project_root, tmp_path: Path) -> Path:
    """Run cleaning's downstream pipeline (ts → fe) on a tiny synthetic
    frame so the datasets stage has a real engineered parquet to read."""
    clean = tmp_path / "clean.csv"
    df = tiny_frame_factory(n_rows=80, period_s=60.0)
    df.to_csv(clean, index=False)

    ts_out = tmp_path / "features.parquet"
    rc = run_ts_engineering.main(
        [
            "--clean", str(clean),
            "--classification",
            str(project_root / "data" / "features" / "variable_classification.csv"),
            "--policy", str(project_root / "configs" / "time_series.yaml"),
            "--out-parquet", str(ts_out),
            "--out-json", str(tmp_path / "ts_report.json"),
            "--out-md", str(tmp_path / "ts_report.md"),
        ]
    )
    assert rc == 0

    engineered = tmp_path / "engineered.parquet"
    rc = run_feature_engineering.main(
        [
            "--features", str(ts_out),
            "--classification",
            str(project_root / "data" / "features" / "variable_classification.csv"),
            "--policy", str(project_root / "configs" / "feature_engineering.yaml"),
            "--out-parquet", str(engineered),
            "--out-json", str(tmp_path / "fe_report.json"),
            "--out-md", str(tmp_path / "fe_report.md"),
        ]
    )
    assert rc == 0
    return engineered


def _dataset_args(tmp_path: Path, engineered: Path, project_root: Path) -> list[str]:
    return [
        "--engineered", str(engineered),
        "--classification",
        str(project_root / "data" / "features" / "variable_classification.csv"),
        "--policy", str(project_root / "configs" / "specialized_datasets.yaml"),
        "--schema-lock", str(tmp_path / "schema_lock_does_not_exist.json"),
        "--master-parquet", str(tmp_path / "master.parquet"),
        "--master-report-json", str(tmp_path / "master.json"),
        "--master-report-md", str(tmp_path / "master.md"),
        "--anomaly-parquet", str(tmp_path / "anomaly.parquet"),
        "--anomaly-report-json", str(tmp_path / "anomaly.json"),
        "--anomaly-report-md", str(tmp_path / "anomaly.md"),
        "--forecasting-parquet", str(tmp_path / "forecasting.parquet"),
        "--forecasting-report-json", str(tmp_path / "forecasting.json"),
        "--forecasting-report-md", str(tmp_path / "forecasting.md"),
        "--energy-parquet", str(tmp_path / "energy.parquet"),
        "--energy-report-json", str(tmp_path / "energy.json"),
        "--energy-report-md", str(tmp_path / "energy.md"),
    ]


def test_main_writes_four_parquet_and_four_reports(
    engineered_parquet, project_root, tmp_path: Path,
):
    rc = run_datasets.main(
        _dataset_args(tmp_path, engineered_parquet, project_root)
    )
    assert rc == 0

    for name in ("master", "anomaly", "forecasting", "energy"):
        assert (tmp_path / f"{name}.parquet").exists(), name
        assert (tmp_path / f"{name}.json").exists(), name
        assert (tmp_path / f"{name}.md").exists(), name

    payload = json.loads((tmp_path / "master.json").read_text(encoding="utf-8"))
    assert "master_validation" in payload["findings_by_check"]
    payload = json.loads((tmp_path / "anomaly.json").read_text(encoding="utf-8"))
    assert "anomaly_detection" in payload["findings_by_check"]
    payload = json.loads((tmp_path / "forecasting.json").read_text(encoding="utf-8"))
    assert "forecasting" in payload["findings_by_check"]
    payload = json.loads((tmp_path / "energy.json").read_text(encoding="utf-8"))
    assert "energy" in payload["findings_by_check"]


def test_no_write_skips_parquets(
    engineered_parquet, project_root, tmp_path: Path,
):
    args = _dataset_args(tmp_path, engineered_parquet, project_root) + ["--no-write"]
    rc = run_datasets.main(args)
    assert rc == 0
    for name in ("master", "anomaly", "forecasting", "energy"):
        assert not (tmp_path / f"{name}.parquet").exists(), name
        assert (tmp_path / f"{name}.json").exists(), name
        assert (tmp_path / f"{name}.md").exists(), name


def test_projections_are_subset_of_master(
    engineered_parquet, project_root, tmp_path: Path,
):
    schema_lock = tmp_path / "schema_lock.json"
    master, anomaly, forecasting, energy = run_datasets.run(
        engineered_path=engineered_parquet,
        classification=project_root / "data" / "features" / "variable_classification.csv",
        policy_path=project_root / "configs" / "specialized_datasets.yaml",
        schema_lock_path=schema_lock,
    )
    master_df = master[0]
    master_cols = set(master_df.columns)

    # The synthetic generator's `drift` column is dropped by master.
    assert "drift" not in master_cols

    # Each projection's columns are a subset of master.
    for proj_name, (proj_df, _) in (
        ("anomaly", anomaly),
        ("forecasting", forecasting),
        ("energy", energy),
    ):
        assert set(proj_df.columns).issubset(master_cols), proj_name
        assert proj_df.shape[0] == master_df.shape[0]


def test_union_of_projections_covers_most_of_master(
    engineered_parquet, project_root, tmp_path: Path,
):
    """Catches accidentally over-restrictive selectors: the three
    specialized datasets together should cover the majority of master."""
    master, anomaly, forecasting, energy = run_datasets.run(
        engineered_path=engineered_parquet,
        classification=project_root / "data" / "features" / "variable_classification.csv",
        policy_path=project_root / "configs" / "specialized_datasets.yaml",
        schema_lock_path=tmp_path / "schema_lock.json",
    )
    master_cols = set(master[0].columns)
    union = (
        set(anomaly[0].columns)
        | set(forecasting[0].columns)
        | set(energy[0].columns)
    )
    coverage = len(master_cols & union) / max(len(master_cols), 1)
    assert coverage >= 0.50, (
        f"Union covers only {coverage:.0%} of master — selectors may be too narrow"
    )
