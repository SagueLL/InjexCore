"""CLI orchestrator for the Anomaly Intelligence v1 component.

Linear order::

    load_master + behaviour artifacts (labels, is_train, baselines, manifest)
                + resolve the upstream pca run (--pca-run, default "latest")
                → statistical.score   (baselines-driven, model-free)
                → mahalanobis / iforest fit per profile (TRAIN only) + score
                → pca_detector.score  (persisted pca scores, train thresholds)
                → combine.fit (TRAIN only) → combine.apply (all rows)
                → summaries
                → write run-versioned artifacts + JSON/MD report (manifest LAST)

Inputs (defaults; override with CLI flags):

* ``data/datasets/master/master_dataset.parquet`` — upstream dataset.
* ``data/intelligence/behaviour/`` — profile labels, baselines and fit
  manifest (run behaviour first).
* ``data/intelligence/pca/runs/<id>/`` — a *completed* pca run (run pca
  first); resolved via ``--pca-run`` and recorded in the manifest.
* ``configs/anomaly_intelligence.yaml`` — policy (``--config``).

Outputs are run-versioned and never overwrite earlier runs: see
:mod:`src.intelligence.anomaly.io`. Run standalone::

    python -m src.intelligence.anomaly.run_anomaly
    python -m src.intelligence.anomaly.run_anomaly --no-write --log-level DEBUG
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import CONFIGS_DIR
from src.intelligence._common.column_groups import DEFAULT_CLASSIFICATION, load_groups
from src.intelligence._common.features import select_features
from src.intelligence._common.fingerprint import dataset_fingerprint
from src.intelligence._common.io import (
    DEFAULT_MASTER_IN,
    load_master,
    write_manifest,
    write_table,
)
from src.intelligence._common.manifest import base_manifest
from src.intelligence._common.persistence import runtime_versions, save_model
from src.intelligence._common.reporting import (
    Finding,
    Severity,
    write_json,
    write_markdown,
)
from src.intelligence._common.runs import LATEST, new_run_id, resolve_run, run_dir
from src.intelligence._common.upstream import (
    DEFAULT_BASELINES,
    DEFAULT_BEHAVIOUR_MANIFEST,
    DEFAULT_PROFILE_LABELS,
    align_labels,
    load_baselines,
    load_behaviour_manifest,
    load_profile_labels,
)
from src.intelligence.anomaly import (
    combine,
    iforest,
    io,
    mahalanobis,
    pca_detector,
    statistical,
    summaries,
)
from src.intelligence.anomaly.iforest import IForestModel
from src.intelligence.anomaly.mahalanobis import MahalanobisModel
from src.intelligence.anomaly.policy import AnomalyPolicy, load_policy
from src.intelligence.pca import io as pca_io

DEFAULT_CONFIG = CONFIGS_DIR / "anomaly_intelligence.yaml"

CHECK = "anomaly"

log = logging.getLogger("anomaly")


@dataclass(frozen=True)
class AnomalyArtifacts:
    """Everything ``run()`` produces."""

    scored: pd.DataFrame  # spec schema, full index
    calibration: pd.DataFrame  # long-form ECDF grids
    unsupported: pd.DataFrame  # profile, detector, reason
    mahalanobis_models: dict[str, MahalanobisModel]
    iforest_models: dict[str, IForestModel]
    summary_tables: dict[str, pd.DataFrame]
    manifest: dict
    findings: list[Finding]


def _supported_profiles(
    labels: pd.Series, train_mask: pd.Series, policy: AnomalyPolicy
) -> tuple[list[str], dict[str, str]]:
    """Profiles with enough training rows for the fitted detectors."""
    gate = policy.profiles
    supported: list[str] = []
    skipped: dict[str, str] = {}
    train_labels = labels.loc[train_mask]
    for profile in sorted(str(p) for p in labels.unique() if pd.notna(p)):
        if profile in set(gate.exclude_profiles):
            skipped[profile] = "excluded_by_policy"
            continue
        n_train = int((train_labels == profile).sum())
        if n_train < gate.min_samples_per_profile:
            skipped[profile] = f"insufficient_rows ({n_train})"
            continue
        supported.append(profile)
    return supported, skipped


def _fit_multivariate_detectors(
    df: pd.DataFrame,
    labels: pd.Series,
    train_mask: pd.Series,
    features: list[str],
    supported: list[str],
    policy: AnomalyPolicy,
    raw: pd.DataFrame,
    unsupported_rows: list[dict[str, str]],
    findings: list[Finding],
) -> tuple[dict[str, MahalanobisModel], pd.Series, dict[str, IForestModel]]:
    """Fit + score detectors B (mahalanobis) and D (iforest) per profile."""
    mahal_models: dict[str, MahalanobisModel] = {}
    iforest_models: dict[str, IForestModel] = {}
    mahal_affected = pd.Series("", index=df.index, dtype=str)

    for profile in supported:
        prof_mask = (labels == profile).to_numpy()
        train_rows = df.loc[(train_mask & (labels == profile)).to_numpy(), features]
        all_rows = df.loc[prof_mask]

        if policy.mahalanobis.enabled:
            model, m_findings, skip = mahalanobis.fit_profile(
                train_rows, policy, profile
            )
            findings.extend(m_findings)
            if model is None:
                unsupported_rows.append(
                    {
                        "profile": profile,
                        "detector": "mahalanobis",
                        "reason": skip or "unknown",
                    }
                )
            else:
                mahal_models[profile] = model
                d2, contributions = mahalanobis.score(all_rows, model)
                raw.loc[prof_mask, "mahalanobis"] = d2.to_numpy()
                mahal_affected.loc[prof_mask] = mahalanobis.top_affected(
                    contributions, policy.mahalanobis.top_k_variables
                ).to_numpy()

        if policy.isolation_forest.enabled:
            model_if, i_findings, skip = iforest.fit_profile(
                train_rows, policy, profile
            )
            findings.extend(i_findings)
            if model_if is None:
                unsupported_rows.append(
                    {
                        "profile": profile,
                        "detector": "isolation_forest",
                        "reason": skip or "unknown",
                    }
                )
            else:
                iforest_models[profile] = model_if
                raw.loc[prof_mask, "isolation_forest"] = iforest.score(
                    all_rows, model_if
                ).to_numpy()

    return mahal_models, mahal_affected, iforest_models


def _calibration_table(model: combine.CombineModel) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for profile, grids in model.grids.items():
        for detector, grid in grids.items():
            quantiles = np.linspace(0.0, 1.0, len(grid))
            for q, v in zip(quantiles, grid, strict=True):
                rows.append(
                    {
                        "profile": profile,
                        "detector": detector,
                        "quantile": float(q),
                        "value": float(v),
                    }
                )
    return pd.DataFrame(rows, columns=["profile", "detector", "quantile", "value"])


def run(
    master_path: Path,
    classification: Path,
    config_path: Path,
    labels_path: Path,
    behaviour_manifest_path: Path,
    baselines_path: Path,
    pca_run_dir_path: Path,
    run_id: str,
) -> AnomalyArtifacts:
    """Execute the full Anomaly Intelligence pipeline (pure; no writes)."""
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
    baselines = load_baselines(baselines_path)
    labels_frame = load_profile_labels(labels_path)
    labels, train_mask = align_labels(df, labels_frame)
    log.info(
        "Behaviour contract: %d / %d train rows, %d profiles; pca run: %s",
        int(train_mask.sum()),
        len(df),
        labels.nunique(),
        pca_run_dir_path.name,
    )

    all_findings: list[Finding] = []

    # Upstream consistency: the pca run should have been fitted on this master.
    pca_manifest = json.loads(
        (pca_run_dir_path / pca_io.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    own_fingerprint = dataset_fingerprint(df, master_path)
    pca_fingerprint = pca_manifest.get("dataset_fingerprint", {})
    if pca_fingerprint.get("sha256") != own_fingerprint["sha256"]:
        all_findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="upstream_dataset_mismatch",
                action_taken="proceed_with_warning",
                evidence={
                    "pca_run": pca_run_dir_path.name,
                    "pca_sha256": pca_fingerprint.get("sha256"),
                    "master_sha256": own_fingerprint["sha256"],
                },
            )
        )
        log.warning(
            "pca run %s was fitted on a different master dataset — "
            "its scores/thresholds may not match this data",
            pca_run_dir_path.name,
        )

    if policy.profiles.global_fallback:
        all_findings.append(
            Finding(
                check=CHECK,
                severity=Severity.AWARE,
                finding_type="global_fallback_not_supported",
                action_taken="ignored",
                evidence={"reason": "anomaly v1 scores rows by their own profile only"},
            )
        )

    features, feat_findings = select_features(df, policy.features, groups, check=CHECK)
    all_findings.extend(feat_findings)
    supported, profile_skips = _supported_profiles(labels, train_mask, policy)
    unsupported_rows: list[dict[str, str]] = [
        {"profile": p, "detector": "all", "reason": r} for p, r in profile_skips.items()
    ]
    for profile, reason in profile_skips.items():
        all_findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="profile_unsupported",
                column=profile,
                action_taken="skip_profile",
                evidence={"reason": reason},
            )
        )

    raw = pd.DataFrame(np.nan, index=df.index, columns=list(combine.DETECTORS))

    # --- Detector A: statistical (baselines-driven) -------------------------
    t0 = time.perf_counter()
    if policy.statistical.enabled:
        stat, stat_findings = statistical.score(df, labels, baselines, policy)
        all_findings.extend(stat_findings)
        raw["statistical"] = stat.raw
        stat_affected = stat.affected
        for profile, reason in stat.skipped.items():
            unsupported_rows.append(
                {"profile": profile, "detector": "statistical", "reason": reason}
            )
    else:
        stat_affected = pd.Series("", index=df.index, dtype=str)
        unsupported_rows.append(
            {"profile": "all", "detector": "statistical", "reason": "disabled"}
        )
    log.info("Stage %-12s: done (%.1fs)", "statistical", time.perf_counter() - t0)

    # --- Detectors B + D: mahalanobis + isolation forest --------------------
    t0 = time.perf_counter()
    mahal_models, mahal_affected, iforest_models = _fit_multivariate_detectors(
        df,
        labels,
        train_mask,
        features,
        supported,
        policy,
        raw,
        unsupported_rows,
        all_findings,
    )
    log.info(
        "Stage %-12s: %d mahalanobis + %d iforest models (%.1fs)",
        "multivariate",
        len(mahal_models),
        len(iforest_models),
        time.perf_counter() - t0,
    )

    # --- Detector C: persisted pca run ---------------------------------------
    t0 = time.perf_counter()
    pca_thresholds: dict[str, pca_detector.PcaThresholds] = {}
    if policy.pca_detector.enabled:
        pca_res, pca_findings = pca_detector.score(pca_run_dir_path, df.index, policy)
        all_findings.extend(pca_findings)
        raw["pca_q"] = pca_res.q_raw
        raw["pca_t2"] = pca_res.t2_raw
        pca_affected = pca_res.affected
        pca_thresholds = pca_res.thresholds
        for profile, reason in pca_res.skipped.items():
            unsupported_rows.append(
                {"profile": profile, "detector": "pca", "reason": reason}
            )
    else:
        pca_affected = pd.Series("", index=df.index, dtype=str)
        unsupported_rows.append(
            {"profile": "all", "detector": "pca", "reason": "disabled"}
        )
    log.info("Stage %-12s: done (%.1fs)", "pca_detector", time.perf_counter() - t0)

    # --- Combine: normalize, score, severity (train-fitted) ------------------
    t0 = time.perf_counter()
    combine_model, combine_findings = combine.fit(raw, labels, train_mask, policy)
    all_findings.extend(combine_findings)
    scored = combine.apply(
        raw,
        labels,
        combine_model,
        policy,
        affected_sources={
            "statistical": stat_affected,
            "mahalanobis": mahal_affected,
            "pca_q": pca_affected,
        },
    )
    n_flagged = int(scored["severity"].isin(["warning", "anomaly"]).sum())
    log.info(
        "Stage %-12s: %d rows scored, %d flagged (%.1fs)",
        "combine",
        len(scored),
        n_flagged,
        time.perf_counter() - t0,
    )

    summary_tables = {
        "timeline": summaries.timeline(scored, policy),
        "rates_by_profile": summaries.rates_by_profile(scored),
        "severity_distribution": summaries.severity_distribution(scored),
        "top_events": summaries.top_events(scored, policy),
        "detector_agreement": summaries.detector_agreement(scored),
    }

    unsupported = pd.DataFrame(
        unsupported_rows, columns=["profile", "detector", "reason"]
    )
    manifest = {
        **base_manifest(
            component="anomaly",
            run_id=run_id,
            policy=policy,
            df=df,
            train_mask=train_mask,
            features=features,
            master_path=master_path,
            upstream={
                "behaviour_fit_timestamp": behaviour_manifest.get("fit_timestamp"),
                "behaviour_fit_window": behaviour_manifest.get("fit_window"),
                "pca_run_id": pca_run_dir_path.name,
                "pca_fingerprint_sha256": pca_fingerprint.get("sha256"),
                "pca_fingerprint_matches": bool(
                    pca_fingerprint.get("sha256") == own_fingerprint["sha256"]
                ),
            },
        ),
        "profiles_supported": supported,
        "profiles_skipped": profile_skips,
        "severity_thresholds": {
            p: {"warning": w, "anomaly": a}
            for p, (w, a) in combine_model.severity_thresholds.items()
        },
        "trigger_levels": combine_model.trigger_levels,
        "pca_thresholds": {
            p: {"t2": t.t2_threshold, "q": t.q_threshold}
            for p, t in pca_thresholds.items()
        },
        "versions": runtime_versions(),
    }

    return AnomalyArtifacts(
        scored=scored,
        calibration=_calibration_table(combine_model),
        unsupported=unsupported,
        mahalanobis_models=mahal_models,
        iforest_models=iforest_models,
        summary_tables=summary_tables,
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
    p.add_argument("--baselines", type=Path, default=DEFAULT_BASELINES)
    p.add_argument(
        "--pca-root",
        type=Path,
        default=pca_io.PCA_DIR,
        help="PCA component root holding runs/<id>/ directories.",
    )
    p.add_argument(
        "--pca-run",
        default=LATEST,
        help="PCA run id to consume ('latest' = newest completed run).",
    )
    p.add_argument(
        "--output-root",
        type=Path,
        default=io.ANOMALY_DIR,
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


def _write_profile_models(out: Path, art: AnomalyArtifacts) -> None:
    profiles = sorted(set(art.mahalanobis_models) | set(art.iforest_models))
    for profile in profiles:
        mdir = io.model_dir(out, profile)
        meta: dict[str, object] = {
            "component": "anomaly",
            "profile": profile,
            "versions": runtime_versions(),
        }
        if profile in art.mahalanobis_models:
            m = art.mahalanobis_models[profile]
            mdir.mkdir(parents=True, exist_ok=True)
            (mdir / io.MAHALANOBIS_FILE).write_text(
                json.dumps(m.to_json_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            meta["mahalanobis"] = {
                "features": m.features,
                "n_train": m.n_train,
                "estimator": m.estimator,
            }
        if profile in art.iforest_models:
            f = art.iforest_models[profile]
            save_model(f.estimator, mdir / io.IFOREST_FILE)
            meta["isolation_forest"] = {
                "features": f.features,
                "medians": {k: float(v) for k, v in f.medians.items()},
                "n_train": f.n_train,
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

    pca_run_dir_path = resolve_run(args.pca_root, args.pca_run, pca_io.MANIFEST_NAME)
    run_id = args.run_id or new_run_id(args.output_root)
    art = run(
        args.master,
        args.classification,
        args.config,
        args.profile_labels,
        args.behaviour_manifest,
        args.baselines,
        pca_run_dir_path,
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
    write_table(art.scored, out / io.SCORES_FILE)
    write_table(art.calibration, out / io.CALIBRATION_FILE)
    write_table(art.unsupported, out / io.UNSUPPORTED_FILE)
    write_table(art.summary_tables["timeline"], out / io.TIMELINE_FILE)
    write_table(art.summary_tables["rates_by_profile"], out / io.RATES_FILE)
    write_table(art.summary_tables["severity_distribution"], out / io.SEVERITY_FILE)
    write_table(art.summary_tables["top_events"], out / io.TOP_EVENTS_FILE)
    write_table(art.summary_tables["detector_agreement"], out / io.AGREEMENT_FILE)
    _write_profile_models(out, art)
    write_json(art.findings, out / io.REPORT_JSON)
    write_markdown(
        art.findings, out / io.REPORT_MD, title="Anomaly Intelligence Report"
    )
    # Manifest last: its presence marks the run as complete (resolvable).
    write_manifest(art.manifest, out / io.MANIFEST_NAME)
    log.info("Wrote anomaly run → %s", out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
