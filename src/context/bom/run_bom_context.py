"""CLI orchestrator for the BOM Operational Context Layer.

Linear order::

    read raw CSV (str-typed, traceable)
        → Stage A: required-column gate + raw quality assessment
        → Stage B: normalize components (+ rejected / duplicate side tables)
        → Stage C: aggregate orders + bom_signature / recipe_context_key
        → Stage D: overlaps, gaps, classified transitions
        → Stage E: master-aligned context timeline (hard alignment gate)
        → Stage F: product / recipe / signature / coverage summaries
        → Stage G: forensic candidate-date event windows
        → Stage H: BOM-aware forensic addendum (read-only join, optional)
        → write run-versioned artifacts (manifest LAST)

Context engineering only: never modifies the master dataset, never refits
Intelligence-Layer models, never changes thresholds or profiles. Outputs are
run-versioned and never overwrite earlier runs: see
:mod:`src.context.bom.io`. Run standalone::

    python -m src.context.bom --config configs/bom_context.yaml
    python -m src.context.bom --no-write --log-level DEBUG
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import CONFIGS_DIR, PROJECT_ROOT
from src.context.bom import aggregate, io, normalize, reporting, timeline, validation
from src.context.bom.forensic_addendum import (
    AddendumArtifacts,
    build_addendum,
    write_addendum,
)
from src.context.bom.policy import BomContextPolicy, load_policy
from src.preprocessing._common.reporting import Finding, write_json

DEFAULT_CONFIG = CONFIGS_DIR / "bom_context.yaml"

log = logging.getLogger("bom_context")


@dataclass(frozen=True)
class BomContextArtifacts:
    """Everything ``run()`` produces (no writes happen here)."""

    components: pd.DataFrame
    rejected: pd.DataFrame
    duplicates: pd.DataFrame
    orders: pd.DataFrame
    overlaps: pd.DataFrame
    gaps: pd.DataFrame
    transitions: pd.DataFrame
    context_timeline: pd.DataFrame
    summaries: dict[str, pd.DataFrame]
    events: pd.DataFrame
    findings: list[Finding]
    manifest: dict[str, Any]
    quality_report: str
    context_report: str
    addendum: AddendumArtifacts | None


def _code_version() -> str | None:
    """Current git commit (short), or ``None`` outside a git checkout."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip()


def _build_manifest(
    policy: BomContextPolicy,
    run_id: str,
    csv_path: Path,
    master_path: Path,
    art: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the run manifest (spec §14); written LAST by ``main``."""
    coverage = art["coverage"]
    status_counts = dict(
        zip(
            coverage["bom_context_status"],
            coverage["row_count"].astype(int),
            strict=True,
        )
    )
    coverage_pct = dict(
        zip(
            coverage["bom_context_status"],
            coverage["percentage"].astype(float),
            strict=True,
        )
    )
    orders = art["orders"]
    return {
        "component": "bom_context",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "source_csv": str(csv_path),
        "source_sha256": io.file_sha256(csv_path),
        "master_dataset_path": str(master_path),
        "master_dataset_sha256": io.file_sha256(master_path),
        "raw_row_count": art["raw_stats"]["row_count"],
        "normalized_component_row_count": art["normalize_stats"]["component_row_count"],
        "rejected_row_count": art["normalize_stats"]["rejected_row_count"],
        "duplicate_row_count": art["normalize_stats"]["duplicate_row_count"],
        "order_count": int(len(orders)),
        "product_count": int(orders["product_code"].nunique(dropna=True)),
        "recipe_version_count": int(orders["recipe_version"].nunique(dropna=True)),
        "bom_signature_count": int(orders["bom_signature"].nunique(dropna=True)),
        "master_timeline_row_count": int(len(art["context_timeline"])),
        "context_status_counts": status_counts,
        "coverage_percentages": coverage_pct,
        "overlap_count": int(len(art["overlaps"])),
        "gap_count": int(len(art["gaps"])),
        "transition_count": int(len(art["transitions"])),
        "raw_quality": art["raw_stats"],
        "coverage_vs_master": art["coverage_stats"],
        "addendum": art["addendum_status"],
        "config_snapshot": policy.model_dump(),
        "code_version": _code_version(),
        "generated_files": [],  # filled by main() at write time
        "completion_status": "pending",
    }


def run(
    csv_path: Path,
    master_path: Path,
    policy: BomContextPolicy,
    run_id: str,
    anomaly_dir: Path | None,
    forensic_dir: Path | None,
) -> BomContextArtifacts:
    """Execute the full BOM context pipeline (pure; no writes)."""
    findings: list[Finding] = []

    t0 = time.perf_counter()
    raw = io.read_raw_csv(csv_path, policy.raw_input)
    validation.check_required_columns(raw, policy.raw_input.columns)
    raw_stats, raw_findings = validation.assess_raw_quality(raw, policy)
    findings.extend(raw_findings)
    log.info(
        "Stage %-12s: %d raw rows (%.1fs)",
        "A:inspect",
        len(raw),
        time.perf_counter() - t0,
    )

    t0 = time.perf_counter()
    norm = normalize.normalize(raw, policy)
    findings.extend(norm.findings)
    log.info(
        "Stage %-12s: %d components, %d rejected, %d duplicates (%.1fs)",
        "B:normalize",
        len(norm.components),
        len(norm.rejected),
        len(norm.duplicates),
        time.perf_counter() - t0,
    )

    t0 = time.perf_counter()
    orders, order_findings = aggregate.aggregate_orders(norm.components, policy)
    findings.extend(order_findings)
    overlaps = aggregate.detect_overlaps(orders)
    orders = aggregate.attach_overlaps(orders, overlaps)
    gaps = aggregate.detect_gaps(orders, policy.timeline.gap_tolerance_seconds)
    transitions = aggregate.classify_transitions(
        orders, policy.timeline.gap_tolerance_seconds
    )
    log.info(
        "Stage %-12s: %d orders, %d overlaps, %d gaps, %d transitions (%.1fs)",
        "C+D:orders",
        len(orders),
        len(overlaps),
        len(gaps),
        len(transitions),
        time.perf_counter() - t0,
    )

    t0 = time.perf_counter()
    master_ts = io.load_master_timestamps(master_path)
    coverage_stats, coverage_findings = validation.assess_coverage(orders, master_ts)
    findings.extend(coverage_findings)
    context_timeline, tl_findings = timeline.build_context_timeline(orders, master_ts)
    findings.extend(tl_findings)
    validation.validate_timeline(
        context_timeline, master_ts, policy.timeline.expected_master_rows
    )
    log.info(
        "Stage %-12s: %d rows aligned to master (%.1fs)",
        "E:timeline",
        len(context_timeline),
        time.perf_counter() - t0,
    )

    summaries = {
        "product": aggregate.product_summary(orders),
        "recipe": aggregate.recipe_summary(orders),
        "signature": aggregate.signature_summary(orders),
        "coverage": aggregate.coverage_summary(context_timeline),
    }
    events = timeline.event_windows(
        orders, transitions, overlaps, gaps, norm.components, policy.forensic_windows
    )

    addendum: AddendumArtifacts | None = None
    addendum_status = "skipped"
    if anomaly_dir is not None and forensic_dir is not None:
        t0 = time.perf_counter()
        addendum = build_addendum(
            context_timeline,
            orders,
            transitions,
            events,
            policy,
            run_id,
            anomaly_dir,
            forensic_dir,
        )
        addendum_status = f"built (anomaly run {anomaly_dir.name})"
        log.info("Stage %-12s: done (%.1fs)", "H:addendum", time.perf_counter() - t0)

    manifest = _build_manifest(
        policy,
        run_id,
        csv_path,
        master_path,
        {
            "raw_stats": raw_stats,
            "normalize_stats": norm.stats,
            "orders": orders,
            "overlaps": overlaps,
            "gaps": gaps,
            "transitions": transitions,
            "context_timeline": context_timeline,
            "coverage": summaries["coverage"],
            "coverage_stats": coverage_stats,
            "addendum_status": addendum_status,
        },
    )
    return BomContextArtifacts(
        components=norm.components,
        rejected=norm.rejected,
        duplicates=norm.duplicates,
        orders=orders,
        overlaps=overlaps,
        gaps=gaps,
        transitions=transitions,
        context_timeline=context_timeline,
        summaries=summaries,
        events=events,
        findings=findings,
        manifest=manifest,
        quality_report=reporting.render_quality_report(raw_stats, norm.stats, findings),
        context_report=reporting.render_context_report(
            manifest, orders, overlaps, gaps, transitions, summaries["coverage"], events
        ),
        addendum=addendum,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument(
        "--csv", type=Path, default=None, help="Raw BOM CSV (default: policy path)."
    )
    p.add_argument(
        "--master",
        type=Path,
        default=None,
        help="Master dataset parquet (default: policy path).",
    )
    p.add_argument(
        "--output-root",
        type=Path,
        default=io.BOM_DIR,
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
        help="Skip the Stage H BOM-aware forensic addendum.",
    )
    p.add_argument(
        "--anomaly-run",
        default=None,
        help=(
            "Anomaly run id for the Stage H addendum (default: policy pin; "
            "'latest' supported). Lets the addendum be regenerated against the "
            "canonical rematerialized chain. Ignored with --skip-addendum."
        ),
    )
    p.add_argument(
        "--forensic-run",
        default=None,
        help=(
            "Forensic run id for the Stage H addendum (default: policy pin; "
            "'latest' supported). Ignored with --skip-addendum."
        ),
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def _write_artifacts(out: Path, art: BomContextArtifacts) -> list[str]:
    """Persist every table and report; the manifest is NOT written here."""
    table_map = {
        io.COMPONENTS_FILE: art.components,
        io.REJECTED_FILE: art.rejected,
        io.DUPLICATES_FILE: art.duplicates,
        io.ORDERS_FILE: art.orders,
        io.OVERLAPS_FILE: art.overlaps,
        io.GAPS_FILE: art.gaps,
        io.TRANSITIONS_FILE: art.transitions,
        io.TIMELINE_FILE: art.context_timeline,
        io.PRODUCT_SUMMARY_FILE: art.summaries["product"],
        io.RECIPE_SUMMARY_FILE: art.summaries["recipe"],
        io.SIGNATURE_SUMMARY_FILE: art.summaries["signature"],
        io.COVERAGE_FILE: art.summaries["coverage"],
        io.EVENT_CONTEXT_FILE: art.events,
    }
    for rel_path, frame in table_map.items():
        io.write_table(frame, out / rel_path)
    write_json(art.findings, out / io.FINDINGS_JSON)
    (out / io.QUALITY_REPORT_MD).write_text(art.quality_report, encoding="utf-8")
    (out / io.CONTEXT_REPORT_MD).write_text(art.context_report, encoding="utf-8")
    return [str(p) for p in table_map] + [
        io.FINDINGS_JSON,
        io.QUALITY_REPORT_MD,
        io.CONTEXT_REPORT_MD,
    ]


def _resolve_addendum_run(
    root: str,
    run_id: str,
    manifest_name: str,
    *,
    kind: str,
    expected_component: str | None = None,
) -> Path:
    """Resolve a Stage H upstream run, failing closed with a clear message.

    The addendum must never silently consume a stale or pre-hardening run:
    when the pinned/overridden run cannot be resolved, raise an actionable
    error naming the run and the override flag. ``--skip-addendum`` bypasses
    this path entirely.
    """
    try:
        return io.resolve_run(
            io.resolve_project_path(root),
            run_id,
            manifest_name,
            expected_component=expected_component,
        )
    except FileNotFoundError as exc:
        raise validation.BomContextBlockerError(
            f"Stage H addendum requested but the {kind} run {run_id!r} under "
            f"{root} is unresolvable (missing/invalid {manifest_name}). Pass "
            f"--{kind}-run with a completed run from the canonical chain, or use "
            "--skip-addendum."
        ) from exc


def _resolve_addendum_dirs(
    policy: BomContextPolicy, args: argparse.Namespace
) -> tuple[Path | None, Path | None]:
    """Resolve the pinned (or overridden) anomaly + forensic runs for Stage H.

    CLI ``--anomaly-run`` / ``--forensic-run`` override the config pin so the
    addendum can be regenerated against the canonical rematerialized chain. The
    forensic manifest's component string is not uniform across its writers, so
    it is resolved without an expected_component check (see the dashboard
    contract); the anomaly run is component-checked.
    """
    if args.skip_addendum or not policy.forensic_addendum.enabled:
        return None, None
    pol = policy.forensic_addendum
    anomaly_dir = _resolve_addendum_run(
        pol.anomaly_root,
        args.anomaly_run or pol.anomaly_run_id,
        "anomaly_fit_manifest.json",
        kind="anomaly",
        expected_component="anomaly",
    )
    forensic_dir = _resolve_addendum_run(
        pol.forensic_root,
        args.forensic_run or pol.forensic_run_id,
        "forensic_manifest.json",
        kind="forensic",
    )
    return anomaly_dir, forensic_dir


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    policy = load_policy(args.config)
    csv_path = args.csv or io.resolve_project_path(policy.raw_input.csv_path)
    master_path = args.master or io.resolve_project_path(policy.timeline.master_path)
    anomaly_dir, forensic_dir = _resolve_addendum_dirs(policy, args)
    run_id = args.run_id or io.new_run_id(args.output_root)

    art = run(csv_path, master_path, policy, run_id, anomaly_dir, forensic_dir)

    if args.no_write:
        log.info(
            "--no-write: skipping all artifacts (%d findings; run id %s unused)",
            len(art.findings),
            run_id,
        )
        return 0

    out = io.create_run_dir(args.output_root, run_id)
    generated = _write_artifacts(out, art)

    if art.addendum is not None:
        addendum_root = args.addendum_root or io.resolve_project_path(
            policy.forensic_addendum.output_root
        )
        addendum_out = addendum_root / run_id
        addendum_files = write_addendum(art.addendum, addendum_out)
        generated += [f"{addendum_out}/{name}" for name in addendum_files]
        log.info("Wrote BOM forensic addendum → %s", addendum_out)

    # Manifest last: its presence marks the run as complete (resolvable).
    manifest = dict(art.manifest)
    manifest["generated_files"] = generated
    manifest["completion_status"] = "complete"
    io.write_manifest(manifest, out / io.MANIFEST_NAME)
    log.info("Wrote BOM context run → %s", out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
