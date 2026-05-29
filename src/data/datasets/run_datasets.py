"""CLI orchestrator for the InjexCore specialized-datasets stage.

Linear order:

    load_engineered → master_validation
                    → anomaly_projection
                    → forecasting_projection
                    → energy_projection
                    → write 4 parquet files + 4 JSON/MD report pairs

Inputs (defaults; override with CLI flags):

* ``data/features/Dades_pellet_engineered.parquet`` — feature-engineering
  output (the upstream dependency).
* ``configs/specialized_datasets.yaml`` — policy.
* ``data/features/variable_classification.csv`` — semantic catalogue.

Outputs:

* ``data/datasets/master/master_dataset.parquet`` + report.
* ``data/datasets/specialized/anomaly_detection_dataset.parquet`` + report.
* ``data/datasets/specialized/forecasting_dataset.parquet`` + report.
* ``data/datasets/specialized/energy_dataset.parquet`` + report.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.data.datasets import (
    anomaly_projection,
    energy_projection,
    forecasting_projection,
    master_validation,
)
from src.data.datasets.column_groups import (
    DEFAULT_CLASSIFICATION,
    load_groups,
)
from src.data.datasets.io import (
    DEFAULT_ANOMALY_OUT,
    DEFAULT_ANOMALY_REPORT_JSON,
    DEFAULT_ANOMALY_REPORT_MD,
    DEFAULT_ENERGY_OUT,
    DEFAULT_ENERGY_REPORT_JSON,
    DEFAULT_ENERGY_REPORT_MD,
    DEFAULT_ENGINEERED_IN,
    DEFAULT_FORECASTING_OUT,
    DEFAULT_FORECASTING_REPORT_JSON,
    DEFAULT_FORECASTING_REPORT_MD,
    DEFAULT_MASTER_OUT,
    DEFAULT_MASTER_REPORT_JSON,
    DEFAULT_MASTER_REPORT_MD,
    DEFAULT_SCHEMA_LOCK,
    load_engineered,
    write_dataset,
)
from src.data.datasets.policy import (
    SpecializedDatasetsPolicy,
    load_policy,
)
from src.data.datasets.reporting import Finding, write_json, write_markdown

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_POLICY = PROJECT_ROOT / "configs" / "specialized_datasets.yaml"

log = logging.getLogger("datasets")


@dataclass(frozen=True)
class DatasetOutput:
    """One produced dataset (master or one of the three specialized)."""

    name: str
    title: str
    df: pd.DataFrame
    findings: list[Finding]
    parquet_path: Path
    report_json: Path
    report_md: Path


# Pipeline definition: the master pass runs first; the three projections
# read from the master DataFrame returned by it. Stored as a list of
# names so the orchestrator can iterate predictably.
PIPELINE = [
    "master_validation",
    "anomaly_detection",
    "forecasting",
    "energy",
]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--engineered", type=Path, default=DEFAULT_ENGINEERED_IN)
    p.add_argument("--classification", type=Path, default=DEFAULT_CLASSIFICATION)
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--schema-lock", type=Path, default=DEFAULT_SCHEMA_LOCK)
    # Master outputs
    p.add_argument("--master-parquet", type=Path, default=DEFAULT_MASTER_OUT)
    p.add_argument(
        "--master-report-json", type=Path, default=DEFAULT_MASTER_REPORT_JSON
    )
    p.add_argument(
        "--master-report-md", type=Path, default=DEFAULT_MASTER_REPORT_MD
    )
    # Anomaly outputs
    p.add_argument("--anomaly-parquet", type=Path, default=DEFAULT_ANOMALY_OUT)
    p.add_argument(
        "--anomaly-report-json", type=Path, default=DEFAULT_ANOMALY_REPORT_JSON
    )
    p.add_argument(
        "--anomaly-report-md", type=Path, default=DEFAULT_ANOMALY_REPORT_MD
    )
    # Forecasting outputs
    p.add_argument(
        "--forecasting-parquet", type=Path, default=DEFAULT_FORECASTING_OUT
    )
    p.add_argument(
        "--forecasting-report-json",
        type=Path,
        default=DEFAULT_FORECASTING_REPORT_JSON,
    )
    p.add_argument(
        "--forecasting-report-md",
        type=Path,
        default=DEFAULT_FORECASTING_REPORT_MD,
    )
    # Energy outputs
    p.add_argument("--energy-parquet", type=Path, default=DEFAULT_ENERGY_OUT)
    p.add_argument(
        "--energy-report-json", type=Path, default=DEFAULT_ENERGY_REPORT_JSON
    )
    p.add_argument(
        "--energy-report-md", type=Path, default=DEFAULT_ENERGY_REPORT_MD
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Skip writing the four parquet files; still emit reports.",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def run(
    engineered_path: Path,
    classification: Path,
    policy_path: Path,
    *,
    schema_lock_path: Path | None = None,
) -> tuple[
    tuple[pd.DataFrame, list[Finding]],
    tuple[pd.DataFrame, list[Finding]],
    tuple[pd.DataFrame, list[Finding]],
    tuple[pd.DataFrame, list[Finding]],
]:
    """Execute the full pipeline.

    Returns ``(master, anomaly, forecasting, energy)`` where each entry
    is a ``(DataFrame, findings)`` tuple. The three projections operate
    on the master DataFrame returned by ``master_validation`` (i.e.
    after any policy-driven column drops).
    """
    log.info("Loading policy from %s", policy_path)
    policy: SpecializedDatasetsPolicy = load_policy(policy_path)

    log.info("Loading engineered matrix from %s", engineered_path)
    t0 = time.perf_counter()
    engineered = load_engineered(engineered_path)
    log.info(
        "Loaded %d rows x %d cols in %.1fs",
        len(engineered), engineered.shape[1], time.perf_counter() - t0,
    )

    groups = load_groups(classification)

    t0 = time.perf_counter()
    master_df, master_findings = master_validation.run(
        engineered, policy, groups, schema_lock_path=schema_lock_path,
    )
    log.info(
        "Stage %-22s: %4d findings (%.1fs); master shape %s",
        "master_validation", len(master_findings),
        time.perf_counter() - t0, master_df.shape,
    )

    projections: list[tuple[pd.DataFrame, list[Finding]]] = []
    for name, module in (
        ("anomaly_detection", anomaly_projection),
        ("forecasting", forecasting_projection),
        ("energy", energy_projection),
    ):
        t0 = time.perf_counter()
        df, findings = module.run(master_df, policy, groups)
        log.info(
            "Stage %-22s: %4d findings (%.1fs); shape %s",
            name, len(findings), time.perf_counter() - t0, df.shape,
        )
        projections.append((df, findings))

    return (
        (master_df, master_findings),
        projections[0],
        projections[1],
        projections[2],
    )


def _write_report(findings: list[Finding], json_path: Path, md_path: Path, title: str) -> None:
    write_json(findings, json_path)
    write_markdown(findings, md_path, title=title)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    master, anomaly, forecasting, energy = run(
        args.engineered,
        args.classification,
        args.policy,
        schema_lock_path=args.schema_lock,
    )

    outputs = [
        DatasetOutput(
            name="master",
            title="Master Dataset Report",
            df=master[0],
            findings=master[1],
            parquet_path=args.master_parquet,
            report_json=args.master_report_json,
            report_md=args.master_report_md,
        ),
        DatasetOutput(
            name="anomaly_detection",
            title="Anomaly Detection Dataset Report",
            df=anomaly[0],
            findings=anomaly[1],
            parquet_path=args.anomaly_parquet,
            report_json=args.anomaly_report_json,
            report_md=args.anomaly_report_md,
        ),
        DatasetOutput(
            name="forecasting",
            title="Forecasting Dataset Report",
            df=forecasting[0],
            findings=forecasting[1],
            parquet_path=args.forecasting_parquet,
            report_json=args.forecasting_report_json,
            report_md=args.forecasting_report_md,
        ),
        DatasetOutput(
            name="energy",
            title="Energy Dataset Report",
            df=energy[0],
            findings=energy[1],
            parquet_path=args.energy_parquet,
            report_json=args.energy_report_json,
            report_md=args.energy_report_md,
        ),
    ]

    total_findings = 0
    for out in outputs:
        log.info("Writing report → %s", out.report_json)
        _write_report(out.findings, out.report_json, out.report_md, out.title)
        total_findings += len(out.findings)
        if args.no_write:
            log.info(
                "--no-write: skipping %s parquet (%d cols)",
                out.name, out.df.shape[1],
            )
            continue
        log.info(
            "Writing %-18s → %s (%d rows x %d cols)",
            out.name, out.parquet_path, out.df.shape[0], out.df.shape[1],
        )
        write_dataset(out.df, out.parquet_path)

    log.info("Done. %d total findings across 4 reports.", total_findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
