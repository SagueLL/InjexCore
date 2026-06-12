"""CLI orchestrator for the Correlation Intelligence component.

Linear order::

    load_master + behaviour artifacts (labels, is_train, manifest)
                → matrices.fit       (per-profile Pearson/Spearman, TRAIN only)
                → analysis           (strongest / redundant pairs)
                → shift.diagnose     (validation-vs-train deltas, diagnostics)
                → write run-versioned artifacts + JSON/MD report (manifest LAST)

Inputs (defaults; override with CLI flags):

* ``data/datasets/master/master_dataset.parquet`` — upstream dataset.
* ``data/intelligence/behaviour/profiles/profile_labels.parquet`` and
  ``behaviour_fit_manifest.json`` — the persisted Behaviour Intelligence
  contract (profiles + leakage-safe split). Run behaviour first.
* ``configs/correlation_intelligence.yaml`` — policy (``--config``).

Outputs are run-versioned and never overwrite earlier runs: see
:mod:`src.intelligence.correlation.io`. Run standalone::

    python -m src.intelligence.correlation.run_correlation
    python -m src.intelligence.correlation.run_correlation --no-write --log-level DEBUG
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config import CONFIGS_DIR
from src.intelligence._common.column_groups import DEFAULT_CLASSIFICATION, load_groups
from src.intelligence._common.io import (
    DEFAULT_MASTER_IN,
    load_master,
    write_manifest,
    write_table,
)
from src.intelligence._common.manifest import base_manifest
from src.intelligence._common.reporting import Finding, write_json, write_markdown
from src.intelligence._common.runs import new_run_id, run_dir
from src.intelligence._common.upstream import (
    DEFAULT_BEHAVIOUR_MANIFEST,
    DEFAULT_PROFILE_LABELS,
    align_labels,
    load_behaviour_manifest,
    load_profile_labels,
)
from src.intelligence.correlation import analysis, io, matrices, shift
from src.intelligence.correlation.matrices import CorrelationArtifact
from src.intelligence.correlation.policy import load_policy

DEFAULT_CONFIG = CONFIGS_DIR / "correlation_intelligence.yaml"

log = logging.getLogger("correlation")


@dataclass(frozen=True)
class CorrelationArtifacts:
    """Everything ``run()`` produces."""

    correlation: CorrelationArtifact
    strong: pd.DataFrame
    redundant: pd.DataFrame
    shift: pd.DataFrame
    manifest: dict
    findings: list[Finding]


def run(
    master_path: Path,
    classification: Path,
    config_path: Path,
    labels_path: Path,
    behaviour_manifest_path: Path,
    run_id: str,
) -> CorrelationArtifacts:
    """Execute the full Correlation Intelligence pipeline (pure; no writes)."""
    log.info("Loading policy from %s", config_path)
    policy = load_policy(config_path)

    log.info("Loading master dataset from %s", master_path)
    t0 = time.perf_counter()
    df = load_master(master_path)
    log.info(
        "Loaded %d rows x %d cols in %.1fs",
        len(df),
        df.shape[1],
        time.perf_counter() - t0,
    )

    groups = load_groups(classification)
    behaviour_manifest = load_behaviour_manifest(behaviour_manifest_path)
    labels_frame = load_profile_labels(labels_path)
    labels, train_mask = align_labels(df, labels_frame)
    log.info(
        "Behaviour contract: %d / %d train rows, %d profiles",
        int(train_mask.sum()),
        len(df),
        labels.nunique(),
    )

    all_findings: list[Finding] = []

    t0 = time.perf_counter()
    art, fit_findings = matrices.fit(df, labels, policy, groups, train_mask=train_mask)
    all_findings.extend(fit_findings)
    log.info(
        "Stage %-12s: %3d findings (%.1fs); %d pairs, %d profiles fitted, %d skipped",
        "matrices",
        len(fit_findings),
        time.perf_counter() - t0,
        len(art.correlations),
        len(art.profiles_fitted),
        len(art.profiles_skipped),
    )

    strong = analysis.strongest_pairs(art.correlations, policy)
    redundant = analysis.redundant_pairs(art.correlations, policy)
    log.info(
        "Stage %-12s: %d strong pairs, %d redundant pairs",
        "analysis",
        len(strong),
        len(redundant),
    )

    t0 = time.perf_counter()
    shift_table, shift_findings = shift.diagnose(
        df, labels, policy, art.correlations, train_mask=train_mask
    )
    all_findings.extend(shift_findings)
    log.info(
        "Stage %-12s: %3d findings (%.1fs); %d pair deltas",
        "shift",
        len(shift_findings),
        time.perf_counter() - t0,
        len(shift_table),
    )

    per_profile = {
        profile: {
            "n_pairs": int((art.correlations["profile"] == profile).sum()),
            "n_excluded_features": int((art.excluded["profile"] == profile).sum()),
        }
        for profile in art.profiles_fitted
    }
    manifest = {
        **base_manifest(
            component="correlation",
            run_id=run_id,
            policy=policy,
            df=df,
            train_mask=train_mask,
            features=art.features,
            master_path=master_path,
            upstream={
                "behaviour_fit_timestamp": behaviour_manifest.get("fit_timestamp"),
                "behaviour_fit_window": behaviour_manifest.get("fit_window"),
            },
        ),
        "profiles_fitted": art.profiles_fitted,
        "profiles_skipped": art.profiles_skipped,
        "profiles": per_profile,
    }

    return CorrelationArtifacts(
        correlation=art,
        strong=strong,
        redundant=redundant,
        shift=shift_table,
        manifest=manifest,
        findings=all_findings,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--master", type=Path, default=DEFAULT_MASTER_IN)
    p.add_argument("--classification", type=Path, default=DEFAULT_CLASSIFICATION)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--profile-labels", type=Path, default=DEFAULT_PROFILE_LABELS)
    p.add_argument(
        "--behaviour-manifest", type=Path, default=DEFAULT_BEHAVIOUR_MANIFEST
    )
    p.add_argument(
        "--output-root",
        type=Path,
        default=io.CORRELATION_DIR,
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

    run_id = args.run_id or new_run_id(args.output_root)
    art = run(
        args.master,
        args.classification,
        args.config,
        args.profile_labels,
        args.behaviour_manifest,
        run_id,
    )

    if args.no_write:
        log.info(
            "--no-write: skipping all artifacts (%d findings; run id %s unused)",
            len(art.findings),
            run_id,
        )
        return 0

    out = run_dir(args.output_root, run_id)
    write_table(art.correlation.correlations, out / io.CORRELATIONS_FILE)
    write_table(art.correlation.excluded, out / io.EXCLUDED_FILE)
    write_table(art.strong, out / io.STRONG_FILE)
    write_table(art.redundant, out / io.REDUNDANT_FILE)
    write_table(art.shift, out / io.SHIFT_FILE)
    write_json(art.findings, out / io.REPORT_JSON)
    write_markdown(
        art.findings, out / io.REPORT_MD, title="Correlation Intelligence Report"
    )
    # Manifest last: its presence marks the run as complete (resolvable).
    write_manifest(art.manifest, out / io.MANIFEST_NAME)
    log.info("Wrote correlation run → %s", out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
