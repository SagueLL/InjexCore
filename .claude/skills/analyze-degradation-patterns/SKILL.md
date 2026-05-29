---
name: analyze-degradation-patterns
description: Analyze long-term degradation trends, progressive signal drift, and operational deterioration in industrial telemetry — identifying maintenance-relevant behavioral shifts while preserving uncertainty (does not guarantee failure prediction). Use when the user asks to analyze wear, drift, gradual deterioration, performance decline, or long-term behavioral changes in sensor/machine data.
---

# PURPOSE

Analyze degradation trends, progressive behavioral changes,
and long-term operational deterioration patterns
within industrial and telemetry datasets.

The skill should identify signals potentially relevant
to predictive maintenance workflows.

---

# RESPONSIBILITIES

- Detect gradual behavioral degradation
- Detect performance deterioration
- Detect progressive signal drift
- Detect operational instability trends
- Analyze temporal degradation patterns
- Identify maintenance-relevant behavioral shifts
- Support predictive maintenance analysis

---

# NON-GOALS

- Do not guarantee failure prediction
- Do not fabricate degradation causes
- Do not assume all drift implies degradation
- Do not oversimplify temporal behavior

---

# TOOLS

- Read
- Write

---

# INPUTS

- Telemetry or sensor data
- Time structure
- Operational context (optional)
- Monitoring targets (optional)

---

# WORKFLOW

1. Analyze temporal behavior
2. Detect progressive behavioral changes
3. Analyze long-term signal evolution
4. Evaluate operational consistency
5. Identify degradation indicators
6. Produce structured degradation analysis

---

# OUTPUT FORMAT

# Degradation Overview
# Temporal Trends
# Behavioral Drift Indicators
# Operational Stability Analysis
# Maintenance-Relevant Findings
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve temporal integrity
- Prioritize meaningful degradation analysis
- Avoid simplistic trend assumptions
- Preserve contextual awareness
- Focus on operational relevance

---

# FAILURE BEHAVIOR

If temporal consistency is incomplete:
- explicitly state limitations
- avoid unsupported degradation conclusions
- analyze only observable evidence

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Remaining Useful Life estimation
- Failure probability estimation
- Drift forecasting
- Maintenance scheduling support
- Online degradation monitoring
