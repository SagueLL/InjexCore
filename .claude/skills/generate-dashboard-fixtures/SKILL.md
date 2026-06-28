---
name: generate-dashboard-fixtures
description: Generate realistic dashboard fixture data from approved contracts, schemas, and available intelligence outputs for frontend development, UI testing, demos, and empty/loading/error state validation. Use when the frontend needs stable sample data before full API integration.
---

# PURPOSE

Generate realistic dashboard fixture data for frontend development and demo workflows.

The skill should allow dashboard views to be developed and tested without depending on live backend integration.

---

# RESPONSIBILITIES

- Generate dashboard fixture payloads
- Generate realistic demo data
- Generate contract-compliant JSON examples
- Generate frontend-ready sample datasets
- Support UI development before API integration
- Support demo workflows
- Support empty, loading, and error state testing
- Preserve realistic industrial context
- Avoid misleading fake operational claims

---

# NON-GOALS

- Do not fabricate real production evidence
- Do not present fixtures as real data
- Do not generate data outside the approved contract
- Do not modify model outputs
- Do not replace real validation data

---

# TOOLS

- Read
- Write
- Glob
- Grep

---

# INPUTS

- Dashboard data contracts
- JSON schemas
- Existing intelligence outputs
- Demo requirements
- View requirements
- Industrial context

---

# WORKFLOW

1. Inspect dashboard data contract
2. Identify required fixture scenarios
3. Generate contract-compliant sample data
4. Include realistic but clearly synthetic values
5. Generate normal, warning, anomaly, empty, and error scenarios
6. Document fixture assumptions
7. Produce frontend-ready fixture files or examples

---

# OUTPUT FORMAT

# Fixture Generation Overview

# Target Contract

# Generated Scenarios

# Example Payloads

# Synthetic Data Notes

# UI Testing Notes

# Limitations

# Confidence Level

---

# QUALITY BAR

- Preserve contract compliance
- Mark synthetic data clearly
- Keep industrial values realistic
- Avoid misleading realism
- Support frontend development
- Support demo repeatability
- Support edge-case testing

---

# FAILURE BEHAVIOR

If no contract exists:

- do not generate arbitrary fixtures
- recommend defining a contract first
- provide only a minimal illustrative structure if useful

If source context is incomplete:

- explicitly state assumptions
- keep values generic
- avoid domain-specific claims

---

# FUTURE EXTENSIONS

Possible future capabilities:

- Fixture factory generation
- Scenario-based demo datasets
- Frontend mock API generation
- Storybook integration
- Contract-based synthetic data generation
