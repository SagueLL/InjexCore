---
name: detect-exposed-secrets
description: Detect exposed secrets, credentials, API keys, tokens, and sensitive configuration data within a repository — hardcoded keys, leaked env vars, unsafe secret storage — flagging credential exposure risks without validating or exfiltrating values. Use when the user asks to scan for secrets, credentials, leaked tokens, or sensitive configuration in code.
---

# PURPOSE

Detect exposed secrets, credentials,
tokens, API keys, and sensitive configuration data
within repositories and engineering environments.

The skill should identify meaningful credential exposure risks.

---

# RESPONSIBILITIES

- Detect hardcoded API keys
- Detect exposed credentials
- Detect embedded tokens
- Detect unsafe secret storage
- Detect suspicious configuration exposure
- Detect leaked environment variables
- Support operational security reviews

---

# NON-GOALS

- Do not validate live credentials
- Do not exfiltrate secrets
- Do not fabricate exposures
- Do not expose sensitive values unnecessarily

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Repository or target files
- Optional security scope

---

# WORKFLOW

1. Analyze repository structure
2. Detect suspicious credential patterns
3. Identify exposed secrets and sensitive data
4. Evaluate operational security risks
5. Produce structured security findings

---

# OUTPUT FORMAT

# Security Overview
# Exposed Secrets Findings
# Credential Risks
# Sensitive Configuration Findings
# Severity Assessment
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Prioritize evidence-based findings
- Avoid false-positive inflation
- Preserve operational context
- Focus on actionable security risks
- Avoid unnecessary sensitive disclosure

---

# FAILURE BEHAVIOR

If repository visibility is incomplete:
- explicitly state limitations
- avoid unsupported security conclusions
- analyze only observable evidence

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Secret rotation recommendations
- CI/CD secret analysis
- Vault integration analysis
- Runtime secret monitoring
