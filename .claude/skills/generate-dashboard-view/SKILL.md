---
name: generate-dashboard-view
description: Generate frontend-ready dashboard view structures, page specifications, component compositions, and implementation guidance for technical dashboards using approved layouts, component choices, and dashboard data contracts. Use when creating or scaffolding dashboard views from defined requirements.
---

# PURPOSE

Generate dashboard view specifications or frontend implementation structures from approved layouts, components, and data contracts.

The skill should help convert dashboard planning into buildable UI work.

---

# RESPONSIBILITIES

- Generate dashboard view specifications
- Generate page structure
- Generate component composition
- Generate frontend implementation guidance
- Connect UI components to dashboard data contracts
- Define loading, empty, and error states
- Define basic interaction behavior
- Support reusable dashboard view patterns
- Support frontend implementation readiness

---

# NON-GOALS

- Do not invent data contracts
- Do not modify backend pipelines
- Do not generate misleading UI narratives
- Do not hardcode unstable pipeline artifacts
- Do not over-engineer frontend architecture
- Do not ignore error or empty states

---

# TOOLS

- Read
- Write
- Glob
- Grep
- Bash

Use Bash only for safe static checks, project inspection, dependency inspection, linting, or non-destructive frontend validation.

Never run destructive commands.

---

# INPUTS

- Dashboard layout specification
- Selected UI components
- Dashboard data contracts
- Existing frontend structure
- Design constraints
- Implementation requirements

---

# WORKFLOW

1. Review dashboard layout specification
2. Review selected components
3. Review dashboard data contracts
4. Inspect existing frontend structure
5. Define view composition
6. Define component data dependencies
7. Define UI states
8. Produce frontend-ready implementation plan or scaffold

---

# OUTPUT FORMAT

# Dashboard View Overview

# Target Route or Page

# View Purpose

# Component Composition

# Data Dependencies

# Interaction Behavior

# Loading State

# Empty State

# Error State

# Implementation Plan

# Validation Notes

# Confidence Level

---

# QUALITY BAR

- Preserve contract alignment
- Prioritize buildability
- Include UI states
- Avoid unstable data coupling
- Keep v0 implementation simple
- Support future refactoring
- Maintain clear separation between data and presentation

---

# FAILURE BEHAVIOR

If frontend structure is unavailable:

- explicitly state limitations
- produce implementation-agnostic view specification
- identify missing project context

If data contracts are unavailable:

- do not generate final implementation
- produce provisional scaffold only
- identify required contracts

If component choices are unclear:

- recommend minimal component set
- avoid overbuilding

---

# FUTURE EXTENSIONS

Possible future capabilities:

- React component generation
- Next.js route scaffolding
- Storybook story generation
- UI snapshot testing integration
- Design-to-code integration
