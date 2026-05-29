---
name: generate-time-features
description: Generate meaningful time-series and temporal features (lags, deltas, rates of change, cumulative sums, rolling aggregations) from sequential, sensor, telemetry, or industrial datasets — while preserving temporal consistency and avoiding leakage. Use when the user asks to engineer, create, or add time-series, temporal, lag, rolling, or sensor-based features.
---

# PURPOSE

Generate meaningful time-series and temporal features
from sequential, sensor, telemetry, or industrial datasets.

The skill should improve signal representation and predictive usefulness.

---

# RESPONSIBILITIES

- Generate lag features
- Generate delta/change features
- Generate rate-of-change features
- Generate cumulative features
- Generate temporal aggregation features
- Detect temporal patterns
- Preserve temporal consistency
- Improve predictive signal quality

---

# NON-GOALS

- Do not introduce temporal leakage
- Do not fabricate domain meaning
- Do not apply transformations blindly
- Do not generate redundant features unnecessarily

---

# TOOLS

- Read
- Write

---

# INPUTS

- Dataset or feature set
- Time column
- Target variable (optional)
- Window parameters (optional)

---

# WORKFLOW

1. Inspect temporal structure
2. Detect time-series characteristics
3. Generate meaningful temporal features
4. Validate temporal consistency
5. Detect potential leakage risks
6. Produce feature summary

---

# OUTPUT FORMAT

# Generated Features
# Temporal Logic
# Leakage Risks
# Feature Rationale
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Prioritize meaningful signal extraction
- Avoid feature explosion
- Preserve temporal integrity
- Prioritize model usefulness
- Keep transformations explainable

---

# FAILURE BEHAVIOR

If temporal structure is unclear:
- explicitly state limitations
- avoid speculative transformations
- generate only evidence-supported features

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Frequency-domain features
- Fourier transforms
- Wavelet features
- Event-sequence analysis
- Multi-scale temporal analysis
