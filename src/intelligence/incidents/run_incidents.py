"""CLI orchestrator for the Incident Aggregation component.

Linear order::

    resolve five upstream runs (drift / sensor-health / anomaly /
    operational context / BOM — completed runs only)
        → normalize sources into one candidate frame
        → group (type + family + temporal adjacency + affected-set gate)
        → suppress duplicates (transparently recorded)
        → relationships (associative, causality_status = unknown)
        → recommended actions (quarantine: approval_required, not approved)
        → review pack (prioritized, deduplicated, truncated)
        → drift-aware forensic addendum (read-only; --skip-addendum)
        → write run-versioned artifacts (manifest LAST)

This component never modifies upstream data, never approves quarantine and
never excludes sensors. Run standalone or via the dispatcher::

    python -m src.intelligence --component incidents
    python -m src.intelligence.incidents.run_incidents --no-write
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import CONFIGS_DIR
from src.intelligence._common.reporting import Finding, write_json
from src.intelligence.incidents import (
    actions as actions_mod,
)
from src.intelligence.incidents import (
    grouping,
    io,
    reporting,
)
from src.intelligence.incidents import (
    relationships as relationships_mod,
)
from src.intelligence.incidents import (
    review_pack as review_pack_mod,
)
from src.intelligence.incidents import (
    sources as sources_mod,
)
from src.intelligence.incidents.policy import IncidentsPolicy, load_policy
from src.intelligence.incidents.validation import validate_upstream

DEFAULT_CONFIG = CONFIGS_DIR / "incidents_intelligence.yaml"

log = logging.getLogger("incidents")


@dataclass(frozen=True)
class IncidentArtifacts:
    """Everything ``run()`` produces (no writes happen here)."""

    incidents: pd.DataFrame
    relationships: pd.DataFrame
    review_pack: pd.DataFrame
    timeline: pd.DataFrame
    summary: pd.DataFrame
    actions: pd.DataFrame
    suppressed: pd.DataFrame
    unsupported: pd.DataFrame
    findings: list[Finding]
    manifest: dict[str, Any]
    report: str
    addendum_inputs: dict[str, Any]


@dataclass(frozen=True)
class UpstreamRuns:
    """Resolved completed upstream run directories."""

    drift: Path
    sensor_health: Path
    anomaly: Path
    operational: Path
    bom: Path

    def run_ids(self) -> dict[str, str]:
        return {
            "drift": self.drift.name,
            "sensor_health": self.sensor_health.name,
            "anomaly": self.anomaly.name,
            "operational": self.operational.name,
            "bom": self.bom.name,
        }


def _collect_candidates(
    runs: UpstreamRuns, policy: IncidentsPolicy
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame], list[tuple[str, str]]]:
    """Load + normalize every source; report empty sources transparently."""
    missing: list[tuple[str, str]] = []
    drift_events, comparison = io.load_drift_artifacts(runs.drift)
    sh_events, quarantine = io.load_sensor_health_events(runs.sensor_health)
    anomaly_scores = io.load_anomaly_scores(runs.anomaly)
    op_timeline, op_transitions = io.load_operational_artifacts(runs.operational)
    bom_transitions = io.load_bom_transitions(runs.bom)

    frames = {
        "sensor_health": sources_mod.from_sensor_health(sh_events),
        "drift": sources_mod.from_drift(drift_events),
        "anomaly": sources_mod.anomaly_bursts(anomaly_scores, policy),
        "operational_context": sources_mod.from_context_transitions(
            op_transitions, policy
        ),
        "bom_context": sources_mod.from_bom_transitions(bom_transitions),
    }
    for source, frame in frames.items():
        if not len(frame):
            missing.append((source, "no_candidate_events"))
    candidates = pd.concat(frames.values(), ignore_index=True)
    extras = {
        "drift_events": drift_events,
        "comparison": comparison,
        "quarantine": quarantine,
        "op_timeline": op_timeline,
        "anomaly_scores": anomaly_scores,
    }
    return candidates, op_timeline, extras, missing


def run(
    config_path: Path,
    runs: UpstreamRuns,
    run_id: str,
) -> IncidentArtifacts:
    """Execute the full Incident Aggregation pipeline (pure; no writes)."""
    policy = load_policy(config_path)

    t0 = time.perf_counter()
    candidates, op_timeline, extras, missing = _collect_candidates(runs, policy)
    manifests = {
        "drift": io.load_run_manifest(runs.drift, io.DRIFT_MANIFEST),
        "sensor_health": io.load_run_manifest(
            runs.sensor_health, io.SENSOR_HEALTH_MANIFEST
        ),
        "anomaly": io.load_run_manifest(runs.anomaly, io.ANOMALY_MANIFEST),
        "operational": io.load_run_manifest(runs.operational, io.OPERATIONAL_MANIFEST),
        "bom": io.load_run_manifest(runs.bom, io.BOM_MANIFEST),
    }
    compat, findings = validate_upstream(manifests, runs.run_ids())
    log.info(
        "Loaded %d candidate events from %d sources (%.1fs); upstream runs: %s",
        len(candidates),
        5 - len(missing),
        time.perf_counter() - t0,
        runs.run_ids(),
    )

    data_end = (
        pd.DatetimeIndex(extras["op_timeline"].index).max()
        if len(extras["op_timeline"])
        else candidates["end_timestamp"].max()
    )

    t0 = time.perf_counter()
    incidents = grouping.group_candidates(candidates, policy, data_end)
    incidents = grouping.collapse_recurring(incidents, policy, data_end)
    incidents = grouping.merge_cross_source(incidents, policy)
    incidents, suppressed = grouping.suppress_duplicates(incidents, policy)
    relationships = relationships_mod.detect(incidents, policy)
    actions = actions_mod.recommend(incidents, policy)
    pack = review_pack_mod.build(incidents, relationships, actions, op_timeline, policy)
    log.info(
        "Stage %-12s: %d incidents (%d suppressed), %d relationships, "
        "%d actions, review pack %d rows (%.1fs)",
        "aggregation",
        len(incidents),
        len(suppressed),
        len(relationships),
        len(actions),
        len(pack),
        time.perf_counter() - t0,
    )

    summary = reporting.incident_summary(incidents)
    timeline = reporting.incident_timeline(incidents)
    unsupported = sources_mod.unsupported_sources(missing)
    findings.extend(reporting.build_findings(incidents, suppressed, relationships))
    manifest = _build_manifest(
        policy,
        run_id,
        runs,
        candidates,
        incidents,
        relationships,
        suppressed,
        actions,
        pack,
        compat,
    )
    report = reporting.render_report(
        incidents, summary, suppressed, relationships, pack, manifest
    )
    return IncidentArtifacts(
        incidents=incidents,
        relationships=relationships,
        review_pack=pack,
        timeline=timeline,
        summary=summary,
        actions=actions,
        suppressed=suppressed,
        unsupported=unsupported,
        findings=findings,
        manifest=manifest,
        report=report,
        addendum_inputs={
            "drift_events": extras["drift_events"],
            "comparison": extras["comparison"],
            "op_timeline": op_timeline,
            "drift_manifest": manifests["drift"],
        },
    )


def _build_manifest(
    policy: IncidentsPolicy,
    run_id: str,
    runs: UpstreamRuns,
    candidates: pd.DataFrame,
    incidents: pd.DataFrame,
    relationships: pd.DataFrame,
    suppressed: pd.DataFrame,
    actions: pd.DataFrame,
    pack: pd.DataFrame,
    compat: dict[str, Any],
) -> dict[str, Any]:
    source_counts = (
        candidates["source"].value_counts().astype(int).to_dict()
        if len(candidates)
        else {}
    )
    incident_counts: dict[str, Any] = {"total": int(len(incidents))}
    if len(incidents):
        incident_counts["by_type"] = (
            incidents["incident_type"].value_counts().astype(int).to_dict()
        )
        incident_counts["by_status"] = (
            incidents["status"].value_counts().astype(int).to_dict()
        )
        incident_counts["persistent"] = int(incidents["is_persistent"].sum())
    return {
        "component": "incidents",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "drift_run_id": runs.drift.name,
        "sensor_health_run_id": runs.sensor_health.name,
        "anomaly_run_id": runs.anomaly.name,
        "operational_context_run_id": runs.operational.name,
        "bom_context_run_id": runs.bom.name,
        "source_event_counts": source_counts,
        "incident_counts": incident_counts,
        "relationship_counts": int(len(relationships)),
        "suppressed_duplicate_counts": int(len(suppressed)),
        "recommended_action_counts": int(len(actions)),
        "review_pack_rows": int(len(pack)),
        "config_snapshot": policy.model_dump(),
        "compat_checks": compat,
        "statements": [
            "Incident relationships are associative and temporal; they do "
            "not establish causality (causality_status=unknown).",
            "No sensor was excluded automatically; no quarantine "
            "recommendation was approved (approval_required=True, "
            "approved=False).",
            "No upstream artifact was modified or overwritten.",
        ],
        "generated_files": [],  # filled by main() at write time
        "completion_status": "pending",
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    for name in ("drift", "sensor-health", "anomaly", "operational", "bom"):
        p.add_argument(
            f"--{name}-run",
            default=None,
            help=f"{name} run id to consume (default: policy pin / 'latest').",
        )
    p.add_argument(
        "--output-root",
        type=Path,
        default=io.INCIDENTS_DIR,
        help="Component root; artifacts land under <root>/runs/<run_id>/.",
    )
    p.add_argument(
        "--addendum-root",
        type=Path,
        default=None,
        help="Forensic addendum root (default: policy output_root).",
    )
    p.add_argument(
        "--run-id",
        default=None,
        help="Run identifier (default: fresh UTC timestamp; never overwrites).",
    )
    p.add_argument(
        "--skip-addendum",
        action="store_true",
        help="Skip the drift-aware forensic addendum stage.",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Diagnostic only: run the full pipeline, write nothing.",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def _resolve_upstream_runs(
    args: argparse.Namespace, policy: IncidentsPolicy
) -> UpstreamRuns:
    """Resolve all five upstream runs (CLI flag > policy pin > latest)."""
    upstream = policy.upstream
    spec = {
        "drift": (
            upstream.drift_root,
            args.drift_run or upstream.drift_run,
            io.DRIFT_MANIFEST,
        ),
        "sensor_health": (
            upstream.sensor_health_root,
            args.sensor_health_run or upstream.sensor_health_run,
            io.SENSOR_HEALTH_MANIFEST,
        ),
        "anomaly": (
            upstream.anomaly_root,
            args.anomaly_run or upstream.anomaly_run,
            io.ANOMALY_MANIFEST,
        ),
        "operational": (
            upstream.operational_root,
            args.operational_run or upstream.operational_run,
            io.OPERATIONAL_MANIFEST,
        ),
        "bom": (upstream.bom_root, args.bom_run or upstream.bom_run, io.BOM_MANIFEST),
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

    out = io.create_run_dir(args.output_root, run_id)
    table_map = {
        io.INCIDENTS_FILE: art.incidents,
        io.RELATIONSHIPS_FILE: art.relationships,
        io.REVIEW_PACK_FILE: art.review_pack,
        io.TIMELINE_FILE: art.timeline,
        io.SUMMARY_FILE: art.summary,
        io.ACTIONS_FILE: art.actions,
        io.SUPPRESSED_FILE: art.suppressed,
        io.UNSUPPORTED_FILE: art.unsupported,
    }
    for rel_path, frame in table_map.items():
        io.write_table(frame, out / rel_path)
    write_json(art.findings, out / io.FINDINGS_JSON)
    (out / io.REPORT_MD).write_text(art.report, encoding="utf-8")

    generated = [str(p) for p in table_map] + [io.FINDINGS_JSON, io.REPORT_MD]
    addendum_status = "skipped"
    if policy.forensic_addendum.enabled and not args.skip_addendum:
        # Lazy import: matplotlib loads only when the addendum actually runs.
        from src.intelligence.incidents import drift_addendum

        addendum_root = args.addendum_root or io.resolve_project_path(
            policy.forensic_addendum.output_root
        )
        addendum_out = addendum_root / run_id
        addendum_art = drift_addendum.build_addendum(
            art.addendum_inputs["drift_events"],
            art.addendum_inputs["comparison"],
            art.incidents,
            art.review_pack,
            art.timeline,
            art.addendum_inputs["op_timeline"],
            art.addendum_inputs["drift_manifest"],
            policy,
            run_id,
            art.manifest["compat_checks"]["run_ids"],
        )
        addendum_files = drift_addendum.write_addendum(addendum_art, addendum_out)
        generated += [str(addendum_out / f) for f in addendum_files]
        addendum_status = "complete"
        log.info("Wrote drift-aware forensic addendum → %s", addendum_out)

    manifest = dict(art.manifest)
    manifest["generated_files"] = generated
    manifest["addendum_status"] = addendum_status
    manifest["completion_status"] = "complete"
    # Manifest last: its presence marks the run as complete (resolvable).
    io.write_manifest(manifest, out / io.MANIFEST_NAME)
    log.info("Wrote incidents run → %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
