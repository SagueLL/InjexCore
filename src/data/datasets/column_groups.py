"""Re-export the cleaning ``ColumnGroups`` loader for the
specialized-datasets stage.

Selectors and master-validation read the semantic catalogue (Process /
Control / State / Metadata + setpoint / running / alarm subsets) via
:func:`ColumnGroups.semantic_category` to filter columns by category
without duplicating routing logic.
"""
from src.data.cleaning.column_groups import (
    DEFAULT_CLASSIFICATION,
    ColumnGroups,
    load_groups,
)

__all__ = ["ColumnGroups", "load_groups", "DEFAULT_CLASSIFICATION"]
