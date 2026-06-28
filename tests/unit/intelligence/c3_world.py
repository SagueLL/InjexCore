"""Synthetic upstream-run builders for Iteration C Part 3 tests.

Reference Governance and the Controlled Scoring Experiment both consume
completed upstream runs read-only. These helpers write tiny *completed* runs
(manifests last, the real on-disk layout) on a tmp_path, plus a synthetic
master + behaviour manifest, so the CLI tests drive the real components
without touching any real artifact and without training a model.

The synthetic world mirrors the real decisive case: ``inlet_hopper_points``
goes faulty from ``FAULT_START``; the anomaly mass, the sensor-fault incident,
the suppressed burst and the sensor-drift event all point at it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from src.intelligence._common.fingerprint import file_sha256

N_ROWS = 240
N_TRAIN = 168
FAULT_START = 180
SENSOR = "inlet_hopper_points"


def timestamps() -> pd.DatetimeIndex:
    return pd.date_range("2024-06-14 00:00:00", periods=N_ROWS, freq="1h")


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _manifest(run_dir: Path, name: str, payload: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    # Synthetic runs are *completed* runs: a valid manifest carries a run_id
    # matching its directory and completion_status == "complete" (ARC-02).
    payload = {"run_id": run_dir.name, "completion_status": "complete", **payload}
    (run_dir / name).write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )


def write_master(tmp: Path) -> tuple[Path, str]:
    """Tiny master parquet; returns ``(path, file_sha256)``."""
    ts = timestamps()
    df = pd.DataFrame({"timestamp": ts, "material_temp": 1.0, "granulator_power": 2.0})
    path = tmp / "master" / "master_dataset.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path, file_sha256(path)


def write_behaviour(tmp: Path, sha: str) -> Path:
    """A run-versioned *completed* behaviour run; returns the behaviour root.

    The manifest self-reports its ``run_id`` + ``master_dataset_sha256`` —
    the provenance Reference Governance seeds ``reference_v1`` from (GOV-01).
    """
    ts = timestamps()
    root = tmp / "behaviour"
    run = root / "runs" / "b1"
    run.mkdir(parents=True, exist_ok=True)
    (run / "behaviour_fit_manifest.json").write_text(
        json.dumps(
            {
                "component": "behaviour",
                "run_id": "b1",
                "completion_status": "complete",
                "created_at": "2026-01-01T00:00:00+00:00",
                "master_dataset_sha256": sha,
                "fit_timestamp": "2026-01-01T00:00:00+00:00",
                "fit_window": {
                    "strategy": "fraction",
                    "train_fraction": 0.7,
                    "n_train": N_TRAIN,
                    "n_total": N_ROWS,
                    "train_start": str(ts[0]),
                    "train_end": str(ts[N_TRAIN - 1]),
                },
                "train_window": {
                    "n_train": N_TRAIN,
                    "n_total": N_ROWS,
                    "train_start": str(ts[0]),
                    "train_end": str(ts[N_TRAIN - 1]),
                },
                "validation_window": {
                    "n_val": N_ROWS - N_TRAIN,
                    "val_start": str(ts[N_TRAIN]),
                    "val_end": str(ts[-1]),
                },
                "sensors": [SENSOR, "granulator_power"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return root


def write_sensor_health(tmp: Path, sha: str) -> Path:
    ts = timestamps()
    fault, end = ts[FAULT_START], ts[-1]
    run = tmp / "sensor_health" / "runs" / "s1"
    _write(
        pd.DataFrame(
            [
                {
                    "sensor_health_event_id": "SH-inlet_hopper_points-20240917T162322Z",
                    "sensor": SENSOR,
                    "start_timestamp": fault,
                    "end_timestamp": end,
                    "duration_rows": N_ROWS - FAULT_START,
                    "duration_seconds": float((end - fault).total_seconds()),
                    "status": "faulty",
                    "issue_types": "flatline_zero",
                    "max_health_score": 0.95,
                    "affected_profiles": "high_production",
                    "evidence": "{}",
                    "recommended_action": "quarantine_recommended",
                    "is_persistent": True,
                    "review_status": "pending_review",
                }
            ]
        ),
        run / "events" / "sensor_health_events.parquet",
    )
    _write(
        pd.DataFrame(
            [
                {
                    "sensor": SENSOR,
                    "start_timestamp": fault,
                    "end_timestamp": end,
                    "reason": "1 persistent faulty event(s) [flatline_zero]",
                    "issue_types": "flatline_zero",
                    "severity": "faulty",
                    "recommended_action": "quarantine_from_process_scoring",
                    "approval_required": True,
                    "approved": False,
                }
            ]
        ),
        run / "summaries" / "quarantine_recommendations.parquet",
    )
    _manifest(
        run,
        "sensor_health_manifest.json",
        {"component": "sensor_health", "run_id": "s1", "master_dataset_sha256": sha},
    )
    return run


SENSOR_FAULT_ID = "INC-sensor_fault-20240917T162322Z-1822"
BURST_ID = "INC-anomaly_burst-20240917T163000Z-5381"


def write_incidents(tmp: Path) -> Path:
    ts = timestamps()
    fault, end = ts[FAULT_START], ts[-1]
    run = tmp / "incidents" / "runs" / "i1"
    _write(
        pd.DataFrame(
            [
                {
                    "incident_id": SENSOR_FAULT_ID,
                    "incident_type": "sensor_fault",
                    "group_family": "flatline_zero",
                    "start_timestamp": fault,
                    "end_timestamp": end,
                    "duration_seconds": float((end - fault).total_seconds()),
                    "status": "persistent",
                    "severity": "critical",
                    "affected_sensors": SENSOR,
                    "affected_profiles": "high_production",
                    "contexts": "",
                    "n_members": 3,
                    "source_event_ids": "SH-inlet_hopper_points-20240917T162322Z",
                    "sources": "[]",
                    "is_persistent": True,
                    "evidence": "{}",
                    "review_status": "pending_review",
                },
                {
                    "incident_id": BURST_ID,
                    "incident_type": "anomaly_burst",
                    "group_family": "anomaly_burst",
                    "start_timestamp": fault,
                    "end_timestamp": end,
                    "duration_seconds": float((end - fault).total_seconds()),
                    "status": "persistent",
                    "severity": "anomaly",
                    "affected_sensors": SENSOR,
                    "affected_profiles": "high_production",
                    "contexts": "",
                    "n_members": 1,
                    "source_event_ids": "",
                    "sources": "[]",
                    "is_persistent": True,
                    "evidence": "{}",
                    "review_status": "pending_review",
                },
            ]
        ),
        run / "incidents" / "incidents.parquet",
    )
    _write(
        pd.DataFrame(
            [
                {
                    "incident_id": SENSOR_FAULT_ID,
                    "recommended_action": "quarantine_from_process_scoring",
                    "reason": '{"basis":"persistent_critical_sensor_fault"}',
                    "priority": "high",
                    "approval_required": True,
                    "approved": False,
                }
            ]
        ),
        run / "incidents" / "recommended_actions.parquet",
    )
    _write(
        pd.DataFrame(
            [
                {
                    "suppressed_incident_id": BURST_ID,
                    "suppressed_by_incident_id": SENSOR_FAULT_ID,
                    "reason": "burst_explained_by_sensor_fault",
                    "coverage": 0.9,
                    "incident_type": "anomaly_burst",
                    "start_timestamp": fault,
                    "end_timestamp": end,
                    "source_event_ids": "",
                    "evidence": "{}",
                }
            ]
        ),
        run / "incidents" / "suppressed_duplicate_events.parquet",
    )
    _manifest(
        run, "incidents_manifest.json", {"component": "incidents", "run_id": "i1"}
    )
    return run


def write_drift(tmp: Path, sha: str, n_residual: int = 3) -> Path:
    ts = timestamps()
    fault, end = ts[FAULT_START], ts[-1]
    run = tmp / "drift" / "runs" / "dr1"
    _write(
        pd.DataFrame(
            [
                {
                    "drift_event_id": "DR-sensor-inlet_hopper_points-high-x",
                    "scope": "sensor",
                    "view": "raw",
                    "drift_type": "sensor_drift",
                    "temporal_shape": "abrupt",
                    "start_timestamp": fault,
                    "end_timestamp": end,
                    "duration_seconds": float((end - fault).total_seconds()),
                    "status": "persistent",
                    "severity": "critical",
                    "affected_sensors": SENSOR,
                    "affected_profiles": "high_production",
                    "affected_contexts": "",
                    "supporting_metrics": "{}",
                    "evidence": "{}",
                    "is_persistent": True,
                    "review_status": "pending_review",
                }
            ]
        ),
        run / "events" / "drift_events.parquet",
    )
    n_windows = 12
    residual = [True] * n_residual + [False] * (n_windows - n_residual)
    _write(
        pd.DataFrame(
            {
                "window_start": list(ts[:n_windows]),
                "scope": "sensor",
                "entity": SENSOR,
                "profile": (["high_production"] * 6 + ["low_production"] * 6),
                "drift_score_raw": [0.9] * 6 + [0.4] * 6,
                "drift_score_healthy_only": [0.2] * 6 + [0.3] * 6,
                "delta": [0.7] * 6 + [0.1] * 6,
                "residual_drift": residual,
                "dominance": np.nan,
                "exclusion_reason": "",
            }
        ),
        run / "summaries" / "raw_vs_healthy_only_comparison.parquet",
    )
    _manifest(
        run,
        "drift_manifest.json",
        {"component": "drift", "run_id": "dr1", "master_dataset_sha256": sha},
    )
    return run


def write_anomaly(tmp: Path, sha: str) -> Path:
    ts = timestamps()
    run = tmp / "anomaly" / "runs" / "a1"
    post = np.arange(N_ROWS) >= FAULT_START
    severity = np.where(post, "anomaly", "normal")
    _write(
        pd.DataFrame(
            {
                "timestamp": ts,
                "profile": np.where(post, "high_production", "stopped"),
                "statistical_score": np.where(post, 0.9, 0.1),
                "mahalanobis_score": np.where(post, 0.8, 0.1),
                "pca_q_score": 0.1,
                "pca_t2_score": 0.1,
                "isolation_forest_score": 0.1,
                "combined_score": np.where(post, 0.9, 0.1),
                "severity": severity,
                "triggered_detectors": np.where(post, "statistical|mahalanobis", ""),
                "affected_variables": np.where(
                    post, "inlet_hopper_points|granulator_power", ""
                ),
                "evidence": "{}",
            }
        ),
        run / "scores" / "anomaly_scores.parquet",
    )
    _manifest(
        run,
        "anomaly_fit_manifest.json",
        {"component": "anomaly", "run_id": "a1", "master_dataset_sha256": sha},
    )
    return run


def write_operational(tmp: Path, sha: str) -> Path:
    ts = timestamps()
    run = tmp / "operational" / "runs" / "o1"
    post = np.arange(N_ROWS) >= FAULT_START
    _write(
        pd.DataFrame(
            {
                "timestamp": ts,
                "profile": np.where(post, "high_production", "stopped"),
                "is_train": np.arange(N_ROWS) < N_TRAIN,
                "steam_context": "steam_conditioning_off",
                "steam_context_confidence": 1.0,
                "steam_context_evidence": "{}",
                "sensor_health_context": np.where(
                    post, "sensor_faulty", "all_sensors_healthy"
                ),
                "faulty_sensors": np.where(post, SENSOR, ""),
                "warning_sensors": "",
                "quarantine_recommended_sensors": np.where(post, SENSOR, ""),
                "bom_context_status": "matched_single_order",
                "product_code": "P1",
                "recipe_context_key": "R1",
                "bom_signature": "S1",
                "context_key": "K1",
            }
        ),
        run / "timeline" / "operational_context_timeline.parquet",
    )
    _manifest(
        run,
        "operational_context_manifest.json",
        {
            "component": "operational_context",
            "run_id": "o1",
            "master_dataset_sha256": sha,
        },
    )
    return run


def write_reference_run(tmp: Path, sha: str, material: bool = False) -> Path:
    """A pre-baked *completed* reference governance run (for scoring tests)."""
    ts = timestamps()
    fault, end = ts[FAULT_START], ts[-1]
    run = tmp / "reference" / "runs" / "ref1"
    _write(
        pd.DataFrame(
            [
                {
                    "quarantine_proposal_id": "QP-inlet_hopper_points-20240917T162322Z",
                    "sensor": SENSOR,
                    "start_timestamp": fault,
                    "end_timestamp": end,
                    "status": "pending_review",
                    "reason": "flatline_zero",
                    "source_incident_ids": SENSOR_FAULT_ID,
                    "source_sensor_health_event_ids": "SH-x",
                    "source_drift_event_ids": "DR-x",
                    "recommended_action": "quarantine_from_process_scoring",
                    "approval_required": True,
                    "approved": False,
                    "risk_if_ignored": "x",
                    "risk_if_applied": "y",
                    "expected_effect": "z",
                    "review_status": "pending_review",
                }
            ]
        ),
        run / "quarantine_proposals.parquet",
    )
    _write(
        pd.DataFrame(
            [
                {
                    "proposal_id": "RP-quarantine_only",
                    "proposal_type": "quarantine_only",
                    "status": "pending_review",
                },
                {
                    "proposal_id": "RP-reference_candidate_v2",
                    "proposal_type": "reference_candidate_v2",
                    "status": "pending_review",
                },
                {
                    "proposal_id": "RP-external_records_review",
                    "proposal_type": "external_records_review",
                    "status": "pending_review",
                },
            ]
        ),
        run / "reference_proposals.parquet",
    )
    _manifest(
        run,
        "reference_governance_manifest.json",
        {
            "component": "reference_governance",
            "run_id": "ref1",
            "master_dataset_sha256": sha,
            "behaviour_run_id": "b1",
            "sensor_health_run_id": "s1",
            "drift_run_id": "dr1",
            "incidents_run_id": "i1",
            "residual_diagnostic": {
                "n_windows": 12,
                "n_residual_windows": 3,
                "residual_fraction": 0.25,
                "raw_mass": 7.8,
                "healthy_mass": 3.0,
                "reduction_pct": 61.5,
                "material": material,
            },
        },
    )
    return run
