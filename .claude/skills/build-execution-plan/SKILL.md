---
name: build-execution-plan
description: Build a structured execution plan for engineering, ML, industrial, or multi-agent workflows — sequencing tasks, mapping dependencies, identifying bottlenecks and parallelization opportunities, without fabricating requirements. Use when the user asks to produce an execution plan, runbook, sequencing strategy, or end-to-end workflow plan for a project.
---

# PURPOSE

Generate structured execution plans
for engineering, ML, industrial,
and multi-agent operational workflows.

The skill should optimize execution order,
dependency handling, and workflow reliability.

---

# RESPONSIBILITIES

- Build execution plans
- Organize workflow sequencing
- Detect workflow dependencies
- Identify execution bottlenecks
- Optimize workflow structure
- Support autonomous execution
- Improve workflow reliability

---

# NON-GOALS

- Do not fabricate workflow requirements
- Do not ignore execution dependencies
- Do not generate unrealistic plans
- Do not oversimplify operational workflows

---

# TOOLS

- Read
- Write

---

# INPUTS

- Workflow tasks
- Dependencies
- Available agents/tools
- Execution constraints

---

# WORKFLOW

1. Analyze workflow structure
2. Detect dependencies and sequencing
3. Optimize execution order
4. Detect bottlenecks and risks
5. Build structured execution plan
6. Produce workflow execution summary

---

# OUTPUT FORMAT

# Execution Overview
# Workflow Sequence
# Dependencies
# Parallelization Opportunities
# Bottlenecks and Risks
# Execution Recommendations
# Confidence Level

---

# QUALITY BAR

- Prioritize execution reliability
- Preserve workflow consistency
- Avoid unrealistic sequencing
- Focus on operational usefulness
- Preserve contextual awareness

---

# FAILURE BEHAVIOR

If workflow requirements are incomplete:
- explicitly state uncertainty
- avoid unsupported execution assumptions
- identify missing context

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Autonomous execution monitoring
- Dynamic replanning
- Workflow self-healing
- Multi-agent runtime orchestration
