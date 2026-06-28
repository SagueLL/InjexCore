"""Human Decision Overlay — run-versioning, schema and state-separation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from src.intelligence.human_decisions import decision, io
from src.intelligence.human_decisions import run_human_decision_overlay as run_cli


def _run(tmp_path: Path, *extra: str) -> tuple[int, Path]:
    """Run the CLI into a tmp output root with no master (verification skipped)."""
    out_root = tmp_path / "out"
    rc = run_cli.main(
        [
            "--output-root",
            str(out_root),
            "--master-path",
            str(tmp_path / "absent.parquet"),
            *extra,
        ]
    )
    return rc, out_root


def _run_dir(out_root: Path) -> Path:
    children = list(out_root.iterdir())
    assert len(children) == 1, f"expected one run dir, got {children}"
    return children[0]


def test_no_write_creates_nothing(tmp_path: Path) -> None:
    rc, out_root = _run(tmp_path, "--no-write")
    assert rc == 0
    assert not out_root.exists()


def test_full_run_writes_all_files(tmp_path: Path) -> None:
    rc, out_root = _run(tmp_path)
    assert rc == 0
    run = _run_dir(out_root)
    assert run.name.startswith(io.RUN_ID_PREFIX)
    for name in (
        io.SENSOR_DECISIONS_FILE,
        io.DASHBOARD_OVERLAY_FILE,
        io.ADJUSTED_REVIEW_FILE,
        io.FOLLOWUP_RECORDS_FILE,
        io.SUMMARY_MD,
        io.MANIFEST_NAME,
    ):
        assert (run / name).exists(), f"missing {name}"


def test_manifest_completion_and_decision_flags(tmp_path: Path) -> None:
    _, out_root = _run(tmp_path)
    manifest = json.loads((_run_dir(out_root) / io.MANIFEST_NAME).read_text("utf-8"))
    assert manifest["completion_status"] == "complete"
    assert manifest["component"] == io.COMPONENT
    assert manifest["reference_v2_decision"] == "deferred"
    assert manifest["refit_approved"] is False
    assert manifest["automatic_production_action_approved"] is False
    assert manifest["artifact_mutation_performed"] is False
    assert manifest["score_mutation_performed"] is False
    assert manifest["pipeline_quarantine_applied"] is False
    assert (
        manifest["human_decision"] == "approve_scoped_quarantine_from_row_137235_onward"
    )
    assert manifest["human_reported_row"] == 137237
    # generated_files lists the artifacts (manifest itself is written last,
    # after this field is serialized — repo convention).
    assert set(manifest["generated_files"]) == {
        io.SENSOR_DECISIONS_FILE,
        io.DASHBOARD_OVERLAY_FILE,
        io.ADJUSTED_REVIEW_FILE,
        io.FOLLOWUP_RECORDS_FILE,
        io.SUMMARY_MD,
    }
    # Source provenance points at the reference_decision run, not a mutation.
    assert manifest["source_human_review_report"] == decision.APPROVAL_SOURCE
    assert decision.CANONICAL_RUN_ID in manifest["source_reference_decision_dir"]


def test_decision_row_schema_and_realigned_boundary(tmp_path: Path) -> None:
    _, out_root = _run(tmp_path)
    df = pd.read_parquet(_run_dir(out_root) / io.SENSOR_DECISIONS_FILE)
    assert len(df) == 1
    row = df.iloc[0]
    required = {
        "decision_id",
        "decision_type",
        "target_sensor",
        "human_decision",
        "decision_status",
        "scope_type",
        "scope_start_row",
        "scope_start_timestamp",
        "scope_end_row",
        "scope_end_timestamp",
        "applies_from_boundary_onward",
        "approved_by",
        "approval_source",
        "canonical_run_id",
        "reference_decision_run_id",
        "bom_run_id",
        "artifact_state_approval_required",
        "artifact_state_approved",
        "applied_pipeline_state",
        "dashboard_overlay_state",
        "requires_refit",
        "requires_reference_v2",
        "requires_plant_records_before_customer_claims",
        "physical_root_cause_confirmed",
        "timestamp_mapping_status",
        "system_detected_onset_timestamp",
    }
    assert required <= set(df.columns)
    # Boundary realigned to the detected onset; human-reported row preserved.
    assert int(row["scope_start_row"]) == 137235
    assert int(row["human_reported_row"]) == 137237
    assert row["scope_start_timestamp"] == decision.DETECTED_ONSET_TIMESTAMP
    assert row["timestamp_mapping_status"] == "realigned_to_detected_onset"
    # Decision posture.
    assert row["human_decision"] == "approve_scoped_quarantine"
    assert bool(row["artifact_state_approval_required"]) is True
    assert bool(row["artifact_state_approved"]) is False
    assert row["applied_pipeline_state"] == "not_applied"
    assert bool(row["requires_refit"]) is False
    assert bool(row["requires_reference_v2"]) is False
    assert bool(row["physical_root_cause_confirmed"]) is False


def test_dashboard_overlay_states_distinct_and_actions(tmp_path: Path) -> None:
    _, out_root = _run(tmp_path)
    row = pd.read_parquet(_run_dir(out_root) / io.DASHBOARD_OVERLAY_FILE).iloc[0]
    states = {
        row["artifact_state"],
        row["human_review_state"],
        row["applied_pipeline_state"],
        row["dashboard_overlay_state"],
    }
    assert len(states) == 4  # all four states are distinct
    forbidden = row["forbidden_dashboard_actions"]
    for token in decision.FORBIDDEN_DASHBOARD_ACTIONS:
        assert token in forbidden
    assert "view_evidence" in row["allowed_dashboard_actions"]
    # No approval/apply/refit action is offered as allowed.
    for banned in ("approve_quarantine", "apply_quarantine", "run_refit"):
        assert banned not in row["allowed_dashboard_actions"]
    assert row["dashboard_warning"] == decision.DASHBOARD_WARNING


def test_followup_records(tmp_path: Path) -> None:
    _, out_root = _run(tmp_path)
    df = pd.read_parquet(_run_dir(out_root) / io.FOLLOWUP_RECORDS_FILE)
    assert len(df) == 7
    assert set(df["required_before"]) == {"operational_or_customer_facing_claims"}
    assert set(df["status"]) == {"missing_external_record"}


def test_adjusted_review_summary(tmp_path: Path) -> None:
    _, out_root = _run(tmp_path)
    row = pd.read_parquet(_run_dir(out_root) / io.ADJUSTED_REVIEW_FILE).iloc[0]
    assert int(row["non_normal_rows"]) == 33186
    assert int(row["suppressed_rows"]) == 30096
    assert bool(row["residual_material"]) is False


def test_run_id_unique_no_overwrite(tmp_path: Path) -> None:
    out_root = tmp_path / "out"
    run_cli.main(
        [
            "--output-root",
            str(out_root),
            "--master-path",
            str(tmp_path / "x"),
            "--run-id",
            "fixed",
        ]
    )
    with pytest.raises(FileExistsError):
        run_cli.main(
            [
                "--output-root",
                str(out_root),
                "--master-path",
                str(tmp_path / "x"),
                "--run-id",
                "fixed",
            ]
        )


def test_manifest_written_last_on_failure(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    spec = decision.make_spec(
        canonical_run_id=decision.CANONICAL_RUN_ID,
        bom_run_id=decision.BOM_RUN_ID,
        reference_decision_run_id=decision.CANONICAL_RUN_ID,
        target_sensor=decision.TARGET_SENSOR,
        scope_start_row=decision.DETECTED_ONSET_ROW,
        human_reported_row=decision.HUMAN_REPORTED_ROW,
    )
    art = decision.build_overlay(spec, "run-x", "2026-06-17T00:00:00+00:00", "skipped")
    out = tmp_path / "run-x"
    out.mkdir()

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(decision.io, "write_table", boom)
    with pytest.raises(OSError, match="disk full"):
        decision.write_overlay(art, out)
    assert not (out / io.MANIFEST_NAME).exists()


def test_make_spec_realignment_and_override() -> None:
    realigned = decision.make_spec(
        canonical_run_id="c",
        bom_run_id="b",
        reference_decision_run_id="c",
        target_sensor="inlet_hopper_points",
        scope_start_row=137235,
        human_reported_row=137237,
    )
    assert realigned.timestamp_mapping_status == "realigned_to_detected_onset"
    assert realigned.scope_start_timestamp == decision.DETECTED_ONSET_TIMESTAMP

    other = decision.make_spec(
        canonical_run_id="c",
        bom_run_id="b",
        reference_decision_run_id="c",
        target_sensor="inlet_hopper_points",
        scope_start_row=999,
        human_reported_row=137237,
    )
    assert other.timestamp_mapping_status == "not_reconciled"
    assert other.scope_start_timestamp is None


@pytest.mark.parametrize(
    ("value", "row", "expected"),
    [(0.0, 2, "verified"), (5.0, 2, "mismatch"), (0.0, 99, "error")],
)
def test_verify_boundary(value: float, row: int, expected: str) -> None:
    master = pd.DataFrame(
        {
            "timestamp": [
                "2024-09-17 16:21:22.0",
                "2024-09-17 16:22:22.0",
                "2024-09-17 16:23:22.187",
                "2024-09-17 16:24:22.0",
            ],
            "inlet_hopper_points": [1.0, 1.0, value, value],
        }
    )
    spec = decision.HumanDecisionSpec(system_detected_onset_row=row)
    assert decision.verify_boundary(master, spec).startswith(expected)


def test_verify_boundary_skipped_without_master() -> None:
    spec = decision.HumanDecisionSpec()
    assert decision.verify_boundary(None, spec).startswith("skipped")
