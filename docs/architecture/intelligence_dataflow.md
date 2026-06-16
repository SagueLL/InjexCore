# InjexCore — Intelligence Layer Dataflow & Contracts

Authoritative end-to-end view of how data flows from the raw line dataset to the
human decision pack, and the contracts every component upholds. Component-level
detail lives in [docs/intelligence/](../intelligence/) and
[docs/context/](../context/); this document is the map between them.

---

## 1. End-to-end dataflow

```
Raw line CSV
  └─ preprocessing: cleaning → time_series → feature_engineering → datasets
        └─ data/datasets/master/master_dataset.parquet          (the canonical master)
              │
   Behaviour Intelligence ── fits per-profile baselines on a leakage-safe TRAIN window
        └─ behaviour run: profile labels (+ is_train), baselines, fit manifest
              │  (every downstream reuses these labels + the is_train split — never re-derives them)
              ├─ Correlation ── per-profile Pearson/Spearman references
              ├─ PCA          ── per-profile scaler+PCA, T²/Q scores
              │       └─ Anomaly ── 4 explainable detectors + combined severity (consumes a PCA run)
              ├─ Sensor Health ── instrumentation-anomaly events + quarantine recommendations
              │
   External Context (read-only):
        ├─ BOM context        ── master-aligned BOM/recipe timeline
        └─ Operational context ── profile + steam + sensor-health + BOM overlay timeline
              │
   Drift ── windowed drift vs the TRAIN reference; reads anomaly/pca/correlation/sensor-health/operational
        └─ raw vs healthy_only_proxy views
              │
   Incidents ── events (sensor-health, drift, anomaly bursts, context transitions) → reviewable incidents
        └─ relationships (associative), suppression, review pack
              │
   Reference Governance ── tracks reference_v1 + quarantine/candidate proposals (proposes, never approves)
              │
   Controlled Scoring Experiment ── interpretive scenarios over persisted scores (never rescores/refits)
        └─ decision-report addendum (data/intelligence/forensics/reference_decision/)
```

`src/models/` (predictive estimators) and `src/api/` (serving) are planned and
would consume the Intelligence-Layer artifacts; they are not built yet.

---

## 2. Package boundaries

| Package | Role |
|---|---|
| `src/preprocessing/` | Parameter-free Data Foundation; no fitted models. |
| `src/intelligence/` | Fits **descriptive** artifacts (baselines, references) and scores deviation. |
| `src/context/` | Turns external sources into contextual datasets joined against the master. **Analytical only** — never an input to model fitting until explicitly promoted. |
| `src/intelligence/_common/` | Shared run-versioning, lineage, manifest, behaviour loaders. |
| `src/preprocessing/_common/` | Neutral cross-stage contracts (`Finding`, `Severity`, `StrictModel`, writers). |

---

## 3. Artifact locations

```
data/datasets/master/master_dataset.parquet          master (Data Foundation output)
data/intelligence/behaviour/runs/<run_id>/            behaviour run (profiles, baselines, manifest)
data/intelligence/<component>/runs/<run_id>/          correlation, pca, anomaly, sensor_health,
                                                      drift, incidents, reference, scoring_experiments
data/context/{bom,operational}/runs/<run_id>/         external-context runs
data/intelligence/forensics/<addendum>/<run_id>/      read-only forensic addenda (bom, drift, context,
                                                      reference_decision)
```

Everything under `data/` is git-ignored and regenerated locally.

---

## 4. Run-versioning contract

Every Intelligence/Context component writes into `<component_root>/runs/<run_id>/`
and **never overwrites** a prior run:

- `run_id` defaults to a sortable UTC timestamp (`20260616T101500Z`); `--run-id`
  pins one. The directory is created with `create_run_dir` — an atomic
  `mkdir(exist_ok=False)` — so an existing id (auto or explicit) **fails closed**
  with `RunCollisionError` before anything is written.
- `--no-write` runs the full pipeline and writes **nothing** (no files, dirs,
  manifests, or mtime changes).

Helpers: `src/intelligence/_common/runs.py`.

## 5. Manifest-last contract

The fit/run manifest is written **last**, after all artifacts. Its presence
marks a *completed* run. Resolution (`resolve_run`, `list_completed_runs`) does
**not** trust presence alone — a manifest counts only if it:

- parses as JSON,
- carries `component`, `run_id`, `completion_status`,
- reports `completion_status == "complete"`,
- declares a `run_id` equal to its own directory name, and
- matches the expected component when one is supplied.

A crashed, pending, malformed or wrong-component manifest is never resolved as
`latest`.

## 6. Lineage-compatibility contract (fail closed)

Downstream components verify they consume a **coherent** upstream chain and stop
on a mismatch (`src/intelligence/_common/lineage.py`); a semantic lineage
mismatch is never downgraded to a warning:

- **Behaviour provenance** — the behaviour manifest self-reports `run_id` +
  `master_dataset_sha256`; Reference Governance seeds `reference_v1` from it and
  fails closed if it is missing or differs from the current master.
- **Master sha** — sensor-health / operational / reference runs record the
  master file sha; consumers block on a mismatch.
- **Projection-invariant fingerprint** — drift loads a column-projected master,
  so anomaly/pca/correlation runs are checked on row-count + index span.
- **Run-id pins** — drift→incidents and reference→scoring verify the consumed
  runs were built from the same sub-chain (e.g. scoring blocks if its reference
  run was not built from the same sensor-health/drift/incidents runs).

The behaviour `is_train` split is the **leakage contract**: it is fitted once
and reused everywhere; `align_labels` is strict (no silent reindexing).

---

## 7. Original vs interpretive scores

Anomaly Intelligence produces the **original** persisted scores (`severity`,
`combined_score`). The Controlled Scoring Experiment only ever produces
**interpretive** review views on top of them:

- `adjusted_review_*` columns are review-severity adjustments; the original
  `severity`/`combined_score` are **never mutated** and `adjusted_review_score`
  equals `original_combined_score` by construction.
- The `healthy_only_proxy` is a **labeled proxy** read from the drift run, not a
  PCA/Mahalanobis recomputation.
- Suppression is split into **incident-level explained-burst coverage**
  (`incident_explained_for_review`) and **row-level review suppression**
  (`row_suppressed_for_review`, which requires the row's *own* evidence —
  `row_level_evidence_match`). An unrelated anomaly inside an explained burst
  window stays unsuppressed.

A **true** rescoring/refit excluding a quarantined channel is explicit,
human-gated future work — it does not happen here.

## 8. No automatic quarantine / refit / exclusion

Across Sensor Health, Incidents, Reference Governance and Controlled Scoring:

- Quarantine recommendations and proposals are always `approval_required=True`,
  `approved=False`, `review_status=pending_review`.
- Reference Governance **proposes** and tracks decisions; it never approves a
  quarantine, excludes a sensor, refits a model or changes the reference window.
- Incident relationships are associative (`causality_status=unknown`).
- The quarantine-target identity is **derived** from the proposal records
  (`quarantine_<sensor>_interpretive`, or `quarantine_proposals_interpretive`
  for several) — never hardcoded.

---

## 9. Current limitations

- The Intelligence Layer is **descriptive**; no predictive estimator scores
  future failure yet.
- `reference_v1` is immutable; a Reference v2 (refit excluding a quarantined
  channel) is deferred and human-gated.
- The healthy-only and quarantine-aware views are interpretive decision-support,
  not a true rescoring.
- Real-time/streaming inference, alert delivery and a serving API are not built.

## 10. Dashboard consumption contract (read-only)

The Technical Validation Dashboard consumes the persisted artifacts of the
**canonical rematerialized chain** read-only — no new fitting, no mutation:

```
canonical_run_id = remat-v1-20260616T102558Z   # all intelligence + operational
bom_run_id        = 20260612T124909Z            # BOM context
```

- **Narrative contract:** [../dashboard/dashboard_data_contract.md](../dashboard/dashboard_data_contract.md)
  — allowed artifact groups (purpose/safe/unsafe/warning), forbidden MVP views,
  required warning copy, and the read-only / no-approval / no-refit boundaries.
- **Executable contract:** [`src/dashboard/`](../../src/dashboard/) —
  `validate_dashboard_chain(run_id, bom_run_id)` resolves every component's
  pinned run (reusing `runs.is_completed_run`), returns
  `is_valid`/`severity`/`warnings`/`component_statuses`/`lineage_edges`/`canonical_match`,
  fails closed on missing/wrong-component/wrong-id manifests, and surfaces
  non-canonical/stale runs as warnings. **Run-selector rule:** only the
  canonical, lineage-valid chain is shown as valid; everything else is stale or
  hidden. The validator never writes.

### Lineage provenance (LINEAGE-01 / PROV-01)

- Every cross-component consumer now passes `expected_component` to
  `resolve_run` (drift, incidents, reference, scoring, operational, bom, plus
  anomaly's pca resolution), so a right-shaped but wrong-component run is
  rejected at the **consumer boundary**, not silently consumed. The manifest
  `component` strings are **not uniform** (`reference_governance`,
  `operational_context`, `bom_context`, `controlled_scoring_experiment`).
- The leaf manifests (correlation, pca, anomaly, sensor_health) now record
  explicit behaviour provenance: `behaviour_run_id`, `behaviour_manifest_path`,
  `behaviour_created_at`, `behaviour_fit_timestamp`,
  `behaviour_master_dataset_sha256`. The **current canonical manifests predate
  this** and lack those fields, so the validator degrades them to a *warning*
  (the chain stays usable); the next rematerialization refreshes them.
- The operational/BOM forensic addenda accept `--anomaly-run` / `--forensic-run`
  overrides and **fail closed** on stale/unresolvable pins, so they can be
  regenerated against the canonical chain (the operational addendum is not
  present for `remat` until regenerated).

### Reference v2 / true rescoring (still deferred)

- **Reference v2** would be a new, human-approved behaviour-style fit on a
  post-fault window excluding the quarantined channel, producing a new behaviour
  run that the existing run-versioning + lineage contracts already accommodate.
- A **true rescoring** would re-run PCA/Mahalanobis on the altered feature
  matrix — explicit work gated on the decision report, distinct from the
  interpretive scoring experiment.
