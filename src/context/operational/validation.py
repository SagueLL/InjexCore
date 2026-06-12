"""Gate A + overlay invariants for the Operational Context layer.

Behaviour predates the dataset-fingerprint convention, so the de-facto
behaviour fingerprint is strict timestamp equality with the master (the
``align_labels`` contract). Every upstream timeline (sensor-health quality
timeline, BOM context timeline, anomaly scores in the addendum) must align
row-for-row with the master — a mismatch is a blocker, never degraded.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.context.operational.overlay import OVERLAY_COLUMNS
from src.context.operational.steam import STEAM_CONTEXTS

CHECK = "operational_context"


class OperationalContextBlockerError(RuntimeError):
    """A Gate A check failed; the run must stop and report, not degrade."""


def require_timestamp_alignment(
    name: str, timestamps: pd.Series, master_ts: pd.Series
) -> None:
    """Blocker unless ``timestamps`` equals the master's exactly, in order."""
    if len(timestamps) != len(master_ts):
        raise OperationalContextBlockerError(
            f"{name} has {len(timestamps)} rows, master has {len(master_ts)}"
        )
    if not (timestamps.to_numpy() == master_ts.to_numpy()).all():
        raise OperationalContextBlockerError(
            f"{name} timestamps differ from the master's — wrong upstream run?"
        )


def validate_upstream(
    master_ts: pd.Series,
    expected_rows: int | None,
    health_timeline: pd.DataFrame,
    bom_timeline: pd.DataFrame,
    behaviour_manifest: dict[str, Any],
    sensor_health_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Gate A: alignment + train-window coherence; returns compat_checks."""
    if expected_rows is not None and len(master_ts) != expected_rows:
        raise OperationalContextBlockerError(
            f"Master has {len(master_ts)} rows, expected {expected_rows}"
        )
    require_timestamp_alignment(
        "sensor_quality_timeline", health_timeline["timestamp"], master_ts
    )
    require_timestamp_alignment(
        "bom_context_timeline", bom_timeline["timestamp"], master_ts
    )
    behaviour_train_end = behaviour_manifest.get("fit_window", {}).get("train_end")
    sh_train_end = sensor_health_manifest.get("train_window", {}).get("train_end")
    if sh_train_end is not None and sh_train_end != behaviour_train_end:
        raise OperationalContextBlockerError(
            f"Sensor-health run used train_end {sh_train_end!r} but behaviour "
            f"persists {behaviour_train_end!r} — incompatible upstream runs"
        )
    return {
        "master_rows": int(len(master_ts)),
        "sensor_quality_timeline_aligned": True,
        "bom_timeline_aligned": True,
        "train_end_coherent": True,
        "behaviour_train_end": behaviour_train_end,
    }


def validate_overlay(overlay: pd.DataFrame, master_ts: pd.Series) -> None:
    """Hard invariants on the assembled overlay (blocker on violation)."""
    if list(overlay.columns) != OVERLAY_COLUMNS:
        raise OperationalContextBlockerError(
            f"Overlay columns deviate from the contract: {list(overlay.columns)}"
        )
    require_timestamp_alignment(
        "operational_context_timeline", overlay["timestamp"], master_ts
    )
    bad_steam = set(overlay["steam_context"].unique()) - set(STEAM_CONTEXTS)
    if bad_steam:
        raise OperationalContextBlockerError(
            f"Unknown steam contexts: {sorted(bad_steam)}"
        )
    overlap_rows = overlay["bom_context_status"] == "transition_overlap"
    if overlap_rows.any():
        leaked = int(overlay.loc[overlap_rows, "order_id"].notna().sum())
        if leaked:
            raise OperationalContextBlockerError(
                f"{leaked} overlap rows carry a scalar order_id — the overlay "
                "must preserve BOM's no-silent-selection policy"
            )
    if not np.isin(overlay["is_train"].unique(), [True, False]).all():
        raise OperationalContextBlockerError("is_train must be strictly boolean")
