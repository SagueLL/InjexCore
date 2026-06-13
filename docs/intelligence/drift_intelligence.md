# Drift Intelligence (v1)

`src/intelligence/drift/` — structural-change detection over persisted
Intelligence-Layer artifacts. Answers: has the process changed structurally?
Has a *sensor* changed structurally? When did the change start, in what
temporal shape, and does it remain after excluding faulty sensors
analytically?

Strictly read-only: it never refits a model, never modifies thresholds,
Behaviour profiles or the reference window, and never overwrites an upstream
artifact. Runs are versioned under `data/intelligence/drift/runs/<run_id>/`
(`drift_manifest.json` written last = completion marker).

## 1. Purpose

Anomaly Intelligence flags rows; Sensor Health flags instrumentation. Drift
Intelligence sits above both and measures *windowed distribution change*
against the behaviour train window, distinguishing **sensor drift** from
**process drift** from **context shift** from **profile-composition shift** —
instrumentation failure is never presented as process degradation.

## 2. Inputs

Five completed upstream runs (resolved via the completed-run convention,
`latest` or pinned per `configs/drift_intelligence.yaml` → `upstream`, or the
`--<name>-run` CLI flags) plus behaviour's fixed-path artifacts:

| Input | What is consumed |
|---|---|
| `data/datasets/master/master_dataset.parquet` | column-projected raw process sensors |
| behaviour `profile_labels.parquet` + fit manifest | `profile`, `is_train` — the leakage contract |
| anomaly run (`anomaly_fit_manifest.json`) | per-row detector scores, severity, `triggered_detectors`, `affected_variables` |
| pca run (`pca_fit_manifest.json`) | per-profile `t2` / `q_spe` / `reconstruction_error` + per-feature contributions |
| correlation run (`correlation_fit_manifest.json`) | train references + train-vs-validation Pearson shift |
| sensor-health run (`sensor_health_manifest.json`) | quality timeline (health mask) + events (override/promotion) |
| operational-context run (`operational_context_manifest.json`) | master-aligned context timeline (composition shifts) |

Gate A cross-checks every run: structural identity (row count + index span;
the projected master can never match the full-master sha by construction),
file sha for the context layers, and that the operational run merged the
same sensor-health run drift resolves. Mismatches are warn-findings; label
or timeline misalignment is a blocker (`DriftBlockerError`).

## 3. Views: raw vs healthy-only

* **raw** — all configured process sensors.
* **healthy_only** — sensors flagged `faulty` / `quarantine_recommended` by
  Sensor Health are excluded *analytically* for the affected timestamps
  (boolean in-memory mask decoded from the quality timeline; masked cells
  removed before any metric, so `missingness_shift` measures genuine
  missingness only).

**The healthy-only view is an interpretive comparison. It does not refit
upstream models or mutate original anomaly scores**, and no sensor is
excluded from production scoring. Multivariate healthy-only handling has two
honest levels:

* **Level A (always)** — healthy-view multivariate events whose evidence
  dominance is ≥ `healthy_view.evidence_dominance_fraction` are excluded
  from the healthy view and recorded in `unsupported_scopes.parquet` +
  `raw_vs_healthy_only_comparison.parquet`. Dominance per window is the max
  of (a) pca reconstruction mass on excluded sensors and (b) the fraction of
  flagged rows whose *rank-1* `affected_variables` attribution is excluded.
* **Level B (`multivariate_proxy: true`)** — a per-row analytical proxy:
  `q_spe` minus the persisted per-feature contributions of excluded sensors,
  clipped at zero, always labeled **`healthy_only_proxy`**. A documented
  approximation, never presented as rescoring; sensors outside a profile's
  pca feature set contribute nothing to the subtraction. Proxy events are
  exempt from the Level-A filter (they *are* the healthy-only answer).

## 4. Drift measurement

All references are fitted on `is_train = True` rows only — global plus per
supported profile (the Iteration B profile gate). Windows are tumbling
(`windows.granularity`: `daily` default; `hourly` supported, ~24× the
distribution-metric work).

* **Univariate** (per sensor, per scope): `mean_shift`, `median_shift`,
  `std_shift`, `iqr_shift`, `zero_rate_shift`, `missingness_shift`,
  `unique_value_collapse`, `psi`, `ks_statistic`, `wasserstein_distance`
  (W1 normalized by the train robust scale). PSI/KS/W1 are pure-numpy 1-D
  ECDF forms (no scipy dependency; unit tests verify equality with scipy).
* **Multivariate**: the same windowed machinery over *persisted* scores
  (anomaly detector scores + concatenated per-profile pca scores — nothing
  recomputed), plus `severity_rate_shift` and `detector_agreement_shift`.
* **Context**: categorical PSI + total variation of the operational-timeline
  composition (profile, steam, sensor-health, product, recipe, BOM status)
  against the train distribution; new/disappeared categories reported.
* **Correlation**: classification of the persisted train-vs-validation
  Pearson shift (`sign_flip` / `newly_strong` / `collapsed` / `large_shift`);
  pairs dominated by a sensor with a persistent strong instrumentation event
  are `sensor_drift_evidence`, not `process_correlation_break`. Validation
  Spearman values are not persisted upstream — Spearman *changes* are an
  upstream limitation, not fabricated.

## 5. Scoring, calibration and the sensor-health override

Per window: metrics normalized by configured caps → weighted mean →
**train-window self-calibration**: `calibrated = clip((score −
train_quantile) / excess_cap, 0, 1)` per (scope, view, entity, profile) — a
window drifts only by the margin it exceeds the envelope the train period
itself produced (small-window sampling noise and naturally variable context
mixes cancel instead of flagging). A persistence bonus applies after
consecutive active windows; severity cuts map the score into
`info / warning / anomaly / critical`. The uncalibrated score is kept in
`drift_scores.parquet` for transparency.

**Sensor-health override** (spec §7.5): sensor windows overlapping a strong
instrumentation event (`flatline_zero`, `counter_reset`,
`missingness_spike`) by ≥ `min_overlap_fraction` are reclassified
`sensor_drift` (severity never reduced).

## 6. Events

Taxonomies (closed vocabularies in `policy.py`): scope `sensor / profile /
context / correlation / multivariate / global`; drift type `sensor_drift /
process_drift / context_shift / correlation_shift / multivariate_shift /
profile_composition_shift / unknown_shift`; temporal shape `abrupt /
progressive / episodic / persistent / transient / unknown`; status
`candidate / active / persistent / resolved / dismissed / pending_review`
(`dismissed` is never auto-assigned).

Consecutive active windows merge into events (gap-merge); shape precedence:
episodic (toggling) → abrupt (≤ N windows to ~peak) → progressive (slow
monotone onset) → persistent / transient. Additionally, strong *faulty*
sensor-health events are **promoted** directly into `sensor_drift` events
with their precise sub-window timing (a 2.4 h missingness outage inside a
daily window is guaranteed to surface); overlapping window-derived events
are absorbed into the promoted one, recorded in its evidence. Every event
defaults to `review_status = "pending_review"`.

## 7. Outputs

`data/intelligence/drift/runs/<run_id>/`: `scores/drift_scores.parquet`,
`events/drift_events.parquet`, eleven summary tables under `summaries/`
(sensor / profile / context / correlation / multivariate summaries, the four
context shift tables, `raw_vs_healthy_only_comparison.parquet`,
`unsupported_scopes.parquet`), `drift_report.md`, `drift_findings.json` and
`drift_manifest.json` (**last**; records all consumed run ids, the master
sha256, train/validation windows, window/threshold config, event counts and
the no-refit statements).

## 8. CLI

```bash
python -m src.intelligence --component drift                 # via dispatcher
python -m src.intelligence --component drift --no-write --log-level DEBUG
python -m src.intelligence.drift.run_drift                   # direct
python -m src.intelligence.drift.run_drift --anomaly-run 20260611T173316Z \
    --pca-run latest --sensor-health-run latest              # pin upstream runs
```

## 9. What the first real run showed (run `20260612T221931Z`)

187 events (60 persistent). The `inlet_hopper_points` flatline surfaced as a
promoted **persistent critical `sensor_drift`** event starting exactly
2024-09-17 16:23:22; the `granulator_roller_gap` missingness episode stayed
a **separate transient resolved** event (2024-09-12 10:13 → 12:36).
Validation-window sensor drift mass fell ~70 % under the healthy-only
interpretation (active windows 131 → 11); 71 healthy-view multivariate
events were excluded as dominated by faulty-sensor evidence (mean dominance
≈ 1.0 post-onset), while the labeled `healthy_only_proxy` events and a
residual `q_spe` elevation in production profiles (whose pca models do not
even include the failed sensor) survived as candidate findings. Steam and
BOM context compositions stayed within their own train envelopes.

## 10. Limitations

* The healthy-only view is interpretive — only a controlled rescoring
  experiment (Reference Governance, Iteration C Part 3) can quantify the
  residual exactly.
* Correlation drift re-reads one persisted train-vs-validation delta;
  windowed correlation recomputation and validation Spearman are out of
  scope here.
* Train calibration assumes the train window is in-control; a contaminated
  reference dilutes sensitivity (Reference Governance's problem to solve).

## 11. Future use

Drift events feed Incident Aggregation
([incident_aggregation.md](incident_aggregation.md)) and, with the
raw-vs-healthy comparison, are the evidence base for the Reference
Governance layer (reference candidate design + controlled scoring
experiment) planned as Iteration C Part 3.
