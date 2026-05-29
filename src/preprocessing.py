"""Compatibility shim that re-exports the preprocessing entry points.

The real implementations live in :mod:`src.data.cleaning`,
:mod:`src.data.time_series`, :mod:`src.data.feature_engineering` and
:mod:`src.data.datasets`. This module exists so the CLI surface
documented in ``CLAUDE.md`` stays stable while the package grows.

Usage::

    python -m src.preprocessing                  # cleaning only (default)
    python -m src.preprocessing --stage cleaning
    python -m src.preprocessing --stage ts
    python -m src.preprocessing --stage fe       # feature engineering only
    python -m src.preprocessing --stage features # cleaning + ts + fe
    python -m src.preprocessing --stage datasets # specialized datasets only
    python -m src.preprocessing --stage all      # cleaning + ts + fe + datasets
"""
from __future__ import annotations

import sys

from src.data.cleaning.run_cleaning import main as cleaning_main
from src.data.cleaning.run_cleaning import run as cleaning_run
from src.data.datasets.run_datasets import main as datasets_main
from src.data.datasets.run_datasets import run as datasets_run
from src.data.feature_engineering.run_feature_engineering import main as fe_main
from src.data.feature_engineering.run_feature_engineering import run as fe_run
from src.data.time_series.run_ts_engineering import main as ts_main
from src.data.time_series.run_ts_engineering import run as ts_run

__all__ = [
    "main",
    "cleaning_main",
    "cleaning_run",
    "ts_main",
    "ts_run",
    "fe_main",
    "fe_run",
    "datasets_main",
    "datasets_run",
]

_STAGES = ("cleaning", "ts", "fe", "features", "datasets", "all")


def _split_stage_arg(argv: list[str]) -> tuple[str, list[str]]:
    """Extract ``--stage X`` from ``argv``; default to ``cleaning``.

    The stage flag is consumed here so each stage's own ``argparse`` sees
    only the args it understands. Supports ``--stage X`` and
    ``--stage=X``.
    """
    stage = "cleaning"
    rest: list[str] = []
    it = iter(argv)
    for tok in it:
        if tok == "--stage":
            stage = next(it, stage)
        elif tok.startswith("--stage="):
            stage = tok.split("=", 1)[1]
        else:
            rest.append(tok)
    if stage not in _STAGES:
        raise SystemExit(
            f"Unknown --stage {stage!r}; expected one of {_STAGES}."
        )
    return stage, rest


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    stage, rest = _split_stage_arg(argv)
    if stage == "cleaning":
        return cleaning_main(rest)
    if stage == "ts":
        return ts_main(rest)
    if stage == "fe":
        return fe_main(rest)
    if stage == "datasets":
        return datasets_main(rest)
    if stage == "features":
        # features: cleaning → ts → feature engineering (legacy chain).
        code = cleaning_main(rest)
        if code != 0:
            return code
        code = ts_main(rest)
        if code != 0:
            return code
        return fe_main(rest)
    # all: cleaning → ts → fe → specialized datasets.
    code = cleaning_main(rest)
    if code != 0:
        return code
    code = ts_main(rest)
    if code != 0:
        return code
    code = fe_main(rest)
    if code != 0:
        return code
    return datasets_main(rest)


if __name__ == "__main__":
    sys.exit(main())
