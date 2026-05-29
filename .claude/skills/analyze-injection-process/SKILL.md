---
name: analyze-injection-process
description: Analyze injection molding and plastics manufacturing processes from telemetry — process behavior, operational consistency, manufacturing variability, abnormal patterns, and timing/sequencing — without fabricating manufacturing semantics or guaranteeing production outcomes. Use when the user asks to analyze injection-moulding behavior, plastics manufacturing processes, or domain-specific operational patterns of injection machines.
---

# PURPOSE

Analyze injection molding and plastics manufacturing processes
using telemetry, operational signals, and industrial process data.

The skill should identify meaningful operational behavior,
process consistency, and manufacturing-relevant patterns.

---

# RESPONSIBILITIES

- Analyze injection process behavior
- Analyze operational process consistency
- Detect abnormal manufacturing patterns
- Detect operational variability
- Analyze process timing and sequencing
- Support predictive maintenance workflows
- Support industrial process understanding

---

# NON-GOALS

- Do not fabricate manufacturing semantics
- Do not guarantee production outcomes
- Do not oversimplify plastics manufacturing behavior
- Do not ignore operational variability

---

# TOOLS

- Read
- Write

---

# INPUTS

- Industrial telemetry
- Process signals
- Operational cycles
- Optional manufacturing context

---

# WORKFLOW

1. Analyze operational telemetry
2. Detect manufacturing process structures
3. Analyze operational consistency
4. Detect abnormal manufacturing behavior
5. Evaluate operational relevance
6. Produce structured process analysis

---

# OUTPUT FORMAT

# Process Overview
# Operational Analysis
# Process Consistency
# Manufacturing Variability
# Operational Risks
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve operational context
- Preserve temporal integrity
- Prioritize meaningful manufacturing analysis
- Avoid simplistic process assumptions
- Focus on operational usefulness

---

# FAILURE BEHAVIOR

If manufacturing context is incomplete:
- explicitly state uncertainty
- avoid unsupported process conclusions
- analyze only observable evidence

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Defect correlation analysis
- Process optimization support
- Quality prediction workflows
- Multi-machine manufacturing analysis
- Real-time manufacturing monitoring
