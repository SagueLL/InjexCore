# Reference Governance (v1)

`src/intelligence/reference/` — tracks the **current reference**, **candidate
references** and **quarantine proposals** as reviewable, run-versioned records,
turning persisted sensor-health / incident / drift evidence into proposals for
a human reviewer.

**Reference Governance proposes and tracks decisions. It does not approve a
quarantine or refit a model automatically.** Every proposal it emits is
`pending_review` with `approved=False`. It never excludes a sensor, never
modifies the original reference window and never touches an upstream artifact.
Runs are versioned under `data/intelligence/reference/runs/<run_id>/`
(`reference_governance_manifest.json` written last = completion marker).

## 1. Inputs

Three completed upstream runs (policy pins in
`configs/reference_governance.yaml` → `upstream`, or `--<name>-run` CLI flags),
plus the behaviour fit manifest and the master file:

* **sensor-health** run — quarantine recommendations + faulty events;
* **incidents** run — incidents (sensor-fault ids) + recommended actions;
* **drift** run — drift events + the raw-vs-healthy-only comparison;
* **behaviour run** — the latest *completed* run-versioned behaviour run; its
  manifest self-reports the train window **and** `master_dataset_sha256`, the
  provenance `reference_v1` is seeded from (GOV-01);
* **master dataset** — hashed with `file_sha256` for Gate A.

### Gate A — upstream compatibility

Stop (never degrade) when: the behaviour manifest has no train window; the
behaviour manifest carries **no** `master_dataset_sha256` or one that differs
from the current master (so `reference_v1` provenance is unverifiable); or any
upstream run that records a `master_dataset_sha256` was fitted on a *different*
master than the one on disk. `reference_v1.dataset_sha256` is the behaviour
manifest's sha — never the current master substituted in.

## 2. Reference registry

Deterministically re-seeded every run — there is no hidden cross-run state.
Row 0 is always the immutable baseline (`registry.py`):

```
reference_id        = reference_v1
reference_type      = baseline
status              = current
source_train_start  = <behaviour fit_window.train_start>
source_train_end    = <behaviour fit_window.train_end>
dataset_sha256      = <behaviour manifest master_dataset_sha256>   # GOV-01 provenance
excluded_sensors    = ""        reason = "original leakage-safe train reference"
```

Schema: `reference_id, reference_type, status, created_at, source_train_start,
source_train_end, dataset_sha256, sensor_scope, profile_scope, context_scope,
excluded_sensors, source_artifacts, reason, notes`. Multi-valued fields are
pipe-joined strings (the repo idiom).

## 3. Quarantine proposals

One pending proposal per sensor that **both** has an upstream sensor-health
quarantine recommendation **and** is on the `quarantine.candidate_sensors`
allow-list (empty list = accept every recommended sensor). Source ids are wired
from the upstream evidence (the sensor-fault incident, the faulty sensor-health
event, the sensor-drift event) — never fabricated.

```
status = pending_review   approval_required = True   approved = False
recommended_action = quarantine_from_process_scoring   review_status = pending_review
```

Schema: `quarantine_proposal_id, sensor, start_timestamp, end_timestamp,
status, reason, source_incident_ids, source_sensor_health_event_ids,
source_drift_event_ids, recommended_action, approval_required, approved,
risk_if_ignored, risk_if_applied, expected_effect, review_status`.

For the real data this is the `inlet_hopper_points` flatline-zero proposal
(2024-09-17 16:23:22 → 2024-10-08 13:57:28), `approved=False`.

## 4. Candidate reference proposals

Three mandatory proposals (`proposals.py`), all `status=pending_review`:

* **A. `quarantine_only`** — `excluded_sensors=[inlet_hopper_points]`,
  `model_refit_required=False`. Evaluate whether the instrumentation fault
  explains the anomaly mass without changing the reference.
* **B. `reference_candidate_v2`** — `excluded_sensors=[inlet_hopper_points]`,
  `model_refit_required=True`, `approval_required=True`. The candidate train
  window is left **null** (never fabricated). Its `evidence_summary` carries the
  residual-drift materiality assessment and states explicitly: *"This is a
  candidate design only. No model artifacts have been trained."*
* **C. `external_records_review`** — always created;
  `required_human_records = maintenance log | sensor channel log | operator
  notes | setpoint changes`.

### Proposal statuses

`candidate → pending_review → approved | rejected | deprecated`. New proposals
default to `pending_review`; the component never advances them.

## 5. Residual-drift materiality

`residual_diagnostic` reads the drift run's sensor-scope raw-vs-healthy
comparison and reports `n_residual_windows`, `residual_fraction`, `raw_mass`,
`healthy_mass`, `reduction_pct` and a `material` boolean. Residual is material
only when **both** gates pass (conservative on purpose): at least
`candidate_v2.residual_window_min` residual windows **and** at least
`candidate_v2.residual_fraction_min` of all sensor windows. This drives whether
proposal B recommends designing a Reference v2 now or deferring it.

On the real data: 23 residual windows of 10,472 (0.2 %), raw mass 209.6 →
healthy 90.5 → **`material=False`** → defer Reference v2.

## 6. Decision log

`decisions.py` seeds one `pending` row per proposal (3 reference + 1
quarantine = 4 rows), all `status=pending_review`, `decided_by=""`. The audit
ledger opens with every proposal explicitly unresolved; a human advances it.

## 7. Outputs

```
data/intelligence/reference/runs/<run_id>/
├── reference_registry.parquet
├── reference_proposals.parquet
├── quarantine_proposals.parquet
├── decision_log.parquet
├── reference_governance_report.md
├── reference_governance_findings.json
└── reference_governance_manifest.json   written LAST — marks completion
```

The manifest records the upstream run ids, the master sha, `approved_count`
(always 0), the residual diagnostic, and the no-automatic-approval statements.

## 8. CLI

```bash
python -m src.intelligence --component reference                 # write run
python -m src.intelligence --component reference --no-write       # diagnostic only
python -m src.intelligence.reference.run_reference --sensor-health-run latest
```

Flags: `--config`, `--sensor-health-run`, `--incidents-run`, `--drift-run`,
`--output-root`, `--run-id`, `--no-write`, `--log-level`.

## 9. Limitations & future Reference v2 role

* The registry is regenerated deterministically each run; it is **not yet** a
  persistent cross-run ledger of human decisions — the decision log opens fresh
  every run.
* Materiality is a transparent threshold over the drift run's already-computed
  residual; it does not re-derive drift.
* This component never creates an *approved* Reference v2. Promoting the
  `reference_candidate_v2` proposal into a trained Reference v2 (refit on a
  post-fault, quarantine-aware window) is explicit, human-approved, future work
  — gated on plant-record review and the controlled rescoring experiment.

See also: [controlled_scoring_experiment.md](controlled_scoring_experiment.md).
