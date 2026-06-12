"""Context-transition events — every change of the tracked dimensions.

One event row per timestamp where at least one tracked dimension changes;
simultaneous changes are preserved as multi-valued, pipe-joined
``transition_types`` (never collapsed to one). BOM overlap/gap edges are
derived from the preserved BOM columns.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.context.operational.policy import TransitionsPolicy

#: Closed vocabulary of transition types (the contract, not a tunable).
TRANSITION_TYPES = (
    "profile_change",
    "steam_context_change",
    "sensor_health_change",
    "product_change",
    "recipe_change",
    "bom_overlap_start",
    "bom_overlap_end",
    "bom_gap_start",
    "bom_gap_end",
)

TRANSITION_COLUMNS = [
    "transition_timestamp",
    "previous_profile",
    "new_profile",
    "previous_steam_context",
    "new_steam_context",
    "previous_sensor_health_context",
    "new_sensor_health_context",
    "previous_product_code",
    "new_product_code",
    "transition_types",
]


def _changed(series: pd.Series) -> np.ndarray:
    """True where the value differs from the previous row (NaN-stable)."""
    cur = series.map(lambda v: "null" if pd.isna(v) or v == "" else str(v))
    prev = cur.shift(1)
    out = np.array((cur != prev).to_numpy(), dtype=bool)
    out[0] = False  # the first row starts the timeline, it transitions nothing
    return out


def _edges(flags: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """(start, end) edges of a boolean condition."""
    cur = flags.fillna(False).astype(bool).to_numpy()
    prev = np.concatenate(([cur[0]], cur[:-1]))
    starts = cur & ~prev
    ends = ~cur & prev
    starts[0] = ends[0] = False
    return starts, ends


def detect_transitions(
    overlay: pd.DataFrame, policy: TransitionsPolicy
) -> pd.DataFrame:
    """All tracked dimension changes, multi-typed per timestamp."""
    n = len(overlay)
    masks: dict[str, np.ndarray] = {}
    if policy.track_profile:
        masks["profile_change"] = _changed(overlay["profile"])
    if policy.track_steam:
        masks["steam_context_change"] = _changed(overlay["steam_context"])
    if policy.track_sensor_health:
        masks["sensor_health_change"] = _changed(overlay["sensor_health_context"])
    if policy.track_product:
        masks["product_change"] = _changed(overlay["product_code"])
    if policy.track_recipe:
        masks["recipe_change"] = _changed(overlay["recipe_context_key"])
    if policy.track_bom_overlap:
        starts, ends = _edges(overlay["is_transition_overlap"])
        masks["bom_overlap_start"] = starts
        masks["bom_overlap_end"] = ends
    if policy.track_bom_gap:
        starts, ends = _edges(overlay["bom_context_status"] == "no_active_order")
        masks["bom_gap_start"] = starts
        masks["bom_gap_end"] = ends

    any_change = np.zeros(n, dtype=bool)
    for mask in masks.values():
        any_change |= mask

    rows: list[dict[str, Any]] = []
    for idx in np.flatnonzero(any_change):
        types = sorted(t for t, mask in masks.items() if mask[idx])
        rows.append(
            {
                "transition_timestamp": overlay["timestamp"].iloc[idx],
                "previous_profile": overlay["profile"].iloc[idx - 1],
                "new_profile": overlay["profile"].iloc[idx],
                "previous_steam_context": overlay["steam_context"].iloc[idx - 1],
                "new_steam_context": overlay["steam_context"].iloc[idx],
                "previous_sensor_health_context": overlay["sensor_health_context"].iloc[
                    idx - 1
                ],
                "new_sensor_health_context": overlay["sensor_health_context"].iloc[idx],
                "previous_product_code": overlay["product_code"].iloc[idx - 1],
                "new_product_code": overlay["product_code"].iloc[idx],
                "transition_types": "|".join(types),
            }
        )
    return pd.DataFrame(rows, columns=TRANSITION_COLUMNS)
