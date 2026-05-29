"""CLI orchestrator for the InjexCore feature engineering pipeline.

Linear order (each stage's apply step feeds the next):

    load_features → temporal_derivatives → stability → physical_ratios
                  → energetic_features → operative_features → anomaly_features
                  → write(engineered_parquet, report_json, report_md)

Inputs (defaults; override with CLI flags):

* ``data/features/Dades_pellet_features.parquet`` — time-series engineering
  output. Accepts the cleaned CSV as a fallback when the user wants to
  skip the ts stage.
* ``configs/feature_engineering.yaml`` — policy.
* ``data/features/variable_classification.csv`` — semantic catalogue.

Outputs:

* ``data/features/Dades_pellet_engineered.parquet``
* ``data/features/feature_engineering_report.json``
* ``data/features/feature_engineering_report.md``
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

from src.data.feature_engineering import (
    anomaly_features,
    energetic_features,
    operative_features,
    physical_ratios,
    stability,
    temporal_derivatives,
)
from src.data.feature_engineering.column_groups import (
    DEFAULT_CLASSIFICATION,
    load_groups,
)
from src.data.feature_engineering.io import (
    DEFAULT_ENGINEERED_OUT,
    DEFAULT_FEATURES_IN,
    load_features,
    write_engineered,
)
from src.data.feature_engineering.policy import (
    FeatureEngineeringPolicy,
    load_policy,
)
from src.data.feature_engineering.reporting import (
    Finding,
    write_json,
    write_markdown,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_POLICY = PROJECT_ROOT / "configs" / "feature_engineering.yaml"
DEFAULT_REPORT_JSON = (
    PROJECT_ROOT / "data" / "features" / "feature_engineering_report.json"
)
DEFAULT_REPORT_MD = (
    PROJECT_ROOT / "data" / "features" / "feature_engineering_report.md"
)

PIPELINE = [
    ("temporal_derivatives", temporal_derivatives),
    ("stability", stability),
    ("physical_ratios", physical_ratios),
    ("energetic_features", energetic_features),
    ("operative_features", operative_features),
    ("anomaly_features", anomaly_features),
]

log = logging.getLogger("feature_engineering")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--features", type=Path, default=DEFAULT_FEATURES_IN)
    p.add_argument("--classification", type=Path, default=DEFAULT_CLASSIFICATION)
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--out-parquet", type=Path, default=DEFAULT_ENGINEERED_OUT)
    p.add_argument(
        "--out-csv",
        type=Path,
        default=None,
        help="Optional CSV mirror of the engineered matrix (large files).",
    )
    p.add_argument("--out-json", type=Path, default=DEFAULT_REPORT_JSON)
    p.add_argument("--out-md", type=Path, default=DEFAULT_REPORT_MD)
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Skip writing the engineered matrix; still emit the report.",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def run(
    features_path: Path,
    classification: Path,
    policy_path: Path,
) -> tuple[pd.DataFrame, list[Finding]]:
    """Execute the full pipeline and return ``(engineered_df, all_findings)``."""
    log.info("Loading policy from %s", policy_path)
    policy: FeatureEngineeringPolicy = load_policy(policy_path)

    log.info("Loading features from %s", features_path)
    t0 = time.perf_counter()
    df = load_features(features_path)
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
            "Stage %-22s: %4d findings (%.1fs); shape now %s",
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

    df, findings = run(args.features, args.classification, args.policy)

    log.info("Writing report → %s", args.out_json)
    write_json(findings, args.out_json)
    log.info("Writing report → %s", args.out_md)
    write_markdown(findings, args.out_md, title="Feature Engineering Report")

    if args.no_write:
        log.info("--no-write: skipping engineered matrix output")
    else:
        log.info(
            "Writing engineered matrix → %s (%d rows x %d cols)",
            args.out_parquet, len(df), df.shape[1],
        )
        write_engineered(df, args.out_parquet, args.out_csv)

    log.info("Done. %d total findings.", len(findings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
