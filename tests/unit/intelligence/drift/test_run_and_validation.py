"""Orchestrator CLI, Gate A blockers, manifest-last, dispatcher registration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from src.intelligence.__main__ import _COMPONENTS
from src.intelligence.__main__ import main as dispatcher_main
from src.intelligence.drift import io, run_drift


def test_no_write_writes_nothing(drift_world: dict[str, Any]) -> None:
    assert run_drift.main([*drift_world["args"], "--no-write"]) == 0
    assert not drift_world["out_root"].exists()


def test_full_run_produces_all_artifacts_and_ground_truth(
    drift_world: dict[str, Any],
) -> None:
    assert run_drift.main([*drift_world["args"], "--run-id", "t1"]) == 0
    out = drift_world["out_root"] / "runs" / "t1"

    manifest = json.loads((out / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["completion_status"] == "complete"
    assert manifest["upstream"]["anomaly_run_id"] == "a1"
    assert manifest["upstream"]["sensor_health_run_id"] == "s1"
    assert manifest["views"] == ["raw", "healthy_only"]
    assert io.resolve_run(drift_world["out_root"], "latest", io.MANIFEST_NAME) == out
    for statement in manifest["statements"]:
        assert "refit" in statement or "modif" in statement or "healthy" in statement

    for rel in (
        io.SCORES_FILE,
        io.EVENTS_FILE,
        io.SENSOR_SUMMARY_FILE,
        io.PROFILE_SUMMARY_FILE,
        io.CONTEXT_SUMMARY_FILE,
        io.CORRELATION_SUMMARY_FILE,
        io.MULTIVARIATE_SUMMARY_FILE,
        io.PROFILE_COMPOSITION_FILE,
        io.STEAM_SHIFT_FILE,
        io.SENSOR_HEALTH_SHIFT_FILE,
        io.BOM_SHIFT_FILE,
        io.RAW_VS_HEALTHY_FILE,
        io.UNSUPPORTED_FILE,
    ):
        assert (out / rel).exists(), rel

    events = pd.read_parquet(out / io.EVENTS_FILE)
    assert (events["review_status"] == "pending_review").all()

    # The instrumentation flatline surfaces as a promoted critical sensor_drift
    # with the sensor-health onset timing as the authority.
    flatline = events[
        (events["affected_sensors"] == "inlet_hopper_points")
        & (events["drift_type"] == "sensor_drift")
        & (events["drift_event_id"].str.endswith("-SH"))
    ]
    assert len(flatline) == 1
    assert flatline.iloc[0]["severity"] == "critical"
    assert flatline.iloc[0]["status"] == "persistent"
    assert pd.Timestamp(flatline.iloc[0]["start_timestamp"]) == pd.Timestamp(
        drift_world["timestamps"][500]
    )

    # The transient missingness episode stays a separate resolved event.
    transient = events[
        (events["affected_sensors"] == "granulator_power")
        & (events["drift_event_id"].str.endswith("-SH"))
    ]
    assert len(transient) == 1
    assert transient.iloc[0]["status"] == "resolved"
    assert transient.iloc[0]["temporal_shape"] == "transient"

    # The genuine mean shift on the healthy sensor remains in the healthy view.
    residual = events[
        (events["affected_sensors"] == "granulator_power")
        & (events["view"] == "healthy_only")
    ]
    assert len(residual) >= 1

    comparison = pd.read_parquet(out / io.RAW_VS_HEALTHY_FILE)
    assert {"drift_score_raw", "drift_score_healthy_only", "residual_drift"} <= set(
        comparison.columns
    )

    # Upstream fingerprint mismatch (synthetic shas) is a warn finding, not a
    # blocker — recorded in compat_checks and the findings JSON.
    assert manifest["compat_checks"]["anomaly_fingerprint_matches"] is False
    findings = json.loads((out / io.FINDINGS_JSON).read_text(encoding="utf-8"))
    assert "drift" in findings["findings_by_check"]
    types = {f["finding_type"] for f in findings["findings_by_check"]["drift"]}
    assert "upstream_dataset_mismatch" in types


def test_manifest_written_last_failed_run_not_resolvable(
    drift_world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = io.write_table

    def explode(frame: pd.DataFrame, path: Path) -> None:
        if path.name == io.RAW_VS_HEALTHY_FILE.name:
            raise OSError("disk full")
        original(frame, path)

    monkeypatch.setattr(io, "write_table", explode)
    with pytest.raises(OSError, match="disk full"):
        run_drift.main([*drift_world["args"], "--run-id", "crashed"])
    out_root = drift_world["out_root"]
    assert not (out_root / "runs" / "crashed" / io.MANIFEST_NAME).exists()
    with pytest.raises(FileNotFoundError):
        io.resolve_run(out_root, "latest", io.MANIFEST_NAME)


def test_dispatcher_registration(drift_world: dict[str, Any]) -> None:
    assert "drift" in _COMPONENTS
    assert (
        dispatcher_main(["--component", "drift", *drift_world["args"], "--no-write"])
        == 0
    )


def test_label_misalignment_is_a_blocker(drift_world: dict[str, Any]) -> None:
    labels = pd.read_parquet(drift_world["labels_path"]).iloc[:-5]
    labels.to_parquet(drift_world["labels_path"], index=False)
    with pytest.raises(run_drift.DriftBlockerError, match="does not match"):
        run_drift.main([*drift_world["args"], "--no-write"])


def test_incomplete_upstream_run_is_not_resolvable(
    drift_world: dict[str, Any],
) -> None:
    # Remove the anomaly manifest: the run becomes incomplete and resolution
    # must fail instead of consuming a half-written run.
    anomaly_manifest = (
        drift_world["tmp_path"]
        / "anomaly"
        / "runs"
        / "a1"
        / "anomaly_fit_manifest.json"
    )
    anomaly_manifest.unlink()
    with pytest.raises(FileNotFoundError, match="No completed runs"):
        run_drift.main([*drift_world["args"], "--no-write"])
