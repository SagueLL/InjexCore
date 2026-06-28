---
name: select-dashboard-components
description: Select appropriate UI components for dashboard views, including cards, charts, tables, badges, filters, timelines, tabs, detail panels, alerts, empty states, loading states, and error states. Use when mapping dashboard requirements to reusable frontend components.
---

# PURPOSE

Select frontend components that best represent dashboard information clearly, consistently, and efficiently.

The skill should map dashboard needs to practical UI components without overcomplicating the interface.

---

# RESPONSIBILITIES

- Select dashboard UI components
- Select KPI cards
- Select chart components
- Select table components
- Select timeline components
- Select badges and severity indicators
- Select filters and controls
- Select empty states
- Select loading states
- Select error states
- Support component reuse
- Support UI consistency

---

# NON-GOALS

- Do not build backend logic
- Do not define data contracts
- Do not select components based only on aesthetics
- Do not add unnecessary components
- Do not invent unsupported interactions
- Do not create vendor lock-in without need

---

# TOOLS

- Read
- Write
- Glob
- Grep

---

# INPUTS

- Dashboard layout specification
- Dashboard data contracts
- Existing component library
- UI requirements
- User interaction requirements
- Visual design constraints

---

# WORKFLOW

1. Review dashboard layout and requirements
2. Identify required information types
3. Map information types to UI components
4. Select reusable component patterns
5. Define component purpose and data dependency
6. Identify interaction and state needs
7. Produce component selection specification

---

# OUTPUT FORMAT

# Component Selection Overview

# Target View

# Required Components

# KPI Components

# Chart Components

# Table Components

# Timeline Components

# Interaction Components

# State Components

# Component Rationale

# Implementation Notes

# Confidence Level

---

# QUALITY BAR

- Prioritize usability
- Prioritize component reuse
- Preserve UI consistency
- Avoid component overload
- Match components to information type
- Support fast implementation
- Support future design system evolution

---

# FAILURE BEHAVIOR

If component library visibility is incomplete:

- explicitly state limitations
- recommend generic component categories
- avoid library-specific assumptions

If dashboard data contracts are incomplete:

- select provisional components
- identify required data dependencies

---

# FUTURE EXTENSIONS

Possible future capabilities:

- shadcn/ui component registry integration
- design system component mapping
- component usage audits
- accessibility-aware component selection
- Storybook integration
