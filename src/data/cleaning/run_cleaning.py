"""CLI orchestrator for the InjexCore data-cleaning pipeline.

Linear order (each module's apply step may produce NaNs consumed by later
modules — missing_values runs last):

    load → timestamps → duplicates → physical_ranges
         → frozen_sensors → state_consistency → missing_values
         → write(processed_csv, report_json, report_md)

Usage::

    python -m src.data.cleaning.run_cleaning
    python -m src.data.cleaning.run_cleaning --no-write   # dry-run, report only
    python -m src.data.cleaning.run_cleaning --raw path/to/file.csv

Outputs:
    data/processed/Dades_pellet_clean.csv
    data/features/cleaning_report.json
    data/features/cleaning_report.md
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

from src.data.cleaning import (
    duplicates,
    frozen_sensors,
    missing_values,
    physical_ranges,
    state_consistency,
    timestamps,
)
from src.data.cleaning.column_groups import DEFAULT_CLASSIFICATION, load_groups
from src.data.cleaning.io import DEFAULT_DICTIONARY, DEFAULT_RAW, load_raw, write_clean
from src.data.cleaning.policy import CleaningPolicy, load_policy
from src.data.cleaning.reporting import Finding, write_json, write_markdown

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_POLICY = PROJECT_ROOT / "configs" / "cleaning.yaml"
DEFAULT_CLEAN = PROJECT_ROOT / "data" / "processed" / "Dades_pellet_clean.csv"
DEFAULT_REPORT_JSON = PROJECT_ROOT / "data" / "features" / "cleaning_report.json"
DEFAULT_REPORT_MD = PROJECT_ROOT / "data" / "features" / "cleaning_report.md"

PIPELINE = [
    ("timestamps", timestamps),
    ("duplicates", duplicates),
    ("physical_ranges", physical_ranges),
    ("frozen_sensors", frozen_sensors),
    ("state_consistency", state_consistency),
    ("missing_values", missing_values),
]

log = logging.getLogger("cleaning")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    p.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY)
    p.add_argument("--classification", type=Path, default=DEFAULT_CLASSIFICATION)
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--out-csv", type=Path, default=DEFAULT_CLEAN)
    p.add_argument("--out-json", type=Path, default=DEFAULT_REPORT_JSON)
    p.add_argument("--out-md", type=Path, default=DEFAULT_REPORT_MD)
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Skip writing the cleaned CSV; still emit the report.",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def run(
    raw_csv: Path,
    dictionary: Path,
    classification: Path,
    policy_path: Path,
) -> tuple[pd.DataFrame, list[Finding]]:
    """Execute the full pipeline and return ``(cleaned_df, all_findings)``."""
    log.info("Loading policy from %s", policy_path)
    policy = load_policy(policy_path)

    log.info("Loading raw data from %s", raw_csv)
    t0 = time.perf_counter()
    df = load_raw(raw_csv, dictionary)
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
            "Module %-20s: %4d findings (%.1fs); shape now %s",
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

    df, findings = run(args.raw, args.dictionary, args.classification, args.policy)

    log.info("Writing report → %s", args.out_json)
    write_json(findings, args.out_json)
    log.info("Writing report → %s", args.out_md)
    write_markdown(findings, args.out_md)

    if args.no_write:
        log.info("--no-write: skipping cleaned CSV output")
    else:
        log.info("Writing cleaned CSV → %s (%d rows)", args.out_csv, len(df))
        write_clean(df, args.out_csv)

    log.info("Done. %d total findings.", len(findings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
