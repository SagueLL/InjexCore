"""Loaders for the persisted Behaviour Intelligence artifacts.

Iteration B components never re-derive profiles or recompute the train/
validation split — they consume what behaviour persisted: the per-row
``profile`` label, the ``is_train`` flag and the fit manifest. That is the
leakage contract of the layer: one split, fitted once, reused everywhere.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import INTELLIGENCE_DIR

BEHAVIOUR_DIR = INTELLIGENCE_DIR / "behaviour"
DEFAULT_PROFILE_LABELS = BEHAVIOUR_DIR / "profiles" / "profile_labels.parquet"
DEFAULT_BASELINES = BEHAVIOUR_DIR / "baselines" / "baselines.parquet"
DEFAULT_BEHAVIOUR_MANIFEST = BEHAVIOUR_DIR / "behaviour_fit_manifest.json"

_LABEL_COLUMNS = ("profile", "is_train")
_BASELINE_KEY_COLUMNS = ("profile", "sensor", "count", "median", "iqr")


def load_profile_labels(path: Path = DEFAULT_PROFILE_LABELS) -> pd.DataFrame:
    """Load behaviour's per-row profile labels, timestamp-indexed."""
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


def load_behaviour_manifest(path: Path = DEFAULT_BEHAVIOUR_MANIFEST) -> dict[str, Any]:
    """Load behaviour's fit manifest (train-window bounds, sensors, ...)."""
    if not path.exists():
        raise FileNotFoundError(
            f"Behaviour fit manifest not found at {path} — "
            "run the behaviour component first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_baselines(path: Path = DEFAULT_BASELINES) -> pd.DataFrame:
    """Load behaviour's long-form per-(profile, sensor) baseline table."""
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
