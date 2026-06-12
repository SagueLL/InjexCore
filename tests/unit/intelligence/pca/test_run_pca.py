"""End-to-end pca orchestrator: writes, --no-write, model reload."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.intelligence.pca import io, run_pca

_CLASSIFICATION = PROJECT_ROOT / "data" / "features" / "variable_classification.csv"

_CONFIG_YAML = """
profiles:
  min_samples_per_profile: 5
"""


@pytest.fixture
def chain_inputs(tmp_path: Path, labeled_frame) -> dict[str, Path]:
    """Persisted master + behaviour artifacts + config, as on disk at runtime."""
    df, labels, train_mask = labeled_frame(n_rows=60, train_fraction=0.5)

    master = tmp_path / "master_dataset.parquet"
    df.reset_index().to_parquet(master, index=False)

    labels_path = tmp_path / "profile_labels.parquet"
    pd.DataFrame(
        {"profile": labels, "is_train": train_mask.astype("int8")}
    ).reset_index().to_parquet(labels_path, index=False)

    manifest_path = tmp_path / "behaviour_fit_manifest.json"
    manifest_path.write_text(
        json.dumps({"fit_timestamp": "t0", "fit_window": {"n_train": 30}}),
        encoding="utf-8",
    )

    config = tmp_path / "pca.yaml"
    config.write_text(_CONFIG_YAML, encoding="utf-8")

    return {
        "master": master,
        "labels": labels_path,
        "manifest": manifest_path,
        "config": config,
        "output_root": tmp_path / "pca",
    }


def _argv(inputs: dict[str, Path], *extra: str) -> list[str]:
    return [
        "--master",
        str(inputs["master"]),
        "--classification",
        str(_CLASSIFICATION),
        "--config",
        str(inputs["config"]),
        "--profile-labels",
        str(inputs["labels"]),
        "--behaviour-manifest",
        str(inputs["manifest"]),
        "--output-root",
        str(inputs["output_root"]),
        *extra,
    ]


def test_write_run_creates_versioned_artifacts(chain_inputs) -> None:
    code = run_pca.main(_argv(chain_inputs, "--run-id", "run1"))
    assert code == 0
    out = chain_inputs["output_root"] / "runs" / "run1"
    for name in (
        io.LOADINGS_FILE,
        io.EXPLAINED_VARIANCE_FILE,
        io.SKIPPED_FILE,
        io.REPORT_JSON,
        io.REPORT_MD,
        io.MANIFEST_NAME,
    ):
        assert (out / name).exists(), name
    mdir = io.model_dir(out, "profile_a")
    for name in (io.SCALER_FILE, io.PCA_FILE, io.MODEL_META_FILE):
        assert (mdir / name).exists(), name
    sdir = io.scores_dir(out, "profile_a")
    assert (sdir / io.SCORES_FILE).exists()
    assert (sdir / io.CONTRIBUTIONS_FILE).exists()

    manifest = json.loads((out / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["component"] == "pca"
    assert manifest["profiles"]["profile_a"]["n_components"] >= 1
    assert "sklearn" in manifest["versions"]

    meta = json.loads((mdir / io.MODEL_META_FILE).read_text(encoding="utf-8"))
    assert meta["profile"] == "profile_a"
    assert meta["features"]
    assert len(meta["train_medians"]) == len(meta["features"])

    scores = pd.read_parquet(sdir / io.SCORES_FILE)
    for col in ("t2", "q_spe", "recon_error", "is_train"):
        assert col in scores.columns


def test_no_write_writes_nothing(chain_inputs) -> None:
    code = run_pca.main(_argv(chain_inputs, "--no-write"))
    assert code == 0
    assert not chain_inputs["output_root"].exists()


def test_second_run_does_not_touch_first(chain_inputs) -> None:
    assert run_pca.main(_argv(chain_inputs, "--run-id", "run1")) == 0
    first = chain_inputs["output_root"] / "runs" / "run1" / io.MANIFEST_NAME
    before = first.read_text(encoding="utf-8")
    assert run_pca.main(_argv(chain_inputs, "--run-id", "run2")) == 0
    assert first.read_text(encoding="utf-8") == before
