"""Backward-compatible re-export of the shared column-group helpers.

The canonical definitions now live in :mod:`src.preprocessing._common.column_groups`.
This shim keeps the historical ``src.preprocessing.cleaning.column_groups`` import
path valid for the cleaning modules and their tests.
"""

from src.preprocessing._common.column_groups import (
    DEFAULT_CLASSIFICATION,
    ColumnGroups,
    load_groups,
)

__all__ = ["ColumnGroups", "load_groups", "DEFAULT_CLASSIFICATION"]
