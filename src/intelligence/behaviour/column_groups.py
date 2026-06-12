"""Re-export the shared ``ColumnGroups`` loader for the Behaviour
Intelligence stage.

Profile segmentation and statistical baselines read the semantic
catalogue (Process / Control / State / Metadata + setpoint / running /
alarm subsets) via :class:`ColumnGroups` to select the sensor set without
duplicating routing logic. Identical import surface to the data stages so
contracts stay uniform.
"""

from src.preprocessing._common.column_groups import (
    DEFAULT_CLASSIFICATION,
    ColumnGroups,
    load_groups,
)

__all__ = ["ColumnGroups", "load_groups", "DEFAULT_CLASSIFICATION"]
