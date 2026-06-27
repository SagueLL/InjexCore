---
name: validate-dashboard-payloads
description: Validate dashboard JSON payloads, fixtures, schemas, and frontend-facing data contracts for completeness, consistency, type correctness, semantic clarity, version compatibility, and UI readiness. Use when checking whether dashboard data is safe and reliable for frontend consumption.
---

# PURPOSE

Validate dashboard data payloads before they are consumed by frontend views.

The skill should detect incomplete, inconsistent, unstable, or misleading dashboard data structures.

---

# RESPONSIBILITIES

- Validate dashboard payload completeness
- Validate required fields
- Validate optional fields
- Validate data types
- Validate field semantics
- Validate schema consistency
- Validate version metadata
- Validate UI readiness
- Detect missing values
- Detect inconsistent identifiers
- Detect invalid severity labels
- Detect timestamp issues
- Detect frontend-breaking payload shapes

---

# NON-GOALS

- Do not modify source data automatically
- Do not fabricate missing values
- Do not suppress validation failures
- Do not validate model correctness beyond payload structure
- Do not make unsupported operational conclusions

---

# TOOLS

- Read
- Glob
- Grep
- Bash

Use Bash only for safe validation commands, schema checks, test commands, or static inspection.

Do not run destructive commands.

---

# INPUTS

- Dashboard JSON payloads
- Dashboard fixtures
- JSON schemas
- TypeScript interfaces
- Contract definitions
- Frontend data requirements

---

# WORKFLOW

1. Inspect dashboard contract definition
2. Inspect dashboard payload or fixture
3. Validate required fields
4. Validate data types and formats
5. Validate identifiers and timestamps
6. Validate severity/status conventions
7. Validate frontend readiness
8. Produce validation report

---

# OUTPUT FORMAT

# Payload Validation Overview

# Contract Version

# Validation Result

# Missing Fields

# Type Issues

# Semantic Issues

# Identifier Issues

# Timestamp Issues

# UI Readiness

# Recommendations

# Confidence Level

# VERDICT

PASS
or
FAIL

---

# QUALITY BAR

- Prioritize frontend safety
- Prioritize contract consistency
- Avoid silent failures
- Distinguish blocking issues from warnings
- Preserve traceability
- Report only evidence-supported issues

---

# FAILURE BEHAVIOR

If contracts are unavailable:

- explicitly state limitations
- perform structural validation only
- recommend contract definition

If payload visibility is incomplete:

- validate only observable data
- identify missing files or fields

If validation cannot be executed:

- provide static review
- clearly state that runtime validation was not performed

---

# FUTURE EXTENSIONS

Possible future capabilities:

- Automated JSON Schema validation
- TypeScript type checking
- Contract regression tests
- API response validation
- Frontend fixture validation suite
