---
name: analyze-bash-security
description: Analyze Bash scripts and shell workflows for unsafe execution patterns, command injection, insecure file/permission handling, and risky automation behavior — producing severity-ranked, evidence-based findings without executing scripts or exploiting vulnerabilities. Use when the user asks to audit, review, or evaluate shell scripts, Bash automation, or CI/CD shell workflows for security risks.
---

# PURPOSE

Analyze Bash scripts and shell workflows
for unsafe operational behavior,
security weaknesses, and risky execution patterns.

The skill should identify meaningful operational risks
within engineering automation workflows.

---

# RESPONSIBILITIES

- Detect unsafe shell execution patterns
- Detect command injection risks
- Detect unsafe file operations
- Detect insecure permission usage
- Detect risky automation behavior
- Detect unsafe environment handling
- Support engineering workflow security

---

# NON-GOALS

- Do not execute scripts
- Do not exploit vulnerabilities
- Do not fabricate security findings
- Do not overstate shell risks

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Shell scripts
- Automation workflows
- CI/CD scripts
- Optional execution context

---

# WORKFLOW

1. Analyze shell and automation scripts
2. Detect risky execution patterns
3. Evaluate operational security implications
4. Rank severity and exploitability risks
5. Produce structured shell security review

---

# OUTPUT FORMAT

# Shell Security Overview
# Unsafe Execution Findings
# Permission Risks
# Automation Risks
# Severity Assessment
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Prioritize operational realism
- Avoid exaggerated security claims
- Preserve contextual awareness
- Focus on actionable remediation
- Avoid excessive false positives

---

# FAILURE BEHAVIOR

If script visibility is incomplete:
- explicitly state limitations
- avoid unsupported conclusions
- review only observable behavior

---

# FUTURE EXTENSIONS

Possible future capabilities:
- CI/CD workflow security analysis
- Runtime execution monitoring
- Container security integration
- Secure automation validation
