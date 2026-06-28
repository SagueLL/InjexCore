"""Findings + Markdown report for Reference Governance."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.intelligence._common.reporting import Finding, Severity

CHECK = "reference_governance"


def build_findings(
    registry: pd.DataFrame,
    proposals: pd.DataFrame,
    quarantine: pd.DataFrame,
    residual: dict[str, Any],
) -> list[Finding]:
    """Structured findings — baseline tracked, proposals pending, never approved."""
    findings: list[Finding] = [
        Finding(
            check=CHECK,
            severity=Severity.NORMAL,
            finding_type="reference_baseline",
            column="reference_v1",
            count=int(len(registry)),
            action_taken="tracked",
            evidence={
                "status": "current",
                "train_start": str(registry.iloc[0]["source_train_start"]),
                "train_end": str(registry.iloc[0]["source_train_end"]),
            },
        )
    ]
    for q in quarantine.itertuples(index=False):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="quarantine_proposal",
                column=str(q.sensor),
                action_taken="proposed_pending_review",
                evidence={
                    "approval_required": bool(q.approval_required),
                    "approved": bool(q.approved),
                    "recommended_action": str(q.recommended_action),
                },
            )
        )
    for p in proposals.itertuples(index=False):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.AWARE,
                finding_type=str(p.proposal_type),
                column=str(p.proposal_id),
                action_taken="proposed_pending_review",
                evidence={
                    "status": str(p.status),
                    "model_refit_required": bool(p.model_refit_required),
                    "excluded_sensors": str(p.excluded_sensors),
                },
            )
        )
    findings.append(
        Finding(
            check=CHECK,
            severity=Severity.AWARE,
            finding_type="residual_drift_diagnostic",
            action_taken="assessed",
            evidence=dict(residual),
        )
    )
    return findings


def render_report(
    registry: pd.DataFrame,
    proposals: pd.DataFrame,
    quarantine: pd.DataFrame,
    decision_log: pd.DataFrame,
    residual: dict[str, Any],
    manifest: dict[str, Any],
) -> str:
    """Human-readable governance report."""
    lines: list[str] = [
        "# Reference Governance report",
        "",
        f"Run `{manifest['run_id']}` — generated {manifest['created_at']}.",
        "",
        "Reference Governance **proposes and tracks** decisions. It does not "
        "approve a quarantine, exclude a sensor, refit a model or change the "
        "reference window. Every proposal below is `pending_review` with "
        "`approved=False`.",
        "",
        "## Reference registry",
        "",
        f"- Current reference: `{registry.iloc[0]['reference_id']}` "
        f"(`{registry.iloc[0]['status']}`), train window "
        f"`{registry.iloc[0]['source_train_start']}` → "
        f"`{registry.iloc[0]['source_train_end']}`.",
        "",
        "## Quarantine proposals",
        "",
    ]
    if len(quarantine):
        for q in quarantine.itertuples(index=False):
            lines.append(
                f"- `{q.sensor}` — {q.recommended_action} "
                f"(`approval_required={q.approval_required}`, "
                f"`approved={q.approved}`); window "
                f"{q.start_timestamp} → {q.end_timestamp}."
            )
    else:
        lines.append("- None (no upstream quarantine recommendation matched).")
    lines += ["", "## Candidate reference proposals", ""]
    for p in proposals.itertuples(index=False):
        lines.append(
            f"- `{p.proposal_id}` ({p.proposal_type}, `{p.status}`): "
            f"{p.recommended_next_step}"
        )
    lines += [
        "",
        "## Residual healthy-only drift diagnostic",
        "",
        f"- {residual['n_residual_windows']} of {residual['n_windows']} sensor "
        f"windows ({residual['residual_fraction'] * 100:.1f}%) remain after "
        f"excluding faulty/quarantined-sensor evidence; raw drift mass "
        f"{residual['raw_mass']:.1f} → {residual['healthy_mass']:.1f} "
        f"({residual['reduction_pct']:.0f}% reduction).",
        f"- Materially significant residual? **{residual['material']}** — "
        "drives whether a Reference v2 design is recommended now.",
        "",
        "## Decision log",
        "",
        f"- {len(decision_log)} proposal(s) seeded `pending` — all awaiting "
        "human review; none decided.",
        "",
    ]
    return "\n".join(lines)
