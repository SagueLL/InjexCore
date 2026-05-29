---
name: rolling-window-analysis
description: Generate rolling-window statistical features (rolling means, std, min/max, trend, anomaly indicators) for time-series, telemetry, and industrial datasets — capturing local behavior and trend dynamics without redundancy or leakage. Use when the user asks for rolling-window features, moving averages, sliding-window statistics, or local trend indicators on sequential/sensor data.
---

# PURPOSE

Generate rolling-window statistical and analytical features
for time-series, telemetry, and industrial datasets.

The skill should capture local temporal behavior and trend dynamics.

---

# RESPONSIBILITIES

- Generate rolling means
- Generate rolling standard deviations
- Generate rolling min/max features
- Generate rolling trend indicators
- Generate rolling anomaly indicators
- Capture local signal behavior
- Improve temporal pattern representation

---

# NON-GOALS

- Do not create excessive feature redundancy
- Do not generate meaningless window sizes
- Do not introduce temporal leakage

---

# TOOLS

- Read
- Write

---

# INPUTS

- Dataset
- Target columns
- Window sizes
- Time structure

---

# WORKFLOW

1. Analyze temporal structure
2. Select meaningful rolling strategies
3. Generate rolling features
4. Validate consistency and usefulness
5. Detect redundancy risks
6. Produce rolling analysis summary

---

# OUTPUT FORMAT

# Rolling Features
# Window Configuration
# Statistical Logic
# Redundancy Risks
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Prioritize meaningful local behavior
- Avoid unnecessary feature explosion
- Preserve temporal integrity
- Focus on predictive usefulness

---

# FAILURE BEHAVIOR

If temporal consistency is unclear:
- explicitly state uncertainty
- avoid unsafe transformations
- limit feature generation to reliable structures

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Adaptive windows
- Dynamic trend analysis
- Multi-resolution rolling analysis
- Online feature generation
