---
name: generate-unit-tests
description: Generate meaningful, maintainable unit tests for software modules, functions, services, or ML/data components — covering normal paths, edge cases, error handling, and missing validation scenarios, while following the project's existing testing conventions. Use when the user asks to write, generate, scaffold, or add unit tests for specific code, modules, or a Python codebase.
---

# PURPOSE

Generate meaningful and maintainable unit tests
for software modules, functions, services, and ML/data components.

The skill should prioritize correctness, edge cases,
maintainability, and realistic validation scenarios.

---

# RESPONSIBILITIES

- Generate unit tests for target code
- Cover normal and edge-case behavior
- Validate expected outputs
- Validate error handling
- Detect missing validation scenarios
- Improve test maintainability
- Generate readable test structure
- Follow project testing conventions when visible

---

# NON-GOALS

- Do not modify production logic
- Do not generate meaningless tests
- Do not fabricate undocumented behavior
- Do not generate brittle implementation-coupled tests

---

# TOOLS

- Read
- Write
- Glob
- Grep

---

# INPUTS

- Target files/modules
- Existing test structure
- Testing framework
- Optional coverage goals

---

# WORKFLOW

1. Inspect target implementation
2. Detect expected behavior
3. Analyze edge cases and failure conditions
4. Generate maintainable tests
5. Follow project testing conventions
6. Validate readability and structure

---

# OUTPUT FORMAT

# Test Coverage Summary
# Generated Tests
# Covered Scenarios
# Missing Scenarios
# Assumptions
# Confidence Level

---

# QUALITY BAR

- Prioritize meaningful coverage
- Avoid brittle tests
- Cover edge cases
- Keep tests readable and maintainable
- Prefer deterministic behavior
- Avoid unnecessary mocking

---

# FAILURE BEHAVIOR

If expected behavior is unclear:
- explicitly state assumptions
- avoid inventing undocumented functionality
- generate only evidence-supported tests

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Property-based testing
- ML pipeline testing
- Performance testing
- API contract testing
- Security-focused testing
