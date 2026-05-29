---
name: detect-organization-drift
description: Detect repository organization drift, misplaced files, duplicated structures, inconsistent naming conventions, orphan assets, and growing structural entropy. Use when validating repository consistency, reviewing project growth, or identifying organizational degradation.
---

# PURPOSE

Detect divergence between intended repository organization and actual repository state.

The skill should identify organizational entropy before it becomes technical debt.

---

# RESPONSIBILITIES

- Detect misplaced files
- Detect duplicated folders
- Detect inconsistent naming conventions
- Detect orphan files
- Detect orphan directories
- Detect repository sprawl
- Detect organizational inconsistencies
- Detect growing structural entropy

---

# NON-GOALS

- Do not restructure repositories automatically
- Do not fabricate inconsistencies
- Do not enforce arbitrary conventions
- Do not generate unsupported findings

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Repository structure
- Naming conventions
- Project organization
- Folder hierarchy

---

# WORKFLOW

1. Analyze repository organization
2. Identify organizational patterns
3. Detect inconsistencies and drift
4. Assess severity and impact
5. Identify root causes
6. Generate drift report

---

# OUTPUT FORMAT

# Organization Overview
# Detected Drift
# Naming Issues
# Structural Inconsistencies
# Orphan Assets
# Severity Assessment
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Prioritize meaningful findings
- Avoid false positives
- Preserve repository context
- Focus on maintainability
- Produce actionable recommendations

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
- Convention enforcement analysis
- Repository governance integration
- Organizational health scoring
