---
name: analyze-repository-structure
description: Analyze repository organization, folder hierarchy, module boundaries, documentation placement, data organization, and project structure scalability. Use when reviewing repository architecture, evaluating project organization quality, assessing maintainability, or planning future repository growth.
---

# PURPOSE

Analyze repository structure and organizational architecture.

The skill should identify strengths, weaknesses, scalability concerns, and maintainability risks within the repository layout.

---

# RESPONSIBILITIES

- Analyze repository hierarchy
- Evaluate folder organization
- Evaluate module boundaries
- Evaluate documentation placement
- Evaluate data organization
- Evaluate configuration organization
- Assess repository scalability
- Assess maintainability
- Assess discoverability

---

# NON-GOALS

- Do not move files automatically
- Do not enforce architectural decisions
- Do not optimize for aesthetics alone
- Do not invent structural issues

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Repository structure
- Folder hierarchy
- Module organization
- Documentation layout
- Configuration files

---

# WORKFLOW

1. Analyze repository hierarchy
2. Identify major repository domains
3. Evaluate organizational consistency
4. Evaluate scalability and maintainability
5. Identify structural strengths and weaknesses
6. Produce repository architecture assessment

---

# OUTPUT FORMAT

# Repository Overview
# Organizational Assessment
# Structural Strengths
# Structural Weaknesses
# Scalability Considerations
# Maintainability Considerations
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Prioritize maintainability
- Preserve architectural context
- Focus on scalability
- Avoid subjective judgments
- Produce actionable recommendations

---

# FAILURE BEHAVIOR

If repository visibility is incomplete:

- explicitly state limitations
- assess only observable structure
- identify missing context

---

# FUTURE EXTENSIONS

Possible future capabilities:

- Monorepo analysis
- Multi-package analysis
- Repository governance scoring
- Architecture maturity assessment
