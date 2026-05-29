---
name: validate-pipeline-structure
description: Validate ML/data pipeline structure, dependency consistency, and operational maintainability — flagging tight coupling, dependency problems, execution bottlenecks, and scalability risks, producing a PASS/FAIL report. Use when the user asks to audit, review, or validate the structure or design of an ML pipeline, preprocessing pipeline, or feature pipeline (architectural review of the pipeline itself, not the data it produces).
---

# PURPOSE

Validate ML and data pipeline structure,
dependency consistency, and operational maintainability.

The skill should identify architectural weaknesses
and workflow reliability risks.

---

# RESPONSIBILITIES

- Validate pipeline consistency
- Detect dependency problems
- Detect tightly coupled stages
- Detect maintainability risks
- Detect execution bottlenecks
- Detect scalability risks
- Improve pipeline reliability

---

# NON-GOALS

- Do not fabricate pipeline requirements
- Do not oversimplify workflow dependencies
- Do not ignore operational constraints
- Do not redesign pipelines blindly

---

# TOOLS

- Read
- Write

---

# INPUTS

- Pipeline definition
- Workflow dependencies
- Execution constraints (optional)

---

# WORKFLOW

1. Analyze pipeline structure
2. Detect dependency relationships
3. Identify architectural weaknesses
4. Detect scalability and maintainability risks
5. Evaluate execution reliability
6. Produce structured pipeline validation report

---

# OUTPUT FORMAT

# Pipeline Validation Overview
# Dependency Findings
# Maintainability Risks
# Scalability Risks
# Execution Bottlenecks
# Recommendations
# PASS/FAIL Verdict
# Confidence Level

---

# QUALITY BAR

- Prioritize maintainability
- Preserve workflow consistency
- Avoid unsupported architectural conclusions
- Focus on operational reliability
- Preserve scalability awareness

---

# FAILURE BEHAVIOR

If pipeline visibility is incomplete:
- explicitly state limitations
- avoid unsupported conclusions
- validate only observable structure

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Distributed pipeline validation
- DAG analysis
- Pipeline observability analysis
- Runtime execution validation
