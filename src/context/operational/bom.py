"""BOM context consumption for the overlay.

Reads a *completed* BOM context run's master-aligned timeline and preserves
its full column set unchanged: overlap rows keep all matching orders in the
pipe-joined list columns with scalar columns null — the overlay never
re-parses BOM data and never silently chooses one order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.context.operational.io import BOM_MANIFEST

#: BOM columns preserved verbatim on the overlay (everything but timestamp).
BOM_COLUMNS = [
    "bom_context_status",
    "active_order_count",
    "order_id",
    "order_ids",
    "product_code",
    "product_codes",
    "recipe_version",
    "recipe_versions",
    "recipe_context_key",
    "recipe_context_keys",
    "bom_signature",
    "bom_signatures",
    "is_transition_overlap",
    "has_active_order",
]


def load_bom_timeline(run_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """BOM context timeline + manifest of a completed BOM run."""
    timeline = pd.read_parquet(run_path / "timeline" / "bom_context_timeline.parquet")
    timeline["timestamp"] = pd.to_datetime(timeline["timestamp"], errors="raise")
    missing = [c for c in BOM_COLUMNS if c not in timeline.columns]
    if missing:
        raise ValueError(
            f"BOM context timeline at {run_path} is missing columns {missing}"
        )
    manifest = json.loads((run_path / BOM_MANIFEST).read_text(encoding="utf-8"))
    return timeline, manifest
