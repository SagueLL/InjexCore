"""End-to-end correlation orchestrator: writes, --no-write, run versioning."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.intelligence.correlation import io, run_correlation

_CLASSIFICATION = PROJECT_ROOT / "data" / "features" / "variable_classification.csv"

_CONFIG_YAML = """
profiles:
  min_samples_per_profile: 5
thresholds:
  min_valid_observations: 5
"""


@pytest.fixture
def chain_inputs(tmp_path: Path, labeled_frame) -> dict[str, Path]:
    """Persisted master + behaviour artifacts + config, as on disk at runtime."""
    df, labels, train_mask = labeled_frame(n_rows=40, train_fraction=0.5)

    master = tmp_path / "master_dataset.parquet"
    df.reset_index().to_parquet(master, index=False)

    labels_path = tmp_path / "profile_labels.parquet"
    pd.DataFrame(
        {"profile": labels, "is_train": train_mask.astype("int8")}
    ).reset_index().to_parquet(labels_path, index=False)

    manifest_path = tmp_path / "behaviour_fit_manifest.json"
    manifest_path.write_text(
        json.dumps({"fit_timestamp": "t0", "fit_window": {"n_train": 20}}),
        encoding="utf-8",
    )

    config = tmp_path / "correlation.yaml"
    config.write_text(_CONFIG_YAML, encoding="utf-8")

    return {
        "master": master,
        "labels": labels_path,
        "manifest": manifest_path,
        "config": config,
        "output_root": tmp_path / "correlation",
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
    code = run_correlation.main(_argv(chain_inputs, "--run-id", "run1"))
    assert code == 0
    out = chain_inputs["output_root"] / "runs" / "run1"
    for name in (
        io.CORRELATIONS_FILE,
        io.EXCLUDED_FILE,
        io.STRONG_FILE,
        io.REDUNDANT_FILE,
        io.SHIFT_FILE,
        io.REPORT_JSON,
        io.REPORT_MD,
        io.MANIFEST_NAME,
    ):
        assert (out / name).exists(), name

    manifest = json.loads((out / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["component"] == "correlation"
    assert manifest["run_id"] == "run1"
    assert manifest["fit_window"]["n_train"] == 20
    assert manifest["dataset_fingerprint"]["n_rows"] == 40
    assert manifest["upstream"]["behaviour_fit_timestamp"] == "t0"
    assert "profile_a" in manifest["profiles_fitted"]

    corr = pd.read_parquet(out / io.CORRELATIONS_FILE)
    assert list(corr.columns) == [
        "profile",
        "feature_a",
        "feature_b",
        "pearson",
        "spearman",
        "n_valid",
    ]


def test_second_run_does_not_touch_first(chain_inputs) -> None:
    assert run_correlation.main(_argv(chain_inputs, "--run-id", "run1")) == 0
    first = chain_inputs["output_root"] / "runs" / "run1" / io.MANIFEST_NAME
    before = first.read_text(encoding="utf-8")

    assert run_correlation.main(_argv(chain_inputs, "--run-id", "run2")) == 0
    assert (chain_inputs["output_root"] / "runs" / "run2" / io.MANIFEST_NAME).exists()
    assert first.read_text(encoding="utf-8") == before


def test_no_write_writes_nothing(chain_inputs) -> None:
    code = run_correlation.main(_argv(chain_inputs, "--no-write"))
    assert code == 0
    assert not chain_inputs["output_root"].exists()


def test_missing_behaviour_artifacts_raise(chain_inputs, tmp_path: Path) -> None:
    chain_inputs["labels"] = tmp_path / "absent.parquet"
    with pytest.raises(FileNotFoundError, match="behaviour component first"):
        run_correlation.main(_argv(chain_inputs, "--no-write"))
