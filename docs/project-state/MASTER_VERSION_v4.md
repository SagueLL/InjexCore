# InjexCore — MASTER_VERSION_v4

## 1. Version Metadata

| Field | Value |
|---|---|
| Version | `v4.0.0` |
| Date | `2026-06-28` |
| Scope label | Iteration C close-out (Human Decision Overlay → 10-component stack) + **Dashboard v0 frontend started** (`apps/dashboard/`) |
| Snapshot author | `master-version-agent` |
| Previous snapshot | [MASTER_VERSION_v3.md](MASTER_VERSION_v3.md) — Intelligence Iterations B+C + context layers + read-only dashboard contract + hardening (`2026-06-16`) |
| Baseline status | This document diffs against v3; the next `MASTER_VERSION_v5` diffs against this one. v1–v3 remain immutable. |
| Branch | `feature/dashboard-v0-ui` (was `refactor/v1-architecture-stabilization` at v3) |
| Source-of-truth documents (not replaced) | [CLAUDE.md](../../CLAUDE.md), [docs/README.md](../README.md), [docs/architecture/intelligence_dataflow.md](../architecture/intelligence_dataflow.md), [docs/dashboard/dashboard_data_contract.md](../dashboard/dashboard_data_contract.md), [docs/architecture/InjexCore_Technical_Stack_Dashboard_v0.md](../architecture/InjexCore_Technical_Stack_Dashboard_v0.md) |

This snapshot consolidates — it does not rewrite. Where this document makes a claim, the
underlying reference doc remains authoritative. v1–v3 remain immutable records and are not
edited.

---

## 2. Executive Summary

- **The backend phase is sealed and the frontend phase began.** v3 ended with the
  intelligence stack complete and a read-only dashboard *contract* but no UI. v4 closes
  Iteration C with a tenth component and opens the **Dashboard v0** frontend — the first
  code to live outside `src/`.
- **Intelligence Layer went 9 → 10 components.** The new `human-decision` overlay
  (`src/intelligence/human_decisions/`) records the reviewer's scoped
  `inlet_hopper_points` quarantine approval + the Reference-v2 deferral as a run-versioned,
  read-only **decision-support artifact**. It mutates nothing, approves no quarantine in
  the pipeline, and refits/rescores nothing — decision *metadata*, not a pipeline action.
- **Dashboard v0 is a real Next.js app.** `apps/dashboard/` — Next.js 16 (App Router,
  Turbopack), React 19, Tailwind v4, shadcn/ui, Recharts (installed). The app shell + all
  five planned routes are scaffolded; the **Executive Overview** view is fully built on
  static demo data. The other four routes are honest placeholders.
- **Still read-only and honest about scope.** The dashboard runs on static demo data — no
  backend wiring, no Parquet reads from the frontend yet. The planned path
  (intelligence outputs → dashboard-ready JSON → Next.js) is not built. The descriptive /
  interpretive / human-gated boundaries from v3 are untouched: no model was refit, no
  sensor excluded, no score mutated.
- **Quality gates green on both sides.** Python: **590 tests** (up from 575; +15 for the
  human-decision overlay). Frontend: `eslint`, `tsc --noEmit`, and `next build` all clean
  (9/9 static pages).
- **The next immediate step is the Operational Timeline view** (`/timeline`) — the second
  structural dashboard view, over the pinned canonical chain.

---

## 3. What Changed Since v3 (v3 → v4 diff)

v3's scope was "Intelligence Iterations B+C + context + dashboard contract + hardening."
v4 keeps all of it intact and adds one intelligence component and the frontend.

| Area | v3 (baseline) | v4 (now) |
|---|---|---|
| Intelligence components | 9 | **10** (+ `human-decision`) |
| Dispatcher | `--component …\|scoring-experiment` | `…\|scoring-experiment\|human-decision` |
| Dashboard | read-only contract only (`src/dashboard/`), UI not started | contract **+ a started Next.js UI** in `apps/dashboard/` (Dashboard v0) |
| Repository shape | everything under `src/` | **first non-`src/` workspace** — `apps/dashboard/` (no root `package.json`; standalone) |
| Frontend stack | none | Next.js 16.2.9 (Turbopack) · React 19.2.4 · Tailwind v4 · shadcn/ui · Recharts 3.9 (installed) · date-fns · react-day-picker · hugeicons |
| Dashboard views | none | `/overview` **built** (demo data); `/timeline`, `/sensor-health`, `/drift-anomaly`, `/incidents` scaffolded as placeholders |
| Coding rules | global standards | + expanded `.claude/rules/code-style.md` + `.claude/rules/frontend/react.md` (Dashboard v0 scope, `src/` layout contract, industrial-UX language) |
| Tests | 575 | **590** (+15: human-decision overlay + dispatcher param) |
| Configs | 16 entries | 16 (unchanged — `human-decision` uses seeded constants, no YAML policy) |
| Decision record | Iteration C decision *report* produced | reviewer decision *captured* — prose review + the `human-decision` overlay artifact |

What did **not** change: the four preprocessing stages, the 9 prior intelligence
components, the two context layers, the dashboard contract pins
(`remat-v1-20260616T102558Z` / BOM `20260612T124909Z`), the descriptive-vs-predictive
boundary, and the rule that `src/models/` stays reserved. v4 is additive on top of v3.

---

## 4. Architecture State

The backend pipeline is unchanged from v3. v4 appends a read-only decision overlay at the
tail of the intelligence chain and a separate frontend workspace that *consumes* (will
consume) the pinned chain through the dashboard contract.

```
src/data_generation/generate.py
  → src/preprocessing/{cleaning → time_series → feature_engineering → datasets}   (master + specialized parquet)
    → src/intelligence/behaviour → {correlation, pca} → anomaly → drift → incidents → reference → scoring_experiment
        → src/intelligence/human_decisions/      ── read-only decision overlay (forensics/human_decisions/<run_id>/)
  src/intelligence/sensor_health/   ── instrumentation vs process anomalies
  src/context/{bom, operational}/   ── read-only joins against master + anomaly scores
  src/dashboard/                    ── read-only consumption contract + lineage validator (pins the canonical chain)
            → apps/dashboard/       ── Dashboard v0 UI (Next.js); demo data now, dashboard-ready JSON later
            → [src/models/ pending: PREDICTIVE scorers]
```

### 4.1 The layer boundary (extended in v4)

| Layer | Package | Responsibility | Fits / mutates? |
|---|---|---|---|
| Preprocessing | `src/preprocessing/` | Cleans + engineers features | No — parameter-free |
| Intelligence | `src/intelligence/` | Characterises *normal* (descriptive) + interprets persisted scores + **records human decisions** | DESCRIPTIVE fits + decision *metadata* only; **never** refits, rescores, approves a quarantine, or excludes a sensor |
| Context | `src/context/` | External sources → master-aligned contextual datasets | No fitting — read-only joins |
| Dashboard contract | `src/dashboard/` | Read-only consumption contract + lineage validation | No mutation — fails closed on bad provenance |
| **Dashboard UI** | `apps/dashboard/` | Presents the pinned chain to humans | **No mutation — read-only presentation; demo data for now** |
| Models (planned) | `src/models/` | Scores deviation from normal | Yes — PREDICTIVE estimators |

### 4.2 The Human Decision Overlay (new in v4)

`src/intelligence/human_decisions/` encodes the reviewer's decision as a run-versioned,
read-only artifact under the flat `data/intelligence/forensics/human_decisions/<run_id>/`
layout (run id `human-decision-v1-<UTC>`; manifest written last). It deliberately keeps
four states distinct — `artifact_state`, `human_review_state`, `applied_pipeline_state`,
`dashboard_overlay_state` — so "the human approved a scoped quarantine" never silently
becomes "the pipeline applied it." Authoritative boundary `scope_start_row=137235`
(`2024-09-17 16:23:22`, the data-confirmed flatline onset), with `human_reported_row=137237`
preserved for traceability. Forbidden dashboard actions: approve / apply / refit /
create-v2 / mutate-scores / alert. Run via `--component human-decision`.

### 4.3 Dashboard v0 frontend (new in v4)

First code outside `src/`, in `apps/dashboard/` (standalone; no root `package.json` yet):

- **Routing** — Next.js App Router under `src/app/`; five planned routes scaffolded
  (`/overview`, `/timeline`, `/sensor-health`, `/drift-anomaly`, `/incidents`). Route pages
  stay thin (compose components). `/incidents/[incidentId]` deliberately not created.
- **Components** — `src/components/app/` (app-shell, sidebar-nav, page-header),
  `src/components/dashboard/` (kpi-card, status-badge, section-card, insight-card,
  empty-state), `src/components/ui/` (shadcn/ui primitives).
- **Data** — `src/types/dashboard.ts` + static `src/lib/dashboard/{demo-overview,navigation}.ts`.
  Demo-data-driven; no backend integration, no Parquet reads. Charts (Recharts) not yet
  used — reserved for dedicated `"use client"` chart components per the frontend rules.
- **Industrial-UX constraint** — honest operational language ("Operational status",
  "Sensor health", "Drift detected"); no "guaranteed failure prediction." The Executive
  Overview ships an explicit *Limitations* section.

---

## 5. Data Flow

The preprocessing + intelligence + context data flow is unchanged from v3 (master
`167,331 × 566`; all of `data/` git-ignored). v4 adds one artifact family and one
consumer.

| Artefact | Path | Form |
|---|---|---|
| *(v3 families — unchanged)* | `data/{datasets,intelligence,context}/…` | see [MASTER_VERSION_v3.md](MASTER_VERSION_v3.md#5-data-flow) |
| **Human decision overlay** | `data/intelligence/forensics/human_decisions/<run_id>/` | decision-support records + manifest (read-only; mutates no upstream artifact) |
| **Dashboard v0 (demo)** | `apps/dashboard/src/lib/dashboard/demo-overview.ts` | static TypeScript demo payload (placeholder for the future dashboard-ready JSON export) |

The canonical pinned chain for the dashboard remains `remat-v1-20260616T102558Z`
(BOM `20260612T124909Z`). The frontend does **not** yet read it — wiring the intelligence
outputs → dashboard-ready JSON → Next.js is the open data-flow gap.

---

## 6. Active Systems

- **Preprocessing layer** (`src/preprocessing/`) — unchanged (4 stages + `_common/` + `--stage` dispatcher).
- **Intelligence Layer** (`src/intelligence/`) — **10 components** + shared utilities:
  - the 9 from v3 ([behaviour](../../src/intelligence/behaviour/), [correlation](../../src/intelligence/correlation/), [pca](../../src/intelligence/pca/), [anomaly](../../src/intelligence/anomaly/), [sensor_health](../../src/intelligence/sensor_health/), [drift](../../src/intelligence/drift/), [incidents](../../src/intelligence/incidents/), [reference](../../src/intelligence/reference/), [scoring_experiment](../../src/intelligence/scoring_experiment/)),
  - **NEW** [human_decisions/](../../src/intelligence/human_decisions/) — the decision overlay,
  - [_common/](../../src/intelligence/_common/) + [__main__.py](../../src/intelligence/__main__.py) (10-component `--component` dispatcher, defaults to `behaviour`).
- **External Context Layer** (`src/context/{bom,operational}`) — unchanged from v3.
- **Dashboard contract** (`src/dashboard/`) — unchanged from v3 (read-only contract + fail-closed lineage validator).
- **Dashboard v0 UI** (`apps/dashboard/`) — **NEW in v4**: Next.js 16 / React 19 / Tailwind v4 / shadcn/ui app; app shell + 5 routes scaffolded; Executive Overview built on demo data.
- **Configuration** — 16 entries unchanged (the human-decision overlay uses seeded constants in `decision.py`, not a YAML policy).
- **Test suite** — **590 tests** under `tests/unit/{preprocessing,intelligence,context,dashboard}/` (intelligence now includes `human_decisions/`) + `tests/integration/`. ~55 s.
- **Coding rules** — expanded `.claude/rules/code-style.md` + `.claude/rules/frontend/react.md` (Dashboard v0 scope, `src/` layout contract, App Router rules, industrial-UX language).
- **Reference docs** — 4 pipeline + 9 intelligence + 2 context + dashboard contract + dataflow + the Dashboard v0 stack note. (Doc gap: the `human-decision` overlay has no dedicated `docs/intelligence/` reference yet — see §10.)
- **Still placeholders / not yet implemented**: `src/models/` (predictive scorers); the four non-overview dashboard views; the dashboard-ready JSON export; `src/visualization/` (Python-side plots); output API.

---

## 7. Agent & Skill Ecosystem

Per [CLAUDE.md](../../CLAUDE.md), the ecosystem is **20 agents** and **60 skills**,
auto-discovered via YAML frontmatter (the dashboard agents/skills documented in v3's count
of 18/52 are now reflected as 20/60 in CLAUDE.md). Agents that shaped v4:

- `dashboard-data-contract-agent`, `dashboard-ui-agent` — the Dashboard v0 view composition, component selection, and the read-only / demo-data boundary.
- `master-version-agent` *(Opus)*, `day-closing-agent` — this snapshot and the 2026-06-28 session note.
- `repository-architecture-agent` — the `apps/` workspace split (first code outside `src/`).

The dashboard skill family (8 skills: `define-dashboard-data-contract`,
`map-intelligence-outputs-to-ui`, `validate-dashboard-payloads`,
`generate-dashboard-fixtures`, `design-dashboard-layout`, `select-dashboard-components`,
`generate-dashboard-view`, `review-dashboard-usability`) is the substrate for the
remaining Dashboard v0 views.

---

## 8. Technical Decisions

v1–v3 decisions still hold. New non-obvious calls that define v4:

1. **Human decisions are recorded, not applied.** The reviewer's scoped quarantine
   approval is captured as overlay *metadata* with four distinct states; the pipeline
   itself is unchanged (no sensor excluded, no model refit, no score mutated). "Approved by
   a human" and "applied to the pipeline" are kept separable on purpose.
2. **The dashboard lives in `apps/`, not `src/visualization/`.** The Next.js UI is a
   separate frontend workspace (first code outside `src/`), distinct from the planned
   Python-side `src/visualization/`. No root `package.json` yet — the app stands alone
   until a monorepo tool is justified.
3. **Demo data before integration.** Dashboard v0 ships on static TypeScript demo payloads
   so the layout/UX can be validated before the dashboard-ready JSON contract is wired.
   The frontend never reads Parquet directly — the boundary is intentional.
4. **Honest UI language is a rule, not a style.** The frontend rules forbid
   failure-prediction claims and mandate operational language + explicit limitations
   sections — the same honesty constraint the intelligence layer enforces on its scores.

---

## 9. Roadmap Progress

| Milestone | Status as of v4 |
|---|---|
| Preprocessing layer — 4 stages | Done (v1) |
| Intelligence Layer — Iterations A/B/C (9 components) | Done (v2/v3) |
| External Context Layer (`src/context/{bom,operational}`) | Done (v3) |
| Read-only Dashboard contract + lineage validator (`src/dashboard/`) | Done (v3) |
| **Iteration C close-out — Human Decision Overlay (`src/intelligence/human_decisions/`)** | **Done (v4)** |
| **Dashboard v0 — app shell + 5 routes scaffolded + Executive Overview view** | **Done (v4)** |
| **Dashboard v0 — Operational Timeline view (`/timeline`)** | **In progress — the immediate next step** |
| Dashboard v0 — `/sensor-health`, `/drift-anomaly`, `/incidents` views | Not started — placeholders scaffolded |
| Dashboard-ready JSON export (intelligence → JSON → Next.js) | Not started — replaces the static demo data |
| *Approved* Reference v2 refit + true PCA/Mahalanobis rescoring | Not started — deferred, gated on plant records |
| Predictive `src/models/` layer (Isolation Forest, LOF, Mahalanobis) | Not started |
| Output API (FastAPI) | Not started |

### 9.1 Immediate next chapter — the Operational Timeline view

The Dashboard v0 foundation (shell + Executive Overview) is solid and demo-ready. The next
structural view is **Operational Timeline** (`/timeline`) — machine operational states and
events over time. Build notes:

- Source it from the pinned canonical chain via the dashboard contract once the
  dashboard-ready JSON export exists; until then, extend the demo-data pattern
  (`src/lib/dashboard/`) used by Executive Overview.
- Charts go in dedicated `"use client"` components (`src/components/`), never in the route
  page; Recharts is installed and ready.
- Keep the industrial-UX language: operational status, profile transitions, anomaly/drift
  windows — the `inlet_hopper_points` story is the highest-signal narrative to carry
  through `/timeline` → `/sensor-health` → `/incidents`.

### 9.2 After Timeline

Fill the remaining three views, then wire the dashboard-ready JSON export to replace demo
data. The predictive `src/models/` layer and an *approved* Reference v2 remain deferred and
gated as in v3.

---

## 10. Risks & Open Questions

- **The dashboard shows demo data, not real intelligence outputs.** Until the
  dashboard-ready JSON export is wired, `/overview` (and any new view) reflects placeholder
  numbers, not the pinned canonical chain. Risk: demo figures being mistaken for analysed
  results — mitigated by the explicit Limitations section, but the wiring is the priority.
- **Human decisions are encoded but not applied.** The scoped `inlet_hopper_points`
  quarantine remains `approved` only in the overlay's `human_review_state`; the pipeline's
  `applied_pipeline_state` is unchanged. No sensor is excluded and no model refit — by
  design, pending plant-record confirmation.
- **Doc gap.** The `human-decision` overlay has no dedicated `docs/intelligence/` reference
  doc yet; it is described in CLAUDE.md, this snapshot, and `reports/decision_reviews/`.
- **Frontend has no tests.** Dashboard v0 relies on `eslint` / `tsc` / `next build` as
  gates; no component/unit tests exist (acceptable at v0 scope, a gap to revisit).
- **Carried from v3:** pending human decisions block promotion; real-machine anomaly
  thresholds (`.claude/CLAUDE.local.md`) still unfinalised; scores are descriptive/
  interpretive, not validated against ground truth; non-derivable regimes remain blind
  spots; single-source evidence (one vendor CSV + the BOM CSV).

---

## 11. Current Priorities & Recommended Focus

1. **Build the Operational Timeline view** (`/timeline`) — the immediate next structural
   dashboard view.
2. **Design + wire the dashboard-ready JSON export** (intelligence outputs → JSON → Next.js)
   so the dashboard reads the pinned canonical chain instead of demo data — surface the
   incidents review pack + scoring scenarios first.
3. **Fill the remaining Dashboard v0 views** — `/sensor-health`, `/drift-anomaly`, `/incidents`.
4. **Human review of the Iteration C decision report** — resolve the `inlet_hopper_points`
   quarantine + the deferred Reference v2 candidate (gates any refit/rescore).
5. **Then** begin the predictive `src/models/` layer and finalise real-machine anomaly
   thresholds.

---

## 12. Confidence Level

- **High confidence**: the 10-component intelligence stack + dispatcher set, the
  human-decision overlay's read-only / non-mutating contract, the `apps/dashboard/` Next.js
  stack + route scaffold + built Executive Overview, the green frontend gates
  (`eslint` / `tsc` / `next build`, 9/9 static pages), and the **590-test** count — all
  verified against `src/`, `apps/`, `tests/`, and git history in this pass.
- **Medium confidence**: master/specialized dataset shapes (carried from v1/v2, not
  re-counted); the 20-agent / 60-skill ecosystem counts (sourced from CLAUDE.md).
- **Lower confidence / explicit uncertainty**: real-machine anomaly thresholds (private);
  external correctness of derived profiles/scores (no ground-truth labels); the outcome of
  the pending quarantine / Reference v2 decisions (gated on plant records); the
  dashboard-ready JSON export schema and the remaining view designs (not yet produced).

---

## 13. References

- Project guidance: [CLAUDE.md](../../CLAUDE.md)
- Documentation index: [docs/README.md](../README.md)
- Architecture + contracts: [docs/architecture/intelligence_dataflow.md](../architecture/intelligence_dataflow.md)
- Dashboard contract: [docs/dashboard/dashboard_data_contract.md](../dashboard/dashboard_data_contract.md)
- Dashboard v0 stack: [docs/architecture/InjexCore_Technical_Stack_Dashboard_v0.md](../architecture/InjexCore_Technical_Stack_Dashboard_v0.md)
- Decision review: [reports/decision_reviews/iteration_c_part3_human_decision_review.md](../../reports/decision_reviews/iteration_c_part3_human_decision_review.md)
- Session notes: [day_close_2026-06-28.md](../sessions/day_close_2026-06-28.md), [day_close_2026-06-16.md](../sessions/day_close_2026-06-16.md)
- Previous snapshots: [MASTER_VERSION_v3.md](MASTER_VERSION_v3.md), [MASTER_VERSION_v2.md](MASTER_VERSION_v2.md), [MASTER_VERSION_v1.md](MASTER_VERSION_v1.md)
- Global standards (apply automatically): `~/.claude/CLAUDE.md`, `~/.claude/rules/python.md`, `~/.claude/rules/ml-pipeline.md`, `~/.claude/rules/git.md`

---

*End of MASTER_VERSION_v4. Next snapshot: `MASTER_VERSION_v5` — cut when Dashboard v0 is
feature-complete (all five views over the dashboard-ready JSON export), or when the first
fitted predictive model lands in `src/models/`.*
