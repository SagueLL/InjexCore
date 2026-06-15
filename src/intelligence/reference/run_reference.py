"""CLI orchestrator for the Reference Governance component.

Linear order::

    resolve three upstream runs (sensor-health / incidents / drift —
    completed runs only)
        → Gate A: behaviour train window present + upstream master sha matches
        → seed reference_v1 registry (immutable baseline)
        → build quarantine proposals (approval_required, not approved)
        → assess residual healthy-only drift materiality
        → build the three candidate reference proposals (pending_review)
        → seed the decision log (one pending row per proposal)
        → write run-versioned artifacts (manifest LAST)

This component never modifies upstream data, never approves a quarantine,
never excludes a sensor and never refits a model. Run standalone or via the
dispatcher::

    python -m src.intelligence --component reference
    python -m src.intelligence.reference.run_reference --no-write
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
from src.intelligence.reference import (
    decisions,
    io,
    proposals,
    registry,
    reporting,
)
from src.intelligence.reference.policy import ReferencePolicy, load_policy
from src.intelligence.reference.validation import validate_upstream

DEFAULT_CONFIG = CONFIGS_DIR / "reference_governance.yaml"

log = logging.getLogger("reference")


@dataclass(frozen=True)
class UpstreamRuns:
    """Resolved completed upstream run directories."""

    sensor_health: Path
    incidents: Path
    drift: Path

    def run_ids(self) -> dict[str, str]:
        return {
            "sensor_health": self.sensor_health.name,
            "incidents": self.incidents.name,
            "drift": self.drift.name,
        }


@dataclass(frozen=True)
class ReferenceArtifacts:
    """Everything ``run()`` produces (no writes happen here)."""

    registry: pd.DataFrame
    proposals: pd.DataFrame
    quarantine: pd.DataFrame
    decision_log: pd.DataFrame
    residual: dict[str, Any]
    findings: list[Finding]
    manifest: dict[str, Any]
    report: str


def run(config_path: Path, runs: UpstreamRuns, run_id: str) -> ReferenceArtifacts:
    """Execute the full Reference Governance pipeline (pure; no writes)."""
    policy = load_policy(config_path)
    master_path = io.resolve_project_path(policy.upstream.master_path)
    master_sha256 = io.file_sha256(master_path)
    behaviour_manifest_path = io.resolve_project_path(
        policy.upstream.behaviour_manifest
    )
    behaviour_manifest = io.load_behaviour_manifest(behaviour_manifest_path)

    upstream_manifests = {
        "sensor_health": io.load_run_manifest(
            runs.sensor_health, io.SENSOR_HEALTH_MANIFEST
        ),
        "incidents": io.load_run_manifest(runs.incidents, io.INCIDENTS_MANIFEST),
        "drift": io.load_run_manifest(runs.drift, io.DRIFT_MANIFEST),
    }
    compat, findings = validate_upstream(
        master_sha256, behaviour_manifest, upstream_manifests, runs.run_ids()
    )

    recommendations = io.load_quarantine_recommendations(runs.sensor_health)
    sh_events = io.load_sensor_health_events(runs.sensor_health)
    incidents = io.load_incidents(runs.incidents)
    drift_events = io.load_drift_events(runs.drift)
    raw_vs_healthy = io.load_raw_vs_healthy(runs.drift)

    reference_registry = registry.build_registry(
        behaviour_manifest, master_sha256, str(behaviour_manifest_path)
    )
    quarantine = proposals.build_quarantine_proposals(
        recommendations,
        sh_events,
        incidents,
        drift_events,
        policy.quarantine.candidate_sensors,
    )
    residual = proposals.residual_diagnostic(
        raw_vs_healthy,
        policy.candidate_v2.residual_window_min,
        policy.candidate_v2.residual_fraction_min,
    )
    quarantine_sensors = quarantine["sensor"].astype(str).tolist()
    candidate_proposals = proposals.build_reference_proposals(
        quarantine_sensors, residual, incidents, drift_events
    )
    decision_log = decisions.build_decision_log(candidate_proposals, quarantine)

    findings.extend(
        reporting.build_findings(
            reference_registry, candidate_proposals, quarantine, residual
        )
    )
    manifest = _build_manifest(
        policy,
        run_id,
        runs,
        master_sha256,
        reference_registry,
        candidate_proposals,
        quarantine,
        decision_log,
        residual,
        compat,
    )
    report = reporting.render_report(
        reference_registry,
        candidate_proposals,
        quarantine,
        decision_log,
        residual,
        manifest,
    )
    log.info(
        "Reference governance: %d reference(s), %d quarantine proposal(s), "
        "%d candidate proposal(s), residual_material=%s",
        len(reference_registry),
        len(quarantine),
        len(candidate_proposals),
        residual["material"],
    )
    return ReferenceArtifacts(
        registry=reference_registry,
        proposals=candidate_proposals,
        quarantine=quarantine,
        decision_log=decision_log,
        residual=residual,
        findings=findings,
        manifest=manifest,
        report=report,
    )


def _build_manifest(
    policy: ReferencePolicy,
    run_id: str,
    runs: UpstreamRuns,
    master_sha256: str,
    reference_registry: pd.DataFrame,
    candidate_proposals: pd.DataFrame,
    quarantine: pd.DataFrame,
    decision_log: pd.DataFrame,
    residual: dict[str, Any],
    compat: dict[str, Any],
) -> dict[str, Any]:
    return {
        "component": "reference_governance",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "master_dataset_sha256": master_sha256,
        "sensor_health_run_id": runs.sensor_health.name,
        "incidents_run_id": runs.incidents.name,
        "drift_run_id": runs.drift.name,
        "reference_count": int(len(reference_registry)),
        "quarantine_proposal_count": int(len(quarantine)),
        "candidate_proposal_count": int(len(candidate_proposals)),
        "decision_log_rows": int(len(decision_log)),
        "approved_count": int(
            (quarantine["approved"] == True).sum() if len(quarantine) else 0  # noqa: E712
        ),
        "residual_diagnostic": dict(residual),
        "config_snapshot": policy.model_dump(),
        "compat_checks": compat,
        "statements": [
            "Reference Governance proposes and tracks decisions; it does not "
            "approve a quarantine or refit a model automatically.",
            "reference_v1 is the immutable baseline; its train window was not "
            "modified.",
            "Every proposal is pending_review with approved=False.",
            "No upstream artifact was modified or overwritten.",
        ],
        "generated_files": [],  # filled by main() at write time
        "completion_status": "pending",
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    for name in ("sensor-health", "incidents", "drift"):
        p.add_argument(
            f"--{name}-run",
            default=None,
            help=f"{name} run id to consume (default: policy pin / 'latest').",
        )
    p.add_argument(
        "--output-root",
        type=Path,
        default=io.REFERENCE_DIR,
        help="Component root; artifacts land under <root>/runs/<run_id>/.",
    )
    p.add_argument(
        "--run-id",
        default=None,
        help="Run identifier (default: fresh UTC timestamp; never overwrites).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Diagnostic only: run the full pipeline, write nothing.",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def _resolve_upstream_runs(
    args: argparse.Namespace, policy: ReferencePolicy
) -> UpstreamRuns:
    """Resolve all three upstream runs (CLI flag > policy pin > latest)."""
    upstream = policy.upstream
    spec = {
        "sensor_health": (
            upstream.sensor_health_root,
            args.sensor_health_run or upstream.sensor_health_run,
            io.SENSOR_HEALTH_MANIFEST,
        ),
        "incidents": (
            upstream.incidents_root,
            args.incidents_run or upstream.incidents_run,
            io.INCIDENTS_MANIFEST,
        ),
        "drift": (
            upstream.drift_root,
            args.drift_run or upstream.drift_run,
            io.DRIFT_MANIFEST,
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
        io.REGISTRY_FILE: art.registry,
        io.PROPOSALS_FILE: art.proposals,
        io.QUARANTINE_FILE: art.quarantine,
        io.DECISION_LOG_FILE: art.decision_log,
    }
    for rel_path, frame in table_map.items():
        io.write_table(frame, out / rel_path)
    write_json(art.findings, out / io.FINDINGS_JSON)
    (out / io.REPORT_MD).write_text(art.report, encoding="utf-8")

    manifest = dict(art.manifest)
    manifest["generated_files"] = [*table_map, io.FINDINGS_JSON, io.REPORT_MD]
    manifest["completion_status"] = "complete"
    # Manifest last: its presence marks the run as complete (resolvable).
    io.write_manifest(manifest, out / io.MANIFEST_NAME)
    log.info("Wrote reference governance run → %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
