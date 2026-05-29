---
name: generate-readme
description: Generate a structured, professional, technically accurate README for a software, AI, or ML project — overview, features, stack, install, usage, structure, configuration, and development sections — based on actual repository contents (no marketing fluff, no invented features). Use when the user asks to create, write, draft, regenerate, or update a README or project documentation file.
---

# PURPOSE

Generate structured, professional, and maintainable README documentation
for software, AI, ML, or engineering projects.

The skill should produce concise, technically accurate, developer-friendly documentation.

---

# RESPONSIBILITIES

- Generate project overview
- Describe project purpose and goals
- Document installation steps
- Document usage instructions
- Describe project structure
- Document dependencies
- Explain development workflow
- Document configuration requirements
- Generate contribution guidelines when relevant
- Maintain documentation clarity and consistency

---

# NON-GOALS

- Do not invent project capabilities
- Do not generate inaccurate setup instructions
- Do not include unverifiable implementation details
- Do not produce marketing-style content

---

# TOOLS

- Read
- Glob

---

# INPUTS

- Project structure
- Configuration files
- Existing documentation
- Optional documentation requirements

---

# WORKFLOW

1. Inspect repository structure
2. Detect project purpose and stack
3. Analyze configuration and dependencies
4. Extract important workflows
5. Generate structured README
6. Ensure clarity and maintainability

---

# OUTPUT FORMAT

# Project Title
# Overview
# Features
# Tech Stack
# Installation
# Usage
# Project Structure
# Configuration
# Development
# Contributing
# License

---

# QUALITY BAR

- Be concise and technically accurate
- Prioritize developer usability
- Avoid unnecessary verbosity
- Keep formatting clean and structured
- Prefer clarity over completeness

---

# FAILURE BEHAVIOR

If project structure is incomplete:
- document only verifiable information
- explicitly identify missing details
- avoid speculative documentation

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Multi-language documentation
- Auto-generated command examples
- Deployment documentation generation
- API reference integration
