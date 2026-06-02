"""Time-series engineering package for InjexCore.

Six stages — temporal conversion, temporal index, optional resampling,
rolling windows, generic temporal features, specialised state features —
that turn a cleaned, evenly-spaced telemetry table into a feature matrix
for the downstream anomaly classifier.

Public entry point: :func:`src.preprocessing.time_series.run_ts_engineering.main`.
"""

from src.preprocessing.time_series.reporting import Finding, Severity

__all__ = ["Finding", "Severity"]
