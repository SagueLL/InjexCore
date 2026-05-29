---
name: summarize-paper
description: Produce a structured, technically rigorous summary of a research or technical paper — problem, method, datasets, evaluation, findings, limitations, and practical relevance — without hype or fabrication. Use when the user asks to summarize, analyze, digest, or extract findings from a paper, PDF, arXiv link, or technical document.
---

# PURPOSE

Analyze and summarize technical, scientific, or research papers
in a structured and technically rigorous manner.

The skill should preserve important methodological details,
limitations, assumptions, and practical implications.

---

# RESPONSIBILITIES

- Identify the core problem
- Identify the proposed solution
- Extract methodology and approach
- Identify datasets used
- Identify evaluation methods and metrics
- Summarize key findings and conclusions
- Identify strengths and limitations
- Identify assumptions and constraints
- Evaluate practical relevance
- Detect reproducibility concerns when possible

---

# NON-GOALS

- Do not oversimplify technical concepts
- Do not invent missing information
- Do not exaggerate results
- Do not claim validity beyond the paper's evidence

---

# TOOLS

- Read
- WebFetch

---

# INPUTS

- Paper or document
- Optional focus area
- Optional summary depth

---

# WORKFLOW

1. Identify paper objective and research question
2. Analyze methodology and experimental setup
3. Extract datasets, metrics, and evaluation strategy
4. Identify key findings and limitations
5. Assess practical relevance and applicability
6. Produce structured technical summary

---

# OUTPUT FORMAT

# Paper Overview
# Problem Statement
# Proposed Method
# Methodology
# Datasets
# Evaluation Strategy
# Key Findings
# Strengths
# Limitations
# Practical Relevance
# Open Questions
# Confidence Level

---

# QUALITY BAR

- Preserve technical accuracy
- Distinguish evidence from interpretation
- Preserve important limitations
- Avoid hype-driven language
- Prioritize clarity and rigor

---

# FAILURE BEHAVIOR

If the paper is incomplete or inaccessible:
- explicitly state limitations
- avoid fabricating missing details
- summarize only verifiable content

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Multi-paper comparison
- Citation graph analysis
- Reproducibility analysis
- SOTA benchmarking
- Experimental validity scoring
