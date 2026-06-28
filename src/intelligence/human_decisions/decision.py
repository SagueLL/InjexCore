"""Pure builders for the Human Decision Overlay artifacts (no writes here).

Encodes the reviewer's scoped ``inlet_hopper_points`` quarantine approval and
the Reference v2 deferral into compact, dashboard-consumable tables plus a
markdown summary and a completion manifest. Every value is either a verified
constant (see the module-level facts) or derived from the decision spec — none
is recomputed from the pipeline. Writing happens in :func:`write_overlay`,
which persists the manifest last.

Boundary note: the reviewer reported row ``137237``; data inspection of the
master places the ``inlet_hopper_points`` flatline-to-zero two rows earlier, at
row ``137235`` / ``2024-09-17 16:23:22`` (the system-detected onset). On the
reviewer's instruction the authoritative boundary is realigned to the detected
onset while the human-reported row is preserved for traceability.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import Field

from src.intelligence.human_decisions import io
from src.preprocessing._common.models import StrictModel

# --- Verified facts (constants; not recomputed) ---------------------------
CANONICAL_RUN_ID = "remat-v1-20260616T102558Z"
BOM_RUN_ID = "20260612T124909Z"
TARGET_SENSOR = "inlet_hopper_points"
DETECTED_ONSET_ROW = 137235
DETECTED_ONSET_TIMESTAMP = "2024-09-17 16:23:22"
HUMAN_REPORTED_ROW = 137237
APPROVAL_SOURCE = "reports/decision_reviews/iteration_c_part3_human_decision_review.md"
REFERENCE_DECISION_ROOT = "data/intelligence/forensics/reference_decision"

# Interpretive-impact metrics, sourced verbatim from the verified decision
# report (controlled scoring experiment) — recorded, never recomputed here.
NON_NORMAL_ROWS = 33186
SUPPRESSED_ROWS = 30096
SUPPRESSION_RATE = 0.907
RAW_DRIFT_BEFORE = 209.6
RAW_DRIFT_AFTER = 90.5
RAW_DRIFT_REDUCTION_RATE = 0.57
RESIDUAL_WINDOWS = 23
RESIDUAL_MATERIAL = False

# Dashboard contract: how the read-only MVP may surface this overlay. Stored as
# ``;``-joined strings (repo idiom) so the single-row parquet round-trips simply.
DASHBOARD_WARNING = (
    "Human review approves scoped quarantine treatment, but existing artifacts "
    "have not been regenerated or mutated. This is a dashboard decision "
    "overlay, not an applied pipeline state."
)
ALLOWED_DASHBOARD_ACTIONS = (
    "view_evidence",
    "view_scope",
    "view_required_records",
    "compare_original_vs_interpretive",
)
FORBIDDEN_DASHBOARD_ACTIONS = (
    "approve_quarantine",
    "apply_quarantine",
    "mutate_scores",
    "create_reference_v2",
    "run_refit",
    "trigger_production_alert",
)

LIMITATIONS = [
    "Physical root cause is not proven; the evidence supports an invalid "
    "signal from the boundary onward, not a confirmed mechanical cause.",
    "Plant/sensor records are still required before operational or "
    "customer-facing claims.",
    "Original anomaly scores are unchanged; no rescore and no refit were performed.",
    "Reference v2 remains deferred; no new reference baseline was created.",
    "This is a human decision overlay, not an applied pipeline state.",
]

BOUNDARY_COLUMNS = ("timestamp", TARGET_SENSOR)


class HumanDecisionSpec(StrictModel):
    """Inputs that fully determine the overlay (CLI args + derived boundary)."""

    canonical_run_id: str = CANONICAL_RUN_ID
    bom_run_id: str = BOM_RUN_ID
    reference_decision_run_id: str = CANONICAL_RUN_ID
    target_sensor: str = TARGET_SENSOR
    scope_start_row: int = DETECTED_ONSET_ROW
    human_reported_row: int = HUMAN_REPORTED_ROW
    system_detected_onset_row: int = DETECTED_ONSET_ROW
    system_detected_onset_timestamp: str = DETECTED_ONSET_TIMESTAMP
    scope_start_timestamp: str | None = Field(default=DETECTED_ONSET_TIMESTAMP)
    timestamp_mapping_status: str = "realigned_to_detected_onset"


def make_spec(
    *,
    canonical_run_id: str,
    bom_run_id: str,
    reference_decision_run_id: str,
    target_sensor: str,
    scope_start_row: int,
    human_reported_row: int,
) -> HumanDecisionSpec:
    """Build the spec, deriving the boundary timestamp + mapping status.

    When the authoritative boundary equals the system-detected onset row the
    timestamp is known; if it differs from the human-reported row the status is
    a realignment. Any other (overridden) boundary is left ``not_reconciled``.
    """
    if scope_start_row == DETECTED_ONSET_ROW:
        ts: str | None = DETECTED_ONSET_TIMESTAMP
        status = (
            "realigned_to_detected_onset"
            if scope_start_row != human_reported_row
            else "exact_match"
        )
    else:
        ts, status = None, "not_reconciled"
    return HumanDecisionSpec(
        canonical_run_id=canonical_run_id,
        bom_run_id=bom_run_id,
        reference_decision_run_id=reference_decision_run_id,
        target_sensor=target_sensor,
        scope_start_row=scope_start_row,
        human_reported_row=human_reported_row,
        scope_start_timestamp=ts,
        timestamp_mapping_status=status,
    )


@dataclass(frozen=True)
class OverlayArtifacts:
    """Everything :func:`build_overlay` produces (no writes happen here)."""

    sensor_quarantine_decisions: pd.DataFrame
    dashboard_decision_overlay: pd.DataFrame
    human_adjusted_review_summary: pd.DataFrame
    required_followup_records: pd.DataFrame
    summary_md: str
    manifest: dict[str, Any]


def verify_boundary(master: pd.DataFrame | None, spec: HumanDecisionSpec) -> str:
    """Read-only check that the realigned boundary matches the master.

    Confirms the positional onset row carries the expected timestamp and that
    the target channel reads zero there. Never raises: returns a descriptive
    status string (``skipped`` / ``verified`` / ``mismatch`` / ``error``).
    """
    if master is None:
        return "skipped: master dataset not available"
    row = spec.system_detected_onset_row
    if row >= len(master) or spec.target_sensor not in master.columns:
        return f"error: row {row} or column {spec.target_sensor} not in master"
    try:
        ts = str(master["timestamp"].iloc[row])[:19]
        value = float(master[spec.target_sensor].iloc[row])
    except (KeyError, ValueError, TypeError) as exc:  # pragma: no cover
        return f"error: {exc}"
    ok = ts == spec.system_detected_onset_timestamp and value == 0.0
    verdict = "verified" if ok else "mismatch"
    return f"{verdict}: master row {row} timestamp={ts} {spec.target_sensor}={value}"


def _decision_id(target: str) -> str:
    return f"human_quarantine_{target}"


def _decision_row(
    spec: HumanDecisionSpec, created_at: str, master_verification: str
) -> dict[str, Any]:
    """The single scoped-quarantine decision record."""
    realignment = (
        f"Authoritative boundary realigned to the system-detected onset row "
        f"{spec.system_detected_onset_row} ({spec.system_detected_onset_timestamp}); "
        f"the reviewer reported row {spec.human_reported_row} (~2 rows / ~2 min "
        f"later). The raw CSV holds 2 more rows than the master, a plausible "
        f"row-basis offset; reconcile against plant records."
    )
    return {
        "decision_id": _decision_id(spec.target_sensor),
        "decision_type": "sensor_quarantine",
        "target_sensor": spec.target_sensor,
        "human_decision": "approve_scoped_quarantine",
        "decision_status": "human_approved_documentation_level",
        "scope_type": "row_boundary_onward",
        "scope_start_row": spec.scope_start_row,
        "scope_start_timestamp": spec.scope_start_timestamp,
        "scope_end_row": None,
        "scope_end_timestamp": None,
        "applies_from_boundary_onward": True,
        "human_reported_row": spec.human_reported_row,
        "system_detected_onset_row": spec.system_detected_onset_row,
        "system_detected_onset_timestamp": spec.system_detected_onset_timestamp,
        "timestamp_mapping_status": spec.timestamp_mapping_status,
        "realignment_note": realignment,
        "approved_by": "human_reviewer",
        "approval_source": APPROVAL_SOURCE,
        "approval_timestamp_utc": created_at,
        "canonical_run_id": spec.canonical_run_id,
        "reference_decision_run_id": spec.reference_decision_run_id,
        "bom_run_id": spec.bom_run_id,
        "artifact_state_approval_required": True,
        "artifact_state_approved": False,
        "applied_pipeline_state": "not_applied",
        "dashboard_overlay_state": "active",
        "requires_refit": False,
        "requires_reference_v2": False,
        "requires_plant_records_before_customer_claims": True,
        "physical_root_cause_confirmed": False,
        "master_verification": master_verification,
        "notes": (
            "Documentation-level human decision; no artifact mutated, no "
            "sensor excluded automatically, no model refitted."
        ),
    }


def _overlay_row(spec: HumanDecisionSpec, run_id: str) -> dict[str, Any]:
    """The compact dashboard overlay record."""
    return {
        "overlay_id": f"overlay_{_decision_id(spec.target_sensor)}",
        "overlay_type": "human_decision",
        "target": spec.target_sensor,
        "display_title": (
            f"Human-approved scoped quarantine treatment — {spec.target_sensor}"
        ),
        "display_status": "human_approved_overlay_not_applied",
        "severity": "high",
        "canonical_run_id": spec.canonical_run_id,
        "human_decision_run_id": run_id,
        "artifact_state": "approval_required=True; approved=False",
        "human_review_state": (
            f"approved_scoped_quarantine_from_row_{spec.scope_start_row}"
        ),
        "applied_pipeline_state": "not_applied_to_original_artifacts",
        "dashboard_overlay_state": "active",
        "scope_start_row": spec.scope_start_row,
        "scope_start_timestamp": spec.scope_start_timestamp,
        "system_detected_onset_timestamp": spec.system_detected_onset_timestamp,
        "human_reported_row": spec.human_reported_row,
        "summary": (
            "Reviewer approved a scoped quarantine treatment of "
            f"{spec.target_sensor} from row {spec.scope_start_row} onward; "
            "Reference v2 deferred; no refit; documentation-level only."
        ),
        "dashboard_warning": DASHBOARD_WARNING,
        "allowed_dashboard_actions": ";".join(ALLOWED_DASHBOARD_ACTIONS),
        "forbidden_dashboard_actions": ";".join(FORBIDDEN_DASHBOARD_ACTIONS),
    }


def _adjusted_review_row(spec: HumanDecisionSpec) -> dict[str, Any]:
    """Interpretive-impact summary (verified constants; not recomputed)."""
    return {
        "target_sensor": spec.target_sensor,
        "canonical_run_id": spec.canonical_run_id,
        "non_normal_rows": NON_NORMAL_ROWS,
        "suppressed_rows": SUPPRESSED_ROWS,
        "suppression_rate": SUPPRESSION_RATE,
        "raw_drift_before": RAW_DRIFT_BEFORE,
        "raw_drift_after": RAW_DRIFT_AFTER,
        "raw_drift_reduction_rate": RAW_DRIFT_REDUCTION_RATE,
        "residual_windows": RESIDUAL_WINDOWS,
        "residual_material": RESIDUAL_MATERIAL,
        "interpretation": (
            "Quarantine-aware view suppresses ~91% of non-normal rows as "
            "instrumentation-dominated; residual healthy-only drift is "
            "immaterial. Interpretive post-processing of persisted scores — "
            "scores unchanged, no refit."
        ),
    }


def _followup_records() -> list[dict[str, Any]]:
    """External records that strengthen the evidence before operational use."""
    before = "operational_or_customer_facing_claims"
    status = "missing_external_record"
    items = [
        ("sensor maintenance logs", "confirm service/failure of the channel"),
        (
            "sensor replacement or disconnection records",
            "confirm a physical channel change",
        ),
        ("PLC/channel logs", "confirm the instrumentation channel failure"),
        ("operator notes", "operational context around the failure window"),
        ("alarm logs", "alarms around the failure window"),
        (
            "production context around the failure point",
            "rule out a deliberate process change",
        ),
        (
            f"timestamp corresponding to row {HUMAN_REPORTED_ROW}",
            "reconcile the human-reported row with the detected onset "
            f"(row {DETECTED_ONSET_ROW} / {DETECTED_ONSET_TIMESTAMP})",
        ),
    ]
    return [
        {
            "record_type": rt,
            "reason": reason,
            "required_before": before,
            "status": status,
        }
        for rt, reason in items
    ]


def _reference_decision_paths(reference_decision_run_id: str) -> dict[str, str]:
    base = f"{REFERENCE_DECISION_ROOT}/{reference_decision_run_id}"
    return {
        "source_reference_decision_dir": base,
        "source_decision_matrix_path": f"{base}/decision_matrix.parquet",
        "source_candidate_actions_path": f"{base}/candidate_actions.parquet",
        "source_required_plant_records_path": f"{base}/required_plant_records.parquet",
        "source_risk_assessment_path": f"{base}/risk_assessment.parquet",
    }


def _manifest(
    spec: HumanDecisionSpec, run_id: str, created_at: str, master_verification: str
) -> dict[str, Any]:
    sources = _reference_decision_paths(spec.reference_decision_run_id)
    return {
        "run_id": run_id,
        "created_at_utc": created_at,
        "component": io.COMPONENT,
        "completion_status": "pending",
        "canonical_run_id": spec.canonical_run_id,
        "bom_run_id": spec.bom_run_id,
        "reference_decision_run_id": spec.reference_decision_run_id,
        "source_human_review_report": APPROVAL_SOURCE,
        **sources,
        "target_sensor": spec.target_sensor,
        "human_decision": (
            f"approve_scoped_quarantine_from_row_{spec.scope_start_row}_onward"
        ),
        "scope_start_row": spec.scope_start_row,
        "scope_start_timestamp": spec.scope_start_timestamp,
        "timestamp_mapping_status": spec.timestamp_mapping_status,
        "human_reported_row": spec.human_reported_row,
        "system_detected_onset_row": spec.system_detected_onset_row,
        "system_detected_onset_timestamp": spec.system_detected_onset_timestamp,
        "reference_v2_decision": "deferred",
        "refit_approved": False,
        "automatic_production_action_approved": False,
        "artifact_mutation_performed": False,
        "score_mutation_performed": False,
        "pipeline_quarantine_applied": False,
        "master_verification": master_verification,
        "generated_files": [],
        "limitations": list(LIMITATIONS),
    }


def build_overlay(
    spec: HumanDecisionSpec,
    run_id: str,
    created_at: str,
    master_verification: str,
) -> OverlayArtifacts:
    """Assemble all overlay artifacts (pure; no writes)."""
    decisions = pd.DataFrame([_decision_row(spec, created_at, master_verification)])
    overlay = pd.DataFrame([_overlay_row(spec, run_id)])
    adjusted = pd.DataFrame([_adjusted_review_row(spec)])
    followups = pd.DataFrame(_followup_records())
    summary = _summary_md(spec, run_id, created_at)
    manifest = _manifest(spec, run_id, created_at, master_verification)
    return OverlayArtifacts(
        sensor_quarantine_decisions=decisions,
        dashboard_decision_overlay=overlay,
        human_adjusted_review_summary=adjusted,
        required_followup_records=followups,
        summary_md=summary,
        manifest=manifest,
    )


def _summary_md(spec: HumanDecisionSpec, run_id: str, created_at: str) -> str:
    """Human-readable summary (sections A–E)."""
    return "\n".join(
        [
            "# Human decision overlay — inlet_hopper_points scoped quarantine",
            "",
            f"Run `{run_id}` · canonical `{spec.canonical_run_id}` · BOM "
            f"`{spec.bom_run_id}`. Generated {created_at}.",
            "",
            "## A. Executive Summary",
            "",
            f"- Human review approves scoped quarantine treatment of "
            f"`{spec.target_sensor}` from row {spec.scope_start_row} onward.",
            "- Reference v2 remains deferred.",
            "- No refit is approved.",
            "- No automatic production action is approved.",
            "- Existing artifacts are not mutated "
            "(`approval_required=True, approved=False` unchanged).",
            "- This overlay is safe for read-only dashboard consumption.",
            "",
            "## B. Decision Scope",
            "",
            f"- Authoritative boundary: row **{spec.scope_start_row}** / "
            f"`{spec.scope_start_timestamp}` "
            f"(status: `{spec.timestamp_mapping_status}`).",
            f"- Human-reported boundary: row **{spec.human_reported_row}** "
            "(preserved for traceability).",
            f"- System-detected onset: row {spec.system_detected_onset_row} / "
            f"`{spec.system_detected_onset_timestamp}` — where the "
            f"`{spec.target_sensor}` flatline-to-zero begins.",
            "- The reviewer's row 137237 is ~2 rows / ~2 min after the detected "
            "onset; the raw CSV has 2 more rows than the master (a plausible "
            "row-basis offset). Reconcile via plant records.",
            "",
            "## C. Artifact vs Human vs Applied vs Dashboard State",
            "",
            "| State | Status | Meaning |",
            "|---|---|---|",
            "| artifact_state | `approval_required=True, approved=False` | "
            "The persisted proposal is unchanged; scores untouched. |",
            "| human_review_state | `approved_scoped_quarantine` | "
            f"The reviewer approved a scoped quarantine from row "
            f"{spec.scope_start_row} onward (documentation-level). |",
            "| applied_pipeline_state | `not_applied` | "
            "No quarantine applied, no rescore, no refit. |",
            "| dashboard_overlay_state | `active` | "
            "Surface as a human decision overlay, not an applied state. |",
            "",
            "## D. Dashboard Usage",
            "",
            "- Show this as a **human decision overlay**, clearly distinct from "
            "the unchanged artifact state and from any applied pipeline state.",
            f"- Allowed actions: {', '.join(ALLOWED_DASHBOARD_ACTIONS)}.",
            f"- Forbidden actions: {', '.join(FORBIDDEN_DASHBOARD_ACTIONS)}.",
            f"- Required warning: {DASHBOARD_WARNING}",
            "",
            "## E. Limitations",
            "",
            *[f"- {line}" for line in LIMITATIONS],
            "",
        ]
    )


def write_overlay(art: OverlayArtifacts, out: Path) -> list[str]:
    """Persist the overlay; manifest LAST within its directory."""
    written: list[str] = []
    tables = {
        io.SENSOR_DECISIONS_FILE: art.sensor_quarantine_decisions,
        io.DASHBOARD_OVERLAY_FILE: art.dashboard_decision_overlay,
        io.ADJUSTED_REVIEW_FILE: art.human_adjusted_review_summary,
        io.FOLLOWUP_RECORDS_FILE: art.required_followup_records,
    }
    for name, frame in tables.items():
        io.write_table(frame, out / name)
        written.append(name)
    (out / io.SUMMARY_MD).write_text(art.summary_md, encoding="utf-8")
    written.append(io.SUMMARY_MD)

    manifest = dict(art.manifest)
    manifest["generated_files"] = written
    manifest["completion_status"] = "complete"
    io.write_manifest(manifest, out / io.MANIFEST_NAME)
    written.append(io.MANIFEST_NAME)
    return written
