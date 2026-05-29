---
name: detect-sampling-irregularities
description: Detect sampling irregularities, missing telemetry intervals, synchronization issues, inconsistent timestamps, and temporal discontinuities in time-series/telemetry data — surfacing temporal integrity risks for downstream ML, without blindly interpolating. Use when the user asks to check sampling rate, timestamp gaps, sensor synchronization, or temporal continuity in telemetry data.
---

# PURPOSE

Detect sampling inconsistencies, irregular telemetry frequencies,
and temporal synchronization issues within industrial datasets.

The skill should identify temporal integrity risks
that may impact downstream ML and monitoring workflows.

---

# RESPONSIBILITIES

- Detect irregular sampling frequencies
- Detect missing telemetry intervals
- Detect synchronization issues
- Detect inconsistent timestamp behavior
- Detect temporal discontinuities
- Evaluate temporal reliability
- Support time-series integrity workflows

---

# NON-GOALS

- Do not fabricate synchronization assumptions
- Do not blindly interpolate telemetry
- Do not ignore timestamp uncertainty
- Do not oversimplify temporal integrity analysis

---

# TOOLS

- Read
- Write

---

# INPUTS

- Telemetry dataset
- Timestamp column
- Expected sampling behavior (optional)

---

# WORKFLOW

1. Analyze temporal structure
2. Detect sampling irregularities
3. Detect synchronization inconsistencies
4. Evaluate temporal continuity
5. Identify high-risk temporal gaps
6. Produce structured temporal integrity report

---

# OUTPUT FORMAT

# Sampling Overview
# Irregular Frequencies
# Missing Intervals
# Synchronization Risks
# Temporal Integrity Findings
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve temporal rigor
- Prioritize telemetry integrity
- Avoid unsupported synchronization assumptions
- Focus on downstream ML reliability
- Preserve operational context

---

# FAILURE BEHAVIOR

If timestamp quality is incomplete:
- explicitly state limitations
- avoid unsupported temporal conclusions
- analyze only observable evidence

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Real-time synchronization monitoring
- Streaming telemetry validation
- Multi-sensor synchronization analysis
- Adaptive sampling analysis
