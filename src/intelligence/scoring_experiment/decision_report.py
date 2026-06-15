"""Decision-report forensic addendum (read-only synthesis; Stage-H idiom).

Joins the Reference Governance proposals with the controlled-scoring results
into a human decision pack: a decision matrix over the candidate actions, a
risk assessment, the plant records still required, and an executive summary.
It approves nothing, refits nothing and mutates no upstream artifact. Outputs
land in ``data/intelligence/forensics/reference_decision/<run_id>/``; the
decision manifest is written last within that directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.intelligence.scoring_experiment import io

DECISION_MATRIX_COLUMNS = [
    "action",
    "recommended",
    "priority",
    "expected_benefit",
    "risk_if_done",
    "risk_if_not_done",
    "requires_human_approval",
    "requires_model_refit",
    "requires_external_records",
    "supporting_evidence",
    "blocking_uncertainties",
]

CANDIDATE_ACTION_COLUMNS = [
    "sequence_order",
    "action",
    "recommended",
    "requires_human_approval",
    "summary",
]

RISK_COLUMNS = ["action", "risk_if_done", "risk_if_not_done", "severity"]

PLANT_RECORD_COLUMNS = ["record_type", "why_needed", "blocks_action"]

_TABLES = [
    "decision_matrix",
    "candidate_actions",
    "risk_assessment",
    "required_plant_records",
]

_PLANT_RECORDS = [
    (
        "maintenance log",
        "confirm whether inlet_hopper_points was serviced/failed",
        "approve_quarantine_inlet_hopper_points",
    ),
    (
        "sensor channel log",
        "confirm the instrumentation channel failure",
        "inspect_sensor_channel",
    ),
    (
        "operator notes",
        "context for the September operational shift",
        "design_reference_candidate_v2",
    ),
    (
        "setpoint changes",
        "rule out a deliberate process change",
        "design_reference_candidate_v2",
    ),
]


@dataclass(frozen=True)
class DecisionReportArtifacts:
    """Everything ``build_decision_report`` produces (no writes happen here)."""

    decision_matrix: pd.DataFrame
    candidate_actions: pd.DataFrame
    risk_assessment: pd.DataFrame
    required_plant_records: pd.DataFrame
    decision_summary: str
    manifest: dict[str, Any]


def _decision_matrix(material: bool, suppressed: int, rate: float) -> pd.DataFrame:
    evidence = f"suppressed={suppressed};suppression_rate={rate:.3f};residual_material={material}"
    rows = [
        {
            "action": "do_nothing",
            "recommended": False,
            "priority": "none",
            "expected_benefit": "none",
            "risk_if_done": "a known instrumentation fault keeps distorting scoring",
            "risk_if_not_done": "n/a",
            "requires_human_approval": False,
            "requires_model_refit": False,
            "requires_external_records": False,
            "supporting_evidence": evidence,
            "blocking_uncertainties": "",
        },
        {
            "action": "inspect_sensor_channel",
            "recommended": True,
            "priority": "high",
            "expected_benefit": "confirms the instrumentation hypothesis at the source",
            "risk_if_done": "minor inspection effort",
            "risk_if_not_done": "the instrumentation-vs-process question stays open",
            "requires_human_approval": False,
            "requires_model_refit": False,
            "requires_external_records": True,
            "supporting_evidence": evidence,
            "blocking_uncertainties": "needs physical/plant confirmation",
        },
        {
            "action": "approve_quarantine_inlet_hopper_points",
            "recommended": True,
            "priority": "high",
            "expected_benefit": (
                f"removes ~{rate * 100:.0f}% of non-normal rows that are "
                "instrumentation-dominated from the review backlog"
            ),
            "risk_if_done": "a co-located process signal could be hidden (reversible)",
            "risk_if_not_done": "anomaly mass keeps masking genuine process signals",
            "requires_human_approval": True,
            "requires_model_refit": False,
            "requires_external_records": False,
            "supporting_evidence": evidence,
            "blocking_uncertainties": "approve only after channel inspection",
        },
        {
            "action": "controlled_rescore_after_quarantine",
            "recommended": True,
            "priority": "medium",
            "expected_benefit": "a true (not interpretive) re-score excluding the channel",
            "risk_if_done": "compute cost; must reuse the leakage-safe split",
            "risk_if_not_done": "only the interpretive view is available",
            "requires_human_approval": True,
            "requires_model_refit": True,
            "requires_external_records": False,
            "supporting_evidence": evidence,
            "blocking_uncertainties": "blocked on quarantine approval",
        },
        {
            "action": "design_reference_candidate_v2",
            "recommended": material,
            "priority": "medium" if material else "low",
            "expected_benefit": "a clean post-fault reference if residual is real",
            "risk_if_done": "baking instrumentation noise into a premature reference",
            "risk_if_not_done": "residual healthy drift remains uncharacterised",
            "requires_human_approval": True,
            "requires_model_refit": True,
            "requires_external_records": True,
            "supporting_evidence": evidence,
            "blocking_uncertainties": (
                ""
                if material
                else "residual healthy-only drift is below the materiality threshold"
            ),
        },
        {
            "action": "collect_plant_records",
            "recommended": True,
            "priority": "high",
            "expected_benefit": "closes the instrumentation-vs-process question",
            "risk_if_done": "coordination effort",
            "risk_if_not_done": "refit/v2 decisions stay unjustified",
            "requires_human_approval": False,
            "requires_model_refit": False,
            "requires_external_records": True,
            "supporting_evidence": evidence,
            "blocking_uncertainties": "",
        },
    ]
    return pd.DataFrame(rows, columns=DECISION_MATRIX_COLUMNS)


def _candidate_actions(matrix: pd.DataFrame) -> pd.DataFrame:
    recommended = matrix[matrix["recommended"]].reset_index(drop=True)
    rows = [
        {
            "sequence_order": i + 1,
            "action": r.action,
            "recommended": bool(r.recommended),
            "requires_human_approval": bool(r.requires_human_approval),
            "summary": str(r.expected_benefit),
        }
        for i, r in enumerate(recommended.itertuples(index=False))
    ]
    return pd.DataFrame(rows, columns=CANDIDATE_ACTION_COLUMNS)


def _risk_assessment(matrix: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {
            "action": r.action,
            "risk_if_done": r.risk_if_done,
            "risk_if_not_done": r.risk_if_not_done,
            "severity": "high" if r.priority == "high" else "medium",
        }
        for r in matrix.itertuples(index=False)
    ]
    return pd.DataFrame(rows, columns=RISK_COLUMNS)


def build_decision_report(
    reference_proposals: pd.DataFrame,
    reference_quarantine: pd.DataFrame,
    anomaly_rate: pd.DataFrame,
    recommendations: pd.DataFrame,
    residual: dict[str, Any],
    run_id: str,
    upstream_run_ids: dict[str, str],
) -> DecisionReportArtifacts:
    """Assemble the decision pack (pure; no writes)."""
    q = anomaly_rate[
        anomaly_rate["scenario_id"] == "quarantine_inlet_hopper_points_interpretive"
    ]
    suppressed = int(q["suppressed_count"].iloc[0]) if len(q) else 0
    rate = float(q["suppression_rate"].iloc[0]) if len(q) else 0.0
    material = bool(residual.get("material", False))

    matrix = _decision_matrix(material, suppressed, rate)
    candidate_actions = _candidate_actions(matrix)
    risk = _risk_assessment(matrix)
    plant_records = pd.DataFrame(_PLANT_RECORDS, columns=PLANT_RECORD_COLUMNS)
    summary = _summary(suppressed, rate, residual, run_id, upstream_run_ids)
    manifest = {
        "component": "reference_decision",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "upstream_run_ids": dict(upstream_run_ids),
        "quarantine_proposals": int(len(reference_quarantine)),
        "candidate_proposals": int(len(reference_proposals)),
        "residual_material": material,
        "tables": list(_TABLES),
        "statements": [
            "Read-only decision-support synthesis; no upstream artifact modified.",
            "Quarantine-aware and healthy-only views are interpretive; original "
            "anomaly scores were not mutated and no model was refitted.",
            "No quarantine was approved; no sensor was excluded automatically.",
        ],
        "generated_files": [],
        "completion_status": "pending",
    }
    return DecisionReportArtifacts(
        decision_matrix=matrix,
        candidate_actions=candidate_actions,
        risk_assessment=risk,
        required_plant_records=plant_records,
        decision_summary=summary,
        manifest=manifest,
    )


def _summary(
    suppressed: int,
    rate: float,
    residual: dict[str, Any],
    run_id: str,
    upstream_run_ids: dict[str, str],
) -> str:
    material = bool(residual.get("material", False))
    v2 = (
        "design a Reference v2 after plant-record review"
        if material
        else "defer Reference v2 (residual healthy-only drift is immaterial)"
    )
    return "\n".join(
        [
            "# Reference decision summary",
            "",
            f"Scoring run `{run_id}`; reference run "
            f"`{upstream_run_ids.get('reference', '?')}`. Generated "
            f"{datetime.now(UTC).isoformat()}.",
            "",
            "## Recommended order (decision-support only)",
            "",
            "1. Inspect/confirm the `inlet_hopper_points` channel failure.",
            "2. Approve the quarantine **only after** human review "
            f"(would clear ~{rate * 100:.0f}% / {suppressed} of the non-normal "
            "review rows; interpretive).",
            "3. Run a controlled rescoring/refit experiment **only after** "
            "quarantine approval.",
            f"4. {v2[0].upper() + v2[1:]}.",
            "5. Collect the required plant records to close the "
            "instrumentation-vs-process question.",
            "",
            "## Honest evidence",
            "",
            f"- Raw drift mass {residual.get('raw_mass', 0.0):.1f} → "
            f"{residual.get('healthy_mass', 0.0):.1f} "
            f"({residual.get('reduction_pct', 0.0):.0f}% reduction); "
            f"{residual.get('n_residual_windows', 0)} residual windows "
            f"({residual.get('residual_fraction', 0.0) * 100:.1f}%).",
            "- The quarantine recommendation remains `approval_required=True`, "
            "`approved=False`. Nothing here changes that.",
            "",
            "## Limitations",
            "",
            "- The quarantine-aware and healthy-only views are interpretive "
            "post-processing of persisted scores — **no rescoring, no refit**.",
            "- Incident relationships are associative (`causality_status="
            "unknown`); this report does not establish causality.",
            "",
        ]
    )


def write_decision_report(art: DecisionReportArtifacts, out: Path) -> list[str]:
    """Persist the decision pack; decision manifest LAST within its directory."""
    written: list[str] = []
    tables = {
        "decision_matrix": art.decision_matrix,
        "candidate_actions": art.candidate_actions,
        "risk_assessment": art.risk_assessment,
        "required_plant_records": art.required_plant_records,
    }
    for name, frame in tables.items():
        io.write_table(frame, out / f"{name}.parquet")
        written.append(f"{name}.parquet")
    (out / "decision_summary.md").write_text(art.decision_summary, encoding="utf-8")
    written.append("decision_summary.md")

    manifest = dict(art.manifest)
    manifest["generated_files"] = written
    manifest["completion_status"] = "complete"
    io.write_manifest(manifest, out / io.DECISION_MANIFEST_NAME)
    written.append(io.DECISION_MANIFEST_NAME)
    return written
