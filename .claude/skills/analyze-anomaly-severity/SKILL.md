---
name: analyze-anomaly-severity
description: Rank and analyze the severity, persistence, and operational impact of detected anomalies — identifying critical patterns and predictive-maintenance relevance, while preserving uncertainty (does not guarantee failure prediction). Use when the user asks to prioritize, score, rank, or evaluate the severity, impact, or maintenance relevance of already-detected anomalies.
---

# PURPOSE

Analyze anomaly severity, operational impact,
and potential predictive maintenance relevance.

The skill should prioritize contextual and operational significance.

---

# RESPONSIBILITIES

- Rank anomaly severity
- Evaluate operational impact
- Detect critical anomaly patterns
- Analyze anomaly persistence
- Evaluate predictive maintenance relevance
- Identify high-risk anomaly clusters
- Support prioritization workflows

---

# NON-GOALS

- Do not guarantee failure prediction
- Do not fabricate operational impact
- Do not oversimplify anomaly severity
- Do not assume all anomalies are actionable

---

# TOOLS

- Read
- Write

---

# INPUTS

- Detected anomalies
- Telemetry context
- Operational constraints
- Severity criteria (optional)

---

# WORKFLOW

1. Analyze anomaly characteristics
2. Evaluate contextual abnormality
3. Assess operational impact
4. Rank severity and persistence
5. Identify high-risk patterns
6. Produce structured severity assessment

---

# OUTPUT FORMAT

# Severity Summary
# Critical Anomalies
# High-Risk Patterns
# Operational Impact
# Predictive Maintenance Relevance
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve contextual awareness
- Prioritize operational relevance
- Avoid simplistic severity scoring
- Focus on actionable prioritization
- Preserve uncertainty indicators

---

# FAILURE BEHAVIOR

If anomaly context is incomplete:
- explicitly state uncertainty
- avoid unsupported severity conclusions
- rank only evidence-supported findings

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Failure probability estimation
- Real-time severity scoring
- Alert prioritization
- Maintenance scheduling integration
