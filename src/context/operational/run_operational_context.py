"""CLI orchestrator for the Operational Context Overlay.

Linear order::

    load master steam columns (column-projected) + behaviour labels
        + completed sensor-health run (quality timeline)
        + completed BOM context run (timeline)
        → Gate A: exact master alignment + train-window coherence
        → derive steam context (persistence-windowed, never single-row)
        → assemble the master-aligned overlay (BOM columns preserved)
        → context transitions
        → summaries + report
        → context-aware forensic addendum (read-only join, optional)
        → write run-versioned artifacts (manifest LAST)

Context engineering only: never modifies the master dataset or BOM
artifacts, never refits Intelligence-Layer models, never changes
thresholds. Run standalone::

    python -m src.context.operational --config configs/operational_context.yaml
    python -m src.context.operational --no-write --log-level DEBUG
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
from src.context.operational import (
    bom,
    io,
    overlay,
    reporting,
    steam,
    transitions,
    validation,
)
from src.context.operational import sensor_health as health
from src.context.operational.forensic_addendum import (
    AddendumArtifacts,
    build_addendum,
    write_addendum,
)
from src.context.operational.policy import OperationalContextPolicy, load_policy
from src.intelligence._common.upstream import (
    BEHAVIOUR_MANIFEST_NAME,
    PROFILE_LABELS_FILE,
    align_labels,
    load_behaviour_manifest,
    load_profile_labels,
    resolve_behaviour_run,
)
from src.preprocessing._common.reporting import Finding, write_json

DEFAULT_CONFIG = CONFIGS_DIR / "operational_context.yaml"

log = logging.getLogger("operational_context")


@dataclass(frozen=True)
class OperationalContextArtifacts:
    """Everything ``run()`` produces (no writes happen here)."""

    timeline: pd.DataFrame
    transitions: pd.DataFrame
    summaries: dict[str, pd.DataFrame]
    findings: list[Finding]
    manifest: dict[str, Any]
    report: str
    addendum: AddendumArtifacts | None


def _build_manifest(
    policy: OperationalContextPolicy,
    run_id: str,
    paths: dict[str, Any],
    art: dict[str, Any],
) -> dict[str, Any]:
    timeline = art["timeline"]
    return {
        "component": "operational_context",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "master_dataset_path": str(paths["master"]),
        "master_dataset_sha256": io.file_sha256(paths["master"]),
        "behaviour_artifact_path": str(paths["labels"]),
        "sensor_health_run_id": paths["sensor_health_dir"].name,
        "sensor_health_manifest_path": str(
            paths["sensor_health_dir"] / io.SENSOR_HEALTH_MANIFEST
        ),
        "bom_context_run_id": paths["bom_dir"].name,
        "bom_context_manifest_path": str(paths["bom_dir"] / io.BOM_MANIFEST),
        "timeline_row_count": int(len(timeline)),
        "context_status_counts": timeline["bom_context_status"]
        .value_counts()
        .to_dict(),
        "steam_context_counts": timeline["steam_context"].value_counts().to_dict(),
        "sensor_health_context_counts": timeline["sensor_health_context"]
        .value_counts()
        .to_dict(),
        "transition_counts": {
            "total": int(len(art["transitions"])),
            "by_type": art["transition_type_counts"],
        },
        "compat_checks": art["compat"],
        "addendum": art["addendum_status"],
        "config_snapshot": policy.model_dump(),
        "statements": [
            "No model was refitted; no thresholds were modified.",
            "The master dataset and the BOM artifacts were not modified.",
            "Steam/sensor-health/BOM contexts are interpretation metadata; "
            "they are not model inputs.",
        ],
        "generated_files": [],  # filled by main() at write time
        "completion_status": "pending",
    }


def run(
    master_path: Path,
    policy: OperationalContextPolicy,
    run_id: str,
    sensor_health_dir: Path,
    bom_dir: Path,
    anomaly_dir: Path | None,
    forensic_dir: Path | None,
) -> OperationalContextArtifacts:
    """Execute the full operational-context pipeline (pure; no writes)."""
    t0 = time.perf_counter()
    steam_cols = [policy.steam.pressure_sensor, policy.steam.temp_sensor]
    steam_cols += list(policy.steam.auxiliary_sensors)
    df = io.load_master_columns(master_path, steam_cols)
    labels_cfg = policy.upstream.profile_labels_path
    manifest_cfg = policy.upstream.behaviour_manifest_path
    # Empty config paths -> resolve the latest completed behaviour run.
    if labels_cfg and manifest_cfg:
        labels_path = io.resolve_project_path(labels_cfg)
        manifest_path = io.resolve_project_path(manifest_cfg)
    else:
        behaviour_run = resolve_behaviour_run()
        labels_path = (
            io.resolve_project_path(labels_cfg)
            if labels_cfg
            else behaviour_run / PROFILE_LABELS_FILE
        )
        manifest_path = (
            io.resolve_project_path(manifest_cfg)
            if manifest_cfg
            else behaviour_run / BEHAVIOUR_MANIFEST_NAME
        )
    labels_frame = load_profile_labels(labels_path)
    behaviour_manifest = load_behaviour_manifest(manifest_path)
    try:
        profile, train_mask = align_labels(df, labels_frame)
    except ValueError as exc:
        raise validation.OperationalContextBlockerError(str(exc)) from exc
    health_timeline, sh_manifest = health.load_sensor_quality_timeline(
        sensor_health_dir
    )
    bom_timeline, bom_manifest = bom.load_bom_timeline(bom_dir)
    master_ts = pd.Series(df.index, name="timestamp")
    compat = validation.validate_upstream(
        master_ts,
        policy.timeline.expected_master_rows,
        health_timeline,
        bom_timeline,
        behaviour_manifest,
        sh_manifest,
    )
    log.info(
        "Gate A passed: %d rows aligned across master/health/bom (%.1fs)",
        len(master_ts),
        time.perf_counter() - t0,
    )

    t0 = time.perf_counter()
    indicator = steam.steam_activity_indicator(df, policy.steam)
    steam_ctx = steam.classify_steam_context(indicator, df, policy.steam)
    log.info(
        "Stage %-12s: %s (%.1fs)",
        "steam",
        steam_ctx["steam_context"].value_counts().to_dict(),
        time.perf_counter() - t0,
    )

    t0 = time.perf_counter()
    timeline = overlay.build_overlay(
        master_ts,
        profile,
        train_mask,
        steam_ctx,
        health_timeline,
        bom_timeline,
        policy.context_key,
    )
    validation.validate_overlay(timeline, master_ts)
    transition_events = transitions.detect_transitions(timeline, policy.transitions)
    type_counts = (
        transition_events["transition_types"]
        .str.split("|")
        .explode()
        .value_counts()
        .to_dict()
        if len(transition_events)
        else {}
    )
    log.info(
        "Stage %-12s: %d rows, %d transitions (%.1fs)",
        "overlay",
        len(timeline),
        len(transition_events),
        time.perf_counter() - t0,
    )

    summaries = {
        "steam": reporting.dimension_summary(timeline, "steam_context"),
        "health": reporting.dimension_summary(timeline, "sensor_health_context"),
        "bom": reporting.dimension_summary(timeline, "bom_context_status"),
        "coverage": reporting.coverage_summary(timeline),
    }
    findings = reporting.build_findings(timeline, transition_events)

    addendum: AddendumArtifacts | None = None
    addendum_status = "skipped"
    if anomaly_dir is not None and forensic_dir is not None:
        t0 = time.perf_counter()
        addendum = build_addendum(
            timeline, transition_events, policy, run_id, anomaly_dir, forensic_dir
        )
        addendum_status = f"built (anomaly run {anomaly_dir.name})"
        log.info("Stage %-12s: done (%.1fs)", "addendum", time.perf_counter() - t0)

    manifest = _build_manifest(
        policy,
        run_id,
        {
            "master": master_path,
            "labels": labels_path,
            "sensor_health_dir": sensor_health_dir,
            "bom_dir": bom_dir,
        },
        {
            "timeline": timeline,
            "transitions": transition_events,
            "transition_type_counts": type_counts,
            "compat": compat,
            "addendum_status": addendum_status,
        },
    )
    report = reporting.render_report(
        timeline,
        transition_events,
        summaries,
        manifest,
        policy.forensic_addendum.candidate_dates,
        policy.forensic_addendum.window_hours,
    )
    return OperationalContextArtifacts(
        timeline=timeline,
        transitions=transition_events,
        summaries=summaries,
        findings=findings,
        manifest=manifest,
        report=report,
        addendum=addendum,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument(
        "--master", type=Path, default=None, help="Master parquet (default: policy)."
    )
    p.add_argument(
        "--sensor-health-run",
        default=None,
        help="Sensor-health run id (default: policy; 'latest' supported).",
    )
    p.add_argument(
        "--bom-run",
        default=None,
        help="BOM context run id (default: policy; 'latest' supported).",
    )
    p.add_argument(
        "--anomaly-run",
        default=None,
        help=(
            "Anomaly run id for the forensic addendum (default: policy pin; "
            "'latest' supported). Lets the addendum be regenerated against the "
            "canonical rematerialized chain. Ignored with --skip-addendum."
        ),
    )
    p.add_argument(
        "--forensic-run",
        default=None,
        help=(
            "Forensic run id for the forensic addendum (default: policy pin; "
            "'latest' supported). Ignored with --skip-addendum."
        ),
    )
    p.add_argument(
        "--output-root",
        type=Path,
        default=io.OPERATIONAL_DIR,
        help="Component root; artifacts land under <root>/runs/<run_id>/.",
    )
    p.add_argument(
        "--addendum-root",
        type=Path,
        default=None,
        help="Addendum output root (default: policy forensic_addendum.output_root).",
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
    p.add_argument(
        "--skip-addendum",
        action="store_true",
        help="Skip the context-aware forensic addendum.",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def _resolve_addendum_run(
    root: str,
    run_id: str,
    manifest_name: str,
    *,
    kind: str,
    expected_component: str | None = None,
) -> Path:
    """Resolve an addendum upstream run, failing closed with a clear message.

    The forensic addendum must never silently consume a stale or pre-hardening
    run: when the pinned/overridden run cannot be resolved (missing manifest,
    not a completed run, or wrong component), raise an actionable error naming
    the run and the override flag rather than letting a bare ``FileNotFoundError``
    surface. ``--skip-addendum`` bypasses this path entirely.
    """
    try:
        return io.resolve_run(
            io.resolve_project_path(root),
            run_id,
            manifest_name,
            expected_component=expected_component,
        )
    except FileNotFoundError as exc:
        raise validation.OperationalContextBlockerError(
            f"Forensic addendum requested but the {kind} run {run_id!r} under "
            f"{root} is unresolvable (missing/invalid {manifest_name}). Pass "
            f"--{kind}-run with a completed run from the canonical chain, or use "
            "--skip-addendum."
        ) from exc


def _resolve_upstream_dirs(
    policy: OperationalContextPolicy, args: argparse.Namespace
) -> tuple[Path, Path, Path | None, Path | None]:
    """Resolve every run-versioned upstream to a completed run directory."""
    up = policy.upstream
    sensor_health_dir = io.resolve_run(
        io.resolve_project_path(up.sensor_health_root),
        args.sensor_health_run or up.sensor_health_run,
        io.SENSOR_HEALTH_MANIFEST,
        expected_component="sensor_health",
    )
    bom_dir = io.resolve_run(
        io.resolve_project_path(up.bom_root),
        args.bom_run or up.bom_run,
        io.BOM_MANIFEST,
        expected_component="bom_context",
    )
    anomaly_dir: Path | None = None
    forensic_dir: Path | None = None
    if policy.forensic_addendum.enabled and not args.skip_addendum:
        # CLI override beats the config pin so the addendum can be regenerated
        # against the canonical rematerialized chain. The forensic manifest's
        # component string is not uniform across its writers, so it is resolved
        # without an expected_component check (see docs/dashboard contract).
        anomaly_dir = _resolve_addendum_run(
            up.anomaly_root,
            args.anomaly_run or up.anomaly_run,
            "anomaly_fit_manifest.json",
            kind="anomaly",
            expected_component="anomaly",
        )
        forensic_dir = _resolve_addendum_run(
            up.forensic_root,
            args.forensic_run or up.forensic_run,
            "forensic_manifest.json",
            kind="forensic",
        )
    return sensor_health_dir, bom_dir, anomaly_dir, forensic_dir


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    policy = load_policy(args.config)
    master_path = args.master or io.resolve_project_path(policy.timeline.master_path)
    sensor_health_dir, bom_dir, anomaly_dir, forensic_dir = _resolve_upstream_dirs(
        policy, args
    )
    run_id = args.run_id or io.new_run_id(args.output_root)

    art = run(
        master_path,
        policy,
        run_id,
        sensor_health_dir,
        bom_dir,
        anomaly_dir,
        forensic_dir,
    )

    if args.no_write:
        log.info(
            "--no-write: skipping all artifacts (%d findings; run id %s unused)",
            len(art.findings),
            run_id,
        )
        return 0

    out = io.create_run_dir(args.output_root, run_id)
    table_map = {
        io.TIMELINE_FILE: art.timeline,
        io.TRANSITIONS_FILE: art.transitions,
        io.STEAM_SUMMARY_FILE: art.summaries["steam"],
        io.HEALTH_SUMMARY_FILE: art.summaries["health"],
        io.BOM_SUMMARY_FILE: art.summaries["bom"],
        io.COVERAGE_FILE: art.summaries["coverage"],
    }
    for rel_path, frame in table_map.items():
        io.write_table(frame, out / rel_path)
    write_json(art.findings, out / io.FINDINGS_JSON)
    (out / io.REPORT_MD).write_text(art.report, encoding="utf-8")
    generated = [str(p) for p in table_map] + [io.FINDINGS_JSON, io.REPORT_MD]

    if art.addendum is not None:
        addendum_root = args.addendum_root or io.resolve_project_path(
            policy.forensic_addendum.output_root
        )
        addendum_out = addendum_root / run_id
        addendum_files = write_addendum(art.addendum, addendum_out)
        generated += [f"{addendum_out}/{name}" for name in addendum_files]
        log.info("Wrote context forensic addendum → %s", addendum_out)

    # Manifest last: its presence marks the run as complete (resolvable).
    manifest = dict(art.manifest)
    manifest["generated_files"] = generated
    manifest["completion_status"] = "complete"
    io.write_manifest(manifest, out / io.MANIFEST_NAME)
    log.info("Wrote operational-context run → %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
