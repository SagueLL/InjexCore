"""Behaviour Intelligence — end-to-end CLI orchestration."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.intelligence.behaviour import run_behaviour

_CLASSIFICATION = PROJECT_ROOT / "data" / "features" / "variable_classification.csv"
_POLICY = PROJECT_ROOT / "configs" / "behaviour_intelligence.yaml"


def _write_master(behaviour_frame, tmp_path: Path, n_rows: int = 500) -> Path:
    """Persist a master-like frame so load_master() can read it back."""
    df = behaviour_frame(n_rows=n_rows)
    path = tmp_path / "master_dataset.parquet"
    df.reset_index().to_parquet(path, index=False)
    return path


def test_run_end_to_end(behaviour_frame, tmp_path) -> None:
    master = _write_master(behaviour_frame, tmp_path)
    art = run_behaviour.run(master, _CLASSIFICATION, _POLICY)
    assert art.findings  # non-empty
    assert art.profiles.profile_names
    # Enough steady-production training rows -> baselines were fitted.
    assert not art.baseline.table.empty
    assert "production_edges" in art.manifest


def test_missing_master_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        run_behaviour.run(tmp_path / "nope.parquet", _CLASSIFICATION, _POLICY)


def test_no_write_skips_artifacts(behaviour_frame, tmp_path) -> None:
    master = _write_master(behaviour_frame, tmp_path)
    labels_out = tmp_path / "profile_labels.parquet"
    report = tmp_path / "report.json"
    code = run_behaviour.main(
        [
            "--master",
            str(master),
            "--classification",
            str(_CLASSIFICATION),
            "--policy",
            str(_POLICY),
            "--profile-labels",
            str(labels_out),
            "--out-json",
            str(report),
            "--out-md",
            str(tmp_path / "report.md"),
            "--no-write",
        ]
    )
    assert code == 0
    assert report.exists()  # report always written
    assert not labels_out.exists()  # artifacts skipped


def test_main_writes_artifacts(behaviour_frame, tmp_path) -> None:
    master = _write_master(behaviour_frame, tmp_path)
    labels_out = tmp_path / "profile_labels.parquet"
    baselines_out = tmp_path / "baselines.parquet"
    manifest_out = tmp_path / "manifest.json"
    code = run_behaviour.main(
        [
            "--master",
            str(master),
            "--classification",
            str(_CLASSIFICATION),
            "--policy",
            str(_POLICY),
            "--profile-labels",
            str(labels_out),
            "--baselines",
            str(baselines_out),
            "--fit-manifest",
            str(manifest_out),
            "--distribution",
            str(tmp_path / "dist.parquet"),
            "--durations",
            str(tmp_path / "dur.parquet"),
            "--transitions",
            str(tmp_path / "trans.parquet"),
            "--out-json",
            str(tmp_path / "report.json"),
            "--out-md",
            str(tmp_path / "report.md"),
        ]
    )
    assert code == 0
    assert labels_out.exists()
    assert baselines_out.exists()
    assert manifest_out.exists()
    labels = pd.read_parquet(labels_out)
    assert "profile" in labels.columns
    assert "is_train" in labels.columns
