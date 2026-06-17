# InjexCore — MASTER_VERSION_v3

## 1. Version Metadata

| Field | Value |
|---|---|
| Version | `v3.0.0` |
| Date | `2026-06-16` |
| Scope label | Intelligence Layer Iterations B + C (9-component stack) + External Context layers + read-only Dashboard contract + hardening |
| Snapshot author | `master-version-agent` |
| Previous snapshot | [MASTER_VERSION_v2.md](MASTER_VERSION_v2.md) — Intelligence Layer Iteration A + package restructure (`2026-06-02`) |
| Baseline status | This document diffs against v2; the next `MASTER_VERSION_v4` diffs against this one. v1 and v2 remain immutable. |
| Source-of-truth documents (not replaced) | [CLAUDE.md](../../CLAUDE.md), [docs/README.md](../README.md), [docs/architecture/intelligence_dataflow.md](../architecture/intelligence_dataflow.md), [docs/dashboard/dashboard_data_contract.md](../dashboard/dashboard_data_contract.md), the 9 `docs/intelligence/*` and 2 `docs/context/*` reference docs |

This snapshot consolidates — it does not rewrite. Where this document makes a claim, the
underlying reference doc remains authoritative. v1 (preprocessing baseline) and v2
(Intelligence Iteration A) remain immutable records and are not edited.

---

## 2. Executive Summary

- **InjexCore** is a predictive-maintenance system for plastic injection moulding machines that classifies each production cycle as `normal` / `warning` / `anomaly` (see [CLAUDE.md](../../CLAUDE.md)).
- **Since v2, the Intelligence Layer went from one component to nine.** v2 shipped only Behaviour Intelligence (Iteration A). v3 adds Iteration B (Correlation, PCA, Anomaly), Sensor Health, Drift, Incident Aggregation, Reference Governance and Controlled Scoring Experiment — a full descriptive-and-interpretive analytics stack.
- **A new analytical sibling layer landed: `src/context/`.** BOM Operational Context and the Operational Context Overlay turn external sources (BOM / production orders) into master-aligned contextual datasets via read-only joins — analytical only, never an input to model fitting.
- **The system became "dashboard-ready" without a model.** A read-only dashboard consumption contract + fail-closed lineage validator (`src/dashboard/`) pins a canonical, rematerialized run chain (`remat-v1-20260616T102558Z` / BOM `20260612T124909Z`). The dashboard UI is intentionally not started.
- **Every component obeys the same contracts**: run-versioned outputs (`runs/<run_id>/`), manifest-written-last as the completion marker, leakage-safe fitting on behaviour's persisted `is_train` window, original-vs-interpretive score separation (scores are never mutated/refit), and human-gated quarantine (`approval_required=True, approved=False` — nothing is auto-excluded).
- **Quality gates are green.** `ruff` (lint + format), `mypy src` (pydantic plugin), and **575 passing tests** (up from 165). A hardening sprint closed 8 Codex findings with an independent qa-agent PASS.
- **The next chapter is the read-only Technical Validation Dashboard MVP** over the pinned chain, plus human review of the Iteration C decision report; the predictive `src/models/` layer remains reserved and unstarted.

---

## 3. What Changed Since v2 (v2 → v3 diff)

This is the primary lens of this snapshot. v2's scope was "Intelligence Layer Iteration A
+ restructure." v3 keeps all of that intact and adds eight intelligence components, two
context layers, and a dashboard contract on top.

| Area | v2 (baseline) | v3 (now) |
|---|---|---|
| Intelligence components | 1 (`behaviour`) | **9** (`behaviour`, `correlation`, `pca`, `anomaly`, `sensor_health`, `drift`, `incidents`, `reference`, `scoring_experiment`) |
| Intelligence shared utils | shims over `preprocessing/_common` | **new `src/intelligence/_common/`** (run-versioning, fingerprint, upstream loaders, fit-manifest base) |
| Context layer | none | **new `src/context/{bom,operational}/`** (read-only analytical overlays) |
| Dashboard | none | **new `src/dashboard/`** — read-only contract + fail-closed lineage validator |
| Dispatcher | `--component behaviour` | `--component behaviour\|correlation\|pca\|anomaly\|sensor-health\|drift\|incidents\|reference\|scoring-experiment` |
| Configs | 5 stage/behaviour YAMLs | **16 entries** (`configs/`): +9 intelligence/context YAMLs (correlation, pca, anomaly, sensor_health, drift, incidents, reference, scoring_experiment) + bom_context + operational_context, plus `schema_lock.json` |
| Run model | single fixed output dir per component | **run-versioned** `runs/<run_id>/` everywhere; manifest-last completion marker; `latest` resolution |
| Leakage contract | behaviour `train_mask` + fit manifest | same, now the **consumed contract** for every Iteration B/C component (`align_labels` / `is_train`) |
| Forensics | none | read-only forensic addenda under `data/intelligence/forensics/{drift_addenda,bom_addenda,context_addenda,reference_decision}/` |
| Tests | 165 | **575** under `tests/unit/{preprocessing,intelligence,context,dashboard}/` + `tests/integration/` |
| Quality events | mypy plugin enabled | + 8-finding hardening sprint (qa-agent PASS) + controlled rematerialization to a pinned canonical chain |

What did **not** change: the four preprocessing stages' contracts, the descriptive-vs-
predictive boundary, the strict pydantic policies, the uniform `Finding` audit record, the
master/specialized dataset shapes, and the rule that `src/models/` stays reserved for
predictive scorers. v3 is purely additive on top of v2.

---

## 4. Architecture State

The production pipeline is still a strictly linear preprocessing chain; v3 fans out
densely *after* the master dataset into the intelligence + context layers.

```
src/data_generation/generate.py
  → src/preprocessing/{cleaning → time_series → feature_engineering → datasets}   (master + specialized parquet)
    → src/intelligence/behaviour/                                                  fits DESCRIPTIVE artifacts (is_train contract)
      → src/intelligence/{correlation, pca}                                        per-profile structure / decomposition
        → src/intelligence/anomaly/                                                4 detectors + combined severity (reads pca run)
          → src/intelligence/drift/                                               windowed drift vs train reference (reads anomaly/pca)
            → src/intelligence/incidents/                                          events → reviewable incidents
              → src/intelligence/reference/                                        reference + quarantine/candidate proposals
                → src/intelligence/scoring_experiment/                             interpretive scenarios over persisted scores
  src/intelligence/sensor_health/   ── instrumentation vs process anomalies (feeds drift + context + incidents)
  src/context/{bom, operational}/   ── read-only joins against master + anomaly scores (interpretation only)
  src/dashboard/                    ── read-only consumption contract + lineage validator over the pinned chain
            → [src/models/ pending: PREDICTIVE scorers]
```

### 4.1 The layer boundary (extended in v3)

| Layer | Package | Responsibility | Fits / mutates? |
|---|---|---|---|
| Preprocessing | `src/preprocessing/` | Cleans + engineers features | No — parameter-free |
| Intelligence | `src/intelligence/` | Characterises *normal* (descriptive) + interprets persisted scores | DESCRIPTIVE fits only; **never** refits predictive estimators, rescores with altered matrices, approves quarantine, or excludes a sensor |
| **Context** | `src/context/` | External sources → master-aligned contextual datasets | **No fitting — read-only joins; never a model-fitting input** |
| Dashboard | `src/dashboard/` | Read-only consumption contract + lineage validation | No mutation — fails closed on bad provenance |
| Models (planned) | `src/models/` | Scores deviation from normal | Yes — PREDICTIVE estimators |

### 4.2 Per-component conventions (codified in v3)

Every Iteration B/C component shares three contracts, implemented in
`src/intelligence/_common/`:

- **Run-versioning** — outputs land in `data/intelligence/<component>/runs/<run_id>/`
  (UTC-timestamp run-ids); the fit/run **manifest is written LAST** as the atomic
  completion marker; downstream resolves the `latest` *completed* run.
- **Leakage safety** — components consume behaviour's persisted labels + `is_train` flag
  (`align_labels`, strict) rather than recomputing a split; references are fit train-window
  only.
- **Original-vs-interpretive scores** — anomaly/pca/Mahalanobis scores are computed once
  and persisted; downstream (drift, scoring_experiment) reads them read-only and never
  rescores or refits. Iteration B CLIs take policy via `--config`; behaviour predates this
  and uses `--policy`. `--no-write` writes nothing at all.

---

## 5. Data Flow

The preprocessing data flow is unchanged from v1/v2 (master `167,331 × 566`). v3 adds the
run-versioned intelligence + context artifact families downstream of the master dataset.
All of `data/` is git-ignored; shapes below are carried forward / schema-verified, not
re-counted in this pass.

| Artefact | Path | Form |
|---|---|---|
| Master (canonical) | `data/datasets/master/master_dataset.parquet` | 167,331 × 566 |
| Specialized datasets | `data/datasets/specialized/{anomaly_detection,forecasting,energy}_dataset.parquet` | model-family projections |
| Behaviour | `data/intelligence/behaviour/runs/<run_id>/{profiles,baselines,validation}/` + `behaviour_fit_manifest.json` | profiles + per-profile baselines + `is_train` contract |
| Correlation | `data/intelligence/correlation/runs/<run_id>/` | per-profile Pearson/Spearman + shift diagnostics |
| PCA | `data/intelligence/pca/runs/<run_id>/` | joblib scaler+PCA models, loadings, per-row T²/Q + contributions |
| Anomaly | `data/intelligence/anomaly/runs/<run_id>/` | 4 detectors + combined severity (`normal`/`warning`/`anomaly`/`unscored`) |
| Sensor Health | `data/intelligence/sensor_health/runs/<run_id>/` | scores, events, `sensor_quality_timeline`, quarantine_recommendations |
| Drift | `data/intelligence/drift/runs/<run_id>/` | drift_scores, drift_events, 11 summary tables incl. `raw_vs_healthy_only_comparison` |
| Incidents | `data/intelligence/incidents/runs/<run_id>/` | incidents, relationships, review pack, actions, suppressed duplicates |
| Reference | `data/intelligence/reference/runs/<run_id>/` | reference_registry, reference/quarantine proposals, decision_log |
| Scoring Experiment | `data/intelligence/scoring_experiments/runs/<run_id>/` | scenario_scores + 4 comparison/recommendation tables |
| BOM context | `data/context/bom/runs/<run_id>/` | components, orders, overlaps/gaps/transitions, master-aligned `bom_context_timeline` |
| Operational context | `data/context/operational/runs/<run_id>/` | overlay timeline, transitions, summaries |
| Forensic addenda | `data/intelligence/forensics/{drift_addenda,bom_addenda,context_addenda,reference_decision}/<run_id>/` | read-only joins against persisted anomaly scores |

Every component writes its `Finding`-style `{json,md}` report pair plus a manifest. The
master dataset is **not** modified by any downstream layer — each is independently
rerunnable. The canonical pinned chain for the dashboard is `remat-v1-20260616T102558Z`
(BOM `20260612T124909Z`).

---

## 6. Active Systems

- **Preprocessing layer** (`src/preprocessing/`) — unchanged from v2: `cleaning/`, `time_series/`, `feature_engineering/`, `datasets/`, neutral `_common/` contracts (`Finding`, `Severity`, `StrictModel`, writers), `--stage` dispatcher.
- **Intelligence Layer** (`src/intelligence/`) — 9 components + shared utilities:
  - [behaviour/](../../src/intelligence/behaviour/) (Iteration A), [correlation/](../../src/intelligence/correlation/), [pca/](../../src/intelligence/pca/), [anomaly/](../../src/intelligence/anomaly/) (Iteration B), [sensor_health/](../../src/intelligence/sensor_health/), [drift/](../../src/intelligence/drift/), [incidents/](../../src/intelligence/incidents/) (Iteration C Parts 1–2), [reference/](../../src/intelligence/reference/), [scoring_experiment/](../../src/intelligence/scoring_experiment/) (Iteration C Part 3).
  - [_common/](../../src/intelligence/_common/) — run-versioning (`runs.py`), fingerprint, upstream loaders + `align_labels`, feature selection, joblib persistence, base fit manifest.
  - [__main__.py](../../src/intelligence/__main__.py) — registry-based `--component` dispatcher (defaults to `behaviour`).
- **External Context Layer** (`src/context/`) — NEW in v3:
  - [bom/](../../src/context/bom/) — BOM normalization → orders → diagnostics → master-aligned timeline + forensic addendum.
  - [operational/](../../src/context/operational/) — profile + steam + sensor-health + BOM overlay, transitions, context-aware forensic addendum.
- **Dashboard contract** (`src/dashboard/`) — NEW in v3: [contract.py](../../src/dashboard/contract.py) (canonical run pins + component registry), [lineage.py](../../src/dashboard/lineage.py) (`validate_dashboard_chain`, fail-closed, read-only). The executable half of [dashboard_data_contract.md](../dashboard/dashboard_data_contract.md). The dashboard **UI** is not started.
- **Configuration** — 15 pydantic-validated YAML policies (all `extra="forbid"`) + `schema_lock.json` under [configs/](../../configs/): the 4 preprocessing stages, `behaviour_intelligence`, `correlation_intelligence`, `pca_intelligence`, `anomaly_intelligence`, `sensor_health_intelligence`, `drift_intelligence`, `incidents_intelligence`, `reference_governance`, `scoring_experiment`, `bom_context`, `operational_context`.
- **Central paths** — [src/config.py](../../src/config.py): `PROJECT_ROOT`, `RAW/PROCESSED/FEATURES/DATASETS/INTELLIGENCE_DIR`, `CONFIGS_DIR`.
- **Test suite** — **575 tests** under `tests/unit/{preprocessing,intelligence,context,dashboard}/` and `tests/integration/` (chain contract tests). Run with `pytest` (~55 s).
- **Reference docs** — 4 pipeline + 9 intelligence + 2 context + the dashboard contract + the [intelligence_dataflow.md](../architecture/intelligence_dataflow.md) architecture doc (see [docs/README.md](../README.md)).
- **Quality reports** — [post_iteration_c_hardening_report.md](../../reports/hardening/post_iteration_c_hardening_report.md), [controlled_rematerialization_report.md](../../reports/hardening/controlled_rematerialization_report.md), [pre_dashboard_contract_cleanup_report.md](../../reports/dashboard/pre_dashboard_contract_cleanup_report.md).
- **Still placeholders (not yet implemented)**: `src/models/` (predictive scorers), `src/visualization/` / dashboard UI, output API.

---

## 7. Agent & Skill Ecosystem

The project-local Claude Code tooling under [.claude/agents/](../../.claude/agents/) and
`.claude/skills/` remains the delivery substrate. Per [CLAUDE.md](../../CLAUDE.md), the
ecosystem is **18 agents** and **52 skills**, auto-discovered via YAML frontmatter. No net
change in counts since v2 was observed in this pass.

Agents that materially shaped what ships in v3:

- `anomaly-detection-agent`, `predictive-maintenance-agent` *(Opus)* — the four-detector design, conservative-max combined severity, and the rule that anomalies are flagged, never assumed to be failures.
- `sensor-intelligence-agent`, `machine-cycle-agent` — the nine sensor-health rule families and profile-aware suppression (stopped-state zeros never flag).
- `time-series-agent` — windowed drift metrics vs the train reference and the raw-vs-healthy-only analytical split.
- `plastics-industry-agent` *(Opus)* — BOM / recipe context interpretation and the honesty constraint that overlaps are preserved unresolved.
- `code-reviewer-agent`, `qa-agent` — the hardening sprint (8 Codex findings) and the test growth to 575 with an independent PASS.
- `repository-architecture-agent` — the `src/context/` and `src/dashboard/` layer splits and the run-versioning convention.
- `documentation-architect-agent` — the 9 intelligence + 2 context + dashboard reference docs and the dataflow doc.
- `master-version-agent` *(Opus)*, `day-closing-agent` — this snapshot and the 2026-06-16 session note.

Skill inventory (52 skills across 15 domains) is not enumerated here; see
[CLAUDE.md](../../CLAUDE.md#skills-52). The four project-state/master-version skills
(`generate-project-state-report`, `consolidate-project-knowledge`,
`track-project-evolution`, `generate-master-version`) produced this document.

---

## 8. Technical Decisions

v1's and v2's decisions still hold. New non-obvious calls that define v3:

1. **Run-versioning + manifest-as-completion-marker.** Every component writes to `runs/<run_id>/` and writes its manifest **last**; a run is "complete" iff its manifest exists. Downstream resolves the `latest` completed run. This makes the whole layer non-destructive and reproducible, and lets the dashboard pin an exact chain.
2. **Leakage contract is consumed, not recomputed.** Behaviour's persisted labels + `is_train` flag are the single source of the train/validation split; every Iteration B/C component aligns to it via strict `align_labels` rather than re-splitting. References are fit train-window only.
3. **Original scores are immutable; interpretation is layered.** Anomaly/PCA/Mahalanobis scores are computed once and persisted. Drift reads multivariate score shifts from them without refit; the scoring experiment produces *scenarios* (quarantine-aware, healthy-only proxy, reference-candidate) that never mutate `severity`/`combined_score`. No deep learning / forecasting / streaming (explicitly deferred).
4. **Human-gated quarantine — propose, never approve.** Sensor Health recommends quarantine and Reference Governance tracks proposals, but everything is `approval_required=True, approved=False` / `pending_review`. Nothing auto-excludes a sensor, refits a model, or changes the reference window. An *approved* Reference v2 refit is explicitly deferred and gated on the decision report + plant records.
5. **Context layers are analytical-only.** `src/context/{bom,operational}` join external sources against the master timeline read-only; overlaps are preserved unresolved. They are never inputs to model fitting until explicitly promoted — a deliberate firewall between "context" and "training signal."
6. **Honest raw-vs-healthy-only views.** Drift exposes both the raw signal and a `healthy_only_proxy` (Level-A evidence-dominance filter + Level-B proxy), honestly labeled and never rescoring — surfacing that ~70% of validation drift mass is `inlet_hopper_points`-dominated without hiding the raw evidence.
7. **Fail-closed dashboard lineage.** `validate_dashboard_chain` resolves every component's pinned run read-only, fails closed on missing/wrong-component/wrong-id manifests, and surfaces non-canonical/stale chains as warnings. The dashboard cannot silently read a half-written or mismatched run. Provenance hardening: `expected_component` enforcement (LINEAGE-01), `behaviour_run_id` in manifests (PROV-01), addendum run overrides that fail closed (CTX-01).

---

## 9. Roadmap Progress

| Milestone | Status as of v3 |
|---|---|
| Synthetic data generation | Done (MVP scaffolding) |
| Preprocessing layer — 4 stages | Done (v1), carried forward |
| Intelligence Layer — Behaviour (Iteration A) | Done (v2) |
| **Intelligence Layer — Iteration B (Correlation, PCA, Anomaly)** | **Done (v3)** |
| **Intelligence Layer — Iteration C Parts 1–2 (Sensor Health, Operational/BOM Context, Drift, Incidents)** | **Done (v3)** |
| **Intelligence Layer — Iteration C Part 3 (Reference Governance, Controlled Scoring Experiment)** | **Done (v3)** |
| **External Context Layer (`src/context/{bom,operational}`)** | **Done (v3)** |
| **Read-only Dashboard consumption contract + lineage validator (`src/dashboard/`)** | **Done (v3)** |
| Read-only Technical Validation Dashboard **UI** (`src/visualization/`) | Not started — contract in place, UI pending |
| *Approved* Reference v2 refit (excluding quarantined channel) + true PCA/Mahalanobis rescoring | Not started — deferred, gated on the decision report + plant records |
| Predictive `src/models/` layer (Isolation Forest, LOF, Mahalanobis) | Not started — consumes the behaviour fit manifest |
| Output API (FastAPI) | Not started |

### 9.1 Immediate next chapter — decision review + dashboard MVP

The decision report at `data/intelligence/forensics/reference_decision/<latest>/`
(`decision_summary.md` + `decision_matrix.parquet`) holds two pending human decisions: the
`inlet_hopper_points` quarantine approval and the deferred (residual `material=False`)
Reference v2 candidate. With the dashboard contract + lineage validator pinned to the
canonical chain, the lowest-friction next increment is the read-only Technical Validation
Dashboard UI over that chain.

### 9.2 Predictive layer (after the dashboard MVP)

`src/models/` consumes the behaviour fit manifest + specialized datasets and must honour
the inherited constraints: per-package conventions, pydantic `extra="forbid"` policies,
`Finding`-style audit reports, run-versioning, leakage safety, and reproducibility
(pinned versions, logged seeds, dataset hashes) per `~/.claude/rules/ml-pipeline.md`.

---

## 10. Risks & Open Questions

- **Pending human decisions block promotion.** The `inlet_hopper_points` quarantine and the Reference v2 candidate are `pending_review`; until reviewed against plant records, no sensor is excluded and no model is refit. The materiality assessment is conservative (`material=False`) but not a substitute for plant confirmation.
- **Anomaly thresholds for real-machine data still pending.** Criteria live in `.claude/CLAUDE.local.md` (git-ignored), not finalised — still blocking supervised evaluation. (Carried from v1/v2.)
- **Scores are descriptive/interpretive, not validated against ground truth.** "Normal" is derived from the data's own per-profile distribution; the validation/drift reports check internal coherence, not external correctness. No labelled confirmation exists. (Carried from v2.)
- **Non-derivable regimes remain blind spots.** `cleaning` / `maintenance` / `recipe_change` need an external log that does not yet exist; the BOM context narrows but does not close this gap.
- **Single-source evidence.** All analysis derives from one vendor CSV (`Dades_pellet.csv`) plus the raw BOM CSV; multi-source generalisation is unverified. (Carried from v1/v2.)
- **Resolved since v2:** the run-versioning / manifest-last contract, leakage propagation across components, sensor-health manifest creation, operational/BOM addendum CLI overrides, and the dashboard lineage validator are all in place — no longer open risks.

---

## 11. Current Priorities & Recommended Focus

1. **Human review of the Iteration C Part 3 decision report** — resolve the `inlet_hopper_points` quarantine and the deferred Reference v2 candidate; this gates any refit/rescore.
2. **Build the read-only Technical Validation Dashboard MVP** over the pinned canonical chain (`remat-v1-20260616T102558Z` / BOM `20260612T124909Z`) — the contract + lineage validator already exist; surface the review pack + scoring scenarios first.
3. **Begin the predictive `src/models/` layer** — Isolation Forest / LOF / Mahalanobis scoring against the behaviour baselines + fit manifest.
4. **Finalise real-machine anomaly thresholds** in `.claude/CLAUDE.local.md` — still the gating input for supervised evaluation.
5. **Plan external-log integration** (maintenance / material-change events) to close the non-derivable-regime gaps.

---

## 12. Confidence Level

- **High confidence**: the 9-component intelligence stack, `src/context/{bom,operational}`, `src/dashboard/`, the 16-entry `configs/` set, the run-versioning / manifest-last / leakage / no-auto-quarantine contracts, the dispatcher `--component` set, the canonical pinned chain id, and the **575-test** count — all verified against the `src/`, `configs/`, `tests/`, and git history in this pass.
- **Medium confidence**: master/specialized dataset row/column shapes (carried from v1/v2, not independently re-counted); the run-internal artifact counts cited from CLAUDE.md / component docs; the 18-agent / 52-skill ecosystem counts (sourced from `CLAUDE.md`).
- **Lower confidence / explicit uncertainty**: real-machine anomaly thresholds (private); external correctness of the derived profiles/scores (no ground-truth labels); the outcome of the pending quarantine / Reference v2 decisions (gated on plant records not visible to this snapshot); `src/models/` and dashboard-UI design specifics (not yet produced).

---

## 13. References

- Project guidance: [CLAUDE.md](../../CLAUDE.md)
- Documentation index: [docs/README.md](../README.md)
- Architecture + contracts: [docs/architecture/intelligence_dataflow.md](../architecture/intelligence_dataflow.md)
- Dashboard contract: [docs/dashboard/dashboard_data_contract.md](../dashboard/dashboard_data_contract.md)
- Intelligence references: [behaviour](../intelligence/behaviour_intelligence.md), [correlation](../intelligence/correlation_intelligence.md), [pca](../intelligence/pca_intelligence.md), [anomaly](../intelligence/anomaly_intelligence.md), [sensor_health](../intelligence/sensor_health_intelligence.md), [drift](../intelligence/drift_intelligence.md), [incidents](../intelligence/incident_aggregation.md), [reference](../intelligence/reference_governance.md), [scoring_experiment](../intelligence/controlled_scoring_experiment.md)
- Context references: [bom_context.md](../context/bom_context.md), [operational_context.md](../context/operational_context.md)
- Quality reports: [hardening](../../reports/hardening/post_iteration_c_hardening_report.md), [rematerialization](../../reports/hardening/controlled_rematerialization_report.md), [dashboard cleanup](../../reports/dashboard/pre_dashboard_contract_cleanup_report.md)
- Session note: [docs/sessions/day_close_2026-06-16.md](../sessions/day_close_2026-06-16.md)
- Previous snapshots: [MASTER_VERSION_v2.md](MASTER_VERSION_v2.md), [MASTER_VERSION_v1.md](MASTER_VERSION_v1.md)
- Global standards (apply automatically): `~/.claude/CLAUDE.md`, `~/.claude/rules/python.md`, `~/.claude/rules/ml-pipeline.md`, `~/.claude/rules/git.md`

---

*End of MASTER_VERSION_v3. Next snapshot: `MASTER_VERSION_v4` — cut when the first fitted predictive model lands in `src/models/`, or when the read-only Technical Validation Dashboard UI ships.*
