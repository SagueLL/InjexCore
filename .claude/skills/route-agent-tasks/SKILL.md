---
name: route-agent-tasks
description: Route tasks and subtasks to the most appropriate specialized agents in a multi-agent ecosystem — matching capabilities, detecting overlaps, identifying parallel execution opportunities, and preserving workflow consistency, without fabricating agent capabilities. Use when the user asks to dispatch, assign, route, or coordinate work across multiple agents.
---

# PURPOSE

Route tasks and subtasks to the most appropriate agents
within a multi-agent engineering and ML ecosystem.

The skill should optimize specialization,
execution efficiency, and workflow consistency.

---

# RESPONSIBILITIES

- Match tasks to specialized agents
- Detect agent capability overlap
- Optimize task routing
- Reduce duplicated effort
- Maintain workflow consistency
- Support coordinated execution
- Improve ecosystem efficiency

---

# NON-GOALS

- Do not assign tasks blindly
- Do not overload inappropriate agents
- Do not fabricate agent capabilities
- Do not ignore workflow dependencies

---

# TOOLS

- Read
- Write

---

# INPUTS

- Workflow tasks
- Available agents
- Agent capabilities
- Optional execution constraints

---

# WORKFLOW

1. Analyze workflow requirements
2. Match tasks to capabilities
3. Detect dependencies and overlaps
4. Optimize execution routing
5. Validate workflow consistency
6. Produce structured routing plan

---

# OUTPUT FORMAT

# Workflow Routing Summary
# Task-to-Agent Mapping
# Dependency Coordination
# Parallel Execution Opportunities
# Workflow Risks
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Prioritize specialization quality
- Avoid redundant routing
- Preserve workflow consistency
- Focus on execution efficiency
- Preserve contextual awareness

---

# FAILURE BEHAVIOR

If agent capabilities are unclear:
- explicitly state uncertainty
- avoid unsupported routing assumptions
- identify missing capability information

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Dynamic agent orchestration
- Autonomous load balancing
- Adaptive workflow routing
- Multi-agent optimization
