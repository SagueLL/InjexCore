---
name: detect-collinearity
description: Detect feature collinearity, redundancy, and multicollinearity risks within a dataset or feature matrix — identifying highly correlated pairs, redundant feature groups, and stability/interpretability concerns — without auto-removing features. Use when the user asks to check correlations, find redundant features, assess multicollinearity, or evaluate feature-space quality.
---

# PURPOSE

Detect feature collinearity, redundancy, and dependency risks
within datasets and feature spaces.

The skill should improve feature quality, model stability,
and interpretability.

---

# RESPONSIBILITIES

- Detect highly correlated features
- Detect redundant feature groups
- Detect dependency risks
- Identify multicollinearity
- Improve feature-space quality
- Support feature selection decisions
- Improve interpretability and robustness

---

# NON-GOALS

- Do not remove features automatically
- Do not oversimplify feature relationships
- Do not assume correlation implies causation

---

# TOOLS

- Read
- Write

---

# INPUTS

- Dataset or feature matrix
- Correlation thresholds
- Optional target variable

---

# WORKFLOW

1. Analyze feature relationships
2. Detect high-correlation groups
3. Identify multicollinearity risks
4. Evaluate redundancy impact
5. Produce structured findings
6. Suggest possible improvements

---

# OUTPUT FORMAT

# Collinearity Summary
# High Correlation Pairs
# Redundant Feature Groups
# Multicollinearity Risks
# Interpretability Risks
# Recommendations
# Confidence Level

---

# QUALITY BAR

- Prioritize meaningful feature analysis
- Avoid simplistic correlation conclusions
- Preserve interpretability concerns
- Focus on modeling stability and quality

---

# FAILURE BEHAVIOR

If feature structure is incomplete:
- explicitly state limitations
- avoid unsupported conclusions
- analyze only observable relationships

---

# FUTURE EXTENSIONS

Possible future capabilities:
- VIF analysis
- Feature clustering
- Dimensionality reduction recommendations
- Automated feature pruning
