---
name: analyze-cycle-phases
description: Analyze operational phases and stage transitions within industrial machine cycles — detecting phase boundaries, transition behavior, phase-specific dynamics, and timing consistency, without fabricating process semantics. Use when the user asks to segment a cycle into phases/stages, analyze phase transitions, or examine phase-specific behavior (e.g. injection, holding, cooling phases on a moulding cycle).
---

# PURPOSE

Analyze operational phases and stage transitions
within industrial machine cycles.

The skill should identify meaningful process segmentation
and phase-specific behavior.

---

# RESPONSIBILITIES

- Detect operational phases
- Analyze phase transitions
- Detect abnormal phase behavior
- Analyze phase timing consistency
- Detect phase-specific anomalies
- Support industrial process understanding
- Support predictive maintenance workflows

---

# NON-GOALS

- Do not fabricate process-state semantics
- Do not assume all phases are observable
- Do not oversimplify operational segmentation
- Do not ignore uncertainty in phase boundaries

---

# TOOLS

- Read
- Write

---

# INPUTS

- Machine telemetry
- Time-series structure
- Operational signals
- Optional process hints

---

# WORKFLOW

1. Analyze operational telemetry
2. Detect phase boundaries and transitions
3. Analyze phase-specific behavior
4. Detect abnormal phase dynamics
5. Evaluate operational relevance
6. Produce structured phase analysis

---

# OUTPUT FORMAT

# Phase Overview
# Operational Segmentation
# Phase Timing Analysis
# Transition Behavior
# Phase-Specific Risks
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve temporal integrity
- Preserve operational context
- Prioritize meaningful segmentation
- Avoid unsupported process assumptions
- Focus on operational usefulness

---

# FAILURE BEHAVIOR

If operational phases are unclear:
- explicitly state uncertainty
- avoid unsupported segmentation conclusions
- analyze only observable behavior

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Real-time phase detection
- Process-state classification
- Transition anomaly detection
- Multi-cycle phase comparison
