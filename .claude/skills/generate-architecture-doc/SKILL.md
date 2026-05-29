---
name: generate-architecture-doc
description: Generate structured, technically rigorous architecture documentation for a software, AI/ML, or infrastructure project — system overview, components, data flow, infrastructure, ML pipeline, integrations, scalability, and risks — based on observable repository structure (no fabricated components). Use when the user asks to document, describe, diagram, or write up the architecture, system design, components, or data flow of a project.
---

# PURPOSE

Generate structured software and system architecture documentation
for engineering, AI, ML, and infrastructure projects.

The skill should clearly explain system structure, components,
interactions, responsibilities, and design rationale.

---

# RESPONSIBILITIES

- Document system architecture
- Describe major components and responsibilities
- Explain data flow
- Explain service interactions
- Describe infrastructure structure
- Document AI/ML pipelines when relevant
- Identify architectural patterns
- Document scalability considerations
- Explain deployment architecture
- Summarize technical decisions

---

# NON-GOALS

- Do not invent architecture components
- Do not fabricate infrastructure details
- Do not oversimplify critical system behavior
- Do not produce vague documentation

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Repository structure
- Infrastructure files
- Configuration files
- Existing architecture docs
- Optional focus area

---

# WORKFLOW

1. Inspect repository and infrastructure structure
2. Identify major components and modules
3. Detect architecture patterns
4. Analyze interactions and dependencies
5. Map system responsibilities
6. Generate structured architecture documentation

---

# OUTPUT FORMAT

# System Overview
# Architecture Style
# Core Components
# Data Flow
# Infrastructure
# AI/ML Pipeline
# Integrations
# Scalability Considerations
# Risks and Limitations
# Future Improvements

---

# QUALITY BAR

- Be technically rigorous
- Keep explanations structured and readable
- Preserve architectural accuracy
- Avoid speculative assumptions
- Focus on system understanding

---

# FAILURE BEHAVIOR

If architecture visibility is incomplete:
- explicitly state uncertainty
- avoid fabricating system relationships
- document only observable structure

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Architecture diagram generation
- Sequence flow generation
- Cloud infrastructure analysis
- Distributed systems analysis
- Dependency graph visualization
