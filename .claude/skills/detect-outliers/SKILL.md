---
name: detect-outliers
description: Detect statistical outliers, suspicious sensor values, abnormal distributions, and extreme observations in a dataset — ranked by severity, with downstream ML impact analysis — without auto-removing data. Use when the user asks to find, analyze, or rank outliers, anomalies, or extreme values in a dataset (statistical detection, not classification-model anomaly detection).
---

# PURPOSE

Detect anomalous, suspicious, or statistically unusual observations
within datasets and feature spaces.

The skill should identify outliers while preserving contextual awareness.

---

# RESPONSIBILITIES

- Detect statistical outliers
- Detect suspicious sensor values
- Detect abnormal feature distributions
- Detect extreme observations
- Detect inconsistent records
- Evaluate anomaly severity
- Analyze potential downstream impact

---

# NON-GOALS

- Do not remove outliers automatically
- Do not assume anomalies are errors
- Do not ignore domain context
- Do not oversimplify anomaly detection

---

# TOOLS

- Read
- Write

---

# INPUTS

- Dataset
- Target features
- Detection thresholds (optional)
- Domain constraints (optional)

---

# WORKFLOW

1. Analyze feature distributions
2. Detect statistical anomalies
3. Evaluate contextual abnormality
4. Assess downstream impact
5. Rank anomaly severity
6. Produce structured anomaly report

---

# OUTPUT FORMAT

# Outlier Summary
# Anomalous Features
# Suspicious Records
# Distribution Analysis
# Severity Assessment
# ML Impact Risks
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve contextual awareness
- Avoid simplistic anomaly assumptions
- Prioritize meaningful findings
- Focus on downstream ML impact
- Preserve interpretability

---

# FAILURE BEHAVIOR

If dataset visibility is incomplete:
- explicitly state uncertainty
- avoid unsupported anomaly claims
- analyze only observable evidence

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Time-series anomaly analysis
- Sensor anomaly validation
- Drift-aware anomaly detection
- Multivariate anomaly analysis
