---
name: review-dashboard-usability
description: Review dashboard usability, information hierarchy, visual clarity, navigation, state handling, industrial interpretability, and frontend user experience. Use when evaluating whether a technical dashboard is understandable, actionable, and ready for demos or users.
---

# PURPOSE

Review dashboard usability and user-facing clarity.

The skill should identify whether the dashboard helps users understand operational information quickly, accurately, and without misleading interpretation.

---

# RESPONSIBILITIES

- Review dashboard clarity
- Review information hierarchy
- Review navigation usability
- Review chart readability
- Review table readability
- Review severity indicators
- Review empty states
- Review loading states
- Review error states
- Review industrial interpretability
- Identify confusing UI patterns
- Identify misleading presentation risks
- Recommend usability improvements

---

# NON-GOALS

- Do not modify source code automatically
- Do not redesign the entire product without need
- Do not judge aesthetics without usability relevance
- Do not invent user feedback
- Do not ignore data uncertainty
- Do not override product decisions

---

# TOOLS

- Read
- Glob
- Grep
- Bash

Use Bash only for safe inspection, build checks, linting, tests, or non-destructive validation.

If browser tooling is available, use it only for non-sensitive local dashboard inspection.

---

# INPUTS

- Dashboard implementation
- Dashboard screenshots
- Dashboard routes
- Dashboard data contracts
- UI requirements
- Demo requirements
- User context

---

# WORKFLOW

1. Inspect dashboard view or specification
2. Review information hierarchy
3. Review visual and interaction clarity
4. Review state handling
5. Review industrial interpretability
6. Identify usability issues
7. Rank issues by severity
8. Produce usability review report

---

# OUTPUT FORMAT

# Dashboard Usability Review

# Target View

# Clarity Assessment

# Information Hierarchy

# Navigation Assessment

# Chart and Table Readability

# State Handling

# Industrial Interpretability

# Usability Issues

# Severity Assessment

# Recommendations

# Confidence Level

---

# QUALITY BAR

- Prioritize user understanding
- Prioritize operational clarity
- Avoid subjective design criticism
- Focus on actionable improvements
- Preserve data uncertainty
- Identify misleading UI risks
- Keep recommendations realistic for project phase

---

# FAILURE BEHAVIOR

If dashboard visibility is incomplete:

- explicitly state limitations
- review only observable UI or specifications
- identify missing context

If no user role is defined:

- review from a general technical-operator perspective
- mark assumptions clearly

If browser validation is unavailable:

- provide static usability review only
- state that runtime behavior was not inspected

---

# FUTURE EXTENSIONS

Possible future capabilities:

- Chrome DevTools MCP validation
- Playwright usability smoke tests
- Accessibility review
- Demo-readiness scoring
- Role-based usability testing
