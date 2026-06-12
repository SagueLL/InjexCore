"""BOM Operational Context Layer.

Transforms the raw BOM / production-order CSV into validated contextual
datasets (normalized components, aggregated orders, overlap/gap/transition
diagnostics, a master-aligned context timeline) plus a read-only BOM-aware
forensic addendum. Context engineering only: this component never modifies
the master dataset, never refits Intelligence-Layer models, never changes
anomaly thresholds, Behaviour profiles, or the training window.
"""
