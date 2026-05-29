---
name: build-preprocessing-pipeline
description: Build structured, modular, maintainable preprocessing pipelines for ML, telemetry, industrial, and time-series datasets — cleaning, missing-value handling, normalization/scaling — while preserving temporal integrity and avoiding leakage. Use when the user asks to build, scaffold, or structure a preprocessing pipeline, ETL flow, or sklearn-style transformer chain for an ML dataset.
---

# PURPOSE

Build structured and maintainable preprocessing pipelines
for ML, telemetry, industrial, and time-series datasets.

The skill should improve data reliability,
reusability, and downstream ML quality.

---

# RESPONSIBILITIES

- Build preprocessing workflows
- Structure data-cleaning pipelines
- Handle missing-value workflows
- Handle normalization and scaling workflows
- Coordinate preprocessing dependencies
- Improve pipeline modularity
- Support ML-ready dataset generation

---

# NON-GOALS

- Do not blindly transform datasets
- Do not fabricate preprocessing requirements
- Do not ignore temporal integrity
- Do not tightly couple preprocessing stages

---

# TOOLS

- Read
- Write

---

# INPUTS

- Dataset structure
- Processing requirements
- ML objectives
- Optional operational constraints

---

# WORKFLOW

1. Analyze dataset structure
2. Identify preprocessing requirements
3. Build modular preprocessing stages
4. Validate temporal and operational integrity
5. Optimize maintainability and reusability
6. Produce structured preprocessing pipeline

---

# OUTPUT FORMAT

# Pipeline Overview
# Preprocessing Stages
# Dependency Structure
# Temporal Integrity Risks
# Maintainability Considerations
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Prioritize modularity
- Preserve temporal integrity
- Avoid unnecessary complexity
- Focus on maintainability
- Preserve downstream ML quality

---

# FAILURE BEHAVIOR

If dataset structure is incomplete:
- explicitly state uncertainty
- avoid unsupported preprocessing assumptions
- build only evidence-supported workflows

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Streaming preprocessing pipelines
- Real-time telemetry preprocessing
- Distributed preprocessing workflows
- Adaptive preprocessing
