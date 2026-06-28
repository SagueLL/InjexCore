"""Overlay assembly — one context row per master timestamp.

Pure column composition: profile + is_train (behaviour), steam context
(derived), sensor-health context (consumed) and the full BOM column set
(preserved). Alignment is the caller's responsibility (hard-gated in
``validation``); this module assumes positionally identical timestamps.
"""

from __future__ import annotations

import pandas as pd

from src.context.operational.bom import BOM_COLUMNS
from src.context.operational.policy import ContextKeyPolicy
from src.context.operational.sensor_health import HEALTH_COLUMNS

#: Overlay schema, in output order (the contract).
OVERLAY_COLUMNS = [
    "timestamp",
    "profile",
    "is_train",
    "steam_context",
    "steam_context_confidence",
    "steam_context_evidence",
    *HEALTH_COLUMNS,
    *BOM_COLUMNS,
    "context_key",
]


def build_overlay(
    master_ts: pd.Series,
    profile: pd.Series,
    is_train: pd.Series,
    steam: pd.DataFrame,
    health: pd.DataFrame,
    bom: pd.DataFrame,
    key_policy: ContextKeyPolicy,
) -> pd.DataFrame:
    """Assemble the master-aligned operational context timeline."""
    overlay = pd.DataFrame(
        {
            "timestamp": master_ts.to_numpy(),
            "profile": profile.to_numpy(),
            "is_train": is_train.to_numpy().astype(bool),
        }
    )
    for col in ("steam_context", "steam_context_confidence", "steam_context_evidence"):
        overlay[col] = steam[col].to_numpy()
    for col in HEALTH_COLUMNS:
        overlay[col] = health[col].to_numpy()
    for col in BOM_COLUMNS:
        overlay[col] = bom[col].to_numpy()
    overlay["context_key"] = (
        context_key(overlay, key_policy.fields) if key_policy.enabled else ""
    )
    return overlay[OVERLAY_COLUMNS]


def context_key(overlay: pd.DataFrame, fields: list[str]) -> pd.Series:
    """Deterministic composite key (metadata only, never a model input).

    Missing/null field values render as ``null`` so the key stays total and
    reproducible; fields are joined with ``:`` in policy order.
    """
    parts = [
        overlay[f].map(lambda v: "null" if pd.isna(v) or v == "" else str(v))
        for f in fields
    ]
    out = parts[0]
    for p in parts[1:]:
        out = out + ":" + p
    return out.rename("context_key")
