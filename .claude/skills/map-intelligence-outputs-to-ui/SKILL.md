---
name: map-intelligence-outputs-to-ui
description: Map technical Intelligence Layer outputs such as anomaly scores, drift events, sensor health summaries, incidents, baselines, and forensic findings into dashboard-ready UI sections, cards, charts, tables, and timelines. Use when translating backend analytics outputs into frontend dashboard views.
---

# PURPOSE

Translate technical intelligence outputs into clear dashboard-facing UI data mappings.

The skill should bridge the gap between machine learning artifacts and user-facing operational dashboard views.

---

# RESPONSIBILITIES

- Map technical outputs to dashboard views
- Map anomaly outputs to UI elements
- Map drift outputs to UI elements
- Map sensor health outputs to UI elements
- Map incident outputs to UI elements
- Map forensic findings to dashboard narratives
- Identify which metrics belong in cards, charts, tables, and timelines
- Preserve technical meaning while improving UI clarity
- Support operational interpretation

---

# NON-GOALS

- Do not build frontend components
- Do not redesign models
- Do not modify intelligence outputs
- Do not oversimplify critical technical meaning
- Do not invent operational conclusions
- Do not turn uncertainty into certainty

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Anomaly detection outputs
- Drift intelligence outputs
- Sensor health outputs
- Incident aggregation outputs
- Baseline outputs
- Forensic analysis outputs
- Dashboard view requirements
- Existing documentation

---

# WORKFLOW

1. Inspect available intelligence outputs
2. Identify operational meaning of each output
3. Determine the best dashboard representation
4. Map outputs to UI sections
5. Identify required transformations
6. Identify missing fields or ambiguity
7. Produce UI mapping specification

---

# OUTPUT FORMAT

# Intelligence-To-UI Mapping Overview

# Source Outputs

# Target Dashboard Views

# KPI Card Mappings

# Chart Mappings

# Table Mappings

# Timeline Mappings

# Detail View Mappings

# Required Transformations

# Missing Data

# Confidence Level

---

# QUALITY BAR

- Preserve operational meaning
- Avoid misleading simplification
- Prioritize dashboard clarity
- Keep mappings traceable to source outputs
- Distinguish raw values from derived presentation fields
- Support future UI evolution

---

# FAILURE BEHAVIOR

If source outputs are incomplete:

- explicitly state limitations
- map only observable outputs
- identify missing source fields

If operational meaning is uncertain:

- mark interpretation as provisional
- avoid definitive claims
- request domain validation when needed

---

# FUTURE EXTENSIONS

Possible future capabilities:

- Automated UI mapping generation
- Dashboard view model generation
- Operational narrative generation
- Human-readable explanation mapping
- Multi-dashboard role-based mappings
