"""Anomaly Intelligence v1 — explainable deviation detection per profile.

Four detectors, each fitted on the leakage-safe training window and scored
over every row of its profile:

* **statistical** — percentile breaches + robust deviation against the
  Behaviour Intelligence baselines (model-free; the baselines *are* the model);
* **mahalanobis** — regularized covariance (Ledoit-Wolf) distance with exact,
  signed per-variable contributions;
* **pca** — Hotelling T² and Q-residual from the persisted PCA Intelligence
  run, with thresholds fitted on training scores only;
* **isolation_forest** — seeded, persisted, score exposed transparently and
  *without* fabricated feature attributions.

Individual detector scores are always preserved; a simple configurable rule
(conservative max by default) produces a combined score and a
normal/warning/anomaly severity, with thresholds fitted on training data
only. Evidence wording stays descriptive ("primary contributing signals"),
never causal. v1 explicitly excludes deep learning, forecasting and
streaming — see the component documentation for the deferred list.
"""
