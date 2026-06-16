"""CLI orchestrator for the InjexCore Behaviour Intelligence stage.

Linear order::

    load_master → compute train window (leakage guard)
                → profiles.derive   (operational regimes + material candidate)
                → baselines.fit      (per-profile, per-sensor stats, TRAIN only)
                → validation.build   (distribution / durations / transitions / coverage)
                → write artifacts + JSON/MD report

Inputs (defaults; override with CLI flags):

* ``data/datasets/master/master_dataset.parquet`` — the upstream dependency.
* ``configs/behaviour_intelligence.yaml`` — policy.
* ``data/features/variable_classification.csv`` — semantic catalogue.

Outputs: see :mod:`src.intelligence.behaviour.io`.

This stage *fits descriptive artifacts*; it is intentionally NOT wired into
the ``python -m src.preprocessing`` ``--stage`` dispatcher (different output
contract, sits past the preprocessing chain). Run it standalone::

    python -m src.intelligence.behaviour.run_behaviour
    python -m src.intelligence.behaviour.run_behaviour --no-write --log-level DEBUG
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
from src.intelligence.behaviour import baselines, io, profiles, validation
from src.intelligence.behaviour.baselines import BaselineArtifact
from src.intelligence.behaviour.column_groups import (
    DEFAULT_CLASSIFICATION,
    load_groups,
)
from src.intelligence.behaviour.io import (
    DEFAULT_MASTER_IN,
    load_master,
    write_manifest,
    write_table,
)
from src.intelligence.behaviour.policy import BehaviourPolicy, load_policy
from src.intelligence.behaviour.profiles import ProfileArtifact
from src.intelligence.behaviour.reporting import Finding, write_json, write_markdown
from src.intelligence.behaviour.validation import ValidationArtifact

DEFAULT_POLICY = CONFIGS_DIR / "behaviour_intelligence.yaml"

log = logging.getLogger("behaviour")


@dataclass(frozen=True)
class BehaviourArtifacts:
    """Everything ``run()`` produces."""

    profiles: ProfileArtifact
    baseline: BaselineArtifact
    validation: ValidationArtifact
    manifest: dict
    train_mask: pd.Series
    findings: list[Finding]


def compute_train_mask(df: pd.DataFrame, policy: BehaviourPolicy) -> pd.Series:
    """Boolean Series marking the leakage-safe training window.

    ``fraction`` (default) → the first ``train_fraction`` of the time-ordered
    rows. ``date_range`` → rows within ``[start, end]`` (requires a
    DatetimeIndex). ``all`` → every row (EDA only; leaks future statistics).
    """
    fw = policy.fit_window
    if fw.strategy == "all":
        return pd.Series(True, index=df.index)
    if fw.strategy == "date_range":
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("fit_window.strategy='date_range' needs a DatetimeIndex")
        mask = pd.Series(True, index=df.index)
        if fw.start:
            mask &= df.index >= pd.Timestamp(fw.start)
        if fw.end:
            mask &= df.index <= pd.Timestamp(fw.end)
        return mask
    # fraction
    n = len(df)
    k = int(round(n * fw.train_fraction))
    mask = pd.Series(False, index=df.index)
    if k > 0:
        mask.iloc[:k] = True
    return mask


def _windows(
    df: pd.DataFrame, train_mask: pd.Series
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Train / validation window bounds for the fit manifest."""
    n_total = int(len(df))
    n_train = int(train_mask.sum())
    train_start = train_end = val_start = val_end = None
    if isinstance(df.index, pd.DatetimeIndex) and n_total:
        tmask = train_mask.to_numpy()
        if n_train:
            tidx = df.index[tmask]
            train_start, train_end = str(tidx.min()), str(tidx.max())
        if n_train < n_total:
            vidx = df.index[~tmask]
            val_start, val_end = str(vidx.min()), str(vidx.max())
    train_window = {
        "n_train": n_train,
        "n_total": n_total,
        "train_start": train_start,
        "train_end": train_end,
    }
    validation_window = {
        "n_val": n_total - n_train,
        "val_start": val_start,
        "val_end": val_end,
    }
    return train_window, validation_window


def run(
    master_path: Path,
    classification: Path,
    policy_path: Path,
    run_id: str,
) -> BehaviourArtifacts:
    """Execute the full Behaviour Intelligence pipeline (pure; no file writes)."""
    log.info("Loading policy from %s", policy_path)
    policy = load_policy(policy_path)

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
    train_mask = compute_train_mask(df, policy)
    log.info(
        "Train window: %d / %d rows (%.1f%%)",
        int(train_mask.sum()),
        len(df),
        100.0 * train_mask.mean() if len(df) else 0.0,
    )

    all_findings: list[Finding] = []

    t0 = time.perf_counter()
    prof, prof_findings = profiles.derive(df, policy, groups, train_mask=train_mask)
    all_findings.extend(prof_findings)
    log.info(
        "Stage %-12s: %3d findings (%.1fs); %d profiles",
        "profiles",
        len(prof_findings),
        time.perf_counter() - t0,
        len(prof.profile_names),
    )

    t0 = time.perf_counter()
    base, base_findings = baselines.fit(
        df, prof.labels, policy, groups, train_mask=train_mask
    )
    all_findings.extend(base_findings)
    log.info(
        "Stage %-12s: %3d findings (%.1fs); %d baseline rows",
        "baselines",
        len(base_findings),
        time.perf_counter() - t0,
        len(base.table),
    )

    t0 = time.perf_counter()
    val, val_findings = validation.build(prof.labels, policy, train_mask=train_mask)
    all_findings.extend(val_findings)
    log.info(
        "Stage %-12s: %3d findings (%.1fs); labeled %.1f%%",
        "validation",
        len(val_findings),
        time.perf_counter() - t0,
        100.0 * val.coverage["labeled_pct"],
    )

    train_window, validation_window = _windows(df, train_mask)
    manifest = {
        "component": io.COMPONENT,
        "run_id": run_id,
        # Flipped to "complete" at write time (manifest-last contract): a
        # crashed run never leaves a resolvable manifest behind.
        "completion_status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
        "master_dataset_path": str(master_path),
        "master_dataset_sha256": io.file_sha256(master_path),
        **base.fit_manifest,
        "train_window": train_window,
        "validation_window": validation_window,
        "row_count": int(len(df)),
        "profile_count": int(val.coverage["n_profiles"]),
        "machine_on_source": prof.machine_on_source,
        "production_edges": prof.production_edges,
        "production_quantiles": policy.profiles.production_quantiles,
        "material_change_enabled": prof.material_change is not None,
        "generated_files": [],  # filled by main() at write time
    }

    return BehaviourArtifacts(
        profiles=prof,
        baseline=base,
        validation=val,
        manifest=manifest,
        train_mask=train_mask,
        findings=all_findings,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--master", type=Path, default=DEFAULT_MASTER_IN)
    p.add_argument("--classification", type=Path, default=DEFAULT_CLASSIFICATION)
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument(
        "--output-root",
        type=Path,
        default=io.BEHAVIOUR_DIR,
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


def _profile_labels_frame(
    art: BehaviourArtifacts, train_mask: pd.Series
) -> pd.DataFrame:
    out = pd.DataFrame({"profile": art.profiles.labels})
    if art.profiles.material_change is not None:
        out["material_change_candidate"] = art.profiles.material_change.astype("int8")
    out["is_train"] = train_mask.astype("int8")
    return out


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    run_id = args.run_id or io.new_run_id(args.output_root)
    art = run(args.master, args.classification, args.policy, run_id)

    if args.no_write:
        log.info(
            "--no-write: skipping all artifacts (%d findings; run id %s unused)",
            len(art.findings),
            run_id,
        )
        return 0

    out = io.create_run_dir(args.output_root, run_id)
    write_table(
        _profile_labels_frame(art, art.train_mask), out / io.PROFILE_LABELS_FILE
    )
    if not art.baseline.table.empty:
        write_table(art.baseline.table, out / io.BASELINES_FILE)
    else:
        log.warning("Baseline table empty — no baselines written")
    write_table(art.validation.distribution, out / io.DISTRIBUTION_FILE)
    write_table(art.validation.durations, out / io.DURATIONS_FILE)
    write_table(art.validation.transitions, out / io.TRANSITIONS_FILE)
    write_json(art.findings, out / io.REPORT_JSON)
    write_markdown(
        art.findings, out / io.REPORT_MD, title="Behaviour Intelligence Report"
    )

    manifest = dict(art.manifest)
    manifest["generated_files"] = [
        str(io.PROFILE_LABELS_FILE),
        str(io.BASELINES_FILE),
        str(io.DISTRIBUTION_FILE),
        str(io.DURATIONS_FILE),
        str(io.TRANSITIONS_FILE),
        io.REPORT_JSON,
        io.REPORT_MD,
    ]
    manifest["completion_status"] = "complete"
    # Manifest last: its presence marks the run as complete (resolvable).
    write_manifest(manifest, out / io.MANIFEST_NAME)
    log.info("Wrote behaviour run → %s", out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
