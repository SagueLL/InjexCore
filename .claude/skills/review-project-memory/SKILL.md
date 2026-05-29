---
name: review-project-memory
description: Review project memory sources such as MEMORY.md, CLAUDE.md, CLAUDE.local.md, architecture documents, and project knowledge files to identify missing knowledge, outdated information, inconsistencies, and recommended updates. Use when maintaining project continuity and long-term context.
---

# PURPOSE

Review project memory sources and identify information that should be persisted or updated.

The skill should help maintain project continuity and knowledge consistency.

---

# RESPONSIBILITIES

- Review MEMORY.md
- Review CLAUDE.md
- Review CLAUDE.local.md
- Detect missing project knowledge
- Detect outdated information
- Detect memory inconsistencies
- Recommend updates
- Improve project continuity

---

# NON-GOALS

- Do not modify files automatically
- Do not overwrite project memory
- Do not invent project knowledge
- Do not remove information without evidence

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- MEMORY.md
- CLAUDE.md
- CLAUDE.local.md
- Project documentation
- Architecture documentation

---

# WORKFLOW

1. Review project memory sources
2. Compare against repository state
3. Detect missing knowledge
4. Detect outdated information
5. Detect inconsistencies
6. Generate update recommendations

---

# OUTPUT FORMAT

# Memory Review
# Missing Knowledge
# Outdated Information
# Consistency Issues
# Recommended Updates
# Confidence Level

---

# QUALITY BAR

- Preserve project continuity
- Focus on important knowledge
- Avoid speculative recommendations
- Maintain consistency

---

# FAILURE BEHAVIOR

If memory visibility is incomplete:

- explicitly state limitations
- review only observable knowledge
- identify missing context

---

# FUTURE EXTENSIONS

Possible future capabilities:

- Automated memory synchronization
- Knowledge graph generation
- Context compression
- Project history tracking
