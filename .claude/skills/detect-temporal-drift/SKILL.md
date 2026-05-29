---
name: detect-temporal-drift
description: Detect temporal drift, behavioral instability, and distribution evolution in time-series and telemetry signals — surfacing operational behavior shifts and high-risk deviations while preserving uncertainty (does not assume drift implies degradation). Use when the user asks to find drift, distribution shift, signal evolution, or behavioral changes over time in sensor/telemetry data.
---

# PURPOSE

Detect temporal drift, behavioral instability,
and evolving signal characteristics within time-series data.

The skill should identify meaningful distributional and operational changes over time.

---

# RESPONSIBILITIES

- Detect signal drift
- Detect distribution evolution
- Detect temporal instability
- Detect operational behavior shifts
- Detect changing feature characteristics
- Detect long-term signal deviations
- Support predictive maintenance monitoring

---

# NON-GOALS

- Do not assume drift implies degradation
- Do not fabricate root-cause explanations
- Do not oversimplify temporal evolution
- Do not ignore contextual uncertainty

---

# TOOLS

- Read
- Write

---

# INPUTS

- Time-series dataset
- Target features/signals
- Temporal segmentation configuration (optional)

---

# WORKFLOW

1. Analyze temporal distributions
2. Detect behavioral changes over time
3. Detect instability and signal evolution
4. Evaluate operational relevance
5. Identify high-risk temporal deviations
6. Produce structured drift analysis

---

# OUTPUT FORMAT

# Drift Overview
# Behavioral Changes
# Distribution Evolution
# Operational Instability
# High-Risk Signals
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve temporal integrity
- Prioritize meaningful drift detection
- Avoid simplistic drift interpretation
- Preserve contextual awareness
- Focus on operational relevance

---

# FAILURE BEHAVIOR

If temporal consistency is incomplete:
- explicitly state uncertainty
- avoid unsupported drift conclusions
- analyze only observable evidence

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Online drift monitoring
- Streaming drift analysis
- Adaptive drift detection
- Drift forecasting
- Sensor aging analysis
