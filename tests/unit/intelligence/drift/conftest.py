"""Fixtures for the Drift Intelligence unit tests.

``drift_world`` builds a complete synthetic upstream universe on tmp_path —
master + behaviour labels/manifest + completed anomaly / pca / correlation /
sensor-health / operational-context runs (manifests written last, as the
completion contract requires) — so run-level tests drive the real CLI
end-to-end without touching any real artifact.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml
from src.config import PROJECT_ROOT
from src.intelligence._common.fingerprint import file_sha256
from src.intelligence.drift.policy import DriftPolicy, load_policy

_CLASSIFICATION = PROJECT_ROOT / "data" / "features" / "variable_classification.csv"

SENSORS = ["conditioner_inlet_temp", "granulator_power", "inlet_hopper_points"]
N_ROWS = 720
N_TRAIN = 360
FLATLINE_START = 500  # inlet_hopper_points zeros from here (validation)
SHIFT_START = 360  # granulator_power mean shift from here (healthy residual)


@pytest.fixture(scope="session")
def drift_policy() -> DriftPolicy:
    """Real policy loaded from configs/drift_intelligence.yaml."""
    return load_policy(PROJECT_ROOT / "configs" / "drift_intelligence.yaml")


@pytest.fixture
def policy_factory() -> Callable[..., DriftPolicy]:
    def _make(**overrides: Any) -> DriftPolicy:
        return DriftPolicy.model_validate(overrides)

    return _make


@pytest.fixture
def test_policy(policy_factory: Callable[..., DriftPolicy]) -> DriftPolicy:
    """Hourly-window policy sized for the 720-row synthetic world."""
    return policy_factory(**_test_policy_dict())


def _test_policy_dict() -> dict[str, Any]:
    return {
        "profiles": {"min_samples_per_profile": 50},
        "windows": {
            "granularity": "hourly",
            "min_rows_per_window": 20,
            "min_valid_fraction": 0.3,
        },
        "scoring": {
            "train_calibration_min_windows": 3,
            "persistence_min_windows": 2,
        },
        "events": {"persistent_min_windows": 3, "candidate_max_windows": 1},
    }


def _write_manifest_last(run_dir: Path, name: str, manifest: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / name).write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )


def build_world(tmp_path: Path) -> dict[str, Any]:
    """Synthetic master + behaviour + five completed upstream runs."""
    rng = np.random.default_rng(7)
    ts = pd.date_range("2024-09-01", periods=N_ROWS, freq="1min")
    profiles = np.array(
        ["mid_production"] * 200 + ["stopped"] * 100 + ["mid_production"] * 420,
        dtype=object,
    )
    is_train = np.arange(N_ROWS) < N_TRAIN

    temp = rng.normal(40.0, 3.0, N_ROWS)
    power = rng.normal(55.0, 6.0, N_ROWS)
    power[SHIFT_START:] += 25.0  # genuine validation mean shift (healthy sensor)
    counter = rng.normal(800_000.0, 10_000.0, N_ROWS)
    counter[FLATLINE_START:] = 0.0  # instrumentation flatline-zero
    master = pd.DataFrame(
        {
            "timestamp": ts,
            "conditioner_inlet_temp": temp,
            "granulator_power": power,
            "inlet_hopper_points": counter,
        }
    )
    master_path = tmp_path / "master.parquet"
    master.to_parquet(master_path, index=False)
    master_sha = file_sha256(master_path)

    labels_path = tmp_path / "profile_labels.parquet"
    pd.DataFrame(
        {
            "timestamp": ts,
            "profile": profiles,
            "material_change_candidate": 0,
            "is_train": is_train.astype("int8"),
        }
    ).to_parquet(labels_path, index=False)
    behaviour_manifest_path = tmp_path / "behaviour_fit_manifest.json"
    behaviour_manifest_path.write_text(
        json.dumps(
            {
                "profiles_fitted": ["stopped", "mid_production"],
                "sensors": SENSORS,
                "fit_window": {
                    "n_train": N_TRAIN,
                    "n_total": N_ROWS,
                    "train_start": str(ts[0]),
                    "train_end": str(ts[N_TRAIN - 1]),
                },
                "fit_timestamp": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    severity = np.where(np.arange(N_ROWS) >= FLATLINE_START, "anomaly", "normal")
    anomaly_run = tmp_path / "anomaly" / "runs" / "a1"
    pd.DataFrame(
        {
            "timestamp": ts,
            "profile": profiles,
            "statistical_score": rng.uniform(0, 0.2, N_ROWS) + 0.7 * (~is_train),
            "mahalanobis_score": rng.uniform(0, 0.2, N_ROWS),
            "pca_q_score": rng.uniform(0, 0.2, N_ROWS),
            "pca_t2_score": rng.uniform(0, 0.2, N_ROWS),
            "isolation_forest_score": rng.uniform(0, 0.2, N_ROWS),
            "combined_score": np.where(
                np.arange(N_ROWS) >= FLATLINE_START,
                rng.uniform(0.7, 1.0, N_ROWS),
                rng.uniform(0, 0.3, N_ROWS),
            ),
            "severity": severity,
            "triggered_detectors": np.where(
                severity == "anomaly", "statistical|mahalanobis", ""
            ),
            "affected_variables": np.where(
                severity == "anomaly",
                "inlet_hopper_points|conditioner_inlet_temp",
                "",
            ),
            "evidence": "{}",
        }
    ).pipe(_write_run_table, anomaly_run / "scores" / "anomaly_scores.parquet")
    _write_manifest_last(
        anomaly_run,
        "anomaly_fit_manifest.json",
        {
            "component": "anomaly",
            "run_id": "a1",
            "dataset_fingerprint": {"sha256": "not-the-real-fingerprint"},
        },
    )

    pca_run = tmp_path / "pca" / "runs" / "p1"
    for profile in ("stopped", "mid_production"):
        rows = profiles == profile
        pd.DataFrame(
            {
                "timestamp": ts[rows],
                "t2": rng.uniform(0, 1, int(rows.sum())),
                "q_spe": np.where(np.arange(N_ROWS)[rows] >= FLATLINE_START, 5.0, 1.0),
                "recon_error": rng.uniform(0, 1, int(rows.sum())),
                "is_train": is_train[rows],
            }
        ).pipe(_write_run_table, pca_run / "scores" / profile / "scores.parquet")
        pd.DataFrame(
            {
                "timestamp": ts[rows],
                "conditioner_inlet_temp": rng.uniform(0, 1, int(rows.sum())),
                "inlet_hopper_points": np.where(
                    np.arange(N_ROWS)[rows] >= FLATLINE_START, 4.0, 0.5
                ),
            }
        ).pipe(_write_run_table, pca_run / "scores" / profile / "contributions.parquet")
    pd.DataFrame({"profile": [], "reason": [], "n_train": [], "n_features": []}).pipe(
        _write_run_table, pca_run / "skipped_profiles.parquet"
    )
    _write_manifest_last(
        pca_run,
        "pca_fit_manifest.json",
        {
            "component": "pca",
            "run_id": "p1",
            "dataset_fingerprint": {"sha256": "not-the-real-fingerprint"},
        },
    )

    correlation_run = tmp_path / "correlation" / "runs" / "c1"
    pd.DataFrame(
        [
            {
                "profile": "mid_production",
                "feature_a": "conditioner_inlet_temp",
                "feature_b": "granulator_power",
                "pearson": 0.9,
                "spearman": 0.88,
                "n_valid": 300,
            },
            {
                "profile": "mid_production",
                "feature_a": "conditioner_inlet_temp",
                "feature_b": "inlet_hopper_points",
                "pearson": 0.8,
                "spearman": 0.79,
                "n_valid": 300,
            },
        ]
    ).pipe(_write_run_table, correlation_run / "correlations.parquet")
    pd.DataFrame(
        [
            {
                "profile": "mid_production",
                "feature_a": "conditioner_inlet_temp",
                "feature_b": "granulator_power",
                "pearson_train": 0.9,
                "pearson_validation": 0.1,
                "abs_delta": 0.8,
                "n_valid_train": 300,
                "n_valid_validation": 200,
            },
            {
                "profile": "mid_production",
                "feature_a": "conditioner_inlet_temp",
                "feature_b": "inlet_hopper_points",
                "pearson_train": 0.8,
                "pearson_validation": 0.0,
                "abs_delta": 0.8,
                "n_valid_train": 300,
                "n_valid_validation": 200,
            },
        ]
    ).pipe(_write_run_table, correlation_run / "correlation_shift.parquet")
    _write_manifest_last(
        correlation_run,
        "correlation_fit_manifest.json",
        {
            "component": "correlation",
            "run_id": "c1",
            "dataset_fingerprint": {"sha256": "not-the-real-fingerprint"},
        },
    )

    sensor_health_run = tmp_path / "sensor_health" / "runs" / "s1"
    faulty = np.where(np.arange(N_ROWS) >= FLATLINE_START, "inlet_hopper_points", "")
    pd.DataFrame(
        {
            "timestamp": ts,
            "sensor_health_context": np.where(
                faulty != "", "sensor_faulty", "all_sensors_healthy"
            ),
            "faulty_sensors": faulty,
            "warning_sensors": "",
            "quarantine_recommended_sensors": faulty,
            "unknown_sensors": "",
            "n_sensors_evaluated": len(SENSORS),
        }
    ).pipe(
        _write_run_table,
        sensor_health_run / "summaries" / "sensor_quality_timeline.parquet",
    )
    pd.DataFrame(
        [
            {
                "sensor_health_event_id": "SH-inlet_hopper_points-x",
                "sensor": "inlet_hopper_points",
                "start_timestamp": ts[FLATLINE_START],
                "end_timestamp": ts[-1],
                "duration_rows": N_ROWS - FLATLINE_START,
                "duration_seconds": float(
                    (ts[-1] - ts[FLATLINE_START]).total_seconds()
                ),
                "status": "faulty",
                "issue_types": "flatline_zero|counter_reset:persistent_zero_after_reset",
                "max_health_score": 0.95,
                "affected_profiles": "mid_production",
                "evidence": "{}",
                "recommended_action": "quarantine_recommended",
                "is_persistent": True,
                "review_status": "pending_review",
            },
            {
                "sensor_health_event_id": "SH-granulator_power-y",
                "sensor": "granulator_power",
                "start_timestamp": ts[100],
                "end_timestamp": ts[140],
                "duration_rows": 40,
                "duration_seconds": float((ts[140] - ts[100]).total_seconds()),
                "status": "faulty",
                "issue_types": "missingness_spike",
                "max_health_score": 0.7,
                "affected_profiles": "mid_production",
                "evidence": "{}",
                "recommended_action": "review_data_pipeline",
                "is_persistent": False,
                "review_status": "pending_review",
            },
        ]
    ).pipe(
        _write_run_table, sensor_health_run / "events" / "sensor_health_events.parquet"
    )
    pd.DataFrame(
        [
            {
                "sensor": "inlet_hopper_points",
                "start_timestamp": ts[FLATLINE_START],
                "end_timestamp": ts[-1],
                "reason": "flatline_zero",
                "issue_types": "flatline_zero",
                "severity": "critical",
                "recommended_action": "quarantine_from_process_scoring",
                "approval_required": True,
                "approved": False,
            }
        ]
    ).pipe(
        _write_run_table,
        sensor_health_run / "summaries" / "quarantine_recommendations.parquet",
    )
    _write_manifest_last(
        sensor_health_run,
        "sensor_health_manifest.json",
        {
            "component": "sensor_health",
            "run_id": "s1",
            "master_dataset_sha256": master_sha,
        },
    )

    operational_run = tmp_path / "operational" / "runs" / "o1"
    pd.DataFrame(
        {
            "timestamp": ts,
            "profile": profiles,
            "is_train": is_train,
            "steam_context": np.where(
                np.arange(N_ROWS) < 480,
                "steam_conditioning_off",
                "steam_conditioning_on",
            ),
            "sensor_health_context": np.where(
                faulty != "", "sensor_faulty", "all_sensors_healthy"
            ),
            "faulty_sensors": faulty,
            "warning_sensors": "",
            "quarantine_recommended_sensors": faulty,
            "bom_context_status": "matched_single_order",
            "product_code": np.where(np.arange(N_ROWS) < 600, "P1", "P2"),
            "recipe_context_key": "R1",
            "bom_signature": "S1",
        }
    ).pipe(
        _write_run_table,
        operational_run / "timeline" / "operational_context_timeline.parquet",
    )
    pd.DataFrame(
        [
            {
                "transition_id": "CT-1",
                "timestamp": ts[480],
                "transition_types": "steam_context",
                "from_context": "steam_conditioning_off",
                "to_context": "steam_conditioning_on",
            }
        ]
    ).pipe(
        _write_run_table,
        operational_run / "transitions" / "context_transition_events.parquet",
    )
    _write_manifest_last(
        operational_run,
        "operational_context_manifest.json",
        {
            "component": "operational_context",
            "run_id": "o1",
            "master_dataset_sha256": master_sha,
            "sensor_health_run_id": "s1",
            "timeline_row_count": N_ROWS,
        },
    )

    config_path = tmp_path / "drift.yaml"
    config = _test_policy_dict()
    config["upstream"] = {
        "profile_labels_path": labels_path.as_posix(),
        "behaviour_manifest_path": behaviour_manifest_path.as_posix(),
        "anomaly_root": (tmp_path / "anomaly").as_posix(),
        "anomaly_run": "latest",
        "pca_root": (tmp_path / "pca").as_posix(),
        "pca_run": "latest",
        "correlation_root": (tmp_path / "correlation").as_posix(),
        "correlation_run": "latest",
        "sensor_health_root": (tmp_path / "sensor_health").as_posix(),
        "sensor_health_run": "latest",
        "operational_root": (tmp_path / "operational").as_posix(),
        "operational_run": "latest",
    }
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    out_root = tmp_path / "drift_out"
    return {
        "tmp_path": tmp_path,
        "master_path": master_path,
        "labels_path": labels_path,
        "config_path": config_path,
        "out_root": out_root,
        "timestamps": ts,
        "profiles": profiles,
        "is_train": is_train,
        "args": [
            "--master",
            str(master_path),
            "--classification",
            str(_CLASSIFICATION),
            "--config",
            str(config_path),
            "--output-root",
            str(out_root),
        ],
    }


def _write_run_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


@pytest.fixture
def drift_world(tmp_path: Path) -> dict[str, Any]:
    return build_world(tmp_path)


@pytest.fixture
def labeled_frame() -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Small timestamp-indexed frame + profiles + train mask for metric tests."""
    rng = np.random.default_rng(3)
    n = 600
    idx = pd.date_range("2024-06-01", periods=n, freq="1min")
    profiles = np.where(np.arange(n) % 3 == 0, "stopped", "mid_production").astype(
        object
    )
    train = np.arange(n) < 420
    df = pd.DataFrame(
        {"s1": rng.normal(10.0, 1.0, n), "s2": rng.normal(5.0, 2.0, n)}, index=idx
    )
    return df, profiles, train
