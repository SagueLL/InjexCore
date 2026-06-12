"""Specialized dataset construction for InjexCore.

Final preprocessing stage: promotes
``data/features/Dades_pellet_engineered.parquet`` to a canonical
**master dataset** and projects three downstream model-family-specific
datasets from it (anomaly detection, forecasting, energy).

This stage performs *selection + validation only* — it never computes
new features. Feature math lives in :mod:`src.preprocessing.feature_engineering`;
fitted models live in :mod:`src.models`.

Public entry point:
:func:`src.preprocessing.datasets.run_datasets.main`.
"""

from src.preprocessing.datasets.reporting import Finding, Severity

__all__ = ["Finding", "Severity"]
