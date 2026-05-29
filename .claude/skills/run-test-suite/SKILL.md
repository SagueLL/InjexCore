---
name: run-test-suite
description: Execute the project's test suite, capture and analyze output, and produce a structured QA report identifying failures, flaky tests, runtime issues, configuration problems, and regression risks — with a PASS/FAIL verdict. Use when the user asks to run tests, execute the test suite, check CI-style verification, or analyze test failures.
---

# PURPOSE

Execute project test suites and analyze test execution results
in a structured and reliable manner.

The skill should identify failures, regressions, instability,
and execution risks.

---

# RESPONSIBILITIES

- Execute test suites
- Detect failing tests
- Detect flaky tests
- Detect runtime issues
- Detect configuration problems
- Analyze test output
- Summarize failures clearly
- Report execution status
- Identify regression indicators

---

# NON-GOALS

- Do not silently ignore failures
- Do not fabricate execution results
- Do not modify production code automatically
- Do not suppress important error information

---

# TOOLS

- Read
- Bash

---

# INPUTS

- Test command
- Optional target modules
- Optional execution scope

---

# WORKFLOW

1. Detect project testing framework
2. Execute relevant test suite
3. Capture execution output
4. Analyze failures and warnings
5. Detect instability or regressions
6. Produce structured QA report

---

# OUTPUT FORMAT

# Execution Summary
# Passed Tests
# Failed Tests
# Error Analysis
# Warnings
# Regression Risks
# Recommendations
# PASS/FAIL Verdict
# Confidence Level

---

# QUALITY BAR

- Preserve execution accuracy
- Report failures clearly
- Prioritize actionable findings
- Avoid hiding errors
- Keep reports concise and structured

---

# FAILURE BEHAVIOR

If test execution fails unexpectedly:
- report raw failure information
- explain execution limitations
- avoid speculative conclusions

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Coverage analysis
- CI/CD integration
- Parallel test execution
- Benchmark tracking
- ML validation workflows
