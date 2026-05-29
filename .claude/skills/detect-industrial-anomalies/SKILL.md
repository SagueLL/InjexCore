---
name: detect-industrial-anomalies
description: Detect anomalous patterns and abnormal behavior in industrial, sensor, and telemetry datasets — process deviations, suspicious readings, abnormal temporal behavior, abnormal distributions — to support predictive maintenance analysis, with contextual awareness (does not assume anomalies are failures). Use when the user asks to find anomalies, deviations, or abnormal patterns in industrial/machine/sensor data.
---

# PURPOSE

Detect anomalous patterns, abnormal behavior,
and suspicious observations within industrial,
sensor, telemetry, and ML datasets.

The skill should identify meaningful anomalies while preserving contextual awareness.

---

# RESPONSIBILITIES

- Detect statistical anomalies
- Detect abnormal telemetry behavior
- Detect suspicious sensor readings
- Detect process deviations
- Detect unusual temporal behavior
- Detect abnormal feature distributions
- Support predictive maintenance analysis
- Identify potentially relevant anomaly clusters

---

# NON-GOALS

- Do not assume anomalies are failures
- Do not remove anomalous records automatically
- Do not fabricate root-cause explanations
- Do not oversimplify anomaly interpretation

---

# TOOLS

- Read
- Write

---

# INPUTS

- Dataset or telemetry data
- Target features
- Optional anomaly thresholds
- Optional domain constraints

---

# WORKFLOW

1. Analyze dataset structure and distributions
2. Detect statistical and contextual anomalies
3. Analyze temporal and behavioral patterns
4. Evaluate anomaly consistency and significance
5. Identify high-risk observations
6. Produce structured anomaly analysis report

---

# OUTPUT FORMAT

# Anomaly Overview
# Detected Anomalies
# Suspicious Features
# Temporal Patterns
# Severity Indicators
# Potential Risks
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve contextual awareness
- Avoid simplistic anomaly assumptions
- Prioritize meaningful findings
- Focus on downstream operational impact
- Preserve interpretability

---

# FAILURE BEHAVIOR

If telemetry structure is incomplete:
- explicitly state limitations
- avoid unsupported anomaly claims
- analyze only observable evidence

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Online anomaly detection
- Streaming telemetry analysis
- Multivariate anomaly analysis
- Sensor drift analysis
- Sequence anomaly detection
