---
name: validate-sensor-consistency
description: Validate consistency, stability, and structural integrity across industrial sensors and telemetry streams — detecting unstable signals, conflicting telemetry, and abnormal sensor relationships, without assuming inconsistency implies hardware failure. Use when the user asks to cross-check sensors, validate telemetry agreement, or audit consistency across multiple sensor signals.
---

# PURPOSE

Validate consistency, stability, and structural integrity
across industrial sensors and telemetry streams.

The skill should identify unreliable or inconsistent sensor behavior.

---

# RESPONSIBILITIES

- Validate sensor consistency
- Detect inconsistent telemetry patterns
- Detect unstable sensor behavior
- Detect conflicting signals
- Detect abnormal sensor relationships
- Evaluate telemetry reliability
- Support operational monitoring workflows

---

# NON-GOALS

- Do not assume inconsistency implies hardware failure
- Do not fabricate expected sensor behavior
- Do not oversimplify sensor relationships
- Do not remove telemetry automatically

---

# TOOLS

- Read
- Write

---

# INPUTS

- Sensor telemetry
- Sensor relationships (optional)
- Operational constraints (optional)

---

# WORKFLOW

1. Analyze telemetry structure
2. Compare sensor behavior consistency
3. Detect instability and conflicts
4. Evaluate telemetry reliability
5. Identify high-risk inconsistencies
6. Produce structured consistency analysis

---

# OUTPUT FORMAT

# Sensor Consistency Overview
# Unstable Signals
# Conflicting Telemetry
# Reliability Risks
# Operational Relevance
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve contextual awareness
- Prioritize telemetry reliability
- Avoid simplistic consistency assumptions
- Focus on operational usefulness
- Preserve interpretability

---

# FAILURE BEHAVIOR

If telemetry visibility is incomplete:
- explicitly state uncertainty
- avoid unsupported consistency conclusions
- analyze only observable evidence

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Sensor dependency analysis
- Cross-device validation
- Multi-machine consistency analysis
- Online telemetry validation
