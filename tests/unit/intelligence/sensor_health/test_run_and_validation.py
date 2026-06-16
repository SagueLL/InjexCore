"""Orchestrator CLI, Gate A blockers, dispatcher registration."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.intelligence.__main__ import _COMPONENTS
from src.intelligence.__main__ import main as dispatcher_main
from src.intelligence._common import upstream
from src.intelligence.behaviour import io as beh_io
from src.intelligence.sensor_health import io, run_sensor_health
from src.intelligence.sensor_health.policy import SensorHealthPolicy
from src.intelligence.sensor_health.validation import (
    SensorHealthBlockerError,
    validate_upstream,
)

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
_SENSORS = ["conditioner_inlet_temp", "granulator_power", "inlet_hopper_points"]


@pytest.fixture
def world(tmp_path: Path) -> dict:
    """Synthetic master + behaviour artifacts with a must-detect zero run."""
    n = 600
    ts = pd.date_range("2024-09-01", periods=n, freq="1min")
    rng = np.random.default_rng(11)
    profiles = np.array(
        ["mid_production"] * 100 + ["stopped"] * 150 + ["mid_production"] * 350,
        dtype=object,
    )
    temp = rng.normal(40, 3, n)
    temp[300:] = 0.0  # 300-row zero run in validation, never zero in train
    power = rng.normal(55, 6, n)
    power[100:250] = 0.0  # legit stopped-state zeros (must NOT flag)
    counter = 800_000 + rng.normal(0, 10_000, n)
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

    labels_path = tmp_path / "profile_labels.parquet"
    pd.DataFrame(
        {
            "timestamp": ts,
            "profile": profiles,
            "material_change_candidate": 0,
            "is_train": (np.arange(n) < 300).astype("int8"),
        }
    ).to_parquet(labels_path, index=False)

    baselines_path = tmp_path / "baselines.parquet"
    pd.DataFrame(
        [
            {
                "profile": p,
                "sensor": s,
                "count": 200,
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
                    "n_train": 300,
                    "n_total": n,
                    "train_start": str(ts[0]),
                    "train_end": str(ts[299]),
                },
                "fit_timestamp": "2026-01-01T00:00:00+00:00",
                "created_at": "2026-01-01T00:01:00+00:00",
                "master_dataset_sha256": "beh-sha-1",
            }
        ),
        encoding="utf-8",
    )
    out_root = tmp_path / "sensor_health"
    return {
        "args": [
            "--master",
            str(master_path),
            "--classification",
            str(_CLASSIFICATION),
            "--profile-labels",
            str(labels_path),
            "--behaviour-manifest",
            str(manifest_path),
            "--baselines",
            str(baselines_path),
            "--output-root",
            str(out_root),
        ],
        "out_root": out_root,
        "labels": labels_path,
    }


def test_no_write_writes_nothing(world: dict) -> None:
    assert run_sensor_health.main([*world["args"], "--no-write"]) == 0
    assert not world["out_root"].exists()


def test_full_run_detects_and_recommends_quarantine(world: dict) -> None:
    assert run_sensor_health.main([*world["args"], "--run-id", "t1"]) == 0
    out = world["out_root"] / "runs" / "t1"
    manifest = json.loads((out / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["completion_status"] == "complete"
    assert manifest["quarantine_recommendation_counts"] == 1
    assert io.resolve_run(world["out_root"], "latest", io.MANIFEST_NAME) == out

    quarantine = pd.read_parquet(out / io.QUARANTINE_FILE)
    assert list(quarantine["sensor"]) == ["conditioner_inlet_temp"]
    assert bool(quarantine.loc[0, "approval_required"]) is True
    assert bool(quarantine.loc[0, "approved"]) is False

    events = pd.read_parquet(out / io.EVENTS_FILE)
    assert (events["review_status"] == "pending_review").all()
    assert "granulator_power" not in set(events["sensor"])  # stopped zeros silent

    scores = pd.read_parquet(out / io.SCORES_FILE)
    assert len(scores) == 600 * len(_SENSORS)
    flagged = scores[
        (scores["sensor"] == "conditioner_inlet_temp")
        & (scores["health_status"] == "faulty")
    ]
    assert len(flagged) == 300
    assert (flagged["active_issue_types"].str.contains("flatline_zero")).all()


def test_default_labels_resolve_latest_behaviour_run(
    world: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bare run (no --profile-labels): the None sentinel must resolve the
    latest behaviour run, and the manifest must record that run's directory +
    concrete labels file. Regression for ``_build_manifest`` crashing on
    ``None.parent`` when latest-run resolution is used (the documented bare
    ``--component sensor-health`` form)."""
    d = dict(zip(world["args"][::2], world["args"][1::2], strict=False))

    # Lay out a behaviour-run-shaped directory from the fixture artifacts.
    beh_run = tmp_path / "behaviour" / "runs" / "b1"
    (beh_run / beh_io.PROFILE_LABELS_FILE).parent.mkdir(parents=True)
    (beh_run / beh_io.BASELINES_FILE).parent.mkdir(parents=True)
    shutil.copy(d["--profile-labels"], beh_run / beh_io.PROFILE_LABELS_FILE)
    shutil.copy(d["--baselines"], beh_run / beh_io.BASELINES_FILE)
    shutil.copy(d["--behaviour-manifest"], beh_run / beh_io.MANIFEST_NAME)

    # The None sentinel resolves the latest completed behaviour run.
    monkeypatch.setattr(upstream, "resolve_behaviour_run", lambda *a, **k: beh_run)
    monkeypatch.setattr(
        run_sensor_health, "resolve_behaviour_run", lambda *a, **k: beh_run
    )

    art = run_sensor_health.run(
        Path(d["--master"]),
        Path(d["--classification"]),
        run_sensor_health.DEFAULT_CONFIG,
        None,  # labels_path -> default sentinel (latest resolution)
        None,  # behaviour_manifest_path
        None,  # baselines_path
        "t-none",
    )
    assert art.manifest["behaviour_artifact_path"] == str(beh_run)
    assert art.manifest["behaviour_fingerprint"]["source_path"] == str(
        beh_run / beh_io.PROFILE_LABELS_FILE
    )
    assert art.manifest["behaviour_fingerprint"]["sha256"]
    # PROV-01: explicit behaviour provenance recorded without inference.
    assert art.manifest["behaviour_run_id"] == "b1"
    assert art.manifest["behaviour_manifest_path"] == str(
        beh_run / beh_io.MANIFEST_NAME
    )
    assert art.manifest["behaviour_created_at"] == "2026-01-01T00:01:00+00:00"
    assert art.manifest["behaviour_fit_timestamp"] == "2026-01-01T00:00:00+00:00"
    assert art.manifest["behaviour_master_dataset_sha256"] == "beh-sha-1"


def test_manifest_written_last_failed_run_not_resolvable(
    world: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = io.write_table

    def explode(frame: pd.DataFrame, path: Path) -> None:
        if path.name == io.QUALITY_TIMELINE_FILE.name:
            raise OSError("disk full")
        original(frame, path)

    monkeypatch.setattr(io, "write_table", explode)
    with pytest.raises(OSError, match="disk full"):
        run_sensor_health.main([*world["args"], "--run-id", "crashed"])
    assert not (world["out_root"] / "runs" / "crashed" / io.MANIFEST_NAME).exists()
    with pytest.raises(FileNotFoundError):
        io.resolve_run(world["out_root"], "latest", io.MANIFEST_NAME)


def test_dispatcher_registration(world: dict) -> None:
    assert "sensor-health" in _COMPONENTS
    assert (
        dispatcher_main(["--component", "sensor-health", *world["args"], "--no-write"])
        == 0
    )


def test_unknown_profile_name_in_metadata_is_a_blocker() -> None:
    policy = SensorHealthPolicy.model_validate(
        {"sensors": {"overrides": {"x": {"expected_zero_during_profiles": ["paused"]}}}}
    )
    baselines = pd.DataFrame(
        [
            {
                "profile": "stopped",
                "sensor": "x",
                "count": 1,
                "median": 1.0,
                "iqr": 1.0,
                "std": 1.0,
            }
        ]
    )
    with pytest.raises(SensorHealthBlockerError, match="paused"):
        validate_upstream(["x"], {"profiles_fitted": _PROFILES}, baselines, policy)


def test_label_misalignment_is_a_blocker(world: dict) -> None:
    labels = pd.read_parquet(world["labels"]).iloc[:-5]
    labels.to_parquet(world["labels"], index=False)
    with pytest.raises(SensorHealthBlockerError, match="does not match"):
        run_sensor_health.main([*world["args"], "--no-write"])
