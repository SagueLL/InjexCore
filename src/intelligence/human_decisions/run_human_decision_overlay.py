"""CLI for the Human Decision Overlay.

Encodes the reviewer's scoped ``inlet_hopper_points`` quarantine approval and
the Reference v2 deferral as a run-versioned, read-only artifact under
``data/intelligence/forensics/human_decisions/<run_id>/``. It mutates no
existing artifact, approves nothing in the pipeline, refits nothing and
rescores nothing. The manifest is written last (completion marker).

Usage::

    python -m src.intelligence.human_decisions.run_human_decision_overlay
    python -m src.intelligence --component human-decision --no-write
    python -m src.intelligence.human_decisions.run_human_decision_overlay \
        --scope-start-row 137235 --human-reported-row 137237
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from src.intelligence.human_decisions import decision, io

log = logging.getLogger("human_decision_overlay")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else "")
    p.add_argument("--canonical-run", default=decision.CANONICAL_RUN_ID)
    p.add_argument("--bom-run", default=decision.BOM_RUN_ID)
    p.add_argument(
        "--reference-decision-run",
        default=None,
        help="reference_decision run id (default: the canonical run).",
    )
    p.add_argument("--target-sensor", default=decision.TARGET_SENSOR)
    p.add_argument(
        "--scope-start-row",
        type=int,
        default=decision.DETECTED_ONSET_ROW,
        help="Authoritative boundary row (default: detected onset 137235).",
    )
    p.add_argument(
        "--human-reported-row",
        type=int,
        default=decision.HUMAN_REPORTED_ROW,
        help="Row the reviewer reported (preserved for traceability).",
    )
    p.add_argument(
        "--master-path",
        type=Path,
        default=io.DEFAULT_MASTER_IN,
        help="Master parquet for read-only boundary verification (optional).",
    )
    p.add_argument(
        "--output-root",
        type=Path,
        default=io.HUMAN_DECISIONS_DIR,
        help="Root; artifacts land under <root>/<run_id>/.",
    )
    p.add_argument(
        "--run-id",
        default=None,
        help="Run id (default: fresh human-decision-v1-<UTC>; never overwrites).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Diagnostic only: build everything, write nothing.",
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
    spec = decision.make_spec(
        canonical_run_id=args.canonical_run,
        bom_run_id=args.bom_run,
        reference_decision_run_id=args.reference_decision_run or args.canonical_run,
        target_sensor=args.target_sensor,
        scope_start_row=args.scope_start_row,
        human_reported_row=args.human_reported_row,
    )
    run_id = args.run_id or io.new_run_id()
    created_at = datetime.now(UTC).isoformat()

    master = io.load_boundary_columns(args.master_path, decision.BOUNDARY_COLUMNS)
    verification = decision.verify_boundary(master, spec)
    log.info("Boundary verification: %s", verification)

    art = decision.build_overlay(spec, run_id, created_at, verification)

    if args.no_write:
        log.info("--no-write: built overlay for run %s; wrote nothing.", run_id)
        return 0

    out = io.create_run_dir(args.output_root, run_id)
    written = decision.write_overlay(art, out)
    log.info("Wrote human decision overlay (%d files) → %s", len(written), out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
