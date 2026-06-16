"""End-to-end anomaly orchestrator: pca-run resolution, writes, --no-write."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.intelligence.anomaly import io, run_anomaly
from src.intelligence.pca import run_pca

_CLASSIFICATION = PROJECT_ROOT / "data" / "features" / "variable_classification.csv"

_CONFIG_YAML = """
profiles:
  min_samples_per_profile: 5
"""


@pytest.fixture
def chain_inputs(tmp_path: Path, labeled_frame, baselines_factory, groups):
    """Master + behaviour artifacts + a real completed pca run on tmp_path."""
    df, labels, train_mask = labeled_frame(n_rows=160, train_fraction=0.5)

    master = tmp_path / "master_dataset.parquet"
    df.reset_index().to_parquet(master, index=False)

    # Run-versioned behaviour layout so the leaf manifest records a real
    # behaviour_run_id (PROV-01).
    beh_run = tmp_path / "behaviour" / "runs" / "beh1"
    (beh_run / "profiles").mkdir(parents=True)
    labels_path = beh_run / "profiles" / "profile_labels.parquet"
    pd.DataFrame(
        {"profile": labels, "is_train": train_mask.astype("int8")}
    ).reset_index().to_parquet(labels_path, index=False)

    manifest_path = beh_run / "behaviour_fit_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "fit_timestamp": "t0",
                "created_at": "c0",
                "master_dataset_sha256": "beh-sha-1",
                "fit_window": {"n_train": 80},
            }
        ),
        encoding="utf-8",
    )

    sensors = [c for c in groups.process if c in df.columns]
    baselines_path = tmp_path / "baselines.parquet"
    baselines_factory(df, labels, train_mask, sensors).to_parquet(
        baselines_path, index=False
    )

    config = tmp_path / "config.yaml"
    config.write_text(_CONFIG_YAML, encoding="utf-8")

    # A real completed pca run feeding the pca detector.
    pca_root = tmp_path / "pca"
    code = run_pca.main(
        [
            "--master",
            str(master),
            "--classification",
            str(_CLASSIFICATION),
            "--config",
            str(config),
            "--profile-labels",
            str(labels_path),
            "--behaviour-manifest",
            str(manifest_path),
            "--output-root",
            str(pca_root),
            "--run-id",
            "pcarun",
        ]
    )
    assert code == 0

    return {
        "master": master,
        "labels": labels_path,
        "manifest": manifest_path,
        "baselines": baselines_path,
        "config": config,
        "pca_root": pca_root,
        "output_root": tmp_path / "anomaly",
    }


def _argv(inputs, *extra: str) -> list[str]:
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
        "--baselines",
        str(inputs["baselines"]),
        "--pca-root",
        str(inputs["pca_root"]),
        "--output-root",
        str(inputs["output_root"]),
        *extra,
    ]


def test_write_run_full_schema_and_artifacts(chain_inputs) -> None:
    code = run_anomaly.main(_argv(chain_inputs, "--run-id", "run1"))
    assert code == 0
    out = chain_inputs["output_root"] / "runs" / "run1"
    for name in (
        io.SCORES_FILE,
        io.CALIBRATION_FILE,
        io.UNSUPPORTED_FILE,
        io.TIMELINE_FILE,
        io.RATES_FILE,
        io.SEVERITY_FILE,
        io.TOP_EVENTS_FILE,
        io.AGREEMENT_FILE,
        io.REPORT_JSON,
        io.REPORT_MD,
        io.MANIFEST_NAME,
    ):
        assert (out / name).exists(), str(name)

    scored = pd.read_parquet(out / io.SCORES_FILE)
    assert list(scored.columns) == [
        "timestamp",
        "profile",
        "statistical_score",
        "mahalanobis_score",
        "pca_q_score",
        "pca_t2_score",
        "isolation_forest_score",
        "combined_score",
        "severity",
        "triggered_detectors",
        "affected_variables",
        "evidence",
    ]
    assert set(scored["severity"]) <= {"normal", "warning", "anomaly", "unscored"}

    manifest = json.loads((out / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["component"] == "anomaly"
    up = manifest["upstream"]
    assert up["pca_run_id"] == "pcarun"
    assert up["pca_fingerprint_matches"] is True
    assert up["behaviour_run_id"] == "beh1"
    assert up["behaviour_manifest_path"].endswith("behaviour_fit_manifest.json")
    assert up["behaviour_created_at"] == "c0"
    assert up["behaviour_fit_timestamp"] == "t0"
    assert up["behaviour_master_dataset_sha256"] == "beh-sha-1"
    assert "profile_a" in manifest["severity_thresholds"]

    mdir = io.model_dir(out, "profile_a")
    for name in (io.IFOREST_FILE, io.MAHALANOBIS_FILE, io.MODEL_META_FILE):
        assert (mdir / name).exists(), name


def test_pca_run_latest_resolution(chain_inputs) -> None:
    # 'latest' (the default) must resolve to the only completed pca run.
    code = run_anomaly.main(
        _argv(chain_inputs, "--pca-run", "latest", "--run-id", "run1")
    )
    assert code == 0
    out = chain_inputs["output_root"] / "runs" / "run1"
    manifest = json.loads((out / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["upstream"]["pca_run_id"] == "pcarun"


def test_missing_pca_run_raises(chain_inputs, tmp_path: Path) -> None:
    chain_inputs["pca_root"] = tmp_path / "no_pca"
    with pytest.raises(FileNotFoundError, match="run the upstream component"):
        run_anomaly.main(_argv(chain_inputs, "--no-write"))


def test_no_write_writes_nothing(chain_inputs) -> None:
    code = run_anomaly.main(_argv(chain_inputs, "--no-write"))
    assert code == 0
    assert not chain_inputs["output_root"].exists()
