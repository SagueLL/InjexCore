"""Iteration C Part 2 contract: drift -> incidents -> drift-aware addendum.

Runs four real CLIs end-to-end on a synthetic world (steam thirds, a legit
stopped-state zero, a persistent flatline-zero, a transient missingness
episode, a genuine healthy-sensor mean shift, BOM matched/gap/overlap
periods, an anomaly burst; synthesized behaviour/anomaly/pca/correlation/BOM
artifacts). No model fitting happens anywhere; every fixture is
byte-identical afterwards.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from src.config import PROJECT_ROOT
from src.context.bom.io import file_sha256
from src.context.operational import run_operational_context
from src.intelligence.__main__ import main as dispatcher_main
from src.intelligence.drift import io as drift_io
from src.intelligence.incidents import io as inc_io

_CLASSIFICATION = PROJECT_ROOT / "data" / "features" / "variable_classification.csv"
_PROFILES = [
    "stopped",
    "shutdown",
    "startup",
    "alarm",
    "low_production",
    "mid_production",
    "high_production",
]
_SENSORS = [
    "steam_valve_pressure_me2",
    "conditioner_steam_loop_temp",
    "granulator_power",
    "conditioner_inlet_temp",
    "inlet_hopper_points",
    "inlet_hopper_humidity",
]

_N = 2880  # two days at 1-min cadence
_TRAIN = 2016  # 70%
_THIRD = 960
_FLATLINE = 2200  # conditioner_inlet_temp zeros from here (persistent fault)
_MISSING = (2050, 2200)  # granulator_power NaN episode (transient)


def _master_frame() -> tuple[pd.DataFrame, np.ndarray]:
    ts = pd.date_range("2024-09-01", periods=_N, freq="1min")
    rng = np.random.default_rng(42)
    profiles = np.array(["mid_production"] * _N, dtype=object)
    profiles[200:500] = "stopped"

    toggling = np.arange(_THIRD) // 30 % 2 == 0
    pressure = np.r_[
        rng.normal(0.2, 0.05, _THIRD),
        np.where(toggling, 2.6, 0.2),
        rng.normal(2.6, 0.1, _N - 2 * _THIRD),
    ]
    loop_temp = np.r_[
        rng.normal(34, 1, _THIRD),
        np.where(toggling, 86.0, 34.0),
        rng.normal(86, 1, _N - 2 * _THIRD),
    ]
    power = rng.normal(55, 6, _N)
    power[200:500] = 0.0  # legit stopped-state zeros: must NOT flag
    power[_MISSING[0] : _MISSING[1]] = np.nan  # transient missingness episode
    temp = rng.normal(40, 3, _N)
    temp[_FLATLINE:] = 0.0  # must-detect persistent flatline-zero
    counter = 800_000 + rng.normal(0, 10_000, _N)
    humidity = rng.normal(60.0, 2.0, _N)
    humidity[_TRAIN:] += 15.0  # genuine healthy-sensor shift (residual drift)

    master = pd.DataFrame(
        {
            "timestamp": ts,
            "steam_valve_pressure_me2": pressure,
            "conditioner_steam_loop_temp": loop_temp,
            "granulator_power": power,
            "conditioner_inlet_temp": temp,
            "inlet_hopper_points": counter,
            "inlet_hopper_humidity": humidity,
        }
    )
    return master, profiles


def _write_behaviour(tmp_path: Path, ts: pd.Series, profiles: np.ndarray) -> dict:
    labels_path = tmp_path / "profile_labels.parquet"
    pd.DataFrame(
        {
            "timestamp": ts,
            "profile": profiles,
            "material_change_candidate": 0,
            "is_train": (np.arange(_N) < _TRAIN).astype("int8"),
        }
    ).to_parquet(labels_path, index=False)
    baselines_path = tmp_path / "baselines.parquet"
    pd.DataFrame(
        [
            {
                "profile": p,
                "sensor": s,
                "count": 500,
                "median": 50.0,
                "iqr": 6.0,
                "std": 5.0,
            }
            for p in ("stopped", "mid_production")
            for s in _SENSORS
        ]
    ).to_parquet(baselines_path, index=False)
    manifest_path = tmp_path / "behaviour_fit_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "profiles_fitted": _PROFILES,
                "sensors": _SENSORS,
                "fit_window": {
                    "n_train": _TRAIN,
                    "n_total": _N,
                    "train_start": str(ts.iloc[0]),
                    "train_end": str(ts.iloc[_TRAIN - 1]),
                },
                "fit_timestamp": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return {
        "labels": labels_path,
        "baselines": baselines_path,
        "manifest": manifest_path,
    }


def _write_bom_run(root: Path, ts: pd.Series) -> None:
    run = root / "runs" / "chain"
    (run / "timeline").mkdir(parents=True)
    frame = pd.DataFrame({"timestamp": ts})
    frame["bom_context_status"] = "matched_single_order"
    frame["product_code"] = "114"
    frame["recipe_context_key"] = "114:v1:sig"
    frame["bom_signature"] = "sig"
    frame.loc[1200:1399, "bom_context_status"] = "no_active_order"  # gap period
    frame.loc[2300:2599, "bom_context_status"] = "transition_overlap"  # overlap
    frame.to_parquet(run / "timeline" / "bom_context_timeline.parquet", index=False)
    (run / "orders").mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "transition_timestamp": ts.iloc[1400],
                "previous_order_id": "100",
                "next_order_id": "101",
                "previous_product_code": "114",
                "next_product_code": "114",
                "previous_recipe_context_key": "114:v1:sig",
                "next_recipe_context_key": "114:v1:sig",
                "transition_type": "order_change",
            }
        ]
    ).to_parquet(run / "orders" / "bom_order_transitions.parquet", index=False)
    (run / "bom_context_manifest.json").write_text(
        json.dumps({"completion_status": "complete", "run_id": "chain"}),
        encoding="utf-8",
    )


def _bom_timeline_full(root: Path, ts: pd.Series) -> None:
    """Extend the bom timeline with the full column set operational needs."""
    run = root / "runs" / "chain"
    frame = pd.read_parquet(run / "timeline" / "bom_context_timeline.parquet")
    frame["active_order_count"] = np.where(
        frame["bom_context_status"] == "transition_overlap",
        2,
        np.where(frame["bom_context_status"] == "no_active_order", 0, 1),
    )
    frame["order_id"] = np.where(
        frame["bom_context_status"] == "matched_single_order", "100", None
    )
    frame["recipe_version"] = "v1"
    frame["order_ids"] = np.where(
        frame["bom_context_status"] == "transition_overlap", "100|101", "100"
    )
    frame["product_codes"] = "114"
    frame["recipe_versions"] = "v1"
    frame["recipe_context_keys"] = "114:v1:sig"
    frame["bom_signatures"] = "sig"
    frame["is_transition_overlap"] = frame["bom_context_status"] == "transition_overlap"
    frame["has_active_order"] = frame["bom_context_status"] != "no_active_order"
    frame.to_parquet(run / "timeline" / "bom_context_timeline.parquet", index=False)


def _write_anomaly_run(root: Path, ts: pd.Series, profiles: np.ndarray) -> None:
    run = root / "runs" / "chain"
    (run / "scores").mkdir(parents=True)
    burst = np.arange(_N) >= _FLATLINE
    pd.DataFrame(
        {
            "timestamp": ts,
            "profile": profiles,
            "statistical_score": np.where(burst, 0.9, 0.1),
            "mahalanobis_score": 0.1,
            "pca_q_score": 0.1,
            "pca_t2_score": 0.1,
            "isolation_forest_score": 0.1,
            "combined_score": np.where(burst, 0.9, 0.2),
            "severity": np.where(burst, "anomaly", "normal"),
            "triggered_detectors": np.where(burst, "statistical|mahalanobis", ""),
            "affected_variables": np.where(
                burst, "conditioner_inlet_temp|inlet_hopper_humidity", ""
            ),
            "evidence": "{}",
        }
    ).to_parquet(run / "scores" / "anomaly_scores.parquet", index=False)
    (run / "anomaly_fit_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "chain",
                "dataset_fingerprint": {
                    "sha256": "synthetic",
                    "n_rows": _N,
                    "index_start": str(ts.iloc[0]),
                    "index_end": str(ts.iloc[-1]),
                },
            }
        ),
        encoding="utf-8",
    )


def _write_pca_run(root: Path, ts: pd.Series, profiles: np.ndarray) -> None:
    run = root / "runs" / "chain"
    rng = np.random.default_rng(7)
    for profile in ("stopped", "mid_production"):
        rows = profiles == profile
        n_rows = int(rows.sum())
        out = run / "scores" / profile
        out.mkdir(parents=True)
        burst = np.arange(_N)[rows] >= _FLATLINE
        pd.DataFrame(
            {
                "timestamp": ts[rows],
                "t2": rng.uniform(0, 1, n_rows),
                "q_spe": np.where(burst, 5.0, 1.0),
                "recon_error": rng.uniform(0, 1, n_rows),
                "is_train": np.arange(_N)[rows] < _TRAIN,
            }
        ).to_parquet(out / "scores.parquet", index=False)
        pd.DataFrame(
            {
                "timestamp": ts[rows],
                "conditioner_inlet_temp": np.where(burst, 4.0, 0.4),
                "inlet_hopper_humidity": 0.5,
            }
        ).to_parquet(out / "contributions.parquet", index=False)
    pd.DataFrame(
        {"profile": [], "reason": [], "n_train": [], "n_features": []}
    ).to_parquet(run / "skipped_profiles.parquet", index=False)
    (run / "pca_fit_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "chain",
                "dataset_fingerprint": {
                    "sha256": "synthetic",
                    "n_rows": _N,
                    "index_start": str(ts.iloc[0]),
                    "index_end": str(ts.iloc[-1]),
                },
            }
        ),
        encoding="utf-8",
    )


def _write_correlation_run(root: Path) -> None:
    run = root / "runs" / "chain"
    run.mkdir(parents=True)
    pairs = [
        ("conditioner_inlet_temp", "granulator_power", 0.9),  # fault-dominated
        ("inlet_hopper_humidity", "granulator_power", 0.8),  # healthy collapse
    ]
    pd.DataFrame(
        [
            {
                "profile": "mid_production",
                "feature_a": a,
                "feature_b": b,
                "pearson": p,
                "spearman": p,
                "n_valid": 500,
            }
            for a, b, p in pairs
        ]
    ).to_parquet(run / "correlations.parquet", index=False)
    pd.DataFrame(
        [
            {
                "profile": "mid_production",
                "feature_a": a,
                "feature_b": b,
                "pearson_train": p,
                "pearson_validation": 0.0,
                "abs_delta": p,
                "n_valid_train": 500,
                "n_valid_validation": 300,
            }
            for a, b, p in pairs
        ]
    ).to_parquet(run / "correlation_shift.parquet", index=False)
    (run / "correlation_fit_manifest.json").write_text(
        json.dumps({"run_id": "chain"}), encoding="utf-8"
    )


@pytest.fixture
def world(tmp_path: Path) -> dict:
    master, profiles = _master_frame()
    master_path = tmp_path / "master.parquet"
    master.to_parquet(master_path, index=False)
    ts = master["timestamp"]
    behaviour = _write_behaviour(tmp_path, ts, profiles)

    _write_bom_run(tmp_path / "bom", ts)
    _bom_timeline_full(tmp_path / "bom", ts)
    _write_anomaly_run(tmp_path / "anomaly", ts, profiles)
    _write_pca_run(tmp_path / "pca", ts, profiles)
    _write_correlation_run(tmp_path / "correlation")
    forensic_root = tmp_path / "forensics"
    (forensic_root / "runs" / "fr1").mkdir(parents=True)
    (forensic_root / "runs" / "fr1" / "forensic_manifest.json").write_text(
        "{}", encoding="utf-8"
    )

    op_config = tmp_path / "operational.yaml"
    op_config.write_text(
        yaml.safe_dump(
            {
                "timeline": {
                    "master_path": master_path.as_posix(),
                    "expected_master_rows": _N,
                },
                "upstream": {
                    "profile_labels_path": behaviour["labels"].as_posix(),
                    "behaviour_manifest_path": behaviour["manifest"].as_posix(),
                    "sensor_health_root": (tmp_path / "sensor_health").as_posix(),
                    "sensor_health_run": "latest",
                    "bom_root": (tmp_path / "bom").as_posix(),
                    "bom_run": "chain",
                    "anomaly_root": (tmp_path / "anomaly").as_posix(),
                    "anomaly_run": "chain",
                    "forensic_root": forensic_root.as_posix(),
                    "forensic_run": "fr1",
                },
                "steam": {"window_rows": 61, "min_valid_rows": 20},
                "forensic_addendum": {
                    "output_root": (tmp_path / "context_addenda").as_posix(),
                    "candidate_dates": ["2024-09-02"],
                    "window_hours": 12,
                },
            }
        ),
        encoding="utf-8",
    )

    drift_config = tmp_path / "drift.yaml"
    drift_config.write_text(
        yaml.safe_dump(
            {
                "profiles": {"min_samples_per_profile": 50},
                "windows": {"granularity": "hourly", "min_rows_per_window": 20},
                "scoring": {"train_calibration_min_windows": 3},
                "events": {"persistent_min_windows": 4},
                "upstream": {
                    "profile_labels_path": behaviour["labels"].as_posix(),
                    "behaviour_manifest_path": behaviour["manifest"].as_posix(),
                    "anomaly_root": (tmp_path / "anomaly").as_posix(),
                    "anomaly_run": "chain",
                    "pca_root": (tmp_path / "pca").as_posix(),
                    "pca_run": "chain",
                    "correlation_root": (tmp_path / "correlation").as_posix(),
                    "correlation_run": "chain",
                    "sensor_health_root": (tmp_path / "sensor_health").as_posix(),
                    "sensor_health_run": "latest",
                    "operational_root": (tmp_path / "operational").as_posix(),
                    "operational_run": "latest",
                },
            }
        ),
        encoding="utf-8",
    )

    incidents_config = tmp_path / "incidents.yaml"
    incidents_config.write_text(
        yaml.safe_dump(
            {
                "bursts": {"min_duration_minutes": 30},
                "upstream": {
                    "drift_root": (tmp_path / "drift_out").as_posix(),
                    "drift_run": "latest",
                    "sensor_health_root": (tmp_path / "sensor_health").as_posix(),
                    "sensor_health_run": "latest",
                    "anomaly_root": (tmp_path / "anomaly").as_posix(),
                    "anomaly_run": "chain",
                    "operational_root": (tmp_path / "operational").as_posix(),
                    "operational_run": "latest",
                    "bom_root": (tmp_path / "bom").as_posix(),
                    "bom_run": "chain",
                },
            }
        ),
        encoding="utf-8",
    )
    return {
        "tmp": tmp_path,
        "master": master_path,
        "behaviour": behaviour,
        "op_config": op_config,
        "drift_config": drift_config,
        "incidents_config": incidents_config,
        "sh_root": tmp_path / "sensor_health",
        "op_root": tmp_path / "operational",
        "drift_root": tmp_path / "drift_out",
        "incidents_root": tmp_path / "incidents_out",
        "addenda_root": tmp_path / "drift_addenda",
    }


def test_full_iteration_c2_chain(world: dict) -> None:
    fixture_files = [
        world["master"],
        world["tmp"]
        / "bom"
        / "runs"
        / "chain"
        / "timeline"
        / "bom_context_timeline.parquet",
        world["tmp"]
        / "anomaly"
        / "runs"
        / "chain"
        / "scores"
        / "anomaly_scores.parquet",
        world["tmp"]
        / "pca"
        / "runs"
        / "chain"
        / "scores"
        / "mid_production"
        / "scores.parquet",
        world["tmp"] / "correlation" / "runs" / "chain" / "correlation_shift.parquet",
    ]
    shas_before = {p: file_sha256(p) for p in fixture_files}

    # --- 1. sensor-health + operational context (Part 1 chain) --------------
    assert (
        dispatcher_main(
            [
                "--component",
                "sensor-health",
                "--master",
                str(world["master"]),
                "--classification",
                str(_CLASSIFICATION),
                "--profile-labels",
                str(world["behaviour"]["labels"]),
                "--behaviour-manifest",
                str(world["behaviour"]["manifest"]),
                "--baselines",
                str(world["behaviour"]["baselines"]),
                "--output-root",
                str(world["sh_root"]),
                "--run-id",
                "chain",
            ]
        )
        == 0
    )
    assert (
        run_operational_context.main(
            [
                "--config",
                str(world["op_config"]),
                "--output-root",
                str(world["op_root"]),
                "--run-id",
                "chain",
            ]
        )
        == 0
    )

    # --- 2. drift: dry run leaves no trace, then write run ------------------
    drift_args = [
        "--component",
        "drift",
        "--master",
        str(world["master"]),
        "--classification",
        str(_CLASSIFICATION),
        "--config",
        str(world["drift_config"]),
        "--output-root",
        str(world["drift_root"]),
    ]
    assert dispatcher_main([*drift_args, "--no-write"]) == 0
    assert not world["drift_root"].exists()
    assert dispatcher_main([*drift_args, "--run-id", "chain"]) == 0

    drift_run = world["drift_root"] / "runs" / "chain"
    drift_manifest = json.loads(
        (drift_run / drift_io.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert drift_manifest["completion_status"] == "complete"
    assert drift_manifest["compat_checks"]["operational_timeline_aligned"]
    assert drift_manifest["views"] == ["raw", "healthy_only"]

    events = pd.read_parquet(drift_run / drift_io.EVENTS_FILE)
    assert (events["review_status"] == "pending_review").all()

    # Persistent critical sensor_drift for the flatline, precise SH timing.
    flatline = events[
        (events["affected_sensors"] == "conditioner_inlet_temp")
        & events["drift_event_id"].str.endswith("-SH")
    ]
    assert len(flatline) == 1
    assert flatline.iloc[0]["drift_type"] == "sensor_drift"
    assert flatline.iloc[0]["status"] == "persistent"
    assert flatline.iloc[0]["severity"] == "critical"

    # Transient missingness episode stays separate and resolved.
    missing = events[
        (events["affected_sensors"] == "granulator_power")
        & events["drift_event_id"].str.endswith("-SH")
    ]
    assert len(missing) == 1
    assert missing.iloc[0]["temporal_shape"] == "transient"
    assert missing.iloc[0]["status"] == "resolved"

    # The genuine healthy-sensor shift survives in the healthy-only view.
    residual = events[
        (events["affected_sensors"] == "inlet_hopper_humidity")
        & (events["view"] == "healthy_only")
    ]
    assert len(residual) >= 1

    # Raw-vs-healthy comparison: flatline drift mass collapses healthy-only.
    comparison = pd.read_parquet(drift_run / drift_io.RAW_VS_HEALTHY_FILE)
    inlet = comparison[
        (comparison["entity"] == "conditioner_inlet_temp")
        & (comparison["profile"] == "__global__")
    ]
    assert (
        inlet["drift_score_raw"].fillna(0).sum()
        > inlet["drift_score_healthy_only"].fillna(0).sum()
    )

    # Correlation classification is sensor-quality-aware.
    correlation_summary = pd.read_parquet(
        drift_run / drift_io.CORRELATION_SUMMARY_FILE
    ).set_index("feature_a")
    assert (
        correlation_summary.loc["conditioner_inlet_temp", "classification"]
        == "sensor_drift_evidence"
    )
    assert (
        correlation_summary.loc["inlet_hopper_humidity", "classification"]
        == "process_correlation_break"
    )

    # --- 3. incidents: dry run, then write run with addendum ----------------
    incidents_args = [
        "--component",
        "incidents",
        "--config",
        str(world["incidents_config"]),
        "--output-root",
        str(world["incidents_root"]),
        "--addendum-root",
        str(world["addenda_root"]),
    ]
    assert dispatcher_main([*incidents_args, "--no-write"]) == 0
    assert not world["incidents_root"].exists()
    assert not world["addenda_root"].exists()
    assert dispatcher_main([*incidents_args, "--run-id", "chain"]) == 0

    inc_run = world["incidents_root"] / "runs" / "chain"
    inc_manifest = json.loads(
        (inc_run / inc_io.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert inc_manifest["completion_status"] == "complete"
    assert inc_manifest["addendum_status"] == "complete"
    assert inc_manifest["drift_run_id"] == "chain"

    incidents = pd.read_parquet(inc_run / inc_io.INCIDENTS_FILE)
    assert (incidents["review_status"] == "pending_review").all()
    fault = incidents[
        (incidents["incident_type"] == "sensor_fault")
        & incidents["affected_sensors"].str.contains("conditioner_inlet_temp")
    ]
    assert len(fault) == 1  # drift + sensor_health sources, one incident
    assert set(fault.iloc[0]["sources"].split("|")) == {"drift", "sensor_health"}
    assert fault.iloc[0]["status"] == "persistent"
    assert fault.iloc[0]["severity"] == "critical"

    # The burst inside the fault window is suppressed, transparently.
    suppressed = pd.read_parquet(inc_run / inc_io.SUPPRESSED_FILE)
    assert len(suppressed) >= 1
    assert (
        suppressed.iloc[0]["suppressed_by_incident_id"] == fault.iloc[0]["incident_id"]
    )

    relationships = pd.read_parquet(inc_run / inc_io.RELATIONSHIPS_FILE)
    assert (relationships["causality_status"] == "unknown").all()

    actions = pd.read_parquet(inc_run / inc_io.ACTIONS_FILE)
    quarantine = actions[
        actions["recommended_action"] == "quarantine_from_process_scoring"
    ]
    assert len(quarantine) == 1
    assert bool(quarantine.iloc[0]["approval_required"]) is True
    assert bool(quarantine.iloc[0]["approved"]) is False

    pack = pd.read_parquet(inc_run / inc_io.REVIEW_PACK_FILE)
    assert pack.iloc[0]["incident_type"] == "sensor_fault"  # priority order

    addendum = world["addenda_root"] / "chain"
    addendum_manifest = json.loads(
        (addendum / inc_io.ADDENDUM_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert addendum_manifest["completion_status"] == "complete"
    for figure in (
        "raw_vs_healthy_only_drift.png",
        "drift_by_sensor_health_context.png",
        "drift_by_steam_context.png",
        "top_drift_events_timeline.png",
        "incident_timeline.png",
    ):
        assert (addendum / "figures" / figure).exists(), figure
    summary_text = (addendum / "executive_summary.md").read_text(encoding="utf-8")
    assert "interpretive" in summary_text
    assert "causality" in (addendum / "limitations.md").read_text(encoding="utf-8")

    # --- 4. immutability: every fixture byte-identical ----------------------
    for path, sha in shas_before.items():
        assert file_sha256(path) == sha, path
