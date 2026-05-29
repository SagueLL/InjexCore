---
name: review-insecure-configurations
description: Review infrastructure, application, and operational configurations for security weaknesses — insecure defaults, weak access control, overly permissive settings, unsafe deployment patterns, telemetry exposure — with severity-ranked, evidence-based findings. Use when the user asks to review, audit, or evaluate configuration files, infrastructure-as-code, deployment settings, or operational settings for security risks.
---

# PURPOSE

Review infrastructure, application,
and operational configurations for security weaknesses
and unsafe engineering practices.

The skill should identify meaningful configuration risks
without producing excessive false positives.

---

# RESPONSIBILITIES

- Detect insecure configurations
- Detect unsafe defaults
- Detect weak access-control configurations
- Detect overly permissive settings
- Detect insecure deployment patterns
- Detect telemetry exposure risks
- Support operational security validation

---

# NON-GOALS

- Do not fabricate configuration intent
- Do not assume insecure behavior without evidence
- Do not produce fear-driven reports
- Do not oversimplify operational security

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Configuration files
- Infrastructure definitions
- Deployment settings
- Optional operational context

---

# WORKFLOW

1. Analyze configuration structure
2. Detect insecure or risky patterns
3. Evaluate operational security implications
4. Rank severity and exposure risks
5. Produce structured security review

---

# OUTPUT FORMAT

# Configuration Security Overview
# Insecure Configuration Findings
# Access-Control Risks
# Operational Exposure Risks
# Severity Assessment
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Preserve contextual awareness
- Prioritize meaningful security risks
- Avoid unsupported conclusions
- Focus on actionable remediation
- Avoid excessive false positives

---

# FAILURE BEHAVIOR

If configuration visibility is incomplete:
- explicitly state uncertainty
- avoid unsupported security conclusions
- review only observable configurations

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Cloud security analysis
- Kubernetes security validation
- IaC security review
- Zero-trust validation

