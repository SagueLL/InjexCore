"""Shim: semantic column catalogue for Intelligence-Layer components.

Same idiom as :mod:`src.intelligence.behaviour.column_groups` — the canonical
implementation lives in the neutral ``src/preprocessing/_common/`` package.
"""

from __future__ import annotations

from src.preprocessing._common.column_groups import (
    DEFAULT_CLASSIFICATION,
    ColumnGroups,
    load_groups,
)

__all__ = ["ColumnGroups", "load_groups", "DEFAULT_CLASSIFICATION"]
