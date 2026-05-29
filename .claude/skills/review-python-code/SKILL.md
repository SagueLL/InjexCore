---
name: review-python-code
description: Review Python code for quality, maintainability, readability, modularity, error handling, and engineering risks — producing a severity-ranked, evidence-based report with a PASS/FAIL verdict. Read-only (does not modify code). Use when the user asks to review, audit, critique, or evaluate the quality of Python files, modules, or a Python codebase.
---

# PURPOSE

Review Python code for quality, maintainability, readability,
engineering practices, and potential implementation risks.

The skill should provide structured, evidence-based review findings.

---

# RESPONSIBILITIES

- Detect code smells
- Detect maintainability issues
- Detect readability problems
- Detect unnecessary complexity
- Detect poor modularization
- Detect duplicated logic
- Detect bad naming practices
- Detect error-handling issues
- Detect testing gaps when visible
- Detect suspicious engineering practices

---

# NON-GOALS

- Do not modify code
- Do not refactor automatically
- Do not enforce purely subjective style preferences
- Do not invent issues unsupported by evidence

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Target files or repository
- Optional review scope
- Optional severity threshold

---

# WORKFLOW

1. Inspect code structure
2. Analyze readability and maintainability
3. Detect engineering risks and smells
4. Evaluate modularity and organization
5. Rank findings by severity
6. Produce structured review report

---

# OUTPUT FORMAT

# Review Summary
# Critical Issues
# High Severity Issues
# Medium Severity Issues
# Low Severity Issues
# Positive Observations
# Recommendations
# PASS/FAIL Verdict
# Confidence Level

---

# QUALITY BAR

- Be evidence-driven
- Prioritize maintainability and correctness
- Avoid subjective nitpicks
- Explain findings clearly
- Prioritize actionable feedback
- Keep findings technically rigorous

---

# FAILURE BEHAVIOR

If repository visibility is incomplete:
- explicitly state limitations
- avoid speculative findings
- review only observable code

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Automated fix suggestions
- Security-focused review
- Performance-focused review
- Test coverage analysis
- Static analysis integration
