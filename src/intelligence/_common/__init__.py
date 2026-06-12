"""Shared contracts and utilities for Intelligence-Layer components.

Iteration B components (correlation, pca, anomaly) import from here instead
of reaching into each other or duplicating logic. The package hosts:

* thin shims over the neutral ``src/preprocessing/_common/`` contracts
  (``reporting``, ``column_groups``) and over the behaviour stage's generic
  I/O helpers (``io``);
* intelligence-only utilities with no upstream equivalent: run versioning
  (``runs``), dataset fingerprinting (``fingerprint``), behaviour-artifact
  loaders (``upstream``), eligible-feature selection (``features``), model
  persistence (``persistence``) and fit-manifest assembly (``manifest``);
* reusable pydantic policy fragments (``policy``).
"""
