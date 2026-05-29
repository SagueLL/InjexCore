---
name: detect-insecure-dependencies
description: Analyze project dependencies, packages, and lockfiles for security risks — vulnerable, outdated, unmaintained, or risky transitive dependencies — producing severity-ranked, evidence-based findings without exploiting vulnerabilities or overstating risk. Use when the user asks to audit, scan, or evaluate the security of project dependencies, requirements.txt, package.json, lockfiles, or supply-chain risks.
---

# PURPOSE

Analyze project dependencies, packages,
libraries, and external software components
for security risks, outdated versions,
and potentially unsafe dependency usage.

The skill should identify meaningful dependency-related security risks
without generating excessive false positives.

---

# RESPONSIBILITIES

- Detect vulnerable dependencies
- Detect outdated security-sensitive packages
- Detect abandoned or unmaintained libraries
- Detect suspicious dependency usage
- Detect insecure version constraints
- Detect dependency exposure risks
- Detect risky transitive dependency patterns
- Support operational security reviews

---

# NON-GOALS

- Do not exploit vulnerabilities
- Do not fabricate dependency risks
- Do not overstate vulnerability severity
- Do not blindly recommend upgrades
- Do not ignore operational compatibility constraints

---

# TOOLS

- Read
- Glob
- Grep

---

# INPUTS

- Dependency manifests
- Lockfiles
- Environment definitions
- Optional operational constraints

---

# WORKFLOW

1. Analyze dependency manifests and lockfiles
2. Detect outdated and security-sensitive packages
3. Detect risky dependency patterns
4. Evaluate operational security implications
5. Rank dependency risks and exposure severity
6. Produce structured dependency security review

---

# OUTPUT FORMAT

# Dependency Security Overview
# Vulnerable Dependencies
# Outdated Security Risks
# Unmaintained Libraries
# Transitive Dependency Risks
# Severity Assessment
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Prioritize evidence-based findings
- Avoid exaggerated vulnerability claims
- Preserve operational compatibility awareness
- Focus on actionable remediation
- Avoid excessive false positives

---

# FAILURE BEHAVIOR

If dependency visibility is incomplete:
- explicitly state limitations
- avoid unsupported security conclusions
- analyze only observable dependencies

---

# FUTURE EXTENSIONS

Possible future capabilities:
- CVE database integration
- SBOM analysis
- Supply-chain security analysis
- Dependency trust scoring
- Automated remediation planning
