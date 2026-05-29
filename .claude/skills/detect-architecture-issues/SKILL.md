---
name: detect-architecture-issues
description: Detect architectural weaknesses, structural problems, and scalability risks in a software system — tight coupling, layering violations, unclear module boundaries, dependency issues, monolithic bottlenecks — producing an evidence-based, actionable report with a PASS/FAIL verdict. Read-only. Use when the user asks to audit, evaluate, or find issues in a project's architecture, system design, module boundaries, or scalability.
---

# PURPOSE

Detect architectural weaknesses, structural problems,
and scalability risks in software systems and codebases.

The skill should identify system-level engineering concerns.

---

# RESPONSIBILITIES

- Detect tight coupling
- Detect poor separation of concerns
- Detect monolithic bottlenecks
- Detect layering violations
- Detect scalability risks
- Detect dependency problems
- Detect architecture inconsistencies
- Detect maintainability risks
- Detect overly complex structures
- Detect unclear module responsibilities

---

# NON-GOALS

- Do not redesign the entire system automatically
- Do not invent architectural intent
- Do not produce speculative conclusions without evidence

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Repository or module structure
- Optional architecture focus area
- Optional scalability context

---

# WORKFLOW

1. Inspect repository structure
2. Analyze module boundaries and responsibilities
3. Detect dependency relationships
4. Identify structural inconsistencies
5. Detect scalability and maintainability risks
6. Produce structured architecture review

---

# OUTPUT FORMAT

# Architecture Overview
# Structural Findings
# Scalability Risks
# Maintainability Risks
# Dependency Issues
# Design Smells
# Recommendations
# PASS/FAIL Verdict
# Confidence Level

---

# QUALITY BAR

- Prioritize evidence-based findings
- Focus on meaningful engineering risks
- Avoid speculative architecture criticism
- Prioritize maintainability and scalability
- Keep findings actionable

---

# FAILURE BEHAVIOR

If architecture visibility is incomplete:
- explicitly state uncertainty
- avoid unsupported conclusions
- limit findings to observable evidence

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Dependency graph analysis
- Distributed systems analysis
- Infrastructure architecture review
- Service boundary analysis
- Event-driven architecture analysis
