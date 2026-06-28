"""External operational-context layer.

Hosts components that turn external data sources (BOM / production orders,
plant records, ...) into validated contextual datasets joined against the
master timeline. Context engineering only: nothing in this package modifies
the master dataset, refits Intelligence-Layer models, or changes thresholds.
"""
