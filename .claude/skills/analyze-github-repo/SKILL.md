---
name: analyze-github-repo
description: Analyze a GitHub repository or local codebase to produce a structured, evidence-based technical report covering architecture, tech stack, design patterns, engineering practices, risks, and recommendations. Use when the user asks to inspect, audit, evaluate, or understand a repository, codebase, or project structure. Read-only.
---

# PURPOSE

Analyze a GitHub repository or local codebase to understand its architecture,
technology stack, structure, design patterns, quality, workflows, and overall engineering approach.

The skill should provide structured, evidence-based technical analysis.

---

# RESPONSIBILITIES

- Identify project purpose and domain
- Detect technology stack and frameworks
- Analyze folder and module structure
- Detect architectural patterns
- Identify APIs, services, and integrations
- Detect ML/AI components if present
- Analyze testing setup and quality practices
- Detect deployment and infrastructure patterns
- Evaluate code organization and maintainability
- Identify strengths, weaknesses, and technical risks

---

# NON-GOALS

- Do not modify repository files
- Do not refactor code
- Do not execute destructive commands
- Do not invent repository details
- Do not make unsupported assumptions

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Repository path
- Optional focus area
- Optional analysis depth

---

# WORKFLOW

1. Inspect repository structure
2. Identify key technologies and frameworks
3. Analyze architecture and module organization
4. Inspect important configuration files
5. Detect engineering practices and workflows
6. Identify risks, bottlenecks, and inconsistencies
7. Produce structured findings

---

# OUTPUT FORMAT

# Repository Overview
# Tech Stack
# Architecture Analysis
# Key Components
# Engineering Practices
# Code Quality Observations
# Risks and Weaknesses
# Strengths
# Recommendations
# Open Questions
# Confidence Level

---

# QUALITY BAR

- Be evidence-driven
- Reference actual files when possible
- Distinguish facts from assumptions
- Prefer precision over completeness
- Avoid hype-driven conclusions
- Maintain technical rigor

---

# FAILURE BEHAVIOR

If repository access is incomplete:
- explicitly state limitations
- avoid speculative conclusions
- provide partial analysis only where evidence exists

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Git history analysis
- Dependency vulnerability analysis
- Architecture diagram generation
- CI/CD inspection
- Code ownership analysis
