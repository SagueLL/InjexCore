# Controlled Scoring Experiment (v1)

`src/intelligence/scoring_experiment/` — runs controlled, **interpretive**
post-processing scenarios over the *persisted* anomaly, drift and incident
outputs, then assembles a **decision-report forensic addendum** for human
review.

**Controlled scoring experiments do not mutate original scores. Healthy-only
and quarantine-aware outputs are interpretive decision-support views.** No
model is refitted; no PCA/Mahalanobis matrix is recomputed from an altered
feature matrix; the original `severity` and `combined_score` are preserved
verbatim. Runs are versioned under
`data/intelligence/scoring_experiments/runs/<run_id>/`
(`controlled_scoring_manifest.json` written last = completion marker).

## 1. Inputs

Six completed upstream runs (policy pins in `configs/scoring_experiment.yaml` →
`upstream`, or `--<name>-run` CLI flags): the **anomaly** run (per-row scores +
`affected_variables`), the **sensor-health** run, the **drift** run
(raw-vs-healthy comparison), the **incidents** run (incidents + suppressed
duplicates), the **operational-context** run (per-timestamp context), and the
**reference governance** run (the PENDING, unapproved quarantine proposal +
residual diagnostic).

### Gate A — upstream compatibility

Stop when the anomaly scores and the operational context timeline are not
row-aligned (the scenarios join them per timestamp), or any upstream run that
records a `master_dataset_sha256` was fitted on a different master.

## 2. Interpretive vs true rescoring

This component is **post-processing**, not rescoring. The `adjusted_review_*`
columns are a review reinterpretation; `adjusted_review_score` equals
`original_combined_score` by construction because **nothing is rescored**. A
true re-score (recomputing PCA/Mahalanobis from a matrix with the quarantined
channel removed) is explicitly out of scope and only happens later, after
human quarantine approval, under a separate refit experiment.

## 3. Scenarios

| Scenario | Granularity | What it does |
|---|---|---|
| `baseline_v1` | per-row | Original persisted scores, unchanged. |
| `quarantine_<sensor>_interpretive` | per-row | Down-ranks the **review severity** of rows whose own evidence is dominated by the pending-quarantine sensor. |
| `healthy_only_proxy` | window | Reads the drift run's raw-vs-healthy comparison; labels every output a proxy. |
| `candidate_reference_needed` | diagnostic | Decides whether residual healthy-only drift justifies *designing* a Reference v2. No training. |

The quarantine scenario id is **derived** from the pending proposal sensor(s),
not hardcoded (GOV-02): one target → `quarantine_<sensor>_interpretive`
(e.g. `quarantine_inlet_hopper_points_interpretive` on the real data), several →
`quarantine_proposals_interpretive`, none → no quarantine scenario.

### Scenario 1 — quarantine-aware (the core interpretive step)

Two notions are kept **separate** (LOG-01):

* `incident_explained_for_review` — the row lies inside an anomaly-burst window
  already explained by a sensor fault. This is incident-level *coverage* and is
  recorded for **every** non-normal row in the window, suppressed or not.
* `row_suppressed_for_review` — the row is actually down-ranked, which requires
  its **own** row-level evidence (`row_level_evidence_match`): the quarantine
  sensor appears in the row's anomaly `affected_variables` (for a pending
  target, also faulty/quarantined at that timestamp inside the window).

An unrelated process anomaly inside an explained burst window is therefore
reported as incident-explained but **stays unsuppressed**. For suppressed rows
`dominant_faulty_sensor` is set, `adjusted_review_severity` becomes `normal`,
and **`original_severity` / `original_combined_score` are untouched**.

On the real data: 30,096 of 33,186 non-normal rows (~91 %) are suppressed as
`inlet_hopper_points`-dominated, dropping the review backlog from 31,299 to
1,203 anomalies — interpretive only.

## 4. Outputs

```
data/intelligence/scoring_experiments/runs/<run_id>/
├── scenario_definitions.parquet
├── scenario_scores.parquet                    per-row review view (non-normal rows; baseline + quarantine-aware)
├── scenario_incident_comparison.parquet
├── scenario_anomaly_rate_comparison.parquet   full-population counts before/after suppression
├── scenario_drift_comparison.parquet          healthy-only proxy + per-profile residual
├── scenario_recommendations.parquet
├── controlled_scoring_report.md
├── controlled_scoring_findings.json
└── controlled_scoring_manifest.json           written LAST — marks completion
```

`scenario_scores` is restricted to baseline-non-normal rows (the only rows
where a review adjustment is meaningful); full-population counts live in the
comparison tables.

## 5. Decision report (forensic addendum)

After the run dir, unless `--skip-decision-report`, `decision_report.py`
resolves the reference run + this scoring run and writes the human-facing
decision pack under `data/intelligence/forensics/reference_decision/<run_id>/`:

```
decision_matrix.parquet          candidate_actions.parquet
risk_assessment.parquet          required_plant_records.parquet
decision_summary.md              reference_decision_manifest.json   (written LAST)
```

### Decision matrix

Evaluates `do_nothing`, `inspect_sensor_channel`,
`approve_quarantine_<sensor>` (derived from the proposal —
`approve_quarantine_inlet_hopper_points` on the real data, or
`approve_quarantine_proposed_sensors` for several),
`controlled_rescore_after_quarantine`, `design_reference_candidate_v2`,
`collect_plant_records` — each with
`recommended, priority, expected_benefit, risk_if_done, risk_if_not_done,
requires_human_approval, requires_model_refit, requires_external_records,
supporting_evidence, blocking_uncertainties`.

On the real data the honest recommendation is: **(1)** inspect/confirm the
`inlet_hopper_points` channel, **(2)** approve the quarantine only after human
review, **(3)** run a controlled rescore/refit only after approval, **(4)**
defer Reference v2 (residual healthy-only drift is immaterial), **(5)** collect
plant records. `approve_quarantine_*` always `requires_human_approval=True`;
`design_reference_candidate_v2` recommended only when residual is material.

## 6. CLI

```bash
python -m src.intelligence --component scoring-experiment                  # write run + decision report
python -m src.intelligence --component scoring-experiment --no-write        # diagnostic only
python -m src.intelligence --component scoring-experiment --skip-decision-report
python -m src.intelligence.scoring_experiment.run_scoring_experiment --reference-run latest
```

Flags: `--config`, `--anomaly-run`, `--sensor-health-run`, `--drift-run`,
`--incidents-run`, `--operational-run`, `--reference-run`, `--output-root`,
`--decision-root`, `--run-id`, `--skip-decision-report`, `--no-write`,
`--log-level`.

## 7. Limitations & future role

* Every adjustment is **interpretive**: original scores are never mutated, no
  model is refitted, no PCA/Mahalanobis matrix is recomputed.
* The quarantine used is the **pending, unapproved** proposal; nothing here
  approves it or excludes a sensor.
* A true rescoring/refit excluding the quarantined channel — and any approved
  Reference v2 — is explicit, human-gated future work, informed by this
  experiment's evidence and the decision report.

See also: [reference_governance.md](reference_governance.md).
