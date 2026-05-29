---
name: detect-trend-and-seasonality
description: Detect long-term trends, seasonal patterns, cyclic behavior, and recurring operational structures in time-series data — analyzing stability and periodic consistency without assuming seasonality exists. Use when the user asks to find trends, seasonality, cycles, periodic patterns, or decompose a time series.
---

# PURPOSE

Detect trends, seasonality, cyclic behavior,
and recurring temporal structures within time-series data.

The skill should identify meaningful long-term and periodic behavior.

---

# RESPONSIBILITIES

- Detect long-term trends
- Detect seasonal patterns
- Detect cyclic behavior
- Detect recurring operational patterns
- Analyze trend stability
- Analyze periodic consistency
- Support forecasting and predictive workflows

---

# NON-GOALS

- Do not assume seasonality exists automatically
- Do not oversimplify periodic behavior
- Do not fabricate recurring patterns
- Do not ignore operational context

---

# TOOLS

- Read
- Write

---

# INPUTS

- Time-series dataset
- Time column
- Target signals/features
- Optional periodicity assumptions

---

# WORKFLOW

1. Analyze temporal structure
2. Detect long-term trends
3. Detect periodic and seasonal behavior
4. Evaluate consistency and stability
5. Identify operationally relevant cycles
6. Produce structured trend analysis

---

# OUTPUT FORMAT

# Trend Overview
# Seasonal Patterns
# Cyclic Behavior
# Stability Analysis
# Operational Relevance
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve temporal rigor
- Prioritize meaningful temporal behavior
- Avoid unsupported periodic assumptions
- Preserve contextual awareness
- Focus on predictive usefulness

---

# FAILURE BEHAVIOR

If temporal periodicity is unclear:
- explicitly state uncertainty
- avoid unsupported seasonality claims
- analyze only observable behavior

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Spectral analysis
- Fourier decomposition
- Frequency-domain analysis
- Forecast-oriented decomposition
- Online seasonality tracking
