"""Iteration C Part 3 chain: governance → controlled scoring → decision report.

Builds synthetic *completed* upstream runs (sensor-health + drift + incidents
+ anomaly + operational), runs the real Reference Governance CLI, then feeds
its persisted reference run into the real Controlled Scoring Experiment CLI,
and asserts the decision report falls out. No model is trained; the chain
consumes only persisted artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml
from src.intelligence.reference import io as ref_io
from src.intelligence.reference import run_reference
from src.intelligence.scoring_experiment import io as sc_io
from src.intelligence.scoring_experiment import run_scoring_experiment

from tests.unit.intelligence import c3_world


def _reference_config(tmp: Path, master_path: Path, behaviour_root: Path) -> Path:
    path = tmp / "reference_governance.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "upstream": {
                    "sensor_health_root": (tmp / "sensor_health").as_posix(),
                    "incidents_root": (tmp / "incidents").as_posix(),
                    "drift_root": (tmp / "drift").as_posix(),
                    "behaviour_root": behaviour_root.as_posix(),
                    "behaviour_run": "latest",
                    "master_path": master_path.as_posix(),
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _scoring_config(tmp: Path, master_path: Path, reference_root: Path) -> Path:
    path = tmp / "scoring_experiment.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "upstream": {
                    "anomaly_root": (tmp / "anomaly").as_posix(),
                    "sensor_health_root": (tmp / "sensor_health").as_posix(),
                    "drift_root": (tmp / "drift").as_posix(),
                    "incidents_root": (tmp / "incidents").as_posix(),
                    "operational_root": (tmp / "operational").as_posix(),
                    "reference_root": reference_root.as_posix(),
                    "master_path": master_path.as_posix(),
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def test_governance_to_scoring_to_decision(tmp_path: Path) -> None:
    master_path, sha = c3_world.write_master(tmp_path)
    behaviour_root = c3_world.write_behaviour(tmp_path, sha)
    c3_world.write_sensor_health(tmp_path, sha)
    c3_world.write_incidents(tmp_path)
    c3_world.write_drift(tmp_path, sha)
    c3_world.write_anomaly(tmp_path, sha)
    c3_world.write_operational(tmp_path, sha)

    # --- 1. Reference Governance produces a real reference run.
    reference_root = tmp_path / "reference_out"
    ref_config = _reference_config(tmp_path, master_path, behaviour_root)
    assert (
        run_reference.main(
            [
                "--config",
                str(ref_config),
                "--output-root",
                str(reference_root),
                "--run-id",
                "ref",
            ]
        )
        == 0
    )
    quarantine = pd.read_parquet(
        reference_root / "runs" / "ref" / ref_io.QUARANTINE_FILE
    )
    assert quarantine.iloc[0]["sensor"] == "inlet_hopper_points"
    assert bool(quarantine.iloc[0]["approved"]) is False

    # --- 2. Controlled Scoring Experiment consumes that reference run.
    scoring_root = tmp_path / "scoring_out"
    decision_root = tmp_path / "reference_decision"
    sc_config = _scoring_config(tmp_path, master_path, reference_root)
    assert (
        run_scoring_experiment.main(
            [
                "--config",
                str(sc_config),
                "--output-root",
                str(scoring_root),
                "--decision-root",
                str(decision_root),
                "--run-id",
                "sc",
            ]
        )
        == 0
    )

    # --- 3. Scenario scores: original immutable, quarantine rows suppressed.
    ss = pd.read_parquet(scoring_root / "runs" / "sc" / sc_io.SCENARIO_SCORES_FILE)
    quar = ss[ss["scenario_id"] == "quarantine_inlet_hopper_points_interpretive"]
    assert quar["row_suppressed_for_review"].any()
    assert set(quar[quar["row_suppressed_for_review"]]["dominant_faulty_sensor"]) == {
        "inlet_hopper_points"
    }

    # --- 4. Decision report exists and approves nothing automatically.
    decision_dir = decision_root / "sc"
    matrix = pd.read_parquet(decision_dir / "decision_matrix.parquet")
    approve = matrix[matrix["action"] == "approve_quarantine_inlet_hopper_points"].iloc[
        0
    ]
    assert bool(approve["requires_human_approval"]) is True
    dman = json.loads(
        (decision_dir / sc_io.DECISION_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert dman["completion_status"] == "complete"
    assert dman["residual_material"] is False

    # --- 5. The scoring manifest records its lineage to the reference run.
    manifest = json.loads(
        (scoring_root / "runs" / "sc" / sc_io.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert manifest["reference_run_id"] == "ref"
    assert manifest["decision_report_status"] == "complete"
