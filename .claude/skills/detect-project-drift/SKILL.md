---
name: detect-project-drift
description: Detect divergence between repository reality and project documentation, architecture definitions, memory files, workflows, and organizational structure. Use when validating project consistency, identifying outdated documentation, or reviewing long-term project alignment.
---

# PURPOSE

Detect divergence between the current repository state and project documentation.

The skill should identify areas where project reality and project documentation no longer match.

---

# RESPONSIBILITIES

- Detect documentation drift
- Detect architecture drift
- Detect memory drift
- Detect workflow drift
- Detect organizational drift
- Identify outdated references
- Recommend corrective actions

---

# NON-GOALS

- Do not modify project files automatically
- Do not invent inconsistencies
- Do not enforce architectural decisions
- Do not generate unsupported conclusions

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Repository structure
- Documentation
- Architecture files
- Memory files
- Workflow definitions

---

# WORKFLOW

1. Analyze repository structure
2. Review project documentation
3. Compare implementation against documentation
4. Detect divergence and inconsistencies
5. Assess severity and impact
6. Generate drift report

---

# OUTPUT FORMAT

# Drift Overview
# Documentation Drift
# Architecture Drift
# Memory Drift
# Workflow Drift
# Organizational Drift
# Recommended Actions

---

# QUALITY BAR

- Prioritize meaningful inconsistencies
- Avoid false positives
- Preserve contextual awareness
- Focus on maintainability

---

# FAILURE BEHAVIOR

If repository visibility is incomplete:

- explicitly state limitations
- detect only observable drift
- identify missing context

---

# FUTURE EXTENSIONS

Possible future capabilities:

- Continuous drift monitoring
- Architecture governance
- Repository compliance validation
- Project maturity scoring
