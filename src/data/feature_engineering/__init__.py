"""Feature engineering package for InjexCore.

Six families — temporal derivatives, stability, physical ratios,
energetic features, operative features and statistical anomaly features —
layered on top of the time-series engineering output to produce a
feature matrix ready for the downstream anomaly classifier.

Public entry point: :func:`src.data.feature_engineering.run_feature_engineering.main`.

Boundary with ``src/models/``: fitted estimators (Isolation Forest, LOF,
Mahalanobis with a covariance fit) are deliberately out of scope; they
belong in :mod:`src.models.anomaly`.
"""
from src.data.feature_engineering.reporting import Finding, Severity

__all__ = ["Finding", "Severity"]
