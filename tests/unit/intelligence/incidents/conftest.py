"""Fixtures for the Incident Aggregation unit tests.

``incidents_world`` writes five tiny *completed* upstream runs (manifests
last) on tmp_path — a synthetic drift run, sensor-health run, anomaly run,
operational-context run and BOM run — so run-level tests drive the real CLI
without touching any real artifact. ``candidate_factory`` builds normalized
candidate rows for the grouping/suppression unit tests.
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
from src.intelligence.incidents.policy import IncidentsPolicy, load_policy
from src.intelligence.incidents.sources import CANDIDATE_COLUMNS

N_ROWS = 360
FAULT_START = 240  # inlet flatline + anomaly burst from here


@pytest.fixture(scope="session")
def incidents_policy() -> IncidentsPolicy:
    """Real policy loaded from configs/incidents_intelligence.yaml."""
    return load_policy(PROJECT_ROOT / "configs" / "incidents_intelligence.yaml")


@pytest.fixture
def policy_factory() -> Callable[..., IncidentsPolicy]:
    def _make(**overrides: Any) -> IncidentsPolicy:
        return IncidentsPolicy.model_validate(overrides)

    return _make


@pytest.fixture
def candidate_factory() -> Callable[..., pd.DataFrame]:
    """Build a normalized candidate frame from compact row specs."""

    def _make(rows: list[dict[str, Any]]) -> pd.DataFrame:
        defaults = {
            "source": "drift",
            "source_event_id": "E",
            "candidate_type": "process_drift",
            "group_family": "sensor:process_drift",
            "severity": "warning",
            "affected_sensors": "",
            "affected_profiles": "",
            "contexts": "",
            "is_persistent": False,
            "evidence": "{}",
        }
        full = []
        for i, row in enumerate(rows):
            merged = {**defaults, "source_event_id": f"E{i}", **row}
            merged["start_timestamp"] = pd.Timestamp(merged["start_timestamp"])
            merged["end_timestamp"] = pd.Timestamp(merged["end_timestamp"])
            full.append(merged)
        return pd.DataFrame(full, columns=CANDIDATE_COLUMNS)

    return _make


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _manifest(run_dir: Path, name: str, payload: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / name).write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )


@pytest.fixture
def incidents_world(tmp_path: Path) -> dict[str, Any]:
    """Five tiny completed upstream runs + a config pinned to them."""
    ts = pd.date_range("2024-09-01", periods=N_ROWS, freq="1min")
    fault_start, data_end = ts[FAULT_START], ts[-1]

    drift_run = tmp_path / "drift" / "runs" / "d1"
    _write(
        pd.DataFrame(
            [
                {
                    "drift_event_id": "DR-sensor-inlet_hopper_points-x-SH",
                    "scope": "sensor",
                    "view": "raw",
                    "drift_type": "sensor_drift",
                    "temporal_shape": "abrupt",
                    "start_timestamp": fault_start,
                    "end_timestamp": data_end,
                    "duration_seconds": float((data_end - fault_start).total_seconds()),
                    "status": "persistent",
                    "severity": "critical",
                    "affected_sensors": "inlet_hopper_points",
                    "affected_profiles": "mid_production",
                    "affected_contexts": "",
                    "supporting_metrics": "{}",
                    "evidence": "{}",
                    "is_persistent": True,
                    "review_status": "pending_review",
                },
                {
                    "drift_event_id": "DR-sensor-granulator_power-healthy",
                    "scope": "sensor",
                    "view": "healthy_only",
                    "drift_type": "process_drift",
                    "temporal_shape": "progressive",
                    "start_timestamp": ts[250],
                    "end_timestamp": ts[330],
                    "duration_seconds": float((ts[330] - ts[250]).total_seconds()),
                    "status": "resolved",
                    "severity": "anomaly",
                    "affected_sensors": "granulator_power",
                    "affected_profiles": "mid_production",
                    "affected_contexts": "",
                    "supporting_metrics": '{"psi":0.9}',
                    "evidence": "{}",
                    "is_persistent": False,
                    "review_status": "pending_review",
                },
            ]
        ),
        drift_run / "events" / "drift_events.parquet",
    )
    _write(
        pd.DataFrame(
            {
                "window_start": ts[::60],
                "scope": "sensor",
                "entity": "inlet_hopper_points",
                "profile": "__global__",
                "drift_score_raw": [0.1, 0.1, 0.1, 0.1, 0.9, 0.9],
                "drift_score_healthy_only": [0.1, 0.1, 0.1, 0.1, 0.0, 0.0],
                "delta": [0.0, 0.0, 0.0, 0.0, 0.9, 0.9],
                "residual_drift": False,
                "dominance": np.nan,
                "exclusion_reason": "",
            }
        ),
        drift_run / "summaries" / "raw_vs_healthy_only_comparison.parquet",
    )
    _manifest(
        drift_run,
        "drift_manifest.json",
        {
            "component": "drift",
            "run_id": "d1",
            "upstream": {
                "sensor_health_run_id": "s1",
                "anomaly_run_id": "a1",
                "operational_context_run_id": "o1",
            },
            "validation_window": {"start": str(ts[180]), "end": str(data_end)},
            "window_config": {"granularity": "hourly"},
        },
    )

    sensor_health_run = tmp_path / "sensor_health" / "runs" / "s1"
    _write(
        pd.DataFrame(
            [
                {
                    "sensor_health_event_id": "SH-inlet-1",
                    "sensor": "inlet_hopper_points",
                    "start_timestamp": fault_start,
                    "end_timestamp": data_end,
                    "duration_rows": N_ROWS - FAULT_START,
                    "duration_seconds": float((data_end - fault_start).total_seconds()),
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
                    "sensor_health_event_id": "SH-roller-2",
                    "sensor": "granulator_roller_gap",
                    "start_timestamp": ts[60],
                    "end_timestamp": ts[90],
                    "duration_rows": 30,
                    "duration_seconds": float((ts[90] - ts[60]).total_seconds()),
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
        ),
        sensor_health_run / "events" / "sensor_health_events.parquet",
    )
    _write(
        pd.DataFrame(
            [
                {
                    "sensor": "inlet_hopper_points",
                    "start_timestamp": fault_start,
                    "end_timestamp": data_end,
                    "reason": "flatline_zero",
                    "issue_types": "flatline_zero",
                    "severity": "critical",
                    "recommended_action": "quarantine_from_process_scoring",
                    "approval_required": True,
                    "approved": False,
                }
            ]
        ),
        sensor_health_run / "summaries" / "quarantine_recommendations.parquet",
    )
    _manifest(
        sensor_health_run,
        "sensor_health_manifest.json",
        {"component": "sensor_health", "run_id": "s1"},
    )

    anomaly_run = tmp_path / "anomaly" / "runs" / "a1"
    severity = np.where(np.arange(N_ROWS) >= FAULT_START, "anomaly", "normal")
    _write(
        pd.DataFrame(
            {
                "timestamp": ts,
                "profile": "mid_production",
                "combined_score": np.where(severity == "anomaly", 0.9, 0.1),
                "severity": severity,
                "triggered_detectors": np.where(
                    severity == "anomaly", "statistical|mahalanobis", ""
                ),
                "affected_variables": np.where(
                    severity == "anomaly", "inlet_hopper_points|other", ""
                ),
                "evidence": "{}",
            }
        ),
        anomaly_run / "scores" / "anomaly_scores.parquet",
    )
    _manifest(
        anomaly_run,
        "anomaly_fit_manifest.json",
        {"component": "anomaly", "run_id": "a1"},
    )

    operational_run = tmp_path / "operational" / "runs" / "o1"
    _write(
        pd.DataFrame(
            {
                "timestamp": ts,
                "profile": "mid_production",
                "is_train": np.arange(N_ROWS) < 180,
                "steam_context": np.where(
                    np.arange(N_ROWS) < 300,
                    "steam_conditioning_off",
                    "steam_conditioning_on",
                ),
                "sensor_health_context": np.where(
                    np.arange(N_ROWS) >= FAULT_START,
                    "sensor_faulty",
                    "all_sensors_healthy",
                ),
                "faulty_sensors": np.where(
                    np.arange(N_ROWS) >= FAULT_START, "inlet_hopper_points", ""
                ),
                "warning_sensors": "",
                "quarantine_recommended_sensors": "",
                "bom_context_status": "matched_single_order",
                "product_code": "P1",
                "recipe_context_key": "R1",
                "bom_signature": "S1",
            }
        ),
        operational_run / "timeline" / "operational_context_timeline.parquet",
    )
    _write(
        pd.DataFrame(
            [
                {
                    "transition_timestamp": ts[300],
                    "previous_profile": "mid_production",
                    "new_profile": "mid_production",
                    "previous_steam_context": "steam_conditioning_off",
                    "new_steam_context": "steam_conditioning_on",
                    "previous_sensor_health_context": "all_sensors_healthy",
                    "new_sensor_health_context": "all_sensors_healthy",
                    "previous_product_code": "P1",
                    "new_product_code": "P1",
                    "transition_types": "steam_context_change",
                }
            ]
        ),
        operational_run / "transitions" / "context_transition_events.parquet",
    )
    _manifest(
        operational_run,
        "operational_context_manifest.json",
        {"component": "operational_context", "run_id": "o1"},
    )

    bom_run = tmp_path / "bom" / "runs" / "b1"
    _write(
        pd.DataFrame(
            [
                {
                    "transition_timestamp": ts[120],
                    "previous_order_id": "O1",
                    "next_order_id": "O2",
                    "previous_product_code": "P1",
                    "next_product_code": "P1",
                    "previous_recipe_context_key": "R1",
                    "next_recipe_context_key": "R1",
                    "transition_type": "order_change",
                }
            ]
        ),
        bom_run / "orders" / "bom_order_transitions.parquet",
    )
    _manifest(
        bom_run, "bom_context_manifest.json", {"component": "bom", "run_id": "b1"}
    )

    config_path = tmp_path / "incidents.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "upstream": {
                    "drift_root": (tmp_path / "drift").as_posix(),
                    "drift_run": "latest",
                    "sensor_health_root": (tmp_path / "sensor_health").as_posix(),
                    "sensor_health_run": "latest",
                    "anomaly_root": (tmp_path / "anomaly").as_posix(),
                    "anomaly_run": "latest",
                    "operational_root": (tmp_path / "operational").as_posix(),
                    "operational_run": "latest",
                    "bom_root": (tmp_path / "bom").as_posix(),
                    "bom_run": "latest",
                },
                "bursts": {"min_duration_minutes": 30},
            }
        ),
        encoding="utf-8",
    )
    out_root = tmp_path / "incidents_out"
    addendum_root = tmp_path / "drift_addenda"
    return {
        "tmp_path": tmp_path,
        "config_path": config_path,
        "out_root": out_root,
        "addendum_root": addendum_root,
        "timestamps": ts,
        "fault_start": fault_start,
        "args": [
            "--config",
            str(config_path),
            "--output-root",
            str(out_root),
            "--addendum-root",
            str(addendum_root),
        ],
    }
