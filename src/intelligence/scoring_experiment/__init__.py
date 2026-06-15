"""Controlled Scoring Experiment — Iteration C Part 3.

Runs controlled, **interpretive** post-processing scenarios over the
*persisted* anomaly, drift and incident outputs. It never refits a model,
never recomputes PCA/Mahalanobis from altered matrices and never overwrites
an original score. Every scenario preserves the original severity/score and
writes its adjustments into clearly separated ``adjusted_review_*`` columns.

Scenarios: ``baseline_v1`` (unchanged), a quarantine-aware interpretive
review view, a healthy-only proxy view (from the drift run), and a
reference-candidate diagnostic. The component then builds a decision-report
forensic addendum for human review. See
:mod:`src.intelligence.scoring_experiment.run_scoring_experiment`.
"""
