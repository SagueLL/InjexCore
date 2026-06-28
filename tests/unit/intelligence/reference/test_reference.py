"""Reference Governance unit tests.

Covers registry seeding, quarantine + candidate proposals, statuses,
approval defaults, the decision log, manifest-written-last, ``--no-write``,
dispatcher registration and the no-automatic-approval invariant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from src.intelligence.__main__ import _COMPONENTS
from src.intelligence.__main__ import main as dispatcher_main
from src.intelligence.reference import io, proposals, run_reference, validation


def _run(world: dict[str, Any], run_id: str = "r1") -> Path:
    assert run_reference.main([*world["args"], "--run-id", run_id]) == 0
    return world["out_root"] / "runs" / run_id


def test_registry_seeds_reference_v1(reference_world: dict[str, Any]) -> None:
    run = _run(reference_world)
    registry = pd.read_parquet(run / io.REGISTRY_FILE)
    assert list(registry["reference_id"]) == ["reference_v1"]
    row = registry.iloc[0]
    assert row["reference_type"] == "baseline"
    assert row["status"] == "current"
    assert row["excluded_sensors"] == ""
    assert row["dataset_sha256"] == reference_world["master_sha256"]
    assert "2024-06-14" in str(row["source_train_start"])


def test_quarantine_proposal_not_approved(reference_world: dict[str, Any]) -> None:
    run = _run(reference_world)
    q = pd.read_parquet(run / io.QUARANTINE_FILE)
    assert len(q) == 1
    row = q.iloc[0]
    assert row["sensor"] == "inlet_hopper_points"
    assert bool(row["approval_required"]) is True
    assert bool(row["approved"]) is False
    assert row["review_status"] == "pending_review"
    assert row["recommended_action"] == "quarantine_from_process_scoring"
    # Source ids are wired from the upstream evidence, not fabricated.
    assert "INC-sensor_fault" in row["source_incident_ids"]


def test_three_candidate_proposals_pending(reference_world: dict[str, Any]) -> None:
    run = _run(reference_world)
    p = pd.read_parquet(run / io.PROPOSALS_FILE)
    assert set(p["proposal_type"]) == {
        "quarantine_only",
        "reference_candidate_v2",
        "external_records_review",
    }
    assert set(p["status"]) == {"pending_review"}
    v2 = p[p["proposal_type"] == "reference_candidate_v2"].iloc[0]
    assert bool(v2["model_refit_required"]) is True
    # Candidate train window is never fabricated.
    assert v2["proposed_train_start"] == ""
    assert "candidate design only" in v2["evidence_summary"].lower()


def test_decision_log_all_pending(reference_world: dict[str, Any]) -> None:
    run = _run(reference_world)
    log = pd.read_parquet(run / io.DECISION_LOG_FILE)
    assert len(log) == 4  # 3 reference proposals + 1 quarantine proposal
    assert set(log["decision"]) == {"pending"}
    assert set(log["status"]) == {"pending_review"}


def test_manifest_no_automatic_approval(reference_world: dict[str, Any]) -> None:
    run = _run(reference_world)
    import json

    manifest = json.loads((run / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["completion_status"] == "complete"
    assert manifest["approved_count"] == 0
    assert manifest["residual_diagnostic"]["material"] is False


def test_no_write_writes_nothing(reference_world: dict[str, Any]) -> None:
    assert run_reference.main([*reference_world["args"], "--no-write"]) == 0
    assert not reference_world["out_root"].exists()


def test_manifest_written_last_failed_run_not_resolvable(
    reference_world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = io.write_table

    def explode(frame: pd.DataFrame, path: Path) -> None:
        if path.name == io.DECISION_LOG_FILE:
            raise OSError("disk full")
        original(frame, path)

    monkeypatch.setattr(io, "write_table", explode)
    with pytest.raises(OSError, match="disk full"):
        run_reference.main([*reference_world["args"], "--run-id", "crashed"])
    out_root = reference_world["out_root"]
    assert not (out_root / "runs" / "crashed" / io.MANIFEST_NAME).exists()
    with pytest.raises(FileNotFoundError):
        io.resolve_run(out_root, "latest", io.MANIFEST_NAME)


def test_dispatcher_registration(reference_world: dict[str, Any]) -> None:
    assert "reference" in _COMPONENTS
    assert (
        dispatcher_main(
            ["--component", "reference", *reference_world["args"], "--no-write"]
        )
        == 0
    )


def test_residual_diagnostic_materiality_gate() -> None:
    """Both gates must pass for residual to be material."""
    frame = pd.DataFrame(
        {
            "scope": ["sensor"] * 100,
            "drift_score_raw": [0.9] * 100,
            "drift_score_healthy_only": [0.5] * 100,
            "residual_drift": [True] * 60 + [False] * 40,
        }
    )
    # 60 residual windows, 60% fraction -> material under (50, 0.05).
    assert proposals.residual_diagnostic(frame, 50, 0.05)["material"] is True
    # Raise the window gate above 60 -> not material.
    assert proposals.residual_diagnostic(frame, 80, 0.05)["material"] is False


def test_gate_a_blocks_missing_train_window() -> None:
    """A behaviour manifest with no train window stops the run, not degrades it."""
    with pytest.raises(validation.ReferenceBlockerError, match="train window"):
        validation.validate_upstream(
            "sha", {"fit_window": {}}, {"drift": {}}, {"drift": "d1"}
        )


def _behaviour_manifest(sha: str = "sha_now") -> dict[str, Any]:
    return {
        "fit_window": {"train_start": "2024-06-14", "train_end": "2024-09-03"},
        "master_dataset_sha256": sha,
    }


def test_gate_a_blocks_stale_upstream_master() -> None:
    """An upstream run fitted on a different master is a blocker."""
    with pytest.raises(validation.ReferenceBlockerError, match="different master"):
        validation.validate_upstream(
            "sha_now",
            _behaviour_manifest("sha_now"),
            {"drift": {"master_dataset_sha256": "sha_old"}},
            {"drift": "d1"},
        )


def test_gate_a_blocks_missing_behaviour_provenance() -> None:
    """No behaviour master sha -> reference_v1 provenance is unverifiable (GOV-01)."""
    behaviour = {"fit_window": {"train_start": "2024-06-14", "train_end": "2024-09-03"}}
    with pytest.raises(validation.ReferenceBlockerError, match="master_dataset_sha256"):
        validation.validate_upstream("sha_now", behaviour, {}, {})


def test_gate_a_blocks_behaviour_master_mismatch() -> None:
    """Behaviour fitted on a different master than the current one blocks (GOV-01)."""
    with pytest.raises(validation.ReferenceBlockerError, match="different master"):
        validation.validate_upstream(
            "sha_now", _behaviour_manifest("sha_behaviour"), {}, {}
        )


def test_reference_v1_uses_behaviour_provenance(
    reference_world: dict[str, Any],
) -> None:
    """reference_v1's sha comes from behaviour's manifest, and the run records it."""
    run = _run(reference_world)
    registry = pd.read_parquet(run / io.REGISTRY_FILE)
    # Behaviour was fit on the same master, so its recorded sha == master sha.
    assert registry.iloc[0]["dataset_sha256"] == reference_world["master_sha256"]
    import json

    manifest = json.loads((run / io.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["behaviour_run_id"] == "b1"
    assert manifest["compat_checks"]["behaviour_master_sha_matches"] is True
