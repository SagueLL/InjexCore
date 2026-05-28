"""CLI orchestrator for the InjexCore time-series engineering pipeline.

Linear order (each stage's apply step feeds the next):

    load_clean → temporal_conversion → temporal_index → resampling
               → rolling_windows → temporal_features → state_features
               → write(features_parquet, report_json, report_md)

Usage::

    python -m src.data.time_series.run_ts_engineering
    python -m src.data.time_series.run_ts_engineering --no-write
    python -m src.data.time_series.run_ts_engineering --clean path/to/clean.csv

Outputs:
    data/features/Dades_pellet_features.parquet
    data/features/ts_engineering_report.json
    data/features/ts_engineering_report.md
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

from src.data.time_series import (
    resampling,
    rolling_windows,
    state_features,
    temporal_conversion,
    temporal_features,
    temporal_index,
)
from src.data.time_series.column_groups import DEFAULT_CLASSIFICATION, load_groups
from src.data.time_series.io import (
    DEFAULT_CLEAN_IN,
    DEFAULT_FEATURES,
    load_clean,
    write_features,
)
from src.data.time_series.policy import TimeSeriesPolicy, load_policy
from src.data.time_series.reporting import Finding, write_json, write_markdown

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_POLICY = PROJECT_ROOT / "configs" / "time_series.yaml"
DEFAULT_REPORT_JSON = PROJECT_ROOT / "data" / "features" / "ts_engineering_report.json"
DEFAULT_REPORT_MD = PROJECT_ROOT / "data" / "features" / "ts_engineering_report.md"

PIPELINE = [
    ("temporal_conversion", temporal_conversion),
    ("temporal_index", temporal_index),
    ("resampling", resampling),
    ("rolling_windows", rolling_windows),
    ("temporal_features", temporal_features),
    ("state_features", state_features),
]

log = logging.getLogger("ts_engineering")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--clean", type=Path, default=DEFAULT_CLEAN_IN)
    p.add_argument("--classification", type=Path, default=DEFAULT_CLASSIFICATION)
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--out-parquet", type=Path, default=DEFAULT_FEATURES)
    p.add_argument(
        "--out-csv",
        type=Path,
        default=None,
        help="Optional CSV mirror of the feature matrix (large files).",
    )
    p.add_argument("--out-json", type=Path, default=DEFAULT_REPORT_JSON)
    p.add_argument("--out-md", type=Path, default=DEFAULT_REPORT_MD)
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Skip writing the feature matrix; still emit the report.",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def run(
    clean_csv: Path,
    classification: Path,
    policy_path: Path,
) -> tuple[pd.DataFrame, list[Finding]]:
    """Execute the full pipeline and return ``(features_df, all_findings)``."""
    log.info("Loading policy from %s", policy_path)
    policy: TimeSeriesPolicy = load_policy(policy_path)

    log.info("Loading cleaned data from %s", clean_csv)
    t0 = time.perf_counter()
    df = load_clean(clean_csv)
    log.info(
        "Loaded %d rows x %d cols in %.1fs",
        len(df), df.shape[1], time.perf_counter() - t0,
    )

    groups = load_groups(classification)

    all_findings: list[Finding] = []
    for name, module in PIPELINE:
        t0 = time.perf_counter()
        findings = module.detect(df, policy, groups)
        df = module.apply(df, findings, policy, groups)
        all_findings.extend(findings)
        log.info(
            "Stage %-20s: %4d findings (%.1fs); shape now %s",
            name, len(findings), time.perf_counter() - t0, df.shape,
        )
    return df, all_findings


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    df, findings = run(args.clean, args.classification, args.policy)

    log.info("Writing report → %s", args.out_json)
    write_json(findings, args.out_json)
    log.info("Writing report → %s", args.out_md)
    write_markdown(findings, args.out_md, title="Time-Series Engineering Report")

    if args.no_write:
        log.info("--no-write: skipping feature matrix output")
    else:
        log.info(
            "Writing feature matrix → %s (%d rows x %d cols)",
            args.out_parquet, len(df), df.shape[1],
        )
        write_features(df, args.out_parquet, args.out_csv)

    log.info("Done. %d total findings.", len(findings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
