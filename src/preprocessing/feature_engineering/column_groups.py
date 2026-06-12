"""Re-export the shared ``ColumnGroups`` loader for use in the
feature engineering pipeline.

The semantic routing helper (``ColumnGroups.semantic_category``) lives on
the dataclass itself in :mod:`src.preprocessing._common.column_groups`, so every
feature engineering stage can resolve a column to its category without
duplicating logic.
"""

from src.preprocessing._common.column_groups import (
    DEFAULT_CLASSIFICATION,
    ColumnGroups,
    load_groups,
)

__all__ = ["ColumnGroups", "load_groups", "DEFAULT_CLASSIFICATION"]
