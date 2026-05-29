---
name: detect-missing-values
description: Detect and analyze missing-value patterns within a dataset — sparsity, systematic missingness, suspicious null patterns, and downstream ML impact — without auto-imputing or removing data. Use when the user asks to find, analyze, or report on missing values, NaNs, nulls, sparsity, or data completeness in a dataset.
---

# PURPOSE

Detect, analyze, and evaluate missing-value patterns
within datasets and feature spaces.

The skill should identify risks, patterns,
and potential downstream impact.

---

# RESPONSIBILITIES

- Detect missing values
- Detect systematic missingness
- Detect feature sparsity
- Detect suspicious null patterns
- Evaluate downstream impact
- Analyze missing-value distribution
- Identify high-risk features

---

# NON-GOALS

- Do not impute values automatically
- Do not fabricate missing-value explanations
- Do not remove features automatically

---

# TOOLS

- Read
- Write

---

# INPUTS

- Dataset
- Optional target variable
- Missing-value thresholds (optional)

---

# WORKFLOW

1. Analyze missing-value distribution
2. Detect systematic missingness
3. Evaluate feature sparsity
4. Identify high-risk missing patterns
5. Assess downstream ML impact
6. Produce structured findings

---

# OUTPUT FORMAT

# Missing Value Summary
# Feature Sparsity Analysis
# High-Risk Features
# Missingness Patterns
# ML Impact Risks
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Prioritize meaningful missing-value analysis
- Avoid simplistic conclusions
- Preserve downstream modeling context
- Focus on actionable insights

---

# FAILURE BEHAVIOR

If dataset structure is incomplete:
- explicitly state limitations
- avoid unsupported conclusions
- analyze only observable patterns

---

# FUTURE EXTENSIONS

Possible future capabilities:
- Missingness causality analysis
- Time-aware missing-value analysis
- Automated imputation recommendations
- Sensor outage detection
