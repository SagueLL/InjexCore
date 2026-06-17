# Post-Iteration-C Technical State & Product Implications

**Repo:** InjexCore · **Branch:** `refactor/v1-architecture-stabilization` · **Date:** 2026-06-17 (UTC)
**Canonical chain:** `remat-v1-20260616T102558Z` · **BOM run:** `20260612T124909Z`
**Human decision overlay:** `human-decision-v1-20260617T122735Z`
**Phase:** Fase 1 — Cierre técnico (technical closure)
**Document type:** technical-product state bridge (not an implementation report, not a pitch, not a dashboard spec)

**Source material:** [controlled_rematerialization_report.md](hardening/controlled_rematerialization_report.md), [post_iteration_c_hardening_report.md](hardening/post_iteration_c_hardening_report.md), [pre_dashboard_contract_cleanup_report.md](dashboard/pre_dashboard_contract_cleanup_report.md), [iteration_c_part3_human_decision_review.md](decision_reviews/iteration_c_part3_human_decision_review.md), [dashboard_data_contract.md](../docs/dashboard/dashboard_data_contract.md), [intelligence_dataflow.md](../docs/architecture/intelligence_dataflow.md), `README.md`, `CLAUDE.md`, and the human decision overlay run.

---

## A. Executive Summary

- **Phase 1 — technical closure is complete.** The real-data analytical chain is hardened, rematerialized, lineage-validated and frozen as a demonstrable base.
- The **canonical chain is `remat-v1-20260616T102558Z`** (10 components, one shared run id) over the 167,331-row real master (sha `5020956f…`), with BOM run `20260612T124909Z` reused.
- The chain enforces **manifest-last completion, run-versioning (no overwrite), fail-closed lineage, and original-score immutability** — proven by a strict read-only lineage sweep and a dashboard lineage validator.
- The system is **ready for a read-only Technical Validation Dashboard MVP** over this canonical run.
- The system is **not production-ready**, and must **not** be presented as autonomous predictive maintenance.
- The strongest current value is **traceable industrial intelligence and incident interpretation over real data** — explainable observability, not automatic prediction.
- **Human review approved scoped quarantine treatment for `inlet_hopper_points`** (documentation-level; canonical artifacts unchanged).
- The human decision is now encoded in a **structured, run-versioned dashboard overlay** (`human-decision-v1-20260617T122735Z`) keeping artifact / human-review / applied-pipeline / dashboard-overlay states distinct.
- **Reference v2 remains deferred** (`residual_material=False`) and **no model refit is approved**.
- One **non-blocking** caveat remains: the canonical leaf manifests predate explicit `behaviour_run_id` provenance, so the validator emits a warning (not a failure) until the next rematerialization.

---

## B. What Has Been Built

The Intelligence Layer (`src/intelligence/`) sits downstream of parameter-free preprocessing and characterizes *normal* behaviour; the Context Layer (`src/context/`) adds read-only external joins; the dashboard layer is a read-only consumption contract. Maturity is reported honestly.

| Component | Purpose | Maturity | Contribution |
|---|---|---|---|
| Behaviour Intelligence | Operational-profile segmentation + per-profile leakage-safe baselines | Done (Iteration A) | The `is_train` leakage contract every downstream fit consumes |
| Correlation Intelligence | Per-profile Pearson/Spearman references + shift *diagnostics* | Done (B) | Relationship references; AWARE-only shift findings |
| PCA Intelligence | Per-profile RobustScaler+PCA, T²/Q scores + contributions | Done (B) | Multivariate structure; feeds anomaly |
| Anomaly Intelligence | 4 explainable detectors + combined severity (normal/warning/anomaly) | Done (v1) | The original, immutable per-row scores |
| Sensor Health Intelligence | 9 instrumentation rule families; quarantine *recommendations* | Done (v1) | Separates instrumentation faults from process anomalies |
| BOM Context | Normalized recipe/order context joined to the master timeline | Done (v1) | Operational context; analytical only |
| Operational Context | Master-aligned profile+steam+sensor-health+BOM overlay timeline | Done (v1, core) | Context for review; forensic addendum deferred for `remat` |
| Drift Intelligence | Windowed drift vs train reference; raw vs healthy-only views | Done (v1) | Quantifies behavioural shift; honest `healthy_only_proxy` |
| Incident Aggregation | Events → reviewable incidents; associative relationships | Done (v1) | The prioritized review pack |
| Reference Governance | Tracks reference + quarantine/candidate proposals (all `pending_review`) | Done (v1) | Proposes, never approves |
| Controlled Scoring Experiment | Interpretive scenarios over persisted scores (no refit/rescore) | Done (v1) | Decision-support backlog reduction view |
| Dashboard Data Contract | Allowed/forbidden artifacts, required warnings, boundaries | Done | Defines safe consumption |
| Dashboard Lineage Validator | `validate_dashboard_chain` — read-only, fail-closed | Done | Guards run/lineage integrity |
| Human Decision Review | Prose record of the reviewer's decision | Done (2026-06-17) | Human-in-the-loop evidence |
| Human Decision Overlay | Structured, run-versioned dashboard input for the decision | Done (2026-06-17) | Machine-readable human decision state |

---

## C. Canonical Real-Data Chain

**Run id `remat-v1-20260616T102558Z`** — the current stable real-data technical base.

| Aspect | Value |
|---|---|
| Component order | behaviour → correlation → pca → anomaly → sensor-health → operational-context → drift → incidents → reference → scoring-experiment |
| BOM | `20260612T124909Z` **reused** (not regenerated; sha + row count + completion verified) |
| Master dataset | 167,331 rows, sha `5020956f…` (byte-identical before & after) |
| Train window | 117,132 rows (70%); 7 profiles; 116 baselines |
| Completion validation | All 10 manifests parse, `completion_status=complete`, `run_id == dir`, `component` matches |
| Lineage consistency | Every recorded upstream `*_run_id` == the new run; BOM == reused run; strict transitive sweep PASS |
| Manifest-last contract | Each run writes artifacts first, manifest last (presence = completion marker) |
| Original score immutability | `original_severity`/`original_combined_score` preserved for all 33,186 non-normal rows; adjustments live only in separate `adjusted_review_*` columns; no recompute, no refit |

This run is the base for the **read-only technical dashboard**, the **demo narrative**, and **future product validation**.

**Remaining warning (non-blocking):** some leaf manifests (correlation/pca/anomaly/sensor-health) predate the explicit `behaviour_run_id` provenance fields, so `validate_dashboard_chain` returns `is_valid=True, canonical_match=True, severity="warning"` for the chain. A legacy fixed-path behaviour artifact on disk is also warned. **Neither blocks the technical dashboard**; both are slated for the next rematerialization.

---

## D. Human Decision and Overlay State

### D.1 `inlet_hopper_points`

| Field | Value |
|---|---|
| Manual observation | Channel stops providing valid data; flatline-to-zero pattern |
| Human-reported row | 137237 (manual inspection) |
| Data-confirmed boundary row | 137235 (verified against the master) |
| System-detected onset timestamp | 2024-09-17 16:23:22 |
| Decision | Approve scoped quarantine treatment from the data-confirmed onset |
| Scope | Technical review + downstream interpretation only |
| artifact_state | `approval_required=True, approved=False` (unchanged) |
| human_review_state | `approved_scoped_quarantine` (from row 137235) |
| applied_pipeline_state | `not_applied` |
| dashboard_overlay_state | `active` |
| Limitations | Root cause not proven; no production exclusion; plant records still required |

> **Human review approves scoped quarantine treatment of `inlet_hopper_points` from the data-confirmed onset boundary, row 137235, while preserving the original human-reported row 137237 as manual-inspection evidence.**

Clarifications:

- This is a **human decision overlay**.
- Existing **canonical artifacts were not regenerated or mutated**.
- The decision is approved for **technical review and downstream interpretation only**.
- **No automatic production exclusion** is approved.
- The **physical root cause is not proven**.

The boundary realigned from the human-reported row 137237 to the data-confirmed flatline onset at row 137235 (a ~2-row / ~2-minute offset, plausibly a raw-CSV-vs-master row-basis difference). The offset is documented and should be **reconciled with plant/sensor records** before operational or customer-facing claims.

### D.2 Human decision overlay

| Field | Value |
|---|---|
| run_id | `human-decision-v1-20260617T122735Z` |
| location | `data/intelligence/forensics/human_decisions/human-decision-v1-20260617T122735Z/` |
| component | `human_decision_overlay` |
| completion_status | `complete` |
| dashboard_overlay_state | `active` |
| applied_pipeline_state | `not_applied` |

Structured outputs: `sensor_quarantine_decisions.parquet`, `dashboard_decision_overlay.parquet`, `human_adjusted_review_summary.parquet`, `required_followup_records.parquet`, `human_decision_summary.md`, `human_decision_manifest.json`.

**Why it matters:** the dashboard can consume the human decision from **structured artifacts** instead of parsing free-text markdown — with the four states explicit and forbidden actions enumerated.

> The human decision overlay is a structured, run-versioned, read-only dashboard input. It does not mutate canonical artifacts, does not change original anomaly scores, does not apply pipeline quarantine, does not create Reference v2, and does not refit models.

### D.3 Reference v2

- **Decision:** defer Reference v2.
- **Reason:** residual healthy-only drift does not justify a new reference (`residual_material=False`).
- **No refit approved; no new baseline approved.**
- **Reconsider only after** a controlled post-quarantine analysis **and** plant/sensor-record review.

---

## E. Reliable Outputs

Safe to use as technical-validation / demo evidence (all from the canonical chain or the human decision artifacts):

| Output | Classification | Why |
|---|---|---|
| Canonical manifests (10) | Stable | Completion-validated, lineage-coherent |
| Behaviour profiles + baselines | Stable | Leakage-safe, train-window only |
| Correlation outputs | Stable | Diagnostic references (no alerts) |
| PCA outputs (loadings, T²/Q) | Stable | Fitted leakage-safe |
| Original anomaly scores | Stable | Immutable; the authoritative severity |
| Sensor-health events | Stable | Rule-based, train-referenced |
| Operational context timeline (core) | Stable | Master-aligned (Gate A) |
| BOM context (core) | Stable | Read-only joins, overlaps preserved |
| Drift outputs | Stable | Windowed, train-referenced |
| Incident review pack | Stable | Prioritized, deduplicated |
| Reference governance outputs | Stable | Proposals `pending_review` |
| Controlled scoring interpretive outputs | Stable (as interpretive) | `original_*` preserved; adjustments separate |
| Reference decision report | Stable | Decision-support synthesis |
| Human decision review | Stable | Human-in-the-loop record |
| Human decision overlay | Stable | Structured, run-versioned, read-only |
| Dashboard data contract + lineage validator | Stable | Defines + guards safe consumption |

---

## F. Interpretive / Experimental Outputs

Useful, but must always carry a warning and never be shown as applied state or causal fact:

| Output | What it means | How it can be used | Required warning |
|---|---|---|---|
| Controlled scoring adjusted-review fields | Backlog after quarantine-aware suppression (30,096 / 90.69% of 33,186; remaining 1,203 anomaly + 1,887 warning = 3,090) | Show review-backlog reduction | Interpretive post-processing, **not** true model rescoring |
| Healthy-only residual drift | 23 windows (0.2%); raw drift 209.6 → 90.5 (57%) | Show residual after instrumentation effect | A **proxy** view, honestly labeled |
| Incident relationships | Temporal/shared-sensor associations | Navigate related incidents | **Associative, not causal** (`causality_status=unknown`) |
| Quarantine proposals | Recommended, pending review | Show the review queue | `approval_required=True, approved=False` |
| Human decision overlay | The reviewer's scoped approval | Show as a decision overlay | **Not the same as applied pipeline state** |
| Decision matrix / candidate actions | Ordered decision-support actions | Guide review | Decision-support only; nothing applied |
| Required plant records | External evidence still needed | Show prerequisites | Records **still required** before operational claims |
| Raw-vs-adjusted review severity | Original vs interpretive view | Side-by-side comparison | Original scores unchanged; adjusted is interpretive |

Key distinctions to preserve verbatim:

- Controlled scoring is interpretive post-processing, not true model rescoring.
- Healthy-only is a proxy view.
- Incident relationships are associative, not causal.
- Human decision overlay is not the same as applied pipeline state.
- Quarantine treatment is human-approved only within a scoped technical-review boundary.
- Plant records are still required before operational/customer-facing claims.

---

## G. Outputs Not Ready to Show or Claim

| Excluded | Why |
|---|---|
| Reference v2 | Deferred; `residual_material=False`; no approved baseline exists |
| Approved/applied pipeline quarantine | Human approval is documentation-level; quarantine **not applied** to the pipeline; canonical artifacts unchanged |
| True rescoring / refit | Not approved; gated on quarantine approval + plant records |
| Automatic sensor exclusion | No auto-exclusion is performed or approved |
| Operational/BOM forensic-addendum views (for `remat`) | Not regenerated against the canonical chain (base forensic run is non-compliant) |
| Old non-canonical runs | Outside the pinned canonical chain; only `is_valid and canonical_match` is authoritative |
| Legacy fixed-path Behaviour artifacts | Inert pre-hardening files outside `runs/`; validator warns |
| Causal explanations | Relationships are associative only |
| Plant-record conclusions | External records not yet ingested or verified |
| Production alerts / real-time streaming | Not built; out of Phase 1 scope |
| Automatic predictive-maintenance claims | The system does not autonomously predict or prevent failures |

> The human review approves scoped quarantine treatment and the overlay makes it dashboard-consumable, but the quarantine has **not** been applied as a pipeline state and canonical artifacts have **not** been regenerated.

---

## H. Product Implications

- The project has moved **from model experimentation to a traceable industrial intelligence layer** over real data.
- The strongest near-term product value is **not automatic prediction**, but **explainable process visibility and incident review**.
- The human decision overlay **confirms the value of a human-in-the-loop workflow**: the system surfaces and structures evidence; a human decides.
- The first product surface should be a **technical validation dashboard, not a polished commercial dashboard**.
- The narrative should focus on **observability, anomaly interpretation, sensor health, drift, operational context, decision support, and human-reviewed evidence**.

Explicitly:

- **Do not** sell this yet as fully autonomous predictive maintenance.
- Position it as a **pilot-ready technical intelligence layer for reviewing industrial process behaviour over historical data**.

---

## I. Dashboard Implications (Phase 2 enabler)

The canonical chain + overlay enable a **read-only Technical Validation Dashboard MVP**:

- Canonical run **pinned** (`remat-v1-20260616T102558Z` / BOM `20260612T124909Z`).
- Human decision overlay run **available** (`human-decision-v1-20260617T122735Z`).
- **Lineage validation required** (`validate_dashboard_chain`); no stale runs valid without warnings.
- **No** write / approval / apply-quarantine / refit / Reference v2 controls.

Recommended first dashboard sections:

1. Run & Lineage Summary
2. System Overview
3. Incident Review Pack
4. Sensor Health
5. Human Decision Overlay
6. Raw vs Adjusted Review Severity
7. Drift Residual Summary
8. Decision Report Summary

The dashboard is **internal / technical first**. For the human decision overlay specifically:

> The dashboard should distinguish artifact state, human review state, applied pipeline state, and dashboard overlay state.

---

## J. Commercial / Demo Implications

A future demo can show:

- Real-data analysis (not synthetic).
- Incident review and the evidence chain.
- A sensor-health issue and the resulting review-backlog reduction.
- Human-in-the-loop decision support.
- Operational intelligence, **not** automatic action.
- A demo script that **includes limitations and warnings**.

The pelletizer dataset is a **technical proof base, not necessarily the final ICP machine**. This supports the pivot toward:

- an **Industrial Intelligence Layer for plastic transformation plants**;
- a **critical cell / production-zone entry point**;
- a **historical-data pilot before real-time integration**.

Avoid claiming: that the system autonomously diagnosed and fixed a sensor; that it prevents failures automatically; that it is ready for production deployment.

---

## K. Remaining Risks and Constraints

### Must respect in the dashboard phase
- Read-only only.
- Canonical chain only.
- Warnings mandatory.
- artifact / human-review / applied-pipeline / dashboard-overlay states must be separated.
- No approval / refit / quarantine actions.
- No causal claims.

### Should address soon
- Reconcile row 137235 / 137237 / timestamp 2024-09-17 16:23:22 with plant records.
- Refresh canonical manifests in the next rematerialization with explicit `behaviour_run_id`.
- Regenerate operational/BOM forensic addenda only after a compliant forensic run exists.
- Remove/archive the legacy fixed-path Behaviour artifact when convenient.
- Create dashboard MVP tests.

### Can defer
- Reference v2.
- Plant-record ingestion.
- True rescore / refit.
- Production deployment.
- Streaming.
- Customer-facing polished UI.

---

## L. Phase 1 Exit Criteria

| Original Phase 1 task | Status | Note |
|---|---|---|
| Terminar la segunda review de Codex y resolver issues críticos | **Done** | Codex findings resolved across the hardening + pre-dashboard cleanup sprints (8 hardening findings + DASH/LINEAGE/PROV/CTX/DOC items) |
| Cerrar el Controlled Rematerialization Sprint bajo el hardened Lineage Contract | **Done** | 10-component chain under run `remat-v1-20260616T102558Z`; strict lineage sweep PASS |
| Congelar la versión demostrable de la cadena real-data | **Done with caveat** | Pinned + immutable + validated; caveat = `behaviour_run_id` provenance warning + forensic addenda not regenerated (non-blocking) |
| Documentar qué outputs son fiables, experimentales y no mostrables | **Done** | Sections E / F / G of this report + the dashboard data contract |
| Crear documento Post-Iteration-C Technical State & Product Implications | **Done** | This document |

**Result: Fase 1 — Cierre técnico: complete.**

---

## M. Recommended Next Step

Implement the read-only Technical Validation Dashboard MVP over the canonical rematerialized run.
