---
name: analyze-temporal-patterns
description: Analyze sequential behavior, temporal dependencies, recurring structures, and signal dynamics in time-series, telemetry, and industrial datasets — identifying meaningful temporal patterns and irregular behavior while preserving temporal integrity. Use when the user asks to analyze, characterize, or explore temporal patterns, time-series dynamics, sequential dependencies, or signal evolution.
---

# PURPOSE

Analyze temporal and sequential behavior within time-series,
telemetry, and industrial datasets.

The skill should identify meaningful temporal structures,
dependencies, and behavioral dynamics.

---

# RESPONSIBILITIES

- Analyze sequential behavior
- Detect temporal dependencies
- Detect recurring temporal structures
- Analyze signal evolution
- Detect irregular temporal behavior
- Analyze local and long-term dynamics
- Support predictive maintenance workflows

---

# NON-GOALS

- Do not fabricate temporal meaning
- Do not assume stationarity automatically
- Do not oversimplify sequential behavior
- Do not ignore temporal uncertainty

---

# TOOLS

- Read
- Write

---

# INPUTS

- Time-series dataset
- Time column
- Target features/signals
- Optional operational context

---

# WORKFLOW

1. Analyze temporal structure
2. Detect sequential dependencies
3. Analyze signal evolution
4. Detect irregular temporal behavior
5. Evaluate temporal consistency
6. Produce structured temporal analysis

---

# OUTPUT FORMAT

# Temporal Overview
# Sequential Patterns
# Signal Dynamics
# Irregular Temporal Behavior
# Temporal Risks
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve temporal integrity
- Prioritize meaningful temporal analysis
- Avoid simplistic sequence assumptions
- Focus on operational and predictive relevance
- Preserve interpretability

---

# FAILURE BEHAVIOR

If temporal structure is incomplete:
- explicitly state limitations
- avoid unsupported conclusions
- analyze only observable behavior

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Sequence embeddings
- Temporal clustering
- Temporal attention analysis
- Multi-scale temporal analysis
- Streaming telemetry analysis
