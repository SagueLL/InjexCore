---
name: validate-dataset
description: Validate dataset structure, schema consistency, and integrity before ML or analytical workflows — detecting corrupted records, invalid formats, inconsistent columns, and structural anomalies — producing a PASS/FAIL report. Does not modify or clean the data. Use when the user asks to validate, sanity-check, audit, or QA a dataset, CSV, parquet, or feature matrix.
---

# PURPOSE

Validate dataset structure, integrity, consistency,
and general data quality before ML or analytical workflows.

The skill should identify structural and quality risks
that may impact downstream processing and modeling.

---

# RESPONSIBILITIES

- Validate dataset structure
- Validate schema consistency
- Detect corrupted records
- Detect invalid formats
- Detect inconsistent column behavior
- Validate feature integrity
- Detect suspicious dataset patterns
- Detect structural anomalies

---

# NON-GOALS

- Do not modify datasets automatically
- Do not fabricate schema assumptions
- Do not remove records automatically
- Do not perform model training

---

# TOOLS

- Read
- Write

---

# INPUTS

- Dataset
- Expected schema (optional)
- Validation rules (optional)

---

# WORKFLOW

1. Inspect dataset structure
2. Validate schema consistency
3. Detect structural anomalies
4. Detect invalid or suspicious records
5. Evaluate overall dataset integrity
6. Produce structured validation report

---

# OUTPUT FORMAT

# Dataset Overview
# Schema Validation
# Structural Issues
# Invalid Records
# Integrity Risks
# Recommendations
# PASS/FAIL Verdict
# Confidence Level

---

# QUALITY BAR

- Be evidence-driven
- Preserve dataset integrity
- Avoid speculative assumptions
- Prioritize actionable findings
- Focus on downstream ML reliability

---

# FAILURE BEHAVIOR

If dataset visibility is incomplete:
- explicitly state limitations
- validate only observable structures
- avoid unsupported conclusions

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Schema version tracking
- Automated validation pipelines
- Data contract validation
- Cross-dataset consistency analysis
