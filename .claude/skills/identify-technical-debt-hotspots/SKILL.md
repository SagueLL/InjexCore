---
name: identify-technical-debt-hotspots
description: Identify repository areas accumulating structural debt, overloaded directories, mixed responsibilities, fragmented documentation, scaling bottlenecks, and maintainability risks. Use when evaluating repository health, planning refactors, or assessing long-term project sustainability.
---

# PURPOSE

Identify structural technical debt and repository areas that may become maintenance bottlenecks.

The skill should highlight emerging risks before they significantly impact development velocity.

---

# RESPONSIBILITIES

- Identify overloaded directories
- Identify mixed concerns
- Identify fragmented documentation
- Identify scaling bottlenecks
- Identify maintainability risks
- Identify organizational debt
- Assess repository health
- Recommend mitigation actions

---

# NON-GOALS

- Do not perform refactors
- Do not enforce architectural changes
- Do not fabricate technical debt
- Do not overstate risk severity

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Repository structure
- Documentation structure
- Module organization
- Folder hierarchy
- Repository history (optional)

---

# WORKFLOW

1. Analyze repository structure
2. Identify high-growth areas
3. Detect maintainability risks
4. Detect structural bottlenecks
5. Assess debt severity
6. Generate technical debt report

---

# OUTPUT FORMAT

# Repository Health Overview
# Technical Debt Hotspots
# Maintainability Risks
# Scalability Risks
# Organizational Bottlenecks
# Recommended Actions
# Severity Assessment
# Confidence Level

---

# QUALITY BAR

- Prioritize meaningful risks
- Avoid speculative conclusions
- Focus on maintainability
- Preserve repository context
- Produce actionable recommendations

---

# FAILURE BEHAVIOR

If repository visibility is incomplete:

- explicitly state limitations
- assess only observable risks
- identify missing context

---

# FUTURE EXTENSIONS

Possible future capabilities:

- Technical debt trend analysis
- Repository health scoring
- Architecture sustainability analysis
- Automated debt tracking
