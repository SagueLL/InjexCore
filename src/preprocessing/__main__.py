"""Combined ``--stage`` dispatcher for the preprocessing pipeline.

Lets the whole pipeline (or any single stage) run from one entry point while
the real implementations live in :mod:`src.preprocessing.cleaning`,
:mod:`src.preprocessing.time_series`,
:mod:`src.preprocessing.feature_engineering` and
:mod:`src.preprocessing.datasets`.

Usage::

    python -m src.preprocessing                  # cleaning only (default)
    python -m src.preprocessing --stage cleaning
    python -m src.preprocessing --stage ts
    python -m src.preprocessing --stage fe       # feature engineering only
    python -m src.preprocessing --stage features # cleaning + ts + fe
    python -m src.preprocessing --stage datasets # specialized datasets only
    python -m src.preprocessing --stage all      # cleaning + ts + fe + datasets

The chained stages (``features`` / ``all``) forward only the universal flags
``--no-write`` and ``--log-level`` to every stage. Stage-specific flags
(``--raw``, ``--clean``, ``--out-parquet`` ...) differ per stage and are
rejected in chained mode — run a single ``--stage`` to use them.
"""

from __future__ import annotations

import sys

from src.preprocessing.cleaning.run_cleaning import main as cleaning_main
from src.preprocessing.datasets.run_datasets import main as datasets_main
from src.preprocessing.feature_engineering.run_feature_engineering import (
    main as fe_main,
)
from src.preprocessing.time_series.run_ts_engineering import main as ts_main

_STAGES = ("cleaning", "ts", "fe", "features", "datasets", "all")
# Stages that fan the same argv out to multiple sub-stage parsers.
_CHAIN_STAGES = ("features", "all")
# Flags every stage's argparse understands, safe to forward in a chain.
_UNIVERSAL_FLAGS = ("--no-write", "--log-level")


def _first_non_universal(rest: list[str]) -> str | None:
    """Return the first token in ``rest`` that is not a universal flag.

    Used to reject stage-specific flags in chained modes, where the same
    ``rest`` is handed to every sub-stage parser and a flag understood by
    one stage would crash another. ``--log-level`` consumes its value.
    """
    it = iter(rest)
    for tok in it:
        if tok == "--no-write" or tok.startswith("--log-level="):
            continue
        if tok == "--log-level":
            next(it, None)  # skip the level value
            continue
        return tok
    return None


def _split_stage_arg(argv: list[str]) -> tuple[str, list[str]]:
    """Extract ``--stage X`` from ``argv``; default to ``cleaning``.

    The stage flag is consumed here so each stage's own ``argparse`` sees
    only the args it understands. Supports ``--stage X`` and ``--stage=X``.
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
        raise SystemExit(f"Unknown --stage {stage!r}; expected one of {_STAGES}.")
    return stage, rest


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    stage, rest = _split_stage_arg(argv)
    if stage in _CHAIN_STAGES:
        offending = _first_non_universal(rest)
        if offending is not None:
            raise SystemExit(
                f"Chained --stage {stage!r} only accepts the universal flags "
                f"{_UNIVERSAL_FLAGS} (got {offending!r}). Stage-specific flags "
                f"differ per stage; run a single --stage to use them."
            )
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
