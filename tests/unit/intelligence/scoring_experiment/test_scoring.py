"""Controlled Scoring Experiment unit tests.

Covers the four scenarios, suppression + dominant-faulty-sensor logic,
original-severity immutability, scenario comparison + recommendations,
manifest-written-last, ``--no-write`` and dispatcher registration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from src.intelligence.__main__ import _COMPONENTS
from src.intelligence.__main__ import main as dispatcher_main
from src.intelligence.scoring_experiment import io, run_scoring_experiment, validation

from tests.unit.intelligence import c3_world


def _run(world: dict[str, Any], run_id: str = "sc1") -> Path:
    assert run_scoring_experiment.main([*world["args"], "--run-id", run_id]) == 0
    return world["out_root"] / "runs" / run_id


def test_four_scenarios_defined(scoring_world: dict[str, Any]) -> None:
    run = _run(scoring_world)
    defs = pd.read_parquet(run / io.SCENARIO_DEFINITIONS_FILE)
    assert set(defs["scenario_id"]) == {
        "baseline_v1",
        "quarantine_inlet_hopper_points_interpretive",
        "healthy_only_proxy",
        "candidate_reference_needed",
    }
    assert not defs["mutates_original_scores"].any()


def test_baseline_severity_immutable(scoring_world: dict[str, Any]) -> None:
    run = _run(scoring_world)
    ss = pd.read_parquet(run / io.SCENARIO_SCORES_FILE)
    baseline = ss[ss["scenario_id"] == "baseline_v1"]
    # Baseline never adjusts; original == adjusted, nothing suppressed.
    assert (baseline["original_severity"] == baseline["adjusted_review_severity"]).all()
    assert not baseline["suppressed_for_review"].any()
    # adjusted_review_score equals original_combined_score everywhere (no rescore).
    assert (ss["adjusted_review_score"] == ss["original_combined_score"]).all()


def test_quarantine_suppression_dominant_sensor(scoring_world: dict[str, Any]) -> None:
    run = _run(scoring_world)
    ss = pd.read_parquet(run / io.SCENARIO_SCORES_FILE)
    quar = ss[ss["scenario_id"] == "quarantine_inlet_hopper_points_interpretive"]
    suppressed = quar[quar["suppressed_for_review"]]
    assert len(suppressed) > 0
    # Every suppressed row is attributed to the faulty sensor and downgraded.
    assert set(suppressed["dominant_faulty_sensor"]) == {"inlet_hopper_points"}
    assert set(suppressed["adjusted_review_severity"]) == {"normal"}
    # Original severity is preserved on the suppressed rows.
    assert (suppressed["original_severity"] != "normal").all()


def test_anomaly_rate_comparison(scoring_world: dict[str, Any]) -> None:
    run = _run(scoring_world)
    rates = pd.read_parquet(run / io.ANOMALY_RATE_COMPARISON_FILE)
    quar = rates[
        rates["scenario_id"] == "quarantine_inlet_hopper_points_interpretive"
    ].iloc[0]
    base = rates[rates["scenario_id"] == "baseline_v1"].iloc[0]
    assert quar["suppressed_count"] > 0
    assert quar["adjusted_anomaly_count"] < base["original_anomaly_count"]
    assert base["suppressed_count"] == 0


def test_recommendations_defer_v2_when_immaterial(
    scoring_world: dict[str, Any],
) -> None:
    run = _run(scoring_world)
    recs = pd.read_parquet(run / io.RECOMMENDATIONS_FILE)
    v2 = recs[recs["scenario_id"] == "candidate_reference_needed"].iloc[0]
    assert v2["recommendation"] == "defer_reference_v2"
    quar = recs[
        recs["scenario_id"] == "quarantine_inlet_hopper_points_interpretive"
    ].iloc[0]
    assert bool(quar["requires_human_approval"]) is True


def test_decision_report_written(scoring_world: dict[str, Any]) -> None:
    run = _run(scoring_world)
    manifest = json.loads((run / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["completion_status"] == "complete"
    assert manifest["decision_report_status"] == "complete"
    decision_dir = scoring_world["decision_root"] / "sc1"
    matrix = pd.read_parquet(decision_dir / "decision_matrix.parquet")
    assert set(matrix["action"]) >= {
        "approve_quarantine_inlet_hopper_points",
        "design_reference_candidate_v2",
        "collect_plant_records",
    }
    # Quarantine approval still requires a human; v2 not recommended (immaterial).
    approve = matrix[matrix["action"] == "approve_quarantine_inlet_hopper_points"].iloc[
        0
    ]
    assert bool(approve["requires_human_approval"]) is True
    v2 = matrix[matrix["action"] == "design_reference_candidate_v2"].iloc[0]
    assert bool(v2["recommended"]) is False
    dman = json.loads(
        (decision_dir / io.DECISION_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert dman["completion_status"] == "complete"


def test_skip_decision_report(scoring_world: dict[str, Any]) -> None:
    assert (
        run_scoring_experiment.main(
            [*scoring_world["args"], "--run-id", "nodec", "--skip-decision-report"]
        )
        == 0
    )
    assert not (scoring_world["decision_root"] / "nodec").exists()
    manifest = json.loads(
        (scoring_world["out_root"] / "runs" / "nodec" / io.MANIFEST_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert manifest["decision_report_status"] == "skipped"


def test_no_write_writes_nothing(scoring_world: dict[str, Any]) -> None:
    assert run_scoring_experiment.main([*scoring_world["args"], "--no-write"]) == 0
    assert not scoring_world["out_root"].exists()
    assert not scoring_world["decision_root"].exists()


def test_manifest_written_last_failed_run_not_resolvable(
    scoring_world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = io.write_table

    def explode(frame: pd.DataFrame, path: Path) -> None:
        if path.name == io.RECOMMENDATIONS_FILE:
            raise OSError("disk full")
        original(frame, path)

    monkeypatch.setattr(io, "write_table", explode)
    with pytest.raises(OSError, match="disk full"):
        run_scoring_experiment.main([*scoring_world["args"], "--run-id", "crashed"])
    out_root = scoring_world["out_root"]
    assert not (out_root / "runs" / "crashed" / io.MANIFEST_NAME).exists()
    with pytest.raises(FileNotFoundError):
        io.resolve_run(out_root, "latest", io.MANIFEST_NAME)


def test_dispatcher_registration(scoring_world: dict[str, Any]) -> None:
    assert "scoring-experiment" in _COMPONENTS
    assert (
        dispatcher_main(
            ["--component", "scoring-experiment", *scoring_world["args"], "--no-write"]
        )
        == 0
    )


def test_material_residual_recommends_v2(scoring_world: dict[str, Any]) -> None:
    """End-to-end: a material residual surfaces design_reference_v2 + refit."""
    # Overwrite the pre-baked reference run so its residual is material.
    c3_world.write_reference_run(
        scoring_world["tmp_path"], scoring_world["sha"], material=True
    )
    run = _run(scoring_world, "mat")
    recs = pd.read_parquet(run / io.RECOMMENDATIONS_FILE)
    v2 = recs[recs["scenario_id"] == "candidate_reference_needed"].iloc[0]
    assert v2["recommendation"] == "design_reference_v2"
    assert bool(v2["requires_model_refit"]) is True
    matrix = pd.read_parquet(
        scoring_world["decision_root"] / "mat" / "decision_matrix.parquet"
    )
    design = matrix[matrix["action"] == "design_reference_candidate_v2"].iloc[0]
    assert bool(design["recommended"]) is True
    # Approval is still required even when v2 is recommended — never automatic.
    assert bool(design["requires_human_approval"]) is True


def test_gate_a_blocks_misaligned_timelines() -> None:
    """Anomaly + operational timelines must be row-aligned or the run stops."""
    anomaly = pd.DataFrame(
        {"severity": ["normal"]}, index=pd.date_range("2024-01-01", periods=1, freq="h")
    )
    op = pd.DataFrame(
        {"profile": ["stopped"]},
        index=pd.date_range("2024-02-01", periods=1, freq="h"),
    )
    with pytest.raises(validation.ScoringBlockerError, match="row-aligned"):
        validation.validate_upstream("sha", anomaly, op, {}, {})
