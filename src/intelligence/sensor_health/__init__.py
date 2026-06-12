"""Sensor Health Intelligence — instrumentation-anomaly detection.

Separates *instrumentation* anomalies (flatlines, counter resets, saturation,
missingness spikes, variance pathologies) from *process* anomalies so a
faulty sensor cannot silently contaminate process interpretation. Rule
references are fitted on behaviour's persisted train window only
(leakage-safe). The component detects, scores, persists and reports — it
recommends quarantine but never removes sensors from upstream datasets,
never refits models and never changes thresholds.
"""
