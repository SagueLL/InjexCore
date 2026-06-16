"""Recommendations, findings + Markdown report for the scoring experiment."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.intelligence._common.reporting import Finding, Severity

CHECK = "controlled_scoring_experiment"

RECOMMENDATION_COLUMNS = [
    "scenario_id",
    "recommendation",
    "rationale",
    "requires_human_approval",
    "requires_model_refit",
    "requires_external_records",
    "evidence",
]


def _quarantine_row(
    anomaly_rate: pd.DataFrame, quarantine_scenario: str
) -> dict[str, Any]:
    if not quarantine_scenario:
        return {}
    row = anomaly_rate[anomaly_rate["scenario_id"] == quarantine_scenario]
    return row.iloc[0].to_dict() if len(row) else {}


def build_recommendations(
    anomaly_rate: pd.DataFrame,
    drift_comparison: pd.DataFrame,
    residual: dict[str, Any],
    quarantine_scenario: str,
    quarantine_sensors: list[str],
) -> pd.DataFrame:
    """One recommendation row per scenario (decision-support, never an action)."""
    q = _quarantine_row(anomaly_rate, quarantine_scenario)
    suppressed = int(q.get("suppressed_count", 0))
    rate = float(q.get("suppression_rate", 0.0))
    proxy = drift_comparison[drift_comparison["scenario_id"] == "healthy_only_proxy"]
    reduction = float(proxy["reduction_pct"].iloc[0]) if len(proxy) else 0.0
    material = bool(residual.get("material", False))
    sensors_text = ", ".join(quarantine_sensors) if quarantine_sensors else "n/a"
    rows = [
        {
            "scenario_id": "baseline_v1",
            "recommendation": "reference_only",
            "rationale": "Unchanged picture, kept for comparison.",
            "requires_human_approval": False,
            "requires_model_refit": False,
            "requires_external_records": False,
            "evidence": "",
        },
    ]
    if quarantine_scenario:
        rows.append(
            {
                "scenario_id": quarantine_scenario,
                "recommendation": "route_quarantine_for_human_approval",
                "rationale": (
                    f"{suppressed} non-normal rows ({rate * 100:.0f}%) are "
                    f"dominated by the pending-quarantine sensor(s) "
                    f"({sensors_text}); approving the quarantine would clear them "
                    "from the review backlog. Interpretive only."
                ),
                "requires_human_approval": True,
                "requires_model_refit": False,
                "requires_external_records": False,
                "evidence": f"suppressed={suppressed};suppression_rate={rate:.3f}",
            }
        )
    rows += [
        {
            "scenario_id": "healthy_only_proxy",
            "recommendation": "treat_residual_as_candidate_finding",
            "rationale": (
                f"{reduction:.0f}% of sensor drift mass disappears in the "
                f"healthy-only view; {residual.get('n_residual_windows', 0)} "
                "residual windows remain. Proxy view, not a rescoring."
            ),
            "requires_human_approval": False,
            "requires_model_refit": False,
            "requires_external_records": False,
            "evidence": (
                f"reduction_pct={reduction:.1f};"
                f"n_residual_windows={residual.get('n_residual_windows', 0)}"
            ),
        },
        {
            "scenario_id": "candidate_reference_needed",
            "recommendation": (
                "design_reference_v2" if material else "defer_reference_v2"
            ),
            "rationale": (
                "Residual healthy-only drift is materially significant; design a "
                "Reference v2 after plant-record review."
                if material
                else "Residual healthy-only drift is below the materiality "
                "threshold; defer Reference v2 and collect plant records first."
            ),
            "requires_human_approval": True,
            "requires_model_refit": material,
            "requires_external_records": True,
            "evidence": (
                f"material={material};"
                f"residual_fraction={residual.get('residual_fraction', 0.0):.4f}"
            ),
        },
    ]
    return pd.DataFrame(rows, columns=RECOMMENDATION_COLUMNS)


def build_findings(
    anomaly_rate: pd.DataFrame, residual: dict[str, Any], quarantine_scenario: str
) -> list[Finding]:
    """Structured findings — interpretive views, original scores immutable."""
    q = _quarantine_row(anomaly_rate, quarantine_scenario)
    findings = [
        Finding(
            check=CHECK,
            severity=Severity.NORMAL,
            finding_type="baseline_scenario",
            column="baseline_v1",
            action_taken="reference",
            evidence={
                "original_anomaly_count": int(q.get("original_anomaly_count", 0)),
                "original_warning_count": int(q.get("original_warning_count", 0)),
            },
        ),
    ]
    if quarantine_scenario:
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="quarantine_aware_review",
                column=quarantine_scenario,
                count=int(q.get("suppressed_count", 0)),
                action_taken="row_suppressed_for_review_only",
                evidence={
                    "suppressed_count": int(q.get("suppressed_count", 0)),
                    "suppression_rate": float(q.get("suppression_rate", 0.0)),
                    "remaining_anomaly_count": int(q.get("remaining_anomaly_count", 0)),
                    "original_scores_mutated": False,
                },
            )
        )
    findings.append(
        Finding(
            check=CHECK,
            severity=Severity.AWARE,
            finding_type="healthy_only_residual",
            action_taken="assessed",
            evidence=dict(residual),
        )
    )
    return findings


def render_report(
    scenario_defs: pd.DataFrame,
    anomaly_rate: pd.DataFrame,
    incident_cmp: pd.DataFrame,
    drift_cmp: pd.DataFrame,
    recommendations: pd.DataFrame,
    residual: dict[str, Any],
    manifest: dict[str, Any],
    quarantine_scenario: str,
) -> str:
    """Human-readable controlled-scoring report."""
    q = _quarantine_row(anomaly_rate, quarantine_scenario)
    lines = [
        "# Controlled Scoring Experiment report",
        "",
        f"Run `{manifest['run_id']}` — generated {manifest['created_at']}.",
        "",
        "Controlled scoring experiments **do not mutate original scores**. "
        "Healthy-only and quarantine-aware outputs are interpretive "
        "decision-support views; no model was refitted and no PCA/Mahalanobis "
        "matrix was recomputed.",
        "",
        "## Scenarios",
        "",
    ]
    for s in scenario_defs.itertuples(index=False):
        lines.append(f"- `{s.scenario_id}` ({s.scenario_type}, {s.granularity})")
    lines += [
        "",
        "## Quarantine-aware review impact",
        "",
        f"- Original: {q.get('original_anomaly_count', 0)} anomaly / "
        f"{q.get('original_warning_count', 0)} warning rows.",
        f"- Suppressed for review: {q.get('suppressed_count', 0)} "
        f"({q.get('suppression_rate', 0.0) * 100:.0f}% of non-normal rows).",
        f"- Remaining review backlog: {q.get('remaining_anomaly_count', 0)} "
        f"anomaly / {q.get('remaining_warning_count', 0)} warning.",
        f"- Top remaining sensors: {q.get('top_remaining_sensors', '')}",
        "",
        "## Healthy-only residual drift",
        "",
        f"- Raw drift mass {residual.get('raw_mass', 0.0):.1f} → "
        f"{residual.get('healthy_mass', 0.0):.1f} "
        f"({residual.get('reduction_pct', 0.0):.0f}% reduction); "
        f"{residual.get('n_residual_windows', 0)} residual windows.",
        f"- Materially significant? **{residual.get('material', False)}**.",
        "",
        "## Recommendations",
        "",
    ]
    for r in recommendations.itertuples(index=False):
        lines.append(f"- `{r.scenario_id}`: {r.recommendation} — {r.rationale}")
    lines.append("")
    return "\n".join(lines)
