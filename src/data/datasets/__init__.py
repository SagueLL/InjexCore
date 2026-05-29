"""Specialized dataset construction for InjexCore.

Final preprocessing stage: promotes
``data/features/Dades_pellet_engineered.parquet`` to a canonical
**master dataset** and projects three downstream model-family-specific
datasets from it (anomaly detection, forecasting, energy).

This stage performs *selection + validation only* — it never computes
new features. Feature math lives in :mod:`src.data.feature_engineering`;
fitted models live in :mod:`src.models`.

Public entry point:
:func:`src.data.datasets.run_datasets.main`.
"""
from src.data.datasets.reporting import Finding, Severity

__all__ = ["Finding", "Severity"]
