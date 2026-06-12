"""CLI orchestrator for the Sensor Health Intelligence component.

Linear order::

    load master (column-projected) + behaviour artifacts (labels, manifest,
    baselines — fixed paths, not run-versioned)
        → Gate A: strict label alignment + vocabulary/scope checks
        → train references (train window only, suppression-consistent)
        → rule evaluation per sensor (9 families, profile-aware)
        → scoring (status + health_score + evidence)
        → events (merged episodes, pending_review)
        → quarantine recommendations (approval_required=True, approved=False)
        → write run-versioned artifacts (manifest LAST)

This component never excludes sensors, never refits models and never
changes thresholds. Run standalone or via the dispatcher::

    python -m src.intelligence --component sensor-health
    python -m src.intelligence.sensor_health.run_sensor_health --no-write
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
from src.intelligence._common.column_groups import DEFAULT_CLASSIFICATION, load_groups
from src.intelligence._common.features import select_features
from src.intelligence._common.fingerprint import dataset_fingerprint, file_sha256
from src.intelligence._common.reporting import Finding, write_json
from src.intelligence._common.upstream import (
    DEFAULT_BASELINES,
    DEFAULT_BEHAVIOUR_MANIFEST,
    DEFAULT_PROFILE_LABELS,
    align_labels,
    load_baselines,
    load_behaviour_manifest,
    load_profile_labels,
)
from src.intelligence.sensor_health import events as events_mod
from src.intelligence.sensor_health import io, quarantine, reporting, scoring
from src.intelligence.sensor_health.policy import SensorHealthPolicy, load_policy
from src.intelligence.sensor_health.rules import (
    CHECK,
    evaluate_rules,
    train_references,
)
from src.intelligence.sensor_health.validation import (
    SensorHealthBlockerError,
    validate_upstream,
)

DEFAULT_CONFIG = CONFIGS_DIR / "sensor_health_intelligence.yaml"

log = logging.getLogger("sensor_health")


@dataclass(frozen=True)
class SensorHealthArtifacts:
    """Everything ``run()`` produces (no writes happen here)."""

    scores: pd.DataFrame
    events: pd.DataFrame
    summary: pd.DataFrame
    quality_timeline: pd.DataFrame
    quarantine: pd.DataFrame
    unsupported: pd.DataFrame
    findings: list[Finding]
    manifest: dict[str, Any]
    report: str


def _candidate_columns(policy: SensorHealthPolicy, classification: Path) -> list[str]:
    groups = load_groups(classification)
    if policy.features.source == "process_sensor":
        return list(groups.process)
    return list(policy.features.include_columns)


def _build_manifest(
    policy: SensorHealthPolicy,
    run_id: str,
    paths: dict[str, Path],
    labels_frame: pd.DataFrame,
    behaviour_manifest: dict[str, Any],
    sensors: list[str],
    art: dict[str, Any],
) -> dict[str, Any]:
    events = art["events"]
    event_counts = events["status"].value_counts().to_dict() if len(events) else {}
    return {
        "component": "sensor_health",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "master_dataset_path": str(paths["master"]),
        "master_dataset_sha256": file_sha256(paths["master"]),
        "behaviour_artifact_path": str(paths["labels"].parent.parent),
        "behaviour_fingerprint": dataset_fingerprint(labels_frame, paths["labels"]),
        "behaviour_fit_timestamp": behaviour_manifest.get("fit_timestamp"),
        "sensor_scope": sensors,
        "train_window": behaviour_manifest.get("fit_window"),
        "validation_window": {
            "start": behaviour_manifest.get("fit_window", {}).get("train_end"),
            "n_rows": int((~art["train_mask"]).sum()),
        },
        "rule_config": policy.model_dump(),
        "supported_sensors": sensors,
        "unsupported_pairs": int(len(art["unsupported"])),
        "event_counts": {
            "total": int(len(events)),
            "by_status": event_counts,
            "persistent": int(events["is_persistent"].sum()) if len(events) else 0,
        },
        "quarantine_recommendation_counts": int(len(art["quarantine"])),
        "compat_checks": art["compat"],
        "statements": [
            "No model was refitted; no thresholds were modified.",
            "No sensor was excluded automatically — quarantine is a "
            "recommendation requiring human approval.",
            "No upstream artifact was modified or overwritten.",
        ],
        "generated_files": [],  # filled by main() at write time
        "completion_status": "pending",
    }


def run(
    master_path: Path,
    classification: Path,
    config_path: Path,
    labels_path: Path,
    behaviour_manifest_path: Path,
    baselines_path: Path,
    run_id: str,
) -> SensorHealthArtifacts:
    """Execute the full Sensor Health pipeline (pure; no writes)."""
    policy = load_policy(config_path)

    t0 = time.perf_counter()
    df = io.load_master_columns(master_path, _candidate_columns(policy, classification))
    labels_frame = load_profile_labels(labels_path)
    behaviour_manifest = load_behaviour_manifest(behaviour_manifest_path)
    baselines = load_baselines(baselines_path)
    try:
        profile, train_mask = align_labels(df, labels_frame)
    except ValueError as exc:
        raise SensorHealthBlockerError(str(exc)) from exc
    log.info(
        "Loaded %d rows; %d train (%.1fs)",
        len(df),
        int(train_mask.sum()),
        time.perf_counter() - t0,
    )

    groups = load_groups(classification)
    sensors, findings = select_features(df, policy.features, groups, check=CHECK)
    compat, val_findings = validate_upstream(
        sensors, behaviour_manifest, baselines, policy
    )
    findings.extend(val_findings)

    profiles_arr = profile.to_numpy(dtype=object)
    train_arr = train_mask.to_numpy()

    t0 = time.perf_counter()
    refs = train_references(df, sensors, profiles_arr, train_arr, baselines, policy)
    rule_results = evaluate_rules(df, sensors, profiles_arr, train_arr, refs, policy)
    log.info(
        "Stage %-12s: %d sensors evaluated (%.1fs)",
        "rules",
        len(sensors),
        time.perf_counter() - t0,
    )

    t0 = time.perf_counter()
    per_sensor = scoring.score_sensors(df, sensors, rule_results, refs, policy)
    event_table = events_mod.extract_events(df.index, profiles_arr, per_sensor, policy)
    quarantine_table = quarantine.build_recommendations(event_table, policy)
    qrows = quarantine.flag_rows(event_table, policy, df.index)
    scores = scoring.to_scores_frame(df.index, profiles_arr, per_sensor, qrows)
    timeline = scoring.quality_timeline(df.index, per_sensor, qrows)
    log.info(
        "Stage %-12s: %d events, %d quarantine recommendation(s) (%.1fs)",
        "scoring",
        len(event_table),
        len(quarantine_table),
        time.perf_counter() - t0,
    )

    unsupported = pd.DataFrame(
        refs.unsupported, columns=["sensor", "profile", "reason"]
    )
    summary = reporting.build_summary(
        per_sensor, train_arr, event_table, quarantine_table, policy
    )
    findings.extend(
        reporting.build_findings(summary, event_table, quarantine_table, unsupported)
    )
    manifest = _build_manifest(
        policy,
        run_id,
        {"master": master_path, "labels": labels_path},
        labels_frame,
        behaviour_manifest,
        sensors,
        {
            "events": event_table,
            "quarantine": quarantine_table,
            "unsupported": unsupported,
            "compat": compat,
            "train_mask": train_arr,
        },
    )
    report = reporting.render_report(
        summary, event_table, quarantine_table, unsupported, manifest
    )
    return SensorHealthArtifacts(
        scores=scores,
        events=event_table,
        summary=summary,
        quality_timeline=timeline,
        quarantine=quarantine_table,
        unsupported=unsupported,
        findings=findings,
        manifest=manifest,
        report=report,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--master", type=Path, default=io.DEFAULT_MASTER_IN)
    p.add_argument("--classification", type=Path, default=DEFAULT_CLASSIFICATION)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--profile-labels", type=Path, default=DEFAULT_PROFILE_LABELS)
    p.add_argument(
        "--behaviour-manifest", type=Path, default=DEFAULT_BEHAVIOUR_MANIFEST
    )
    p.add_argument("--baselines", type=Path, default=DEFAULT_BASELINES)
    p.add_argument(
        "--output-root",
        type=Path,
        default=io.SENSOR_HEALTH_DIR,
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


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    run_id = args.run_id or io.new_run_id(args.output_root)
    art = run(
        args.master,
        args.classification,
        args.config,
        args.profile_labels,
        args.behaviour_manifest,
        args.baselines,
        run_id,
    )

    if args.no_write:
        log.info(
            "--no-write: skipping all artifacts (%d findings; run id %s unused)",
            len(art.findings),
            run_id,
        )
        return 0

    out = io.run_dir(args.output_root, run_id)
    table_map = {
        io.SCORES_FILE: art.scores,
        io.EVENTS_FILE: art.events,
        io.SUMMARY_FILE: art.summary,
        io.QUALITY_TIMELINE_FILE: art.quality_timeline,
        io.QUARANTINE_FILE: art.quarantine,
        io.UNSUPPORTED_FILE: art.unsupported,
    }
    for rel_path, frame in table_map.items():
        io.write_table(frame, out / rel_path)
    write_json(art.findings, out / io.FINDINGS_JSON)
    (out / io.REPORT_MD).write_text(art.report, encoding="utf-8")
    manifest = dict(art.manifest)
    manifest["generated_files"] = [str(p) for p in table_map] + [
        io.FINDINGS_JSON,
        io.REPORT_MD,
    ]
    manifest["completion_status"] = "complete"
    # Manifest last: its presence marks the run as complete (resolvable).
    io.write_manifest(manifest, out / io.MANIFEST_NAME)
    log.info("Wrote sensor-health run → %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
