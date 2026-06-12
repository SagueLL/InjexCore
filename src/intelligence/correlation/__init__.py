"""Correlation Intelligence — per-profile variable-relationship analysis.

Characterizes how the eligible process signals move together inside each
supported operational profile: Pearson + Spearman matrices fitted on the
leakage-safe training window, strongest/redundant pair reports, and
train-vs-validation correlation-shift *diagnostics* (no alerts).

Consumes the persisted Behaviour Intelligence profile labels — it never
re-derives profiles or recomputes the train/validation split.
"""
