"""CLI orchestrator for the PCA Intelligence component.

Linear order::

    load_master + behaviour artifacts (labels, is_train, manifest)
                → model.fit          (per-profile scaler + PCA, TRAIN only)
                → scoring.score      (all rows per profile, no refit)
                → write run-versioned artifacts + JSON/MD report (manifest LAST)

Inputs (defaults; override with CLI flags):

* ``data/datasets/master/master_dataset.parquet`` — upstream dataset.
* ``data/intelligence/behaviour/profiles/profile_labels.parquet`` and
  ``behaviour_fit_manifest.json`` — the persisted Behaviour Intelligence
  contract (profiles + leakage-safe split). Run behaviour first.
* ``configs/pca_intelligence.yaml`` — policy (``--config``).

Training rows are scored in-sample on purpose: Anomaly Intelligence fits its
T²/Q thresholds from the training-score distribution. Outputs are
run-versioned and never overwrite earlier runs: see
:mod:`src.intelligence.pca.io`. Run standalone::

    python -m src.intelligence.pca.run_pca
    python -m src.intelligence.pca.run_pca --no-write --log-level DEBUG
"""

from __future__ import annotations

import argparse
import json
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
from src.intelligence._common.persistence import runtime_versions, save_model
from src.intelligence._common.policy import GLOBAL_PROFILE
from src.intelligence._common.reporting import Finding, write_json, write_markdown
from src.intelligence._common.runs import create_run_dir, new_run_id
from src.intelligence._common.upstream import (
    DEFAULT_BEHAVIOUR_MANIFEST,
    DEFAULT_PROFILE_LABELS,
    align_labels,
    load_behaviour_manifest,
    load_profile_labels,
)
from src.intelligence.pca import io, model, scoring
from src.intelligence.pca.model import PcaArtifact, ProfilePcaModel
from src.intelligence.pca.policy import load_policy

DEFAULT_CONFIG = CONFIGS_DIR / "pca_intelligence.yaml"

log = logging.getLogger("pca")


@dataclass(frozen=True)
class PcaArtifacts:
    """Everything ``run()`` produces."""

    pca: PcaArtifact
    scores: dict[str, pd.DataFrame]  # per profile
    contributions: dict[str, pd.DataFrame]  # per profile
    manifest: dict
    findings: list[Finding]


def run(
    master_path: Path,
    classification: Path,
    config_path: Path,
    labels_path: Path,
    behaviour_manifest_path: Path,
    run_id: str,
) -> PcaArtifacts:
    """Execute the full PCA Intelligence pipeline (pure; no writes)."""
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
    art, fit_findings = model.fit(df, labels, policy, groups, train_mask=train_mask)
    all_findings.extend(fit_findings)
    log.info(
        "Stage %-12s: %3d findings (%.1fs); %d profiles fitted, %d skipped",
        "model",
        len(fit_findings),
        time.perf_counter() - t0,
        len(art.models),
        len(art.skipped),
    )

    t0 = time.perf_counter()
    scores: dict[str, pd.DataFrame] = {}
    contributions: dict[str, pd.DataFrame] = {}
    for profile, m in art.models.items():
        rows = (
            df if profile == GLOBAL_PROFILE else df.loc[(labels == profile).to_numpy()]
        )
        prof_scores, prof_contrib = scoring.score(rows, m, is_train=train_mask)
        scores[profile] = prof_scores
        contributions[profile] = prof_contrib
    log.info(
        "Stage %-12s: scored %d profiles (%.1fs)",
        "scoring",
        len(scores),
        time.perf_counter() - t0,
    )

    per_profile = {
        profile: {
            "n_train": m.n_train,
            "n_features": len(m.features),
            "n_components": m.n_components,
            "cumulative_evr": round(sum(m.explained_variance_ratio), 4),
        }
        for profile, m in art.models.items()
    }
    manifest = {
        **base_manifest(
            component="pca",
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
        "profiles_fitted": sorted(art.models),
        "profiles_skipped": {
            str(r["profile"]): str(r["reason"]) for r in art.skipped.to_dict("records")
        },
        "profiles": per_profile,
        "versions": runtime_versions(),
    }

    return PcaArtifacts(
        pca=art,
        scores=scores,
        contributions=contributions,
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
        default=io.PCA_DIR,
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


def _write_profile_model(out: Path, profile: str, m: ProfilePcaModel) -> None:
    mdir = io.model_dir(out, profile)
    save_model(m.scaler, mdir / io.SCALER_FILE)
    save_model(m.pca, mdir / io.PCA_FILE)
    meta = {
        "component": "pca",
        "model_type": f"{type(m.scaler).__name__}+PCA",
        "profile": profile,
        "features": m.features,
        "n_components": m.n_components,
        "explained_variance_ratio": m.explained_variance_ratio,
        "n_train": m.n_train,
        "train_medians": {k: float(v) for k, v in m.train_medians.items()},
        "versions": runtime_versions(),
    }
    (mdir / io.MODEL_META_FILE).write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )


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

    out = create_run_dir(args.output_root, run_id)
    for profile, m in art.pca.models.items():
        _write_profile_model(out, profile, m)
        write_table(art.scores[profile], io.scores_dir(out, profile) / io.SCORES_FILE)
        write_table(
            art.contributions[profile],
            io.scores_dir(out, profile) / io.CONTRIBUTIONS_FILE,
        )
    write_table(art.pca.loadings, out / io.LOADINGS_FILE)
    write_table(art.pca.explained_variance, out / io.EXPLAINED_VARIANCE_FILE)
    write_table(art.pca.skipped, out / io.SKIPPED_FILE)
    write_json(art.findings, out / io.REPORT_JSON)
    write_markdown(art.findings, out / io.REPORT_MD, title="PCA Intelligence Report")
    # Manifest last: its presence marks the run as complete (resolvable).
    write_manifest(art.manifest, out / io.MANIFEST_NAME)
    log.info("Wrote pca run → %s", out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
