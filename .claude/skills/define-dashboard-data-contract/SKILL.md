---
name: define-dashboard-data-contract
description: Define stable, versioned dashboard data contracts that transform technical intelligence outputs into frontend-ready JSON payloads, schemas, and interface boundaries. Use when designing dashboard payloads, UI data schemas, API contracts, or presentation-layer data structures for technical dashboards.
---

# PURPOSE

Define stable dashboard data contracts between backend intelligence systems and frontend dashboard views.

The skill should prevent the dashboard from depending directly on internal pipeline artifacts, unstable filenames, or implementation-specific data structures.

---

# RESPONSIBILITIES

- Define dashboard-ready data contracts
- Define stable JSON payload structures
- Define versioned schema boundaries
- Define required and optional fields
- Define semantic field meanings
- Define frontend-facing data shapes
- Separate internal pipeline outputs from UI contracts
- Support dashboard maintainability
- Support future API integration

---

# NON-GOALS

- Do not build frontend components
- Do not implement backend pipelines
- Do not invent unavailable data fields
- Do not expose unstable internal artifacts directly to the UI
- Do not create overly complex schemas without need
- Do not make product decisions autonomously

---

# TOOLS

- Read
- Write
- Glob
- Grep

---

# INPUTS

- Intelligence Layer outputs
- Pipeline artifacts
- Dashboard requirements
- View definitions
- Existing data schemas
- Repository documentation
- Example payloads

---

# WORKFLOW

1. Identify the target dashboard view
2. Identify required frontend information
3. Inspect available backend or intelligence outputs
4. Define a stable dashboard-facing payload
5. Separate required fields from optional fields
6. Add semantic field descriptions
7. Add versioning metadata
8. Produce a dashboard data contract

---

# OUTPUT FORMAT

# Dashboard Contract Overview
# Target View
# Data Contract Name
# Contract Version
# Required Fields
# Optional Fields
# Field Semantics
# Example Payload
# Validation Notes
# Integration Notes
# Confidence Level

---

# QUALITY BAR

- Prioritize contract stability
- Preserve semantic clarity
- Avoid leaking internal pipeline complexity
- Keep payloads frontend-friendly
- Keep schemas versionable
- Avoid unnecessary abstraction
- Support future API evolution

---

# FAILURE BEHAVIOR

If source data visibility is incomplete:

- explicitly state limitations
- define only evidence-supported fields
- mark uncertain fields as provisional
- identify missing source artifacts

If dashboard requirements are unclear:

- propose a minimal contract
- state assumptions clearly
- avoid over-designing

---

# FUTURE EXTENSIONS

Possible future capabilities:

- JSON Schema generation
- OpenAPI contract generation
- TypeScript interface generation
- Contract version migration
- Backend API specification
