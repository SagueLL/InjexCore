---
name: analyze-machine-cycles
description: Analyze operational machine cycles and repetitive industrial process behavior — detecting cycle boundaries, cycle duration consistency, cycle-to-cycle variability, and abnormal transitions in telemetry data, without assuming abnormal cycles imply failure. Use when the user asks to segment, characterize, or audit production cycles, machine cycles, or repetitive operational behavior.
---

# PURPOSE

Analyze operational machine cycles and repetitive industrial process behavior
within telemetry and sensor datasets.

The skill should identify meaningful operational structures,
cycle consistency, and behavioral patterns.

---

# RESPONSIBILITIES

- Detect machine operational cycles
- Analyze cycle duration and consistency
- Detect repetitive operational structures
- Analyze cycle-to-cycle behavior
- Detect abnormal cycle transitions
- Support predictive maintenance workflows
- Support industrial process understanding

---

# NON-GOALS

- Do not fabricate process semantics
- Do not assume abnormal cycles imply failure
- Do not oversimplify operational behavior
- Do not ignore process variability

---

# TOOLS

- Read
- Write

---

# INPUTS

- Telemetry dataset
- Time-series structure
- Target operational signals
- Optional process context

---

# WORKFLOW

1. Analyze telemetry and temporal structure
2. Detect operational cycle boundaries
3. Analyze cycle consistency and variability
4. Detect abnormal operational behavior
5. Evaluate operational relevance
6. Produce structured cycle analysis

---

# OUTPUT FORMAT

# Cycle Overview
# Cycle Structure Analysis
# Cycle Consistency
# Behavioral Variability
# Operational Deviations
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve temporal integrity
- Preserve operational context
- Prioritize meaningful cycle analysis
- Avoid simplistic operational assumptions
- Focus on operational usefulness

---

# FAILURE BEHAVIOR

If cycle structure is unclear:
- explicitly state uncertainty
- avoid unsupported cycle conclusions
- analyze only observable behavior

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Real-time cycle monitoring
- Cycle clustering
- Process-state segmentation
- Cycle forecasting
- Online operational analysis
