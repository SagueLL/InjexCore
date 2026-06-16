"""Intelligence-Layer pipeline contract: behaviour → correlation → pca → anomaly.

Runs the four real component CLIs end-to-end on a small synthetic master,
chained through *persisted* artifacts only — exactly how they consume each
other in production. Verifies that every downstream component reads the
upstream artifacts (not in-memory state) and that the leakage contract
(behaviour's ``is_train`` flag) propagates unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.intelligence.anomaly import io as anomaly_io
from src.intelligence.anomaly import run_anomaly
from src.intelligence.behaviour import io as behaviour_io
from src.intelligence.behaviour import run_behaviour
from src.intelligence.correlation import io as correlation_io
from src.intelligence.correlation import run_correlation
from src.intelligence.pca import io as pca_io
from src.intelligence.pca import run_pca

_CLASSIFICATION = PROJECT_ROOT / "data" / "features" / "variable_classification.csv"

_BEHAVIOUR_YAML = """
profiles:
  min_samples_per_profile: 10
  startup:
    window_samples: 2
  shutdown:
    window_samples: 2
"""

_DOWNSTREAM_YAML = """
profiles:
  min_samples_per_profile: 10
thresholds:
  min_valid_observations: 10
"""

_PCA_ANOMALY_YAML = """
profiles:
  min_samples_per_profile: 10
"""


@pytest.fixture
def master_path(tmp_path: Path, tiny_frame_factory, groups) -> Path:
    """A small synthetic master with non-constant process sensors."""
    n = 240
    df = tiny_frame_factory(n_rows=n).set_index("timestamp")
    rng = np.random.default_rng(42)
    for col in groups.process:
        if col in df.columns:
            df[col] = rng.normal(50.0, 5.0, n)
    df["n_subsystems_running"] = 3.0
    df["time_since_machine_off"] = 0.0
    df["time_since_any_alarm"] = 9999.0
    df["any_alarm_while_running"] = 0
    df["granulator_production_rate"] = rng.normal(10.0, 2.0, n)
    path = tmp_path / "master_dataset.parquet"
    df.reset_index().to_parquet(path, index=False)
    return path


def test_full_chain_consumes_persisted_artifacts(
    tmp_path: Path, master_path: Path
) -> None:
    behaviour_dir = tmp_path / "behaviour"
    behaviour_yaml = tmp_path / "behaviour.yaml"
    behaviour_yaml.write_text(_BEHAVIOUR_YAML, encoding="utf-8")
    downstream_yaml = tmp_path / "downstream.yaml"
    downstream_yaml.write_text(_DOWNSTREAM_YAML, encoding="utf-8")
    pca_anomaly_yaml = tmp_path / "pca_anomaly.yaml"
    pca_anomaly_yaml.write_text(_PCA_ANOMALY_YAML, encoding="utf-8")

    # --- 1. behaviour: derives profiles + leakage-safe split (run-versioned) -
    assert (
        run_behaviour.main(
            [
                "--master",
                str(master_path),
                "--classification",
                str(_CLASSIFICATION),
                "--policy",
                str(behaviour_yaml),
                "--output-root",
                str(behaviour_dir),
                "--run-id",
                "chain",
            ]
        )
        == 0
    )
    behaviour_run = behaviour_dir / "runs" / "chain"
    labels_path = behaviour_run / behaviour_io.PROFILE_LABELS_FILE
    baselines_path = behaviour_run / behaviour_io.BASELINES_FILE
    behaviour_manifest = behaviour_run / behaviour_io.MANIFEST_NAME
    labels = pd.read_parquet(labels_path)
    n_train = int(labels["is_train"].sum())
    assert n_train == 168  # 70% of 240 — the leakage contract downstream reuses

    upstream_args = [
        "--master",
        str(master_path),
        "--classification",
        str(_CLASSIFICATION),
        "--profile-labels",
        str(labels_path),
        "--behaviour-manifest",
        str(behaviour_manifest),
    ]

    # --- 2. correlation: consumes persisted labels --------------------------
    correlation_root = tmp_path / "correlation"
    assert (
        run_correlation.main(
            [
                *upstream_args,
                "--config",
                str(downstream_yaml),
                "--output-root",
                str(correlation_root),
                "--run-id",
                "chain",
            ]
        )
        == 0
    )
    corr_manifest = json.loads(
        (correlation_root / "runs" / "chain" / correlation_io.MANIFEST_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert corr_manifest["fit_window"]["n_train"] == n_train
    assert corr_manifest["profiles_fitted"]

    # --- 3. pca: consumes persisted labels, persists models + scores --------
    pca_root = tmp_path / "pca"
    assert (
        run_pca.main(
            [
                *upstream_args,
                "--config",
                str(pca_anomaly_yaml),
                "--output-root",
                str(pca_root),
                "--run-id",
                "chain",
            ]
        )
        == 0
    )
    pca_run = pca_root / "runs" / "chain"
    pca_manifest = json.loads(
        (pca_run / pca_io.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert pca_manifest["fit_window"]["n_train"] == n_train
    fitted_profiles = pca_manifest["profiles_fitted"]
    assert fitted_profiles
    for profile in fitted_profiles:
        assert (pca_io.model_dir(pca_run, profile) / pca_io.PCA_FILE).exists()
        assert (pca_io.scores_dir(pca_run, profile) / pca_io.SCORES_FILE).exists()

    # --- 4. anomaly: consumes behaviour baselines + the persisted pca run ---
    anomaly_root = tmp_path / "anomaly"
    assert (
        run_anomaly.main(
            [
                *upstream_args,
                "--config",
                str(pca_anomaly_yaml),
                "--baselines",
                str(baselines_path),
                "--pca-root",
                str(pca_root),
                "--pca-run",
                "latest",
                "--output-root",
                str(anomaly_root),
                "--run-id",
                "chain",
            ]
        )
        == 0
    )
    anomaly_run = anomaly_root / "runs" / "chain"
    anomaly_manifest = json.loads(
        (anomaly_run / anomaly_io.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert anomaly_manifest["upstream"]["pca_run_id"] == "chain"
    assert anomaly_manifest["upstream"]["pca_fingerprint_matches"] is True
    assert anomaly_manifest["fit_window"]["n_train"] == n_train

    scored = pd.read_parquet(anomaly_run / anomaly_io.SCORES_FILE)
    assert len(scored) == 240
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
    # Profiles behaviour derived are the profiles anomaly scored.
    assert set(scored["profile"]) == set(labels["profile"].astype(str))
