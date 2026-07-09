# InjexCore — MASTER_VERSION_v5

## 1. Version Metadata

| Field | Value |
|---|---|
| Version | `v5.0.0` |
| Date | `2026-07-02` |
| Scope label | **Dashboard v0.1 feature-complete** — all five views built (Recharts + InjexCore theme), still on static demo data |
| Snapshot author | `master-version-agent` |
| Previous snapshot | [MASTER_VERSION_v4.md](MASTER_VERSION_v4.md) — Iteration C close-out (Human Decision Overlay → 10-component stack) + Dashboard v0 frontend started (`2026-06-28`) |
| Baseline status | This document diffs against v4; the next `MASTER_VERSION_v6` diffs against this one. v1–v4 remain immutable. |
| Branch | `feature/dashboard-v0.1-ui` (was `feature/dashboard-v0-ui` at v4) |
| Source-of-truth documents (not replaced) | [CLAUDE.md](../../CLAUDE.md), [docs/README.md](../README.md), [docs/architecture/intelligence_dataflow.md](../architecture/intelligence_dataflow.md), [docs/dashboard/dashboard_data_contract.md](../dashboard/dashboard_data_contract.md), [docs/architecture/InjexCore_Technical_Stack_Dashboard_v0.md](../architecture/InjexCore_Technical_Stack_Dashboard_v0.md) |

This snapshot consolidates — it does not rewrite. Where this document makes a claim, the
underlying reference doc remains authoritative. v1–v4 remain immutable records and are not
edited.

---

## 2. Executive Summary

- **Dashboard v0.1 is feature-complete.** v4 opened the frontend with only the Executive
  Overview built and four placeholder routes. v5 closes the frontend build-out: the **four
  remaining views** — Operational Timeline, Sensor Health, Drift & Anomaly, Incidents — are
  now fully built, each with a dedicated Recharts chart, and the whole UI got a polish pass.
- **A real chart layer landed.** Recharts went from *installed-but-unused* (v4) to **five
  chart components** in `apps/dashboard/src/components/charts/` (`operational-timeline-chart`,
  `sensor-health-distribution-chart`, `anomaly-evidence-chart`, `incidents-severity-chart`, and
  the shared `chart-container`), all `"use client"` and fed by props — never in a route page.
- **A visual identity landed too.** InjexCore **theme tokens** (`globals.css`, `e97d8b2`)
  replaced ad-hoc styling, followed by a full polish pass across every shared component
  (kpi-card, status-badge, section-card, insight-card, chart-container, app-shell/sidebar/
  page-header) and all four charts.
- **Still demo data, still honest.** All five views run on static per-view TypeScript payloads
  (`src/lib/dashboard/demo-*.ts`). The frontend does **not** read the pinned canonical chain —
  no backend wiring, no Parquet reads, no API. The UI is *structurally* complete; the *data* is
  still a placeholder. This is stated plainly here and on the Overview's Limitations section.
- **The backend was not touched.** `src/` is byte-for-byte the v4 stack: 10 intelligence
  components, two context layers, the read-only dashboard contract, the pinned chain
  (`remat-v1-20260616T102558Z` / BOM `20260612T124909Z`), and **590 Python tests** (not re-run
  — no Python changed). No model refit, no sensor excluded, no score mutated.
- **The next chapter is the real data connection via a backend API.** The open gap is the
  dashboard-ready JSON export (intelligence outputs → JSON → Next.js) that replaces the demo
  payloads. That — not another view — is the immediate next step.

---

## 3. What Changed Since v4 (v4 → v5 diff)

v4's scope was "Iteration C close-out (10th component) + Dashboard v0 started (Overview only)."
v5 keeps all of it intact and completes the Dashboard v0.1 frontend.

| Area | v4 (baseline) | v5 (now) |
|---|---|---|
| Dashboard views built | `/overview` only; 4 placeholders | **all 5 built** — `/overview`, `/timeline`, `/sensor-health`, `/drift-anomaly`, `/incidents` |
| Charts | Recharts installed, not used | **5 chart components** in `src/components/charts/` (2 `ComposedChart`, 2 `Bar`, 1 container) |
| Theme | ad-hoc styling | **InjexCore theme tokens** in `globals.css` + full component polish pass |
| Demo data | 1 file (`demo-overview.ts`) | **5** (`demo-{overview,timeline,sensor-health,drift-anomaly,incidents}.ts`) |
| View types | 1 file (`types/dashboard.ts`) | **5** (`+ timeline, sensor-health, drift-anomaly, incidents`) |
| Recharts + React 19 | not exercised | `react-is` override pinned to `^19` (blank-chart gotcha resolved — see §8) |
| Commits since baseline | — | **20** (`feat(dashboard)` / `style(dashboard)`, 2026-06-29 → 2026-07-01) |
| Branch | `feature/dashboard-v0-ui` | `feature/dashboard-v0.1-ui` |
| Milestone label | "Dashboard v0" | **"Dashboard v0.1"** (UI feature-complete on demo data) |

What did **not** change: the four preprocessing stages, the 10 intelligence components, the two
context layers, the `src/dashboard/` contract + its canonical pins, the descriptive /
interpretive / human-gated boundaries, the 590-test Python suite, the 16 configs, and the rule
that `src/models/` stays reserved. v5 is **frontend-only, additive** on top of v4 — no `src/`
file changed.

---

## 4. Architecture State

The backend pipeline is unchanged from v4. v5 fills out the frontend workspace that *consumes*
(will consume) the pinned chain through the dashboard contract — still on demo data.

```
src/data_generation/generate.py
  → src/preprocessing/{cleaning → time_series → feature_engineering → datasets}   (master + specialized parquet)
    → src/intelligence/behaviour → {correlation, pca} → anomaly → drift → incidents → reference → scoring_experiment
        → src/intelligence/human_decisions/      ── read-only decision overlay (forensics/human_decisions/<run_id>/)
  src/intelligence/sensor_health/   ── instrumentation vs process anomalies
  src/context/{bom, operational}/   ── read-only joins against master + anomaly scores
  src/dashboard/                    ── read-only consumption contract + lineage validator (pins the canonical chain)
            → apps/dashboard/       ── Dashboard v0.1 UI (Next.js): all 5 views built on DEMO data; JSON export/API still to wire
            → [src/models/ pending: PREDICTIVE scorers]
```

### 4.1 The layer boundary (unchanged from v4)

| Layer | Package | Responsibility | Fits / mutates? |
|---|---|---|---|
| Preprocessing | `src/preprocessing/` | Cleans + engineers features | No — parameter-free |
| Intelligence | `src/intelligence/` | Characterises *normal* (descriptive) + interprets persisted scores + records human decisions | DESCRIPTIVE fits + decision *metadata* only; never refits, rescores, approves a quarantine, or excludes a sensor |
| Context | `src/context/` | External sources → master-aligned contextual datasets | No fitting — read-only joins |
| Dashboard contract | `src/dashboard/` | Read-only consumption contract + lineage validation | No mutation — fails closed on bad provenance |
| **Dashboard UI** | `apps/dashboard/` | Presents the (eventual) pinned chain to humans | **No mutation — read-only presentation; all 5 views on demo data for now** |
| Models (planned) | `src/models/` | Scores deviation from normal | Yes — PREDICTIVE estimators |

### 4.2 Dashboard v0.1 views (completed in v5)

All five App-Router routes under `apps/dashboard/src/app/*/page.tsx` are now real views. Route
pages stay thin (compose components + pass demo data); every chart lives in a dedicated
`"use client"` component and receives data through props:

| Route | View | Chart (`src/components/charts/`) | Demo payload |
|---|---|---|---|
| `/overview` | Executive Overview (KPIs + insights + **Limitations**) | — (KPI/insight cards) | `demo-overview.ts` |
| `/timeline` | Operational Timeline | `operational-timeline-chart` (`ComposedChart`: incident-window bars + deviation line) | `demo-timeline.ts` |
| `/sensor-health` | Sensor Health | `sensor-health-distribution-chart` (status-coloured bars) | `demo-sensor-health.ts` |
| `/drift-anomaly` | Drift & Anomaly | `anomaly-evidence-chart` (`ComposedChart`: anomaly/residual bars + score line) | `demo-drift-anomaly.ts` |
| `/incidents` | Incidents | `incidents-severity-chart` (severity bars) | `demo-incidents.ts` |

- **Shared visual layer** — `src/components/dashboard/` (kpi-card, status-badge, section-card,
  insight-card, empty-state) + `src/components/charts/chart-container` (server `Card` wrapper),
  all polished this cycle; `src/components/ui/` holds the 18 shadcn/ui primitives.
- **Theme** — InjexCore tokens in `globals.css` drive colours/spacing across every view.
- **Industrial-UX constraint held** — honest operational language ("Operational status",
  "Sensor health", "Drift detected", "Anomaly evidence"); no "guaranteed failure prediction."
  `/incidents/[incidentId]` deliberately not created (deferred until the data shape is real).

---

## 5. Data Flow

The preprocessing + intelligence + context data flow is unchanged from v4 (master
`167,331 × 566`; all of `data/` git-ignored). v5 adds four demo payloads on the frontend side
and does not add any real artifact family.

| Artefact | Path | Form |
|---|---|---|
| *(v4 families — unchanged)* | `data/{datasets,intelligence,context}/…` | see [MASTER_VERSION_v4.md](MASTER_VERSION_v4.md#5-data-flow) |
| **Dashboard v0.1 demo payloads** | `apps/dashboard/src/lib/dashboard/demo-{overview,timeline,sensor-health,drift-anomaly,incidents}.ts` | static TypeScript demo payloads (placeholder for the future dashboard-ready JSON export) |

The canonical pinned chain for the dashboard remains `remat-v1-20260616T102558Z`
(BOM `20260612T124909Z`). The frontend still does **not** read it — wiring the intelligence
outputs → dashboard-ready JSON → Next.js is the open data-flow gap, and now the single most
important next step (v4 already flagged this; with the views done it becomes the critical path).

---

## 6. Active Systems

- **Preprocessing layer** (`src/preprocessing/`) — unchanged (4 stages + `_common/` + `--stage` dispatcher).
- **Intelligence Layer** (`src/intelligence/`) — unchanged **10 components** + `_common/` + the 10-component `--component` dispatcher.
- **External Context Layer** (`src/context/{bom,operational}`) — unchanged from v4.
- **Dashboard contract** (`src/dashboard/`) — unchanged (read-only contract + fail-closed lineage validator; canonical pins held).
- **Dashboard v0.1 UI** (`apps/dashboard/`) — **all five views built** on demo data (Next.js 16 / React 19 / Tailwind v4 / shadcn/ui / **Recharts now in use**); `src/components/charts/` (5), `src/components/dashboard/` (5, polished), `src/components/ui/` (18 shadcn primitives), `src/lib/dashboard/` (5 demo payloads + `navigation.ts`), `src/types/` (5 view type modules).
- **Configuration** — 16 entries unchanged (no backend config touched).
- **Test suite** — **590 Python tests** unchanged (not re-run — no Python code changed). Frontend gates: `eslint` / `tsc --noEmit` / `next build`.
- **Coding rules** — `.claude/rules/code-style.md` + `.claude/rules/frontend/react.md` (Dashboard v0 scope, `src/` layout contract, App Router rules, chart-isolation, industrial-UX language) — the substrate the v0.1 views were built against.
- **Reference docs** — 4 pipeline + 9 intelligence + 2 context + dashboard contract + dataflow + the Dashboard v0 stack note (carried from v4).
- **Still placeholders / not yet implemented**: `src/models/` (predictive scorers); the dashboard-ready JSON export + backend API; `src/visualization/` (Python-side plots); output API; frontend tests.

> **Honest correction of a v4 prediction.** v4's closing note expected `MASTER_VERSION_v5` to be
> cut "when Dashboard v0 is feature-complete (all five views **over the dashboard-ready JSON
> export**)." v5 lands the views **feature-complete on demo data** instead — the JSON export /
> API is deferred to the next chapter. The UI milestone is met; the data-integration milestone
> is not, and the docs say so rather than papering over it.

---

## 7. Agent & Skill Ecosystem

Per [CLAUDE.md](../../CLAUDE.md), the ecosystem is **20 agents** and **60 skills**,
auto-discovered via YAML frontmatter (unchanged from v4). Agents that shaped v5:

- `dashboard-ui-agent` — the four view compositions, chart selection, and information hierarchy.
- `dashboard-data-contract-agent` — the read-only / demo-data boundary the views respect.
- `master-version-agent` *(Opus)*, `day-closing-agent` — this snapshot and the 2026-07-02 session note.

The dashboard skill family (8 skills — `define-dashboard-data-contract`,
`map-intelligence-outputs-to-ui`, `validate-dashboard-payloads`, `generate-dashboard-fixtures`,
`design-dashboard-layout`, `select-dashboard-components`, `generate-dashboard-view`,
`review-dashboard-usability`) is the substrate for the upcoming JSON-export / real-data work.

---

## 8. Technical Decisions

v1–v4 decisions still hold. New non-obvious calls that define v5:

1. **Charts are isolated `"use client"` components, never in route pages.** Every Recharts
   view (`src/components/charts/`) takes data via props; the route page stays a thin server
   component that composes and passes demo data. This keeps the eventual demo→JSON swap a
   data-source change, not a component rewrite.
2. **A theme-token system before more views, not after.** InjexCore tokens in `globals.css`
   (`e97d8b2`) were introduced and then a full polish pass applied, so the five views share one
   visual language rather than accreting per-view styling.
3. **Demo data retained through the entire UI build.** All five views were completed on static
   payloads so layout/UX/charting could be validated *before* any API contract is wired — the
   frontend still never reads Parquet. The boundary is intentional and unchanged from v4.
4. **The Recharts × React 19 blank-chart trap was pinned, not worked around.** Under React 19,
   Recharts renders **completely blank** if the transitive `react-is` resolves to v16 (it
   can't detect React 19 element/Fragment symbols) — and this is invisible to `lint` / `tsc` /
   `next build`. Fixed with a `"react-is": "^19"` override in `apps/dashboard/package.json`
   (the shadcn-documented fix); charts must be verified **visually**, not via SSR/curl.
5. **Honest UI language stayed a hard rule across all five views.** No failure-prediction
   claims; operational language + the Overview's explicit Limitations section — the same
   honesty constraint the intelligence layer enforces on its scores.

---

## 9. Roadmap Progress

| Milestone | Status as of v5 |
|---|---|
| Preprocessing layer — 4 stages | Done (v1) |
| Intelligence Layer — Iterations A/B/C (10 components) | Done (v2/v3/v4) |
| External Context Layer (`src/context/{bom,operational}`) | Done (v3) |
| Read-only Dashboard contract + lineage validator (`src/dashboard/`) | Done (v3) |
| Dashboard v0 — app shell + 5 routes scaffolded + Executive Overview | Done (v4) |
| **Dashboard v0.1 — Operational Timeline view (`/timeline`)** | **Done (v5)** |
| **Dashboard v0.1 — Sensor Health view (`/sensor-health`)** | **Done (v5)** |
| **Dashboard v0.1 — Drift & Anomaly view (`/drift-anomaly`)** | **Done (v5)** |
| **Dashboard v0.1 — Incidents view (`/incidents`)** | **Done (v5)** |
| **Dashboard v0.1 — chart layer + InjexCore theme + polish pass** | **Done (v5)** |
| **Dashboard-ready JSON export + backend API (intelligence → JSON → Next.js)** | **In progress — the immediate next step** |
| Frontend tests | Not started |
| *Approved* Reference v2 refit + true PCA/Mahalanobis rescoring | Not started — deferred, gated on plant records |
| Predictive `src/models/` layer (Isolation Forest, LOF, Mahalanobis) | Not started |
| Output API (FastAPI) | Not started |

### 9.1 Immediate next chapter — the real data connection via a backend API

Dashboard v0.1 is structurally complete and demo-ready. The next chapter turns it from a demo
into a real technical-validation tool by feeding it the pinned canonical chain:

- **Design the dashboard-ready JSON export** — a stable, versioned contract that serialises the
  intelligence outputs (per the read-only `src/dashboard/` contract) into frontend-safe JSON.
  The `dashboard-data-contract-agent` + the 8 dashboard skills are the substrate.
- **Serve it via an API** and replace `demo-*.ts` per view. Highest-signal artifacts to surface
  first: the incidents **review pack** and the **scoring-experiment scenarios**; the
  `inlet_hopper_points` story is the highest-signal narrative to carry through `/timeline` →
  `/sensor-health` → `/incidents`.
- **Keep the boundary** — the frontend reads JSON from the API, never Parquet directly; the
  contract still fails closed on bad provenance.

### 9.2 After the data connection

Add frontend tests (none exist yet), then resume the deferred backend track: an *approved*
Reference v2 refit / true PCA-Mahalanobis rescore (gated on plant records) and the predictive
`src/models/` layer — both unchanged and still gated as in v4.

---

## 10. Risks & Open Questions

- **All five views now show demo numbers, not analysed results.** In v4 this risk touched only
  `/overview`; in v5 it touches the whole dashboard. Until the JSON export / API is wired, every
  view reflects placeholder figures, not the pinned canonical chain — the wiring is now the top
  priority. Mitigated by the honest labelling + Overview Limitations section, but it is the
  central open item.
- **Charts can pass every automated gate and still be blank.** The React 19 × `react-is` trap
  (§8) is resolved and pinned, but it is a standing reminder that `lint` / `tsc` / `next build`
  do **not** verify chart rendering — visual verification is required for any new chart.
- **Frontend has no tests.** Dashboard v0.1 relies solely on `eslint` / `tsc` / `next build`;
  no component/unit tests exist. Acceptable at v0.1 scope, a widening gap now that five views
  and five charts exist.
- **Doc/boilerplate gaps.** `apps/dashboard/README.md` is still `create-next-app` boilerplate;
  the `human-decision` overlay still has no dedicated `docs/intelligence/` reference doc
  (carried from v4).
- **Carried from v4:** pending human decision on the `inlet_hopper_points` quarantine +
  deferred Reference v2 (gates any refit/rescore); real-machine anomaly thresholds
  (`.claude/CLAUDE.local.md`) still unfinalised; scores are descriptive/interpretive, not
  validated against ground truth; non-derivable regimes remain blind spots; single-source
  evidence (one vendor CSV + the BOM CSV).

---

## 11. Current Priorities & Recommended Focus

1. **Design + wire the dashboard-ready JSON export / backend API** — the single most important
   next step; replace the demo payloads with the pinned canonical chain (incidents review pack
   + scoring scenarios first).
2. **Replace `demo-*.ts` per view** as the export lands, `/overview` → `/incidents`, keeping the
   `inlet_hopper_points` narrative coherent end-to-end.
3. **Add frontend tests** — at minimum smoke/render coverage for the five views + five charts.
4. **Human review of the Iteration C decision report** — resolve the `inlet_hopper_points`
   quarantine + the deferred Reference v2 candidate (gates any refit/rescore).
5. **Then** begin the predictive `src/models/` layer and finalise real-machine anomaly thresholds.

---

## 12. Confidence Level

- **High confidence**: the five built views + five Recharts charts + InjexCore theme, the demo
  payloads + view types, the `"use client"` chart-isolation pattern, and the frontend gates
  (`tsc --noEmit` clean · `next build` green, 9/9 static pages · `eslint` 0 errors / 6
  non-blocking warnings) — all verified against `apps/dashboard/` and git history in this pass. The backend's untouched state (no `src/` change, 590 tests, pins held) verified via
  the v4→HEAD diff (all 30 changed files under `apps/dashboard/`).
- **Medium confidence**: master/specialized dataset shapes (carried from v1/v2, not re-counted);
  the 20-agent / 60-skill ecosystem counts (sourced from CLAUDE.md); the demo payload figures
  (illustrative, not the analysed chain).
- **Lower confidence / explicit uncertainty**: the dashboard-ready JSON export schema + the
  backend API design (not yet produced); external correctness of derived profiles/scores (no
  ground-truth labels); real-machine anomaly thresholds (private); the outcome of the pending
  quarantine / Reference v2 decisions (gated on plant records).

---

## 13. References

- Project guidance: [CLAUDE.md](../../CLAUDE.md)
- Documentation index: [docs/README.md](../README.md)
- Architecture + contracts: [docs/architecture/intelligence_dataflow.md](../architecture/intelligence_dataflow.md)
- Dashboard contract: [docs/dashboard/dashboard_data_contract.md](../dashboard/dashboard_data_contract.md)
- Dashboard v0 stack: [docs/architecture/InjexCore_Technical_Stack_Dashboard_v0.md](../architecture/InjexCore_Technical_Stack_Dashboard_v0.md)
- Frontend rules: [.claude/rules/frontend/react.md](../../.claude/rules/frontend/react.md), [.claude/rules/code-style.md](../../.claude/rules/code-style.md)
- Session notes: [day_close_2026-07-02.md](../sessions/day_close_2026-07-02.md), [day_close_2026-06-28.md](../sessions/day_close_2026-06-28.md)
- Previous snapshots: [MASTER_VERSION_v4.md](MASTER_VERSION_v4.md), [MASTER_VERSION_v3.md](MASTER_VERSION_v3.md), [MASTER_VERSION_v2.md](MASTER_VERSION_v2.md), [MASTER_VERSION_v1.md](MASTER_VERSION_v1.md)
- Global standards (apply automatically): `~/.claude/CLAUDE.md`, `~/.claude/rules/python.md`, `~/.claude/rules/ml-pipeline.md`, `~/.claude/rules/git.md`

---

*End of MASTER_VERSION_v5. Next snapshot: `MASTER_VERSION_v6` — cut when the dashboard-ready
JSON export / backend API is wired and the five views read the pinned canonical chain instead of
demo data, or when the first fitted predictive model lands in `src/models/`.*
