---
name: generate-project-state-report
description: Generate a comprehensive project state report summarizing the current status of architecture, roadmap progress, active systems, agents, skills, documentation, technical decisions, risks, and priorities. Use when creating executive project overviews, milestone reports, project snapshots, or consolidated project-state documents.
---

# PURPOSE

Generate a structured and comprehensive overview of the current state of the project.

The skill should provide an accurate snapshot of project maturity, progress, architecture, active systems, risks, and priorities.

---

# RESPONSIBILITIES

- Summarize current project state
- Summarize architecture status
- Summarize roadmap progress
- Summarize active systems
- Summarize agent ecosystem
- Summarize skills ecosystem
- Summarize documentation maturity
- Identify current priorities
- Identify risks and blockers
- Preserve project continuity

---

# NON-GOALS

- Do not invent project progress
- Do not rewrite project history
- Do not make strategic decisions
- Do not replace detailed documentation

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Project documentation
- Roadmaps
- Architecture documents
- Agent definitions
- Skills definitions
- Memory files
- Repository structure

---

# WORKFLOW

1. Analyze project artifacts
2. Consolidate current project state
3. Identify active systems and components
4. Assess progress and maturity
5. Identify risks and priorities
6. Generate structured project-state report

---

# OUTPUT FORMAT

# Project Overview

# Current Status

# Architecture Status

# Roadmap Progress

# Active Systems

# Agent Ecosystem

# Skill Ecosystem

# Current Risks

# Current Priorities

# Recommended Focus Areas

# Confidence Level

---

# QUALITY BAR

- Prioritize accuracy
- Preserve project context
- Focus on meaningful information
- Avoid unnecessary verbosity
- Produce executive-friendly summaries

---

# FAILURE BEHAVIOR

If project visibility is incomplete:

- explicitly state limitations
- summarize only observable information
- identify missing context

---

# FUTURE EXTENSIONS

Possible future capabilities:

- Project maturity scoring
- Executive dashboards
- Stakeholder reporting
- Automated project snapshots
