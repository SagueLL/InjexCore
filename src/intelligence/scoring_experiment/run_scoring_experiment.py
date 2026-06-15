"""CLI orchestrator for the Controlled Scoring Experiment component.

Linear order::

    resolve six upstream runs (anomaly / sensor-health / drift / incidents /
    operational context / reference governance — completed runs only)
        → Gate A: anomaly + operational timelines row-aligned, master sha ok
        → build the per-row base (anomaly scores ⋈ operational context)
        → quarantine-aware interpretation (down-rank review severity only)
        → scenario scores + comparison tables + recommendations
        → decision-report forensic addendum (read-only; --skip-decision-report)
        → write run-versioned artifacts (manifest LAST)

This component never refits a model, never recomputes PCA/Mahalanobis from
altered matrices and never overwrites an original score. Run standalone or
via the dispatcher::

    python -m src.intelligence --component scoring-experiment
    python -m src.intelligence.scoring_experiment.run_scoring_experiment --no-write
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import CONFIGS_DIR
from src.intelligence._common.reporting import Finding, write_json
from src.intelligence.reference.proposals import (
    residual_diagnostic as _residual_diagnostic,
)
from src.intelligence.scoring_experiment import (
    comparison,
    io,
    quarantine,
    reporting,
    scenarios,
    scoring,
)
from src.intelligence.scoring_experiment.policy import ScoringPolicy, load_policy
from src.intelligence.scoring_experiment.validation import validate_upstream

DEFAULT_CONFIG = CONFIGS_DIR / "scoring_experiment.yaml"

log = logging.getLogger("scoring_experiment")


@dataclass(frozen=True)
class UpstreamRuns:
    """Resolved completed upstream run directories."""

    anomaly: Path
    sensor_health: Path
    drift: Path
    incidents: Path
    operational: Path
    reference: Path

    def run_ids(self) -> dict[str, str]:
        return {
            "anomaly": self.anomaly.name,
            "sensor_health": self.sensor_health.name,
            "drift": self.drift.name,
            "incidents": self.incidents.name,
            "operational": self.operational.name,
            "reference": self.reference.name,
        }


@dataclass(frozen=True)
class ScoringArtifacts:
    """Everything ``run()`` produces (no writes happen here)."""

    scenario_defs: pd.DataFrame
    scenario_scores: pd.DataFrame
    incident_comparison: pd.DataFrame
    anomaly_rate_comparison: pd.DataFrame
    drift_comparison: pd.DataFrame
    recommendations: pd.DataFrame
    findings: list[Finding]
    manifest: dict[str, Any]
    report: str
    decision_inputs: dict[str, Any]


def run(config_path: Path, runs: UpstreamRuns, run_id: str) -> ScoringArtifacts:
    """Execute the full controlled scoring experiment (pure; no writes)."""
    policy = load_policy(config_path)
    top = policy.reporting.top_remaining
    master_path = io.resolve_project_path(policy.upstream.master_path)
    master_sha256 = io.file_sha256(master_path)

    anomaly = io.load_anomaly_scores(runs.anomaly)
    op_timeline = io.load_operational_timeline(runs.operational)
    raw_vs_healthy = io.load_raw_vs_healthy(runs.drift)
    incidents = io.load_incidents(runs.incidents)
    suppressed = io.load_suppressed_duplicates(runs.incidents)
    reference_quarantine = io.load_reference_quarantine(runs.reference)
    reference_proposals = io.load_reference_proposals(runs.reference)
    reference_manifest = io.load_run_manifest(runs.reference, io.REFERENCE_MANIFEST)

    upstream_manifests = {
        "anomaly": io.load_run_manifest(runs.anomaly, io.ANOMALY_MANIFEST),
        "sensor_health": io.load_run_manifest(
            runs.sensor_health, io.SENSOR_HEALTH_MANIFEST
        ),
        "drift": io.load_run_manifest(runs.drift, io.DRIFT_MANIFEST),
        "operational": io.load_run_manifest(runs.operational, io.OPERATIONAL_MANIFEST),
        "reference": reference_manifest,
    }
    compat, findings = validate_upstream(
        master_sha256, anomaly, op_timeline, upstream_manifests, runs.run_ids()
    )

    residual = reference_manifest.get("residual_diagnostic") or _residual_diagnostic(
        raw_vs_healthy, 50, 0.05
    )
    residual_count = int(residual.get("n_residual_windows", 0))

    base = scoring.build_base(anomaly, op_timeline)
    targets = quarantine.quarantine_targets(reference_quarantine)
    burst_windows = quarantine.suppressed_burst_windows(suppressed, incidents)
    base = scoring.apply_quarantine(base, targets, burst_windows)

    scenario_defs = scenarios.scenario_definitions()
    scenario_scores = scoring.scenario_scores(base)
    anomaly_rate = comparison.anomaly_rate_comparison(base, residual_count, top)
    incident_cmp = comparison.incident_comparison(
        incidents, suppressed, [t.sensor for t in targets]
    )
    drift_cmp = comparison.drift_comparison(raw_vs_healthy, top)
    recommendations = reporting.build_recommendations(anomaly_rate, drift_cmp, residual)

    findings.extend(reporting.build_findings(anomaly_rate, residual))
    manifest = _build_manifest(
        policy, run_id, runs, master_sha256, base, scenario_scores, residual, compat
    )
    report = reporting.render_report(
        scenario_defs,
        anomaly_rate,
        incident_cmp,
        drift_cmp,
        recommendations,
        residual,
        manifest,
    )
    log.info(
        "Scoring experiment: %d non-normal rows, %d suppressed for review, "
        "residual_material=%s",
        int((base["original_severity"] != "normal").sum()),
        int(base["suppressed_for_review"].sum()),
        residual.get("material"),
    )
    return ScoringArtifacts(
        scenario_defs=scenario_defs,
        scenario_scores=scenario_scores,
        incident_comparison=incident_cmp,
        anomaly_rate_comparison=anomaly_rate,
        drift_comparison=drift_cmp,
        recommendations=recommendations,
        findings=findings,
        manifest=manifest,
        report=report,
        decision_inputs={
            "reference_proposals": reference_proposals,
            "reference_quarantine": reference_quarantine,
            "anomaly_rate": anomaly_rate,
            "recommendations": recommendations,
            "residual": residual,
            "upstream_run_ids": runs.run_ids(),
        },
    )


def _build_manifest(
    policy: ScoringPolicy,
    run_id: str,
    runs: UpstreamRuns,
    master_sha256: str,
    base: pd.DataFrame,
    scenario_scores: pd.DataFrame,
    residual: dict[str, Any],
    compat: dict[str, Any],
) -> dict[str, Any]:
    return {
        "component": "controlled_scoring_experiment",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "master_dataset_sha256": master_sha256,
        "anomaly_run_id": runs.anomaly.name,
        "sensor_health_run_id": runs.sensor_health.name,
        "drift_run_id": runs.drift.name,
        "incidents_run_id": runs.incidents.name,
        "operational_context_run_id": runs.operational.name,
        "reference_run_id": runs.reference.name,
        "scenario_count": 4,
        "non_normal_rows": int((base["original_severity"] != "normal").sum()),
        "suppressed_for_review": int(base["suppressed_for_review"].sum()),
        "scenario_score_rows": int(len(scenario_scores)),
        "residual_diagnostic": dict(residual),
        "config_snapshot": policy.model_dump(),
        "compat_checks": compat,
        "statements": [
            "Controlled scoring experiments do not mutate original scores; "
            "adjusted_review_* columns are interpretive review views.",
            "Healthy-only and quarantine-aware outputs are decision-support "
            "only; no model was refitted and no PCA/Mahalanobis matrix "
            "recomputed.",
            "No quarantine was approved; no sensor was excluded automatically.",
            "No upstream artifact was modified or overwritten.",
        ],
        "generated_files": [],  # filled by main() at write time
        "decision_report_status": "skipped",
        "completion_status": "pending",
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    for name in (
        "anomaly",
        "sensor-health",
        "drift",
        "incidents",
        "operational",
        "reference",
    ):
        p.add_argument(
            f"--{name}-run",
            default=None,
            help=f"{name} run id to consume (default: policy pin / 'latest').",
        )
    p.add_argument(
        "--output-root",
        type=Path,
        default=io.SCORING_DIR,
        help="Component root; artifacts land under <root>/runs/<run_id>/.",
    )
    p.add_argument(
        "--decision-root",
        type=Path,
        default=None,
        help="Decision-report root (default: policy output_root).",
    )
    p.add_argument(
        "--run-id",
        default=None,
        help="Run identifier (default: fresh UTC timestamp; never overwrites).",
    )
    p.add_argument(
        "--skip-decision-report",
        action="store_true",
        help="Skip the decision-report forensic addendum stage.",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Diagnostic only: run the full pipeline, write nothing.",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def _resolve_upstream_runs(
    args: argparse.Namespace, policy: ScoringPolicy
) -> UpstreamRuns:
    """Resolve all six upstream runs (CLI flag > policy pin > latest)."""
    up = policy.upstream
    spec = {
        "anomaly": (
            up.anomaly_root,
            args.anomaly_run or up.anomaly_run,
            io.ANOMALY_MANIFEST,
        ),
        "sensor_health": (
            up.sensor_health_root,
            args.sensor_health_run or up.sensor_health_run,
            io.SENSOR_HEALTH_MANIFEST,
        ),
        "drift": (up.drift_root, args.drift_run or up.drift_run, io.DRIFT_MANIFEST),
        "incidents": (
            up.incidents_root,
            args.incidents_run or up.incidents_run,
            io.INCIDENTS_MANIFEST,
        ),
        "operational": (
            up.operational_root,
            args.operational_run or up.operational_run,
            io.OPERATIONAL_MANIFEST,
        ),
        "reference": (
            up.reference_root,
            args.reference_run or up.reference_run,
            io.REFERENCE_MANIFEST,
        ),
    }
    resolved = {
        name: io.resolve_run(io.resolve_project_path(root), run, manifest)
        for name, (root, run, manifest) in spec.items()
    }
    return UpstreamRuns(**resolved)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    policy = load_policy(args.config)
    runs = _resolve_upstream_runs(args, policy)
    run_id = args.run_id or io.new_run_id(args.output_root)
    art = run(args.config, runs, run_id)

    if args.no_write:
        log.info(
            "--no-write: skipping all artifacts (%d findings; run id %s unused)",
            len(art.findings),
            run_id,
        )
        return 0

    out = io.run_dir(args.output_root, run_id)
    table_map = {
        io.SCENARIO_DEFINITIONS_FILE: art.scenario_defs,
        io.SCENARIO_SCORES_FILE: art.scenario_scores,
        io.INCIDENT_COMPARISON_FILE: art.incident_comparison,
        io.ANOMALY_RATE_COMPARISON_FILE: art.anomaly_rate_comparison,
        io.DRIFT_COMPARISON_FILE: art.drift_comparison,
        io.RECOMMENDATIONS_FILE: art.recommendations,
    }
    for rel_path, frame in table_map.items():
        io.write_table(frame, out / rel_path)
    write_json(art.findings, out / io.FINDINGS_JSON)
    (out / io.REPORT_MD).write_text(art.report, encoding="utf-8")

    generated = [*table_map, io.FINDINGS_JSON, io.REPORT_MD]
    decision_status = "skipped"
    if policy.decision_report.enabled and not args.skip_decision_report:
        from src.intelligence.scoring_experiment import decision_report

        decision_root = args.decision_root or io.resolve_project_path(
            policy.decision_report.output_root
        )
        decision_out = decision_root / run_id
        decision_art = decision_report.build_decision_report(
            art.decision_inputs["reference_proposals"],
            art.decision_inputs["reference_quarantine"],
            art.decision_inputs["anomaly_rate"],
            art.decision_inputs["recommendations"],
            art.decision_inputs["residual"],
            run_id,
            art.decision_inputs["upstream_run_ids"],
        )
        decision_files = decision_report.write_decision_report(
            decision_art, decision_out
        )
        generated += [str(decision_out / f) for f in decision_files]
        decision_status = "complete"
        log.info("Wrote decision-report addendum → %s", decision_out)

    manifest = dict(art.manifest)
    manifest["generated_files"] = [str(p) for p in generated]
    manifest["decision_report_status"] = decision_status
    manifest["completion_status"] = "complete"
    # Manifest last: its presence marks the run as complete (resolvable).
    io.write_manifest(manifest, out / io.MANIFEST_NAME)
    log.info("Wrote controlled scoring experiment run → %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
