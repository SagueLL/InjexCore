"""CLI orchestrator for the Drift Intelligence component.

Linear order::

    load master (column-projected) + behaviour labels (the leakage contract)
                + resolve five upstream runs (anomaly / pca / correlation /
                  sensor-health / operational context — completed runs only)
        → Gate A: timeline + fingerprint compatibility (blockers stop the run)
        → univariate references (train window only) → raw + healthy-only views
        → multivariate score shifts (persisted scores, never recomputed)
        → context composition shifts → correlation-shift classification
        → scoring (normalized weighted evidence + sensor-health override)
        → events (windowed episodes + promoted sensor-health events)
        → write run-versioned artifacts (manifest LAST)

This component never refits a model, never modifies thresholds, profiles or
the reference window, and never overwrites an upstream artifact. Run
standalone or via the dispatcher::

    python -m src.intelligence --component drift
    python -m src.intelligence.drift.run_drift --no-write --log-level DEBUG
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import CONFIGS_DIR
from src.intelligence._common.column_groups import DEFAULT_CLASSIFICATION, load_groups
from src.intelligence._common.features import select_features
from src.intelligence._common.manifest import base_manifest
from src.intelligence._common.reporting import Finding, write_json
from src.intelligence._common.upstream import (
    align_labels,
    load_behaviour_manifest,
    load_profile_labels,
)
from src.intelligence.drift import (
    context as context_mod,
)
from src.intelligence.drift import (
    correlation as correlation_mod,
)
from src.intelligence.drift import (
    events as events_mod,
)
from src.intelligence.drift import (
    io,
    reporting,
    scoring,
)
from src.intelligence.drift import (
    multivariate as multivariate_mod,
)
from src.intelligence.drift import (
    univariate as univariate_mod,
)
from src.intelligence.drift import (
    windows as windows_mod,
)
from src.intelligence.drift.policy import (
    HEALTHY_ONLY_PROXY_LABEL,
    DriftPolicy,
    load_policy,
)
from src.intelligence.drift.validation import (
    CHECK,
    DriftBlockerError,
    validate_upstream,
)

DEFAULT_CONFIG = CONFIGS_DIR / "drift_intelligence.yaml"

log = logging.getLogger("drift")

_PROXY_ENTITY = f"q_spe_{HEALTHY_ONLY_PROXY_LABEL}"


@dataclass(frozen=True)
class DriftArtifacts:
    """Everything ``run()`` produces (no writes happen here)."""

    scores: pd.DataFrame
    events: pd.DataFrame
    summaries: dict[str, pd.DataFrame]
    unsupported: pd.DataFrame
    findings: list[Finding]
    manifest: dict[str, Any]
    report: str


@dataclass(frozen=True)
class UpstreamRuns:
    """Resolved completed upstream run directories."""

    anomaly: Path
    pca: Path
    correlation: Path
    sensor_health: Path
    operational: Path

    def run_ids(self) -> dict[str, str]:
        return {
            "anomaly": self.anomaly.name,
            "pca": self.pca.name,
            "correlation": self.correlation.name,
            "sensor_health": self.sensor_health.name,
            "operational": self.operational.name,
        }


def _candidate_columns(policy: DriftPolicy, classification: Path) -> list[str]:
    groups = load_groups(classification)
    if policy.features.source == "process_sensor":
        return list(groups.process)
    return list(policy.features.include_columns)


def _load_upstream_manifests(runs: UpstreamRuns) -> dict[str, dict[str, Any]]:
    return {
        "anomaly": io.load_run_manifest(runs.anomaly, io.ANOMALY_MANIFEST),
        "pca": io.load_run_manifest(runs.pca, io.PCA_MANIFEST),
        "correlation": io.load_run_manifest(runs.correlation, io.CORRELATION_MANIFEST),
        "sensor_health": io.load_run_manifest(
            runs.sensor_health, io.SENSOR_HEALTH_MANIFEST
        ),
        "operational": io.load_run_manifest(runs.operational, io.OPERATIONAL_MANIFEST),
    }


def _univariate_rows(
    df: pd.DataFrame,
    sensors: list[str],
    profile_arr: Any,
    train_arr: Any,
    exclusion_mask: pd.DataFrame,
    policy: DriftPolicy,
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    """Raw + healthy-only univariate metric rows."""
    refs, unsupported = univariate_mod.train_references(
        df, sensors, profile_arr, train_arr, policy
    )
    raw_rows, raw_unsup = univariate_mod.score_windows(
        df, sensors, profile_arr, refs, policy, view="raw"
    )
    frames = [raw_rows]
    unsupported += raw_unsup
    if policy.healthy_view.enabled:
        healthy_rows, healthy_unsup = univariate_mod.score_windows(
            df,
            sensors,
            profile_arr,
            refs,
            policy,
            view="healthy_only",
            exclusion_mask=exclusion_mask,
        )
        frames.append(healthy_rows)
        unsupported += healthy_unsup
    return pd.concat(frames, ignore_index=True), unsupported


def _multivariate_rows(
    score_frame: pd.DataFrame,
    contributions: pd.DataFrame,
    exclusion_mask: pd.DataFrame,
    profile_arr: Any,
    train_arr: Any,
    policy: DriftPolicy,
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    """Raw multivariate rows (+ healthy copy + optional labeled proxy)."""
    columns = [
        c for c in multivariate_mod.score_columns(policy) if c in score_frame.columns
    ]
    refs, unsupported = univariate_mod.train_references(
        score_frame,
        columns,
        profile_arr,
        train_arr,
        policy,
        scope="multivariate",
        report_profile_gaps=False,
    )
    raw_rows, raw_unsup = univariate_mod.score_windows(
        score_frame,
        columns,
        profile_arr,
        refs,
        policy,
        view="raw",
        scope="multivariate",
    )
    unsupported += raw_unsup
    rate_rows = multivariate_mod.rate_shift_rows(
        score_frame, profile_arr, train_arr, policy
    )
    frames = [raw_rows, rate_rows]

    if policy.healthy_view.enabled:
        # Level A: the healthy view re-reads the same persisted scores (they
        # cannot be recomputed without refit); dominated events are filtered
        # at event level and recorded transparently.
        healthy_copy = pd.concat([raw_rows, rate_rows], ignore_index=True)
        healthy_copy = healthy_copy.assign(view="healthy_only")
        frames.append(healthy_copy)
        if policy.healthy_view.multivariate_proxy:
            proxy = multivariate_mod.healthy_only_proxy_series(
                score_frame, contributions, exclusion_mask
            )
            if proxy is not None:
                proxy_frame = proxy.to_frame(name=_PROXY_ENTITY)
                proxy_refs, proxy_unsup = univariate_mod.train_references(
                    proxy_frame,
                    [_PROXY_ENTITY],
                    profile_arr,
                    train_arr,
                    policy,
                    scope="multivariate",
                    report_profile_gaps=False,
                )
                proxy_rows, proxy_row_unsup = univariate_mod.score_windows(
                    proxy_frame,
                    [_PROXY_ENTITY],
                    profile_arr,
                    proxy_refs,
                    policy,
                    view="healthy_only",
                    scope="multivariate",
                )
                frames.append(proxy_rows)
                unsupported += proxy_unsup + proxy_row_unsup
    return pd.concat(frames, ignore_index=True), unsupported


def run(
    master_path: Path,
    classification: Path,
    config_path: Path,
    runs: UpstreamRuns,
    run_id: str,
) -> DriftArtifacts:
    """Execute the full Drift Intelligence pipeline (pure; no writes)."""
    policy = load_policy(config_path)

    t0 = time.perf_counter()
    df = io.load_master_columns(master_path, _candidate_columns(policy, classification))
    labels_frame = load_profile_labels(
        io.resolve_project_path(policy.upstream.profile_labels_path)
    )
    behaviour_manifest = load_behaviour_manifest(
        io.resolve_project_path(policy.upstream.behaviour_manifest_path)
    )
    try:
        profile, train_mask = align_labels(df, labels_frame)
    except ValueError as exc:
        raise DriftBlockerError(str(exc)) from exc
    log.info(
        "Loaded %d rows; %d train (%.1fs); upstream runs: %s",
        len(df),
        int(train_mask.sum()),
        time.perf_counter() - t0,
        runs.run_ids(),
    )

    anomaly_scores = io.load_anomaly_scores(runs.anomaly)
    pca_scores, contributions, pca_skipped = io.load_pca_artifacts(runs.pca)
    correlations, corr_shift = io.load_correlation_artifacts(runs.correlation)
    quality_timeline, sh_events, _ = io.load_sensor_health_artifacts(runs.sensor_health)
    op_timeline = io.load_operational_timeline(runs.operational)
    manifests = _load_upstream_manifests(runs)

    compat, findings = validate_upstream(
        df, master_path, manifests, op_timeline, runs.run_ids()
    )

    groups = load_groups(classification)
    sensors, feat_findings = select_features(df, policy.features, groups, check=CHECK)
    findings.extend(feat_findings)

    profile_arr = profile.to_numpy(dtype=object)
    train_arr = train_mask.to_numpy()
    master_index = pd.DatetimeIndex(df.index)
    validation_idx = master_index[~train_arr]
    validation_start = (
        validation_idx.min() if len(validation_idx) else master_index.max()
    )
    validation_end = master_index.max()
    window_len = windows_mod.window_length(policy.windows)

    exclusion_mask = io.build_exclusion_mask(
        quality_timeline, master_index, sensors, policy.healthy_view.exclude_statuses
    )

    t0 = time.perf_counter()
    uni_rows, unsupported_rows = _univariate_rows(
        df, sensors, profile_arr, train_arr, exclusion_mask, policy
    )
    log.info(
        "Stage %-12s: %d metric rows (%.1fs)",
        "univariate",
        len(uni_rows),
        time.perf_counter() - t0,
    )

    t0 = time.perf_counter()
    metric_frames = [uni_rows]
    dominance = pd.Series(dtype=float)
    if policy.multivariate.enabled:
        score_frame, mv_unsup = multivariate_mod.assemble_score_frame(
            anomaly_scores, pca_scores, master_index, policy
        )
        unsupported_rows += mv_unsup
        unsupported_rows += [
            {
                "scope": "multivariate",
                "view": "raw",
                "entity": "pca_scores",
                "profile": p,
                "reason": "profile_skipped_by_pca_run",
            }
            for p in pca_skipped
        ]
        mv_rows, mv_row_unsup = _multivariate_rows(
            score_frame,
            contributions,
            exclusion_mask,
            profile_arr,
            train_arr,
            policy,
        )
        unsupported_rows += mv_row_unsup
        metric_frames.append(mv_rows)
        dominance = multivariate_mod.window_dominance(
            contributions, anomaly_scores, exclusion_mask, policy
        )
    log.info("Stage %-12s: done (%.1fs)", "multivariate", time.perf_counter() - t0)

    context_shift = pd.DataFrame(columns=context_mod.SHIFT_TABLE_COLUMNS)
    if policy.context.enabled:
        context_refs = context_mod.composition_references(
            op_timeline, train_arr, policy
        )
        context_rows, context_shift = context_mod.score_windows(
            op_timeline, context_refs, policy
        )
        metric_frames.append(context_rows)

    classified = pd.DataFrame(columns=correlation_mod.CLASSIFIED_COLUMNS)
    if policy.correlation.enabled:
        dominated_sensors = correlation_mod.strong_instrumentation_sensors(
            sh_events, validation_start, validation_end, policy
        )
        classified = correlation_mod.classify_pairs(
            correlations, corr_shift, dominated_sensors, policy
        )

    t0 = time.perf_counter()
    train_idx = master_index[train_arr]
    train_end = train_idx.max() if len(train_idx) else master_index.min()
    metric_rows = pd.concat(metric_frames, ignore_index=True)
    scored = scoring.normalize_and_score(metric_rows, policy, window_len, train_end)
    scored = scoring.apply_sensor_health_override(scored, sh_events, policy)
    log.info(
        "Stage %-12s: %d scored windows (%.1fs)",
        "scoring",
        len(scored),
        time.perf_counter() - t0,
    )

    t0 = time.perf_counter()
    last_window = scored["window_start"].max() if len(scored) else master_index.max()
    window_events = events_mod.extract_events(scored, policy, last_window)
    promoted = events_mod.promote_sensor_health_events(sh_events, policy)
    all_events = events_mod.merge_promoted(window_events, promoted, policy)
    corr_events = events_mod.correlation_events(
        classified, validation_start, validation_end, policy
    )
    all_events = pd.concat([all_events, corr_events], ignore_index=True)
    all_events, dominated_events = events_mod.filter_dominated_events(
        all_events, dominance, policy
    )
    unsupported_rows += [
        {
            "scope": str(e.scope),
            "view": str(e.view),
            "entity": str(e.drift_event_id),
            "profile": str(e.affected_profiles),
            "reason": (
                f"healthy_view_event_excluded:dominance={float(e.dominance):.3f}"
            ),
        }
        for e in dominated_events.itertuples(index=False)
    ]
    log.info(
        "Stage %-12s: %d events (%d promoted, %d dominance-excluded) (%.1fs)",
        "events",
        len(all_events),
        len(promoted),
        len(dominated_events),
        time.perf_counter() - t0,
    )

    comparison = scoring.comparison_table(scored, dominance, policy)
    threshold = policy.events.active_score_threshold
    correlation_summary = correlation_mod.summary_table(classified, policy)
    summaries: dict[str, pd.DataFrame] = {
        "sensor_drift_summary": scoring.scope_summary(scored, "sensor", threshold),
        "profile_drift_summary": reporting.build_profile_summary(scored, policy),
        "context_drift_summary": context_shift,
        "correlation_drift_summary": correlation_summary,
        "multivariate_drift_summary": scoring.scope_summary(
            scored, "multivariate", threshold
        ),
        "raw_vs_healthy_only_comparison": comparison,
        **context_mod.split_shift_tables(context_shift),
    }

    unsupported = pd.DataFrame(
        unsupported_rows, columns=["scope", "view", "entity", "profile", "reason"]
    )
    manifest = _build_manifest(
        policy,
        run_id,
        master_path,
        df,
        train_mask,
        sensors,
        behaviour_manifest,
        runs,
        manifests,
        compat,
        all_events,
        validation_start,
        validation_end,
    )
    findings.extend(reporting.build_findings(all_events, comparison, unsupported))
    report = reporting.render_report(
        all_events,
        comparison,
        context_shift,
        correlation_summary,
        unsupported,
        manifest,
    )
    return DriftArtifacts(
        scores=scored,
        events=all_events,
        summaries=summaries,
        unsupported=unsupported,
        findings=findings,
        manifest=manifest,
        report=report,
    )


def _build_manifest(
    policy: DriftPolicy,
    run_id: str,
    master_path: Path,
    df: pd.DataFrame,
    train_mask: pd.Series,
    sensors: list[str],
    behaviour_manifest: dict[str, Any],
    runs: UpstreamRuns,
    manifests: dict[str, dict[str, Any]],
    compat: dict[str, Any],
    events: pd.DataFrame,
    validation_start: pd.Timestamp,
    validation_end: pd.Timestamp,
) -> dict[str, Any]:
    event_counts: dict[str, Any] = {"total": int(len(events))}
    if len(events):
        event_counts["by_type"] = (
            events["drift_type"].value_counts().astype(int).to_dict()
        )
        event_counts["by_view"] = events["view"].value_counts().astype(int).to_dict()
        event_counts["by_status"] = (
            events["status"].value_counts().astype(int).to_dict()
        )
        event_counts["persistent"] = int(events["is_persistent"].sum())
    return {
        **base_manifest(
            component="drift",
            run_id=run_id,
            policy=policy,
            df=df,
            train_mask=train_mask,
            features=sensors,
            master_path=master_path,
            upstream={
                "behaviour_fit_timestamp": behaviour_manifest.get("fit_timestamp"),
                "behaviour_fit_window": behaviour_manifest.get("fit_window"),
                "anomaly_run_id": runs.anomaly.name,
                "pca_run_id": runs.pca.name,
                "correlation_run_id": runs.correlation.name,
                "sensor_health_run_id": runs.sensor_health.name,
                "operational_context_run_id": runs.operational.name,
            },
        ),
        "master_dataset_path": str(master_path),
        "master_dataset_sha256": io.file_sha256(master_path),
        "sensor_scope": sensors,
        "views": ["raw", "healthy_only"] if policy.healthy_view.enabled else ["raw"],
        "validation_window": {
            "start": str(validation_start),
            "end": str(validation_end),
        },
        "window_config": policy.windows.model_dump(),
        "threshold_config": {
            "scoring": policy.scoring.model_dump(),
            "events": policy.events.model_dump(),
        },
        "event_counts": event_counts,
        "compat_checks": compat,
        "statements": [
            "No model was refitted; no thresholds were modified.",
            "No Behaviour profile or reference window was modified.",
            "The healthy-only view is an analytical interpretation; upstream "
            "anomaly scores were never mutated and the multivariate proxy is "
            "labeled healthy_only_proxy, never presented as rescoring.",
            "No upstream artifact was modified or overwritten.",
        ],
        "generated_files": [],  # filled by main() at write time
        "completion_status": "pending",
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--master", type=Path, default=io.DEFAULT_MASTER_IN)
    p.add_argument("--classification", type=Path, default=DEFAULT_CLASSIFICATION)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    for name in ("anomaly", "pca", "correlation", "sensor-health", "operational"):
        p.add_argument(
            f"--{name}-run",
            default=None,
            help=f"{name} run id to consume (default: policy pin / 'latest').",
        )
    p.add_argument(
        "--output-root",
        type=Path,
        default=io.DRIFT_DIR,
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
    args: argparse.Namespace, policy: DriftPolicy
) -> UpstreamRuns:
    """Resolve all five upstream runs (CLI flag > policy pin > latest)."""
    upstream = policy.upstream
    spec = {
        "anomaly": (
            upstream.anomaly_root,
            args.anomaly_run or upstream.anomaly_run,
            io.ANOMALY_MANIFEST,
        ),
        "pca": (upstream.pca_root, args.pca_run or upstream.pca_run, io.PCA_MANIFEST),
        "correlation": (
            upstream.correlation_root,
            args.correlation_run or upstream.correlation_run,
            io.CORRELATION_MANIFEST,
        ),
        "sensor_health": (
            upstream.sensor_health_root,
            args.sensor_health_run or upstream.sensor_health_run,
            io.SENSOR_HEALTH_MANIFEST,
        ),
        "operational": (
            upstream.operational_root,
            args.operational_run or upstream.operational_run,
            io.OPERATIONAL_MANIFEST,
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
    art = run(args.master, args.classification, args.config, runs, run_id)

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
        io.SENSOR_SUMMARY_FILE: art.summaries["sensor_drift_summary"],
        io.PROFILE_SUMMARY_FILE: art.summaries["profile_drift_summary"],
        io.CONTEXT_SUMMARY_FILE: art.summaries["context_drift_summary"],
        io.CORRELATION_SUMMARY_FILE: art.summaries["correlation_drift_summary"],
        io.MULTIVARIATE_SUMMARY_FILE: art.summaries["multivariate_drift_summary"],
        io.PROFILE_COMPOSITION_FILE: art.summaries["profile_composition_shift"],
        io.STEAM_SHIFT_FILE: art.summaries["steam_context_shift"],
        io.SENSOR_HEALTH_SHIFT_FILE: art.summaries["sensor_health_context_shift"],
        io.BOM_SHIFT_FILE: art.summaries["bom_context_shift"],
        io.RAW_VS_HEALTHY_FILE: art.summaries["raw_vs_healthy_only_comparison"],
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
    log.info("Wrote drift run → %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
