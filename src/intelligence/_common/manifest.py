"""Fit-manifest assembly shared by Iteration B components.

Every component persists a manifest recording exactly what was fitted on
what — the reproducible fit contract that scoring (and the future
``src/models/`` estimators) consume. ``base_manifest`` covers the fields
common to all components; each orchestrator extends the dict with its own
(thresholds, per-profile support, upstream run ids, ...). Orchestrators
write the manifest **last**: its presence marks the run as complete (see
:mod:`src.intelligence._common.runs`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.intelligence._common.fingerprint import dataset_fingerprint
from src.preprocessing._common.models import StrictModel


def base_manifest(
    *,
    component: str,
    run_id: str,
    policy: StrictModel,
    df: pd.DataFrame,
    train_mask: pd.Series,
    features: list[str],
    master_path: Path,
    upstream: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the component-agnostic part of a fit manifest."""
    n_train = int(train_mask.sum())
    train_start = train_end = None
    if isinstance(df.index, pd.DatetimeIndex) and n_train:
        train_idx = df.index[train_mask.to_numpy()]
        train_start = str(train_idx.min())
        train_end = str(train_idx.max())
    return {
        "component": component,
        "run_id": run_id,
        "fit_timestamp": datetime.now(UTC).isoformat(),
        "dataset_fingerprint": dataset_fingerprint(df, master_path),
        "fit_window": {
            "n_train": n_train,
            "n_total": int(len(df)),
            "train_start": train_start,
            "train_end": train_end,
        },
        "features": features,
        "config_snapshot": policy.model_dump(),
        "upstream": upstream,
    }
