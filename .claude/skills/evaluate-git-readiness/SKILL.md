---
name: evaluate-git-readiness
description: Evaluate repository state and determine whether current changes justify a Git commit and/or push. Analyze modified files, logical change boundaries, unfinished work, and repository consistency. Use when deciding whether work is ready to be committed, pushed, or deferred.
---

# PURPOSE

Evaluate whether repository changes justify a commit and/or push.

The skill should help maintain clean repository history and avoid premature commits.

---

# RESPONSIBILITIES

- Analyze repository modifications
- Evaluate significance of changes
- Detect incomplete work
- Detect logical commit boundaries
- Recommend commit readiness
- Recommend push readiness
- Identify repository risks

---

# NON-GOALS

- Do not perform commits
- Do not perform pushes
- Do not modify repository state
- Do not force commit recommendations

---

# TOOLS

- Read
- Glob
- Grep
- Bash

---

# INPUTS

- Git status
- Git diff
- Modified files
- Repository structure

---

# WORKFLOW

1. Review repository status
2. Analyze modified files
3. Evaluate completeness of changes
4. Detect logical commit grouping
5. Assess push readiness
6. Produce repository recommendation

---

# OUTPUT FORMAT

# Repository Status
# Significant Changes
# Commit Readiness
# Push Readiness
# Risks
# Recommendations

# VERDICT

READY
or
NOT READY

---

# QUALITY BAR

- Prioritize repository hygiene
- Preserve logical commit boundaries
- Avoid premature recommendations
- Focus on maintainability

---

# FAILURE BEHAVIOR

If repository visibility is incomplete:

- explicitly state limitations
- avoid unsupported recommendations
- analyze only observable changes

---

# FUTURE EXTENSIONS

Possible future capabilities:

- Commit message generation
- Conventional commits
- Release readiness analysis
- Branch strategy validation
