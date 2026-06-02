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
from pathlib import Path

import pandas as pd

from src.config import CONFIGS_DIR
from src.intelligence.behaviour import baselines, profiles, validation
from src.intelligence.behaviour.baselines import BaselineArtifact
from src.intelligence.behaviour.column_groups import (
    DEFAULT_CLASSIFICATION,
    load_groups,
)
from src.intelligence.behaviour.io import (
    DEFAULT_BASELINES_OUT,
    DEFAULT_DISTRIBUTION_OUT,
    DEFAULT_DURATIONS_OUT,
    DEFAULT_FIT_MANIFEST_OUT,
    DEFAULT_MASTER_IN,
    DEFAULT_PROFILE_LABELS_OUT,
    DEFAULT_REPORT_JSON,
    DEFAULT_REPORT_MD,
    DEFAULT_TRANSITIONS_OUT,
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


def run(
    master_path: Path,
    classification: Path,
    policy_path: Path,
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

    manifest = {
        **base.fit_manifest,
        "machine_on_source": prof.machine_on_source,
        "production_edges": prof.production_edges,
        "production_quantiles": policy.profiles.production_quantiles,
        "material_change_enabled": prof.material_change is not None,
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
    p.add_argument("--profile-labels", type=Path, default=DEFAULT_PROFILE_LABELS_OUT)
    p.add_argument("--baselines", type=Path, default=DEFAULT_BASELINES_OUT)
    p.add_argument("--fit-manifest", type=Path, default=DEFAULT_FIT_MANIFEST_OUT)
    p.add_argument("--distribution", type=Path, default=DEFAULT_DISTRIBUTION_OUT)
    p.add_argument("--durations", type=Path, default=DEFAULT_DURATIONS_OUT)
    p.add_argument("--transitions", type=Path, default=DEFAULT_TRANSITIONS_OUT)
    p.add_argument("--out-json", type=Path, default=DEFAULT_REPORT_JSON)
    p.add_argument("--out-md", type=Path, default=DEFAULT_REPORT_MD)
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Skip writing artifacts; still emit the JSON/MD report.",
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

    art = run(args.master, args.classification, args.policy)

    log.info("Writing report → %s", args.out_json)
    write_json(art.findings, args.out_json)
    write_markdown(art.findings, args.out_md, title="Behaviour Intelligence Report")

    if args.no_write:
        log.info(
            "--no-write: skipping artifacts (%d findings reported)", len(art.findings)
        )
        return 0

    write_table(_profile_labels_frame(art, art.train_mask), args.profile_labels)
    log.info("Wrote profile labels → %s", args.profile_labels)

    if not art.baseline.table.empty:
        write_table(art.baseline.table, args.baselines)
        log.info(
            "Wrote baselines (%d rows) → %s", len(art.baseline.table), args.baselines
        )
    else:
        log.warning("Baseline table empty — nothing written to %s", args.baselines)

    write_manifest(art.manifest, args.fit_manifest)
    write_table(art.validation.distribution, args.distribution)
    write_table(art.validation.durations, args.durations)
    write_table(art.validation.transitions, args.transitions)
    log.info("Wrote fit manifest + validation artifacts → %s", args.fit_manifest.parent)

    return 0


if __name__ == "__main__":
    sys.exit(main())
