"""Re-export the cleaning ``ColumnGroups`` loader for use in the
time-series pipeline.

The semantic routing helper (``ColumnGroups.semantic_category``) lives on
the dataclass itself in :mod:`src.data.cleaning.column_groups`, so every
TS stage can resolve a column to its category without duplicating logic.
"""
from src.data.cleaning.column_groups import (
    DEFAULT_CLASSIFICATION,
    ColumnGroups,
    load_groups,
)

__all__ = ["ColumnGroups", "load_groups", "DEFAULT_CLASSIFICATION"]
