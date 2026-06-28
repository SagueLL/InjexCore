"""Iteration C Part 1 contract: sensor-health → operational context → addendum.

Runs the two real CLIs end-to-end on a synthetic world (master with steam
off/intermittent/on periods, a legit stopped-state zero, a must-detect
flatline-zero; synthesized behaviour/anomaly/forensic/BOM artifacts). No
model fitting happens anywhere; every fixture is byte-identical afterwards.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.context.bom.io import file_sha256
from src.context.operational import io as op_io
from src.context.operational import run_operational_context
from src.intelligence.__main__ import main as dispatcher_main
from src.intelligence.sensor_health import io as sh_io

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
]

_N = 2880  # two days at 1-min cadence
_TRAIN = 2016  # 70%
_THIRD = 960


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
    temp = rng.normal(40, 3, _N)
    temp[2200:] = 0.0  # must-detect: 680-row zero run during production
    counter = 800_000 + rng.normal(0, 10_000, _N)

    master = pd.DataFrame(
        {
            "timestamp": ts,
            "steam_valve_pressure_me2": pressure,
            "conditioner_steam_loop_temp": loop_temp,
            "granulator_power": power,
            "conditioner_inlet_temp": temp,
            "inlet_hopper_points": counter,
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
    frame["active_order_count"] = 1
    for scalar, value in (
        ("order_id", "100"),
        ("product_code", "114"),
        ("recipe_version", "v1"),
        ("recipe_context_key", "114:v1:sig"),
        ("bom_signature", "sig"),
    ):
        frame[scalar] = value
    frame["order_ids"] = "100"
    frame["product_codes"] = "114"
    frame["recipe_versions"] = "v1"
    frame["recipe_context_keys"] = "114:v1:sig"
    frame["bom_signatures"] = "sig"
    frame["is_transition_overlap"] = False
    frame["has_active_order"] = True
    # gap rows 1200-1399; overlap rows 2300-2599
    frame.loc[1200:1399, "bom_context_status"] = "no_active_order"
    frame.loc[1200:1399, "active_order_count"] = 0
    frame.loc[1200:1399, "has_active_order"] = False
    for scalar in (
        "order_id",
        "product_code",
        "recipe_version",
        "recipe_context_key",
        "bom_signature",
    ):
        frame.loc[1200:1399, scalar] = None
    frame.loc[2300:2599, "bom_context_status"] = "transition_overlap"
    frame.loc[2300:2599, "active_order_count"] = 2
    frame.loc[2300:2599, "is_transition_overlap"] = True
    for scalar in (
        "order_id",
        "product_code",
        "recipe_version",
        "recipe_context_key",
        "bom_signature",
    ):
        frame.loc[2300:2599, scalar] = None
    frame.loc[2300:2599, "order_ids"] = "100|101"
    frame.to_parquet(run / "timeline" / "bom_context_timeline.parquet", index=False)
    (run / "bom_context_manifest.json").write_text(
        json.dumps(
            {
                "component": "bom_context",
                "run_id": "chain",
                "completion_status": "complete",
            }
        ),
        encoding="utf-8",
    )


def _write_anomaly_run(root: Path, ts: pd.Series, train_end: str) -> None:
    run = root / "runs" / "chain"
    (run / "scores").mkdir(parents=True)
    severity = ["anomaly" if i >= 2200 else "normal" for i in range(_N)]
    pd.DataFrame(
        {
            "timestamp": ts,
            "profile": "mid_production",
            "statistical_score": 0.1,
            "mahalanobis_score": 0.1,
            "pca_q_score": 0.1,
            "pca_t2_score": 0.1,
            "isolation_forest_score": 0.1,
            "combined_score": 0.5,
            "severity": severity,
            "triggered_detectors": "",
            "affected_variables": "",
            "evidence": "",
        }
    ).to_parquet(run / "scores" / "anomaly_scores.parquet", index=False)
    (run / "anomaly_fit_manifest.json").write_text(
        json.dumps(
            {
                "component": "anomaly",
                "run_id": "chain",
                "completion_status": "complete",
                "fit_window": {"train_end": train_end},
                "dataset_fingerprint": {"sha256": "synthetic"},
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def world(tmp_path: Path) -> dict:
    master, profiles = _master_frame()
    master_path = tmp_path / "master.parquet"
    master.to_parquet(master_path, index=False)
    behaviour = _write_behaviour(tmp_path, master["timestamp"], profiles)

    bom_root = tmp_path / "bom"
    _write_bom_run(bom_root, master["timestamp"])
    anomaly_root = tmp_path / "anomaly"
    _write_anomaly_run(
        anomaly_root, master["timestamp"], str(master["timestamp"].iloc[_TRAIN - 1])
    )
    forensic_root = tmp_path / "forensics"
    (forensic_root / "runs" / "fr1").mkdir(parents=True)
    (forensic_root / "runs" / "fr1" / "forensic_manifest.json").write_text(
        json.dumps(
            {
                "component": "anomaly_forensic_addendum",
                "run_id": "fr1",
                "completion_status": "complete",
            }
        ),
        encoding="utf-8",
    )

    op_config = tmp_path / "operational.yaml"
    op_config.write_text(
        f"""
timeline:
  master_path: "{master_path.as_posix()}"
  expected_master_rows: {_N}
upstream:
  profile_labels_path: "{behaviour["labels"].as_posix()}"
  behaviour_manifest_path: "{behaviour["manifest"].as_posix()}"
  sensor_health_root: "{(tmp_path / "sensor_health").as_posix()}"
  sensor_health_run: latest
  bom_root: "{bom_root.as_posix()}"
  bom_run: chain
  anomaly_root: "{anomaly_root.as_posix()}"
  anomaly_run: chain
  forensic_root: "{forensic_root.as_posix()}"
  forensic_run: fr1
steam:
  window_rows: 61
  min_valid_rows: 20
forensic_addendum:
  output_root: "{(tmp_path / "context_addenda").as_posix()}"
  candidate_dates: ["2024-09-02"]
  window_hours: 12
""",
        encoding="utf-8",
    )
    return {
        "tmp": tmp_path,
        "master": master_path,
        "behaviour": behaviour,
        "op_config": op_config,
        "sh_root": tmp_path / "sensor_health",
        "op_root": tmp_path / "operational",
        "addenda_root": tmp_path / "context_addenda",
        "bom_root": bom_root,
    }


def test_full_iteration_c_chain(world: dict) -> None:
    master_sha = file_sha256(world["master"])
    bom_timeline = (
        world["bom_root"]
        / "runs"
        / "chain"
        / "timeline"
        / "bom_context_timeline.parquet"
    )
    bom_sha = file_sha256(bom_timeline)

    # --- 1. sensor-health via the dispatcher --------------------------------
    sh_args = [
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
    assert dispatcher_main(sh_args) == 0
    sh_run = world["sh_root"] / "runs" / "chain"
    sh_manifest = json.loads((sh_run / sh_io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert sh_manifest["completion_status"] == "complete"

    quarantine = pd.read_parquet(sh_run / sh_io.QUARANTINE_FILE)
    assert list(quarantine["sensor"]) == ["conditioner_inlet_temp"]  # only must-detect
    assert bool(quarantine.loc[0, "approved"]) is False
    events = pd.read_parquet(sh_run / sh_io.EVENTS_FILE)
    assert "granulator_power" not in set(events["sensor"])  # stopped zeros silent

    # --- 2. operational context CLI -----------------------------------------
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
    op_run = world["op_root"] / "runs" / "chain"
    op_manifest = json.loads((op_run / op_io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert op_manifest["completion_status"] == "complete"
    assert op_manifest["timeline_row_count"] == _N
    assert op_manifest["sensor_health_run_id"] == "chain"
    assert op_manifest["bom_context_run_id"] == "chain"

    overlay = pd.read_parquet(op_run / op_io.TIMELINE_FILE)
    master_ts = pd.read_parquet(world["master"], columns=["timestamp"])["timestamp"]
    assert len(overlay) == _N
    assert (overlay["timestamp"].to_numpy() == master_ts.to_numpy()).all()

    # The three steam periods classify as designed (period midpoints).
    assert overlay["steam_context"].iloc[480] == "steam_conditioning_off"
    assert overlay["steam_context"].iloc[1440] == "steam_conditioning_intermittent"
    assert overlay["steam_context"].iloc[2500] == "steam_conditioning_on"
    # Sensor-health context flips with the must-detect failure.
    assert overlay["sensor_health_context"].iloc[2300] == "sensor_faulty"
    assert "conditioner_inlet_temp" in overlay["faulty_sensors"].iloc[2300]
    # BOM columns preserved (overlap rows unresolved).
    assert overlay["order_ids"].iloc[2400] == "100|101"
    assert pd.isna(overlay["order_id"].iloc[2400])

    transitions = pd.read_parquet(op_run / op_io.TRANSITIONS_FILE)
    types = set(transitions["transition_types"].str.split("|").explode())
    assert {
        "steam_context_change",
        "sensor_health_change",
        "profile_change",
        "bom_gap_start",
        "bom_gap_end",
        "bom_overlap_start",
        "bom_overlap_end",
    } <= types

    # --- 3. context addendum -------------------------------------------------
    addendum = world["addenda_root"] / "chain"
    addendum_manifest = json.loads(
        (addendum / op_io.ADDENDUM_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert addendum_manifest["completion_status"] == "complete"
    by_health = pd.read_parquet(
        addendum / "anomaly_rates_by_sensor_health_context.parquet"
    ).set_index("sensor_health_context")
    assert by_health.loc["sensor_faulty", "anomaly_rate_validation"] == 1.0
    for fig in (
        "anomaly_rate_by_steam_context.png",
        "anomaly_rate_by_sensor_health_context.png",
        "steam_context_timeline.png",
        "sensor_health_timeline.png",
        "candidate_dates_context_timeline.png",
    ):
        assert (addendum / "figures" / fig).exists(), fig

    # --- 4. --no-write leaves no trace; fixtures untouched -------------------
    no_write_root = world["tmp"] / "nowrite"
    assert (
        run_operational_context.main(
            [
                "--config",
                str(world["op_config"]),
                "--output-root",
                str(no_write_root),
                "--no-write",
            ]
        )
        == 0
    )
    assert not no_write_root.exists()
    assert file_sha256(world["master"]) == master_sha
    assert file_sha256(bom_timeline) == bom_sha
