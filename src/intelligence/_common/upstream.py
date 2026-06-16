"""Loaders for the persisted Behaviour Intelligence artifacts.

Iteration B/C components never re-derive profiles or recompute the train/
validation split — they consume what behaviour persisted: the per-row
``profile`` label, the ``is_train`` flag and the fit manifest. That is the
leakage contract of the layer: one split, fitted once, reused everywhere.

Behaviour is run-versioned (``data/intelligence/behaviour/runs/<run_id>/``).
The loaders resolve the **latest completed** behaviour run by default;
:func:`resolve_behaviour_run` is the single resolution point, and the manifest
self-reports its ``run_id`` + ``master_dataset_sha256`` so downstream lineage
checks can verify the whole chain shares one behaviour run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.intelligence._common.runs import LATEST, resolve_run
from src.intelligence.behaviour.io import BASELINES_FILE, PROFILE_LABELS_FILE
from src.intelligence.behaviour.io import BEHAVIOUR_DIR as BEHAVIOUR_DIR
from src.intelligence.behaviour.io import COMPONENT as BEHAVIOUR_COMPONENT
from src.intelligence.behaviour.io import MANIFEST_NAME as BEHAVIOUR_MANIFEST_NAME

# Sentinels: ``None`` means "resolve the latest completed behaviour run".
# Kept as importable names so consumer CLIs can keep ``default=DEFAULT_*`` and
# transparently get latest-run resolution under the clean cutover.
DEFAULT_PROFILE_LABELS: Path | None = None
DEFAULT_BASELINES: Path | None = None
DEFAULT_BEHAVIOUR_MANIFEST: Path | None = None

_LABEL_COLUMNS = ("profile", "is_train")
_BASELINE_KEY_COLUMNS = ("profile", "sensor", "count", "median", "iqr")


def resolve_behaviour_run(behaviour_root: Path = BEHAVIOUR_DIR) -> Path:
    """Resolve the latest *completed* behaviour run directory.

    Raises ``FileNotFoundError`` when no completed behaviour run exists — the
    caller must run the behaviour component first.
    """
    return resolve_run(
        behaviour_root,
        LATEST,
        BEHAVIOUR_MANIFEST_NAME,
        expected_component=BEHAVIOUR_COMPONENT,
    )


def load_profile_labels(path: Path | None = None) -> pd.DataFrame:
    """Load behaviour's per-row profile labels, timestamp-indexed.

    ``path`` defaults to the latest completed behaviour run's labels file.
    """
    if path is None:
        path = resolve_behaviour_run() / PROFILE_LABELS_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Profile labels not found at {path} — run the behaviour component first."
        )
    labels = pd.read_parquet(path)
    if "timestamp" in labels.columns:
        labels["timestamp"] = pd.to_datetime(labels["timestamp"], errors="coerce")
        labels = labels.set_index("timestamp")
    missing = [c for c in _LABEL_COLUMNS if c not in labels.columns]
    if missing:
        raise ValueError(f"Profile labels at {path} are missing columns {missing}.")
    return labels


def load_behaviour_manifest(path: Path | None = None) -> dict[str, Any]:
    """Load behaviour's fit manifest (train-window bounds, master sha, ...).

    ``path`` defaults to the latest completed behaviour run's manifest.
    """
    if path is None:
        path = resolve_behaviour_run() / BEHAVIOUR_MANIFEST_NAME
    if not path.exists():
        raise FileNotFoundError(
            f"Behaviour fit manifest not found at {path} — "
            "run the behaviour component first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_baselines(path: Path | None = None) -> pd.DataFrame:
    """Load behaviour's long-form per-(profile, sensor) baseline table.

    ``path`` defaults to the latest completed behaviour run's baselines file.
    """
    if path is None:
        path = resolve_behaviour_run() / BASELINES_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Baselines not found at {path} — run the behaviour component first."
        )
    baselines = pd.read_parquet(path)
    missing = [c for c in _BASELINE_KEY_COLUMNS if c not in baselines.columns]
    if missing:
        raise ValueError(f"Baselines at {path} are missing columns {missing}.")
    return baselines


def align_labels(df: pd.DataFrame, labels: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Align persisted labels to the master frame; strict, no reindexing.

    Returns ``(profile, train_mask)`` Series on ``df.index``. Raises
    ``ValueError`` when the indices differ — that means the master dataset
    changed since behaviour ran, and silently realigning would break the
    leakage contract. Re-run behaviour instead.
    """
    if len(df) != len(labels) or not df.index.equals(labels.index):
        raise ValueError(
            "Master dataset index does not match the persisted profile labels "
            f"({len(df)} master rows vs {len(labels)} label rows) — the master "
            "changed since behaviour was fitted. Re-run the behaviour component."
        )
    profile = labels["profile"].astype(str)
    train_mask = labels["is_train"].astype(bool)
    return profile, train_mask
