# Controlled Rematerialization Report

**Sprint:** Regenerate the real-data analytical chain under the hardened lineage contracts.
**Date:** 2026-06-16 (UTC).
**Shared run id:** `remat-v1-20260616T102558Z` (all 10 components).
**Reused BOM run:** `20260612T124909Z` (not regenerated — compatibility verified).
**Master dataset:** `data/datasets/master/master_dataset.parquet`, 167,331 rows, sha256
`5020956fc874e91b1a82203f5cd09e68b198fbb5031bb3903760c0538ff5d1a3` (byte-identical before & after).

---

## A. Executive summary

**The controlled rematerialization succeeded.** All ten components of the corrected chain
(behaviour → correlation → pca → anomaly → sensor-health → operational-context → drift →
incidents → reference → scoring-experiment) were regenerated under one shared run id
`remat-v1-20260616T102558Z`, each writing run-versioned, manifest-last, completion-validated
outputs that never overwrote an earlier run. Every downstream manifest records its consumed
upstream run ids as the new run (BOM as the reused `20260612T124909Z`), and a strict lineage
sweep confirms the full transitive chain plus byte-identical master and immutable original
anomaly scores. The post-chain QA gate (pytest 552, ruff, ruff-format, mypy) is green.

One blocker was hit and resolved, and one secondary artifact was deferred (both documented below):

1. **Sensor-health manifest bug (fixed).** Under the hardened latest-resolution contract the
   documented bare `--component sensor-health` form crashed in `_build_manifest`
   (`paths["labels"].parent.parent` on the `None` sentinel). A surgical fix + regression test
   were applied with your approval; the full QA gate was re-run before resuming the chain.
2. **Operational-context forensic addendum (deferred / skipped).** Its config pins an out-of-chain,
   pre-hardening anomaly run and a standalone forensics run that are no longer resolvable, and the
   component has no CLI override for them. The core operational timeline (consumed downstream) was
   rematerialized cleanly with `--skip-addendum`; the secondary context-addenda overlay is not
   produced for this run.

The decision posture is unchanged from the hardened intent: the `inlet_hopper_points` quarantine
remains **`approval_required=True, approved=False`**, Reference v2 stays **deferred**
(`residual_material=False`), and plant records are still required.

---

## B. Run chain

All run ids = `remat-v1-20260616T102558Z` unless noted. Manifests are under
`<output_dir>/<manifest_file>`.

| # | Component | run_id | Manifest | Status | Upstream consumed | Row counts / key outputs |
|---|---|---|---|---|---|---|
| 1 | behaviour | remat-v1-…102558Z | `data/intelligence/behaviour/runs/<rid>/behaviour_fit_manifest.json` | complete | master (sha 5020956f) | 167,331 rows; 117,132 train (70%); 7 profiles; 116 baselines; labels+baselines |
| 2 | correlation | remat-v1-…102558Z | `data/intelligence/correlation/runs/<rid>/correlation_fit_manifest.json` | complete | behaviour (latest = new run) | 850 pairs / 7 profiles; 54 strong, 4 redundant; 850 shift deltas |
| 3 | pca | remat-v1-…102558Z | `data/intelligence/pca/runs/<rid>/pca_fit_manifest.json` | complete | behaviour (latest = new run) | 7 profiles fitted, 0 skipped; 14 joblib models; T²/Q scores (is_train preserved) |
| 4 | anomaly | remat-v1-…102558Z | `data/intelligence/anomaly/runs/<rid>/anomaly_fit_manifest.json` | complete | pca = new run; behaviour (latest) | 167,331 scored; 33,186 flagged (31,299 anomaly / 1,887 warning); 50 top events |
| 5 | sensor-health | remat-v1-…102558Z | `data/intelligence/sensor_health/runs/<rid>/sensor_health_manifest.json` | complete | behaviour (latest = new run) | 17 sensors; 141 events (138 warning / 3 faulty, 1 persistent); 1 quarantine rec |
| 6 | operational-context | remat-v1-…102558Z | `data/context/operational/runs/<rid>/operational_context_manifest.json` | complete | sensor-health = new run; **BOM = 20260612T124909Z** | 167,331 rows aligned (Gate A); 2,575 transitions; steam on 78,087 / off 57,575 / intermittent 31,669 — **addendum skipped** |
| 7 | drift | remat-v1-…102558Z | `data/intelligence/drift/runs/<rid>/drift_manifest.json` | complete | anomaly, pca, correlation, sensor-health, operational = new run | 208,260 metric rows; 35,949 scored windows; 187 events; raw_vs_healthy comparison (18,698 rows) |
| 8 | incidents | remat-v1-…102558Z | `data/intelligence/incidents/runs/<rid>/incidents_manifest.json` | complete | drift, sensor-health, anomaly, operational = new run; **BOM = 20260612T124909Z** | 1,038 candidates → 88 incidents (1 suppressed); 675 relationships; 148 actions; 39 review-pack rows; drift_addenda |
| 9 | reference | remat-v1-…102558Z | `data/intelligence/reference/runs/<rid>/reference_governance_manifest.json` | complete | behaviour, sensor-health, incidents, drift = new run | 1 reference (reference_v1, behaviour-provenanced); 1 quarantine proposal; 3 candidate proposals; residual_material=False |
| 10 | scoring-experiment | remat-v1-…102558Z | `data/intelligence/scoring_experiments/runs/<rid>/controlled_scoring_manifest.json` | complete | anomaly, sensor-health, drift, incidents, operational, reference = new run | 33,186 non-normal; 30,096 suppressed (90.69%); decision-report addendum |

Forensic addenda generated: `data/intelligence/forensics/drift_addenda/<rid>/` (incidents),
`data/intelligence/forensics/reference_decision/<rid>/` (scoring).

---

## C. Lineage validation

**How compatibility is proven (strict sweep, read-only):**
- All 10 manifests parse, report `completion_status = complete`, have `run_id` == their directory
  name, and `component` == the expected component name.
- For every component, `resolve_run(root, "latest", …)` returns the `remat-v1-20260616T102558Z`
  run (the `remat-v1-` prefix sorts after every `2026…` id).
- Every recorded upstream `*_run_id` field equals the new run id, with BOM equal to the reused
  `20260612T124909Z`:
  - anomaly → `pca_run_id`
  - operational → `sensor_health_run_id`, `bom_context_run_id`
  - drift → `anomaly_run_id`, `pca_run_id`, `correlation_run_id`, `sensor_health_run_id`, `operational_context_run_id`
  - incidents → `drift_run_id`, `sensor_health_run_id`, `anomaly_run_id`, `operational_context_run_id`, `bom_context_run_id`
  - reference → `behaviour_run_id`, `sensor_health_run_id`, `incidents_run_id`, `drift_run_id`
  - scoring → `anomaly_run_id`, `sensor_health_run_id`, `drift_run_id`, `incidents_run_id`, `operational_context_run_id`, `reference_run_id`
- Components without a `--behaviour-run` flag (correlation, pca, anomaly, sensor-health) consume
  behaviour via latest-completed resolution; their manifests record `behaviour_fit_timestamp =
  2026-06-16T10:26:23.686395+00:00` — identical to the new behaviour run — and sensor-health's
  `behaviour_artifact_path` ends with the new run id. This proves they consumed the new behaviour
  run, not the old `20260615T231049Z` or the legacy fixed-path artifacts.

**Pinned run ids:** all downstream upstreams were pinned explicitly on the CLI to
`remat-v1-20260616T102558Z` (overriding any policy `latest`/stale pin); BOM pinned to
`20260612T124909Z`.

**BOM reuse, not regeneration:** the latest BOM run `20260612T124909Z` recorded
`master_dataset_sha256 = 5020956f…`, `master_timeline_row_count = 167331`,
`completion_status = complete`, and resolves under the hardened checks. The current master sha is
identical, so the run was reused (pinned) rather than regenerated. Its directory is unchanged
(mtime 2026-06-12).

**No legacy artifacts consumed.** The pre-hardening fixed-path behaviour files
(`data/intelligence/behaviour/{behaviour_fit_manifest.json, profiles/, baselines/, validation/}`,
dated 2026-06-02) remained inert — they live outside `runs/`, are never scanned by `resolve_run`,
and no `--profile-labels/--baselines/--behaviour-manifest` flags were passed. The old per-component
runs (e.g. anomaly `20260611T173316Z`) were neither consumed (every upstream was pinned to the new
run) nor modified.

---

## D. Corrected scoring results (new real-data numbers)

All numbers below are from the new scoring run `remat-v1-20260616T102558Z` (not historical).

**Baseline (`baseline_v1`, original persisted picture):**
- warning: **1,887**; anomaly: **31,299**; total non-normal: **33,186** (of 167,331 rows).

**Quarantine-aware interpretive scenario (`quarantine_inlet_hopper_points_interpretive`):**
- adjusted warning: **1,887**; adjusted anomaly: **1,203**.
- `row_suppressed_for_review`: **30,096** (suppression rate **90.69%**) — **every suppressed row is
  evidence-backed** (30,096 carry a `suppression_reason` and `row_level_evidence_match`; **0 rows
  suppressed without row-level evidence**).
- `incident_explained_for_review`: **30,089** — tracked **separately** from row-level suppression
  (a 7-row gap between the two gates, which the pre-hardening conflated semantics would have hidden).
- **Remaining review backlog:** **1,203 anomaly + 1,887 warning = 3,090 rows**.
- **Healthy-only-proxy residual:** **23** windows (0.2%); raw drift mass **209.6 → 90.5** (57%
  reduction) under the healthy-only view (from the decision summary).

**Top remaining (post-suppression) entities:**
- Sensors: `inlet_hopper_humidity` 1,653 · `inlet_hopper_points` 1,411 · `feeder_hopper_temp` 1,016
  · `inlet_hopper_temp` 987 · `steam_valve_temp_me2` 694.
- Profiles: `stopped` 1,445 · `high_production` 1,224 · `mid_production` 140 · `low_production` 136.
- Contexts: `all_sensors_healthy` 3,006 · `sensor_warning` 66 · `sensor_faulty` 18.

**Immutability of original scores:** `original_severity` and `original_combined_score` are preserved
for all 33,186 rows and equal the anomaly run's persisted `severity`/`combined_score`; the
quarantine adjustment lives **only** in the separate `adjusted_review_severity` /
`adjusted_review_score` columns. No PCA/Mahalanobis recompute, no refit.

---

## E. Comparison with the previous (pre-hardening) interpretation

- **Headline suppression magnitude is similar** (≈30,096 / 91% of non-normal rows are
  `inlet_hopper_points`-instrumentation-dominated), confirming the real-data physics is unchanged.
- **The corrected semantics are the substantive difference.** Previously, broad suppression was an
  **upper bound** that conflated "this row sits inside an instrumentation-explained incident" with
  "this row itself has instrumentation evidence." The hardened, rematerialized view enforces
  **row-level evidence** for every suppressed row (30,096 with evidence, **0 without**) and reports
  **incident-level explanation separately** (30,089). The 7-row difference is exactly the kind of
  case the correction surfaces rather than silently folding into the suppressed mass.
- Treat the **new counts as the corrected decision-support view**; treat any earlier figure as a
  historical upper bound.

---

## F. Decision report outcome

Source: `data/intelligence/forensics/reference_decision/remat-v1-20260616T102558Z/`
(`decision_summary.md`, `decision_matrix.parquet`, `candidate_actions.parquet`,
`required_plant_records.parquet`, `risk_assessment.parquet`).

- **Quarantine proposal (`inlet_hopper_points`):** status `pending_review`,
  **`approval_required = True`, `approved = False`** — unchanged. Nothing in this sprint approves it.
- **Reference v2:** **still deferred** — `design_reference_candidate_v2` is *not recommended*
  (`residual_material = False`; residual healthy-only drift below the materiality threshold).
- **Plant records still required (Yes):** maintenance log (did `inlet_hopper_points` fail/get
  serviced?), sensor-channel log (confirm instrumentation failure), operator notes, setpoint changes
  (rule out a deliberate process change).
- **Recommended order (decision-support only):**
  1. Inspect/confirm the `inlet_hopper_points` channel failure (recommended, high).
  2. Approve the quarantine **only after** human review (recommended, high, requires approval).
  3. Run a controlled rescore/refit **only after** quarantine approval (recommended, medium, requires refit).
  4. Defer Reference v2 (residual immaterial).
  5. Collect the required plant records (recommended, high).

---

## G. Artifacts generated

New run directories (all under run id `remat-v1-20260616T102558Z`):

```
data/intelligence/behaviour/runs/remat-v1-20260616T102558Z/            (8 files)
data/intelligence/correlation/runs/remat-v1-20260616T102558Z/          (8 files)
data/intelligence/pca/runs/remat-v1-20260616T102558Z/                  (41 files)
data/intelligence/anomaly/runs/remat-v1-20260616T102558Z/              (32 files)
data/intelligence/sensor_health/runs/remat-v1-20260616T102558Z/        (9 files)
data/context/operational/runs/remat-v1-20260616T102558Z/               (9 files; addendum skipped)
data/intelligence/drift/runs/remat-v1-20260616T102558Z/                (16 files)
data/intelligence/incidents/runs/remat-v1-20260616T102558Z/            (11 files)
data/intelligence/reference/runs/remat-v1-20260616T102558Z/            (7 files)
data/intelligence/scoring_experiments/runs/remat-v1-20260616T102558Z/  (9 files)
data/intelligence/forensics/drift_addenda/remat-v1-20260616T102558Z/        (13 files)
data/intelligence/forensics/reference_decision/remat-v1-20260616T102558Z/  (6 files)
```

Not generated this run: `data/intelligence/forensics/context_addenda/<rid>/` (operational-context
forensic addendum — deferred, see §A.2 / §I).

Source changes (working tree, uncommitted — the blocker fix):
```
M src/intelligence/sensor_health/run_sensor_health.py     (None-labels manifest fix)
M tests/unit/intelligence/sensor_health/test_run_and_validation.py  (regression test)
```

---

## H. QA results

| Check | Result |
|---|---|
| pytest | **552 passed** (551 baseline + 1 new sensor-health regression), exit 0 |
| ruff check . | All checks passed |
| ruff format --check . | 317 files already formatted |
| mypy src | Success: no issues found in 184 source files |
| Lineage sweep (10 manifests) | **PASS** — parse / complete / run_id==dir / component / latest==new run |
| Transitive upstream pins | **PASS** — every recorded `*_run_id` == new run (BOM = reused run) |
| BOM reuse + compatibility | **PASS** — complete, master_sha matches, resolvable, dir unchanged |
| Master immutability | **PASS** — sha256 identical before & after (`5020956f…`) |
| Original anomaly scores immutable | **PASS** — anomaly score file untouched; scoring `original_*` == anomaly persisted values; adjustments in separate `adjusted_review_*` fields |
| No-overwrite | **PASS** — all pre-existing runs still present and unmodified; only new `remat-v1-…` dirs added |

QA was run twice: once after the sensor-health fix (before resuming the chain) and once after the
full chain completed; both green.

---

## I. Remaining risks

**Must fix before dashboard:** none blocking. (The sensor-health latest-resolution crash is fixed
with a regression test.)

**Should fix soon:**
1. **Operational-context forensic addendum cannot be rematerialized.** Its config
   (`configs/operational_context.yaml`) pins `anomaly_run: 20260611T173316Z` and
   `forensic_run: 20260612T101850Z` — both pre-hardening, now unresolvable — and the CLI exposes no
   `--anomaly-run` / `--forensic-run` override. Recommend: (a) add those CLI overrides to
   `src/context/operational/run_operational_context.py`, and (b) decide whether the standalone
   `forensics` component should be rematerialized; then regenerate the operational context-addenda
   against the new anomaly run. The core operational timeline consumed downstream is unaffected.
2. **Uncommitted source change.** The sensor-health fix + test are in the working tree (tree no
   longer at `658cd58`). Commit them (e.g. `fix(sensor-health): build manifest under None-labels
   latest resolution`) so the rematerialized chain has a committed code baseline.

**Can defer / document:**
1. **`remat-v1-` lexicographic property.** Because `remat-v1-…` sorts after every numeric
   timestamp, this run stays the bare-`latest` winner indefinitely; a future plain-timestamp run
   would **not** auto-supersede it via `latest`. This is desired for now (the remat chain is
   canonical), but any future canonical chain must be pinned explicitly or named to sort later.
2. **Inert pre-hardening run dirs.** Old per-component runs (correlation/pca/anomaly/drift/
   incidents/reference/scoring + operational/bom older runs) remain on disk but are unresolvable
   under hardened checks; they are inert. Optional cleanup; not required.

---

## J. Recommended next action

> **Run a second targeted Codex review over the hardened and rematerialized chain before dashboard planning.**

(Not started automatically.)
