---
name: generate-daily-summary
description: Generate a structured end-of-day summary of repository activity, engineering progress, architecture changes, documentation updates, and project evolution. Use when the user wants to review what was accomplished during a work session, create a daily report, prepare project updates, or preserve development continuity across sessions.
---

# PURPOSE

Generate a concise but complete summary of work completed during the current development session.

The skill should capture meaningful progress, preserve project continuity, and provide a clear picture of the project's current state.

---

# RESPONSIBILITIES

- Review completed work
- Identify meaningful progress
- Summarize important changes
- Highlight architecture updates
- Highlight documentation updates
- Highlight new agents, skills, or workflows
- Preserve project continuity
- Prepare next-session context

---

# NON-GOALS

- Do not invent completed work
- Do not exaggerate progress
- Do not omit significant changes
- Do not rewrite project history

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Repository changes
- Documentation updates
- Architecture changes
- Project artifacts
- Optional session scope

---

# WORKFLOW

1. Review repository activity
2. Identify significant changes
3. Group related work items
4. Summarize accomplishments
5. Identify unfinished work
6. Generate structured daily summary

---

# OUTPUT FORMAT

# Session Summary
# Completed Work
# Architecture Changes
# Documentation Changes
# New Components
# Open Topics
# Recommended Next Steps

---

# QUALITY BAR

- Prioritize clarity
- Preserve factual accuracy
- Focus on meaningful progress
- Avoid unnecessary detail
- Preserve project continuity

---

# FAILURE BEHAVIOR

If session visibility is incomplete:

- explicitly state limitations
- summarize only observable work
- identify missing context

---

# FUTURE EXTENSIONS

Possible future capabilities:

- Weekly summaries
- Sprint summaries
- Milestone summaries
- Automated changelog generation
