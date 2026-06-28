"""Behaviour Intelligence — end-to-end CLI orchestration (run-versioned)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.intelligence._common import runs, upstream
from src.intelligence.behaviour import io, run_behaviour

_CLASSIFICATION = PROJECT_ROOT / "data" / "features" / "variable_classification.csv"
_POLICY = PROJECT_ROOT / "configs" / "behaviour_intelligence.yaml"


def _write_master(behaviour_frame, tmp_path: Path, n_rows: int = 500) -> Path:
    """Persist a master-like frame so load_master() can read it back."""
    df = behaviour_frame(n_rows=n_rows)
    path = tmp_path / "master_dataset.parquet"
    df.reset_index().to_parquet(path, index=False)
    return path


def _tree_snapshot(root: Path) -> dict[str, float]:
    """Map every file under ``root`` to its mtime (for side-effect checks)."""
    if not root.exists():
        return {}
    return {str(p): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}


def test_run_end_to_end(behaviour_frame, tmp_path) -> None:
    master = _write_master(behaviour_frame, tmp_path)
    art = run_behaviour.run(master, _CLASSIFICATION, _POLICY, "r1")
    assert art.findings  # non-empty
    assert art.profiles.profile_names
    # Enough steady-production training rows -> baselines were fitted.
    assert not art.baseline.table.empty
    assert "production_edges" in art.manifest
    # ARC-01 / GOV-01 manifest contract.
    assert art.manifest["component"] == "behaviour"
    assert art.manifest["run_id"] == "r1"
    assert art.manifest["master_dataset_sha256"] == io.file_sha256(master)
    assert art.manifest["train_window"]["n_train"] > 0
    assert art.manifest["row_count"] == len(pd.read_parquet(master))


def test_missing_master_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        run_behaviour.run(tmp_path / "nope.parquet", _CLASSIFICATION, _POLICY, "r1")


def test_no_write_is_side_effect_free(behaviour_frame, tmp_path) -> None:
    master = _write_master(behaviour_frame, tmp_path)
    out_root = tmp_path / "behaviour"
    # Seed a pre-existing file so we can prove nothing is touched.
    out_root.mkdir()
    seed = out_root / "seed.txt"
    seed.write_text("x", encoding="utf-8")
    before = _tree_snapshot(out_root)

    code = run_behaviour.main(
        [
            "--master",
            str(master),
            "--classification",
            str(_CLASSIFICATION),
            "--policy",
            str(_POLICY),
            "--output-root",
            str(out_root),
            "--no-write",
        ]
    )
    assert code == 0
    # No new files, no mtime changes, no runs/ directory created.
    assert _tree_snapshot(out_root) == before
    assert not (out_root / "runs").exists()


def test_main_writes_run_versioned_artifacts(behaviour_frame, tmp_path) -> None:
    master = _write_master(behaviour_frame, tmp_path)
    out_root = tmp_path / "behaviour"
    code = run_behaviour.main(
        [
            "--master",
            str(master),
            "--classification",
            str(_CLASSIFICATION),
            "--policy",
            str(_POLICY),
            "--output-root",
            str(out_root),
            "--run-id",
            "run1",
        ]
    )
    assert code == 0
    run = out_root / "runs" / "run1"
    assert (run / io.PROFILE_LABELS_FILE).exists()
    assert (run / io.BASELINES_FILE).exists()
    assert (run / io.DISTRIBUTION_FILE).exists()
    assert (run / io.MANIFEST_NAME).exists()

    labels = pd.read_parquet(run / io.PROFILE_LABELS_FILE)
    assert "profile" in labels.columns
    assert "is_train" in labels.columns

    manifest = json.loads((run / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["completion_status"] == "complete"
    assert manifest["run_id"] == "run1"
    assert manifest["generated_files"]


def test_manifest_written_last_failed_run_not_resolvable(tmp_path) -> None:
    # A run directory without a (valid) manifest must never resolve as latest.
    out_root = tmp_path / "behaviour"
    (out_root / "runs" / "crashed").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        runs.resolve_run(out_root, "latest", io.MANIFEST_NAME)


def test_resolve_behaviour_run_picks_latest(behaviour_frame, tmp_path) -> None:
    master = _write_master(behaviour_frame, tmp_path)
    out_root = tmp_path / "behaviour"
    for rid in ("20260101T000000Z", "20260102T000000Z"):
        assert (
            run_behaviour.main(
                [
                    "--master",
                    str(master),
                    "--classification",
                    str(_CLASSIFICATION),
                    "--policy",
                    str(_POLICY),
                    "--output-root",
                    str(out_root),
                    "--run-id",
                    rid,
                ]
            )
            == 0
        )
    resolved = upstream.resolve_behaviour_run(out_root)
    assert resolved.name == "20260102T000000Z"
    labels = upstream.load_profile_labels(resolved / io.PROFILE_LABELS_FILE)
    assert "is_train" in labels.columns


def test_run_id_collision_is_rejected(behaviour_frame, tmp_path) -> None:
    master = _write_master(behaviour_frame, tmp_path)
    out_root = tmp_path / "behaviour"
    argv = [
        "--master",
        str(master),
        "--classification",
        str(_CLASSIFICATION),
        "--policy",
        str(_POLICY),
        "--output-root",
        str(out_root),
        "--run-id",
        "dup",
    ]
    assert run_behaviour.main(argv) == 0
    with pytest.raises(runs.RunCollisionError):
        run_behaviour.main(argv)
