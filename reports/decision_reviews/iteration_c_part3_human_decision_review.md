# Iteration C Part 3 — Human Decision Review

**Repo:** InjexCore · **Branch:** `refactor/v1-architecture-stabilization`
**Date:** 2026-06-17 (UTC)
**Canonical run:** `remat-v1-20260616T102558Z` · **BOM run:** `20260612T124909Z`
**Decision scope:** human review of the Iteration C Part 3 decision report + manual real-data inspection
**Decision type:** documentation-only human decision review — no artifact mutation, no refit, no programmatic approval
**Source decision report:** [`data/intelligence/forensics/reference_decision/remat-v1-20260616T102558Z/`](../../data/intelligence/forensics/reference_decision/remat-v1-20260616T102558Z/) (`decision_summary.md` + decision matrix/actions/risk/required-records tables)

> This document records a **human** decision. It is *decision-support documentation* layered on
> top of the system's read-only recommendation. It does not change any persisted artifact, does
> not approve a quarantine programmatically, does not refit a model, and does not mutate any
> anomaly score. The existing artifacts remain exactly as written, including
> `approval_required=True, approved=False`.

---

## A. Executive Summary

- Manual inspection of the real data indicates that **`inlet_hopper_points` stops providing valid data from row 137237 onward** — a sensor/channel failure pattern, not valid process evidence.
- The human reviewer **approves scoped quarantine treatment of `inlet_hopper_points` from row 137237 onward** — for technical review and downstream interpretation only. This is **not** a blanket historical deletion of the sensor; the channel remains valid evidence *before* the failure boundary.
- This approval is **human-reviewed and documentation-level only**. No artifact is mutated, no sensor is excluded automatically, and the persisted quarantine proposal still reads `approval_required=True, approved=False`.
- **Reference v2 remains deferred.** No model refit and no new reference baseline are approved at this stage (the system's residual healthy-only drift assessment is `residual_material=False`).
- **No automatic production action is approved.** Nothing here authorizes production exclusion, alerting, or customer-facing claims.
- The physical root cause is **not** confirmed. The evidence supports the *observed invalid signal* and a scoped quarantine treatment from the failure point forward — not a proven mechanical cause.
- The read-only Technical Validation Dashboard MVP may surface this as a **human decision overlay** (human-approved scoped quarantine, with clear boundaries) — distinct from the unchanged artifact state and from any applied pipeline state.

---

## B. Evidence Reviewed

System decision artifacts inspected under `data/intelligence/forensics/reference_decision/remat-v1-20260616T102558Z/`:

- `decision_summary.md`
- `decision_matrix.parquet`
- `candidate_actions.parquet`
- `required_plant_records.parquet`
- `risk_assessment.parquet`
- `reference_decision_manifest.json` (component/run/upstream provenance + completion status)

Human input:

- **Human manual-inspection note** — direct inspection of the real data, observing that `inlet_hopper_points` stops providing valid data from row 137237 onward.

Cross-referenced for canonical state and boundaries:

- [`reports/hardening/controlled_rematerialization_report.md`](../hardening/controlled_rematerialization_report.md)
- [`reports/dashboard/pre_dashboard_contract_cleanup_report.md`](../dashboard/pre_dashboard_contract_cleanup_report.md)
- [`docs/dashboard/dashboard_data_contract.md`](../../docs/dashboard/dashboard_data_contract.md)
- `CLAUDE.md` (project status), `docs/sessions/day_close_2026-06-16.md` (system-detected onset timestamp)

---

## C. Quarantine Proposal Review — `inlet_hopper_points`

| Field | Value |
|---|---|
| Target sensor | `inlet_hopper_points` |
| Failure boundary (human-observed) | **row 137237 onward** |
| Human observation | From row 137237 onward the channel stops providing valid data — consistent with a failed / broken / disconnected / non-functioning sensor or channel |
| System evidence (independent) | Sensor-health `flatline_zero` + drift `sensor_drift` onset recorded at timestamp **2024-09-17 16:23:22**; quarantine-aware interpretive view suppresses **30,096 of 33,186 non-normal rows (~91%)**; raw drift mass **209.6 → 90.5 (57% reduction)**; **23 residual windows (0.2%)**; ~**1,411** residual `inlet_hopper_points` anomaly rows after suppression |
| System scoring impact (interpretive) | Treating the channel as invalid clears ~91% of the non-normal review backlog as instrumentation-dominated — this is interpretive post-processing of persisted scores, **not** a rescore or refit |
| Risk if ignored | A known instrumentation fault keeps distorting scoring; anomaly mass keeps masking genuine process signals |
| Risk if over-applied | A co-located process signal could be hidden — **reversible**, and bounded here by the *scoped* (row 137237 onward) treatment rather than a full-history exclusion |
| **Human decision** | **Approve scoped quarantine treatment from row 137237 onward** |
| Scope of approval | Technical review and downstream interpretation only |
| Limitations | No historical artifact is mutated in this task; no automatic production exclusion is authorized; the physical root cause is not proven |

**Decision: approve scoped quarantine treatment from row 137237 onward.**

Clarifications:

- This approval is limited to **technical interpretation and future downstream handling**.
- It **does not mutate** historical artifacts in this documentation task — the persisted proposal stays `approval_required=True, approved=False`.
- It **does not authorize automatic production exclusion**.
- It **does not prove the physical root cause**.

**Boundary honesty note (system vs human).** Row `137237` comes from the **human's manual data
inspection**; it does not appear in any persisted artifact. The **system** independently flagged
the `inlet_hopper_points` failure onset as the timestamp **2024-09-17 16:23:22** (sensor-health
flatline-zero / drift `sensor_drift`). These two observations **corroborate** each other — a
row-index boundary from manual inspection and a timestamp boundary from automated detection — but
the exact row↔timestamp mapping has **not** been programmatically reconciled here and should be
confirmed against plant/sensor records (see §E). The scope is "from row 137237 onward unless
future evidence shows a different exact failure boundary."

---

## D. Reference v2 Review

| Field | Value |
|---|---|
| Current system recommendation | `design_reference_candidate_v2` — **not recommended** (`recommended=False`, priority low); Reference v2 deferred because residual healthy-only drift is immaterial (`residual_material=False`) |
| **Human decision** | **Defer Reference v2** |
| Reasoning | The residual healthy-only drift assessment does not justify a new reference at this stage. The dominant issue appears to be the `inlet_hopper_points` sensor/channel failure, not a validated new stable process regime |
| Why refit is not approved | A premature refit risks baking instrumentation noise into a new baseline; a true rescore/refit excluding the channel is itself gated on quarantine approval *and* plant-record review, neither of which is complete |
| What would trigger reconsideration | The scoped quarantine treatment being reflected in a controlled future analysis **and**, ideally, plant/sensor records being reviewed to confirm the failure boundary and rule out a deliberate process change |

**Decision: defer Reference v2.**

Clarifications:

- No new reference baseline should be created now.
- No model refit is approved.
- The next reference decision should happen only after the scoped quarantine treatment is reflected in a controlled future analysis and, ideally, after plant/sensor records are reviewed.

---

## E. Required Plant / Sensor Records

Even though the human reviewer approves scoped quarantine treatment at the documentation level,
the following external records would still strengthen the evidence and are prerequisites for any
operational or customer-facing claim:

- Sensor **maintenance logs** for `inlet_hopper_points` (service / failure history)
- Sensor **replacement or disconnection records**
- **PLC / channel logs** around the failure window
- **Operator notes** for the operational shift around the failure point
- **Alarm logs** spanning the failure window
- **Production context** (e.g. setpoint / recipe changes) around the failure point, to rule out a deliberate process change
- The **timestamp corresponding to row 137237**, to reconcile the human-observed row boundary with the system-detected onset (**2024-09-17 16:23:22**)

Clarification: **these records are not required to make the current documentation-level human
decision, but they are required before operational or customer-facing claims.**

---

## F. Dashboard Treatment

The read-only **Technical Validation Dashboard MVP** may represent this decision as a
**human decision overlay**:

- `inlet_hopper_points` scoped quarantine **approved by human review**
- Failure boundary: **row 137237** (human-observed; system onset `2024-09-17 16:23:22`)
- Approval scope: **technical review / downstream interpretation**
- `approved=False` still present in existing artifacts (artifacts were not regenerated)
- `human_decision = approved_scoped_quarantine`
- **Reference v2 deferred**
- **No refit approved**

**Distinguish three states — do not collapse them.** The dashboard must clearly separate:

| State | Meaning here |
|---|---|
| **Artifact state** | The persisted proposal is unchanged: `approval_required=True, approved=False`. Original `severity` / `combined_score` are untouched |
| **Human review state** | `human_decision = approved_scoped_quarantine` (from row 137237 onward), recorded in this document |
| **Applied pipeline state** | *Not applied.* No quarantine was applied, no rescore/refit ran, no score was mutated |

> Human review approves scoped quarantine treatment, but existing artifacts have not been
> regenerated or mutated. Therefore, the dashboard must show this as a **human decision overlay,
> not as an applied pipeline state**.

The dashboard **must not** include:

- an approve button
- an apply-quarantine button
- a create-Reference-v2 button
- a run-refit button
- an automatic-exclusion control
- a production-alert action

(These align with the forbidden controls and boundaries in
[`docs/dashboard/dashboard_data_contract.md`](../../docs/dashboard/dashboard_data_contract.md).)

---

## G. Product Narrative Treatment

**What can be said:**

- The system identified a dominant suspicious sensor/channel pattern.
- Human inspection confirmed that the signal stops providing valid data from row 137237 onward.
- The workflow supports evidence-backed human review of sensor reliability.
- The system helps separate instrumentation failure from process behaviour.

**What must not be claimed:**

- The system autonomously approved quarantine.
- The system automatically fixed the data.
- The system confirmed the physical root cause.
- The system is production-ready.
- The system performs autonomous predictive maintenance.

---

## H. Final Decision State

| Item | Decision | Scope | Artifact state | Next action | Dashboard visibility |
|---|---|---|---|---|---|
| `inlet_hopper_points` quarantine | Approve scoped quarantine from row 137237 onward | Technical review / downstream interpretation only | Unchanged — `approval_required=True, approved=False` | Reconcile row 137237 with onset `2024-09-17 16:23:22`; collect plant records before operational use | Show as human decision overlay (`human_decision=approved_scoped_quarantine`) |
| Reference v2 | Defer | No new baseline, no refit | `design_reference_candidate_v2` not recommended; `residual_material=False` | Reconsider only after controlled post-quarantine analysis + plant-record review | Show as deferred; no create/refit controls |
| Controlled scoring adjusted review | Use as interpretive evidence | Interpretive post-processing of persisted scores only | Original scores unchanged; adjusted views are interpretive | Continue using as decision-support evidence, clearly labeled interpretive | Show adjusted review as interpretive, never as a rescore |
| Plant / sensor records | Collect before operational/customer-facing claims | Evidence strengthening | n/a (external) | Gather maintenance/channel/PLC/operator/alarm/production records | Show as required-before-operational, not as already-held evidence |
| Dashboard MVP | Show read-only decision-support view | Technical validation only | n/a | Build read-only overlay distinguishing artifact / human / applied states | Read-only; no write/approve/apply/refit/alert controls |

---

## I. Implication for Phase 1 Closure

This human review strengthens Phase 1 closure because:

- The main pending decision has now been reviewed by the human decision-maker.
- The sensor issue now has a **scoped human decision** (approve quarantine treatment from row 137237 onward), rather than an open recommendation.
- Reference v2 remains **safely deferred**, with no refit and no new baseline.
- The next report can reflect **both** the technical state and the human decision state, instead of the technical state alone.

---

## J. Recommended Next Step

Create the Post-Iteration-C Technical State & Product Implications report using this decision review as an input.
