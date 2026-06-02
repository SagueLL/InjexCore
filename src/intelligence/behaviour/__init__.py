"""Behaviour Intelligence — characterise NORMAL machine behaviour.

First component of the Intelligence Layer. Consumes the schema-locked
``data/datasets/master/master_dataset.parquet`` and produces *descriptive*
artifacts that define what "normal" looks like, so downstream anomaly /
predictive models have a reference to deviate from.

Iteration A (this build):

* :mod:`~src.intelligence.behaviour.profiles` — derive operational
  regimes (stopped / startup / shutdown / alarm / low|mid|high production)
  from the signals the real data actually supports; document
  non-derivable regimes (cleaning, maintenance, recipe change) honestly.
* :mod:`~src.intelligence.behaviour.baselines` — per-profile, per-sensor
  statistical baselines, fitted **leakage-safe** on a training window only.
* :mod:`~src.intelligence.behaviour.validation` — profile-quality
  diagnostics (distribution, durations, transitions, coverage).

Correlation Intelligence and PCA are deferred to Iteration B; the module
layout, ``fit(...)`` contract and the persisted fit manifest are designed
so they drop in as new modules without reworking the foundation.

Public entry point: :func:`src.intelligence.behaviour.run_behaviour.main`.
"""

from src.intelligence.behaviour.reporting import Finding, Severity

__all__ = ["Finding", "Severity"]
