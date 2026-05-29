---
name: detect-sensor-drift
description: Detect gradual sensor drift, baseline shifts, evolving telemetry distributions, and long-term signal instability in industrial sensor data — flagging high-risk drift indicators without assuming sensor failure. Use when the user asks to find sensor drift, calibration drift, baseline shifts, or long-term instability in physical sensor/telemetry signals (sensor-specific; not general feature/data drift).
---

# PURPOSE

Detect sensor drift, evolving telemetry behavior,
and long-term signal instability within industrial datasets.

The skill should identify meaningful sensor deviations
while preserving contextual awareness.

---

# RESPONSIBILITIES

- Detect gradual sensor drift
- Detect changing signal distributions
- Detect long-term telemetry instability
- Detect evolving sensor behavior
- Detect suspicious baseline shifts
- Support predictive maintenance workflows
- Support telemetry reliability analysis

---

# NON-GOALS

- Do not assume drift implies sensor failure
- Do not fabricate root-cause explanations
- Do not oversimplify signal evolution
- Do not ignore operational context

---

# TOOLS

- Read
- Write

---

# INPUTS

- Sensor telemetry
- Time structure
- Target signals
- Optional operational context

---

# WORKFLOW

1. Analyze long-term signal behavior
2. Detect evolving distributions
3. Detect baseline shifts and instability
4. Evaluate operational relevance
5. Identify high-risk drift indicators
6. Produce structured drift analysis

---

# OUTPUT FORMAT

# Drift Overview
# Signal Evolution
# Baseline Shifts
# Instability Indicators
# Operational Risks
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve temporal integrity
- Preserve contextual awareness
- Prioritize meaningful drift detection
- Avoid simplistic assumptions
- Focus on telemetry reliability

---

# FAILURE BEHAVIOR

If telemetry consistency is incomplete:
- explicitly state limitations
- avoid unsupported drift conclusions
- analyze only observable evidence

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Online drift monitoring
- Sensor aging analysis
- Calibration monitoring
- Adaptive drift tracking
- Multi-sensor drift analysis
