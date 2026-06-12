# InjexCore — Anomaly Intelligence v1

Reference document for the fourth component of the **Intelligence Layer**.
Anomaly Intelligence v1 detects deviations from each profile's historical
normal behaviour with four simple, explainable detectors — no deep learning,
no forecasting, no streaming.

It answers, per row: *is the machine behaving differently from its training
reference? which detector saw it? which profile was active? which sensors
provide interpretable evidence? how severe is it?*

---

## 1. Detectors

All detectors are fitted **per supported profile** on the **training window
only** (behaviour's persisted `is_train` flag) and score every row of their
profile.

| Detector | Score | Fitted artifact | Evidence |
|---|---|---|---|
| **statistical** | max robust z = \|x − median\| / (iqr/1.349) across the profile's baseline sensors; percentile breach flags (p05/p95) | none — the behaviour `baselines.parquet` *is* the model | top-k sensors above the robust-z threshold |
| **mahalanobis** | D² under a Ledoit-Wolf-regularized covariance | mean + precision matrix, persisted as transparent JSON | exact signed contributions `c_i = d_i·(P d)_i` (sum to D²; ranked by \|c_i\|, sign retained — cross-terms can be negative, documented) |
| **pca** (T² + Q) | Hotelling T² and Q/SPE from the **persisted pca run** (`--pca-run`, default `latest`) | thresholds = empirical training-score percentiles (not F-distribution limits — the data is autocorrelated and non-normal) | top per-feature reconstruction contributions (Q) |
| **isolation_forest** | `-score_samples` of a seeded `IsolationForest` | joblib-persisted model | **none** — IF cannot attribute reliably, and inventing root causes would be fabrication; sensor evidence comes from the interpretable detectors |

## 2. Scoring, combination, severity

Individual detector scores are **always preserved** in the output. Each raw
score is normalized to [0, 1] through the empirical CDF of its own training
scores per (profile, detector) — a 1001-point quantile grid persisted in
`combine_calibration.parquet`, so the normalization is reproducible. Then:

- `combined_score` = **max** of available normalized scores (default,
  conservative) or a configurable `weighted_mean`;
- `severity` ∈ `normal` / `warning` / `anomaly` via percentiles of the
  **training** combined score per profile (default p99 / p99.9);
- rows of profiles no detector supports are labelled **`unscored`** — never
  silently "normal";
- `triggered_detectors` lists detectors above their train trigger percentile;
- `affected_variables` is the deduplicated union of evidence from the
  *triggered interpretable* detectors;
- `evidence` (flagged rows only) is a JSON payload with per-detector
  raw + normalized scores and a descriptive note — wording stays at
  "Unusual behaviour detected. Primary contributing signals: …", never a
  causal claim like "mechanical blockage confirmed".

Output schema (`scores/anomaly_scores.parquet`):

```
timestamp, profile,
statistical_score, mahalanobis_score, pca_q_score, pca_t2_score,
isolation_forest_score, combined_score,
severity, triggered_detectors, affected_variables, evidence
```

## 3. Outputs

Run-versioned under `data/intelligence/anomaly/runs/<run_id>/` — never
overwrites; manifest written last (completion marker).

| File | Purpose |
|---|---|
| `scores/anomaly_scores.parquet` | Full scored dataset (schema above). |
| `combine_calibration.parquet` | Per-(profile, detector) train ECDF grids. |
| `models/<profile>/{isolation_forest.joblib, mahalanobis.json, model_meta.json}` | Fitted detector artifacts + metadata. |
| `summaries/timeline.parquet` | Severity counts per time bucket. |
| `summaries/rates_by_profile.parquet` | Warning/anomaly rates per profile. |
| `summaries/severity_distribution.parquet` | Overall severity counts. |
| `summaries/top_events.parquet` | Highest combined scores + evidence — the manual-review queue. |
| `summaries/detector_agreement.parquet` | Pairwise co-trigger counts per profile (the main label-free plausibility signal). |
| `unsupported_profiles.parquet` | `(profile, detector, reason)` — transparency over silence. |
| `anomaly_fit_manifest.json` | Upstream contract (behaviour timestamps, `pca_run_id`, fingerprint match), all fitted thresholds, config snapshot, versions. Written **last**. |
| `anomaly_intelligence_report.{json,md}` | `Finding` report. |

## 4. How to run it

```bash
python -m src.intelligence --component anomaly                 # via dispatcher
python -m src.intelligence.anomaly.run_anomaly                 # directly
python -m src.intelligence.anomaly.run_anomaly --no-write --log-level DEBUG
python -m src.intelligence.anomaly.run_anomaly --pca-run 20260611T172019Z
```

Requires a completed behaviour run (labels + baselines) **and** a completed
pca run; `--pca-run latest` (default) resolves the newest *completed* pca
run, and the resolved id is recorded in the manifest. If the pca run was
fitted on a different master (structural fingerprint mismatch), an
`IMPORTANT` `upstream_dataset_mismatch` finding is emitted — diagnostic, not
fatal. Policy via `--config`. `--no-write` writes nothing at all.

## 5. Configuration — `configs/anomaly_intelligence.yaml`

Detector blocks (`statistical`, `mahalanobis`, `pca_detector`,
`isolation_forest`) each carry an `enabled` switch plus their thresholds;
`combine` holds the aggregation rule, weights, trigger percentile and the
warning/anomaly severity percentiles; `summaries` sizes the reports. The
Isolation Forest `contamination` parameter is intentionally **not** exposed —
triggering uses the train ECDF, not sklearn's internal offset.
`profiles.global_fallback` is **not supported** in v1 (rows are scored by
their own profile only); setting it emits an AWARE finding.

## 6. Validation expectations (no labels)

No reliable anomaly labels exist, so no supervised accuracy is claimed.
Operational usefulness is evaluated through: anomaly rate by profile, score
distributions, temporal concentration, **detector agreement**, top events,
profile coverage, artifact reproducibility and manual-review readiness.

### What the first real run showed

Train-window flag rates land at ~1.1 % by construction (p99/p99.9). The
**validation window (after 2024-09-03) shows ~62 % anomaly-severity rows**,
flags concentrated in September–October, with all four detectors strongly
agreeing (~19k co-triggers in `stopped`). Combined with the correlation-shift
sign flips in the steam/conditioner relationships, this indicates a
**systematic distribution shift** between the training and validation
windows (process change, recipe, sensor recalibration or seasonal regime) —
a data-level finding for manual review, not a detector defect. Until the
shift is understood (and the reference window possibly refitted), validation
severities should be read as "different from June–August normal" rather than
as machine faults.

## 7. Limitations

- Severity thresholds inherit the training window's representativeness — a
  drifted reference flags entire periods (see above), which is honest but
  operationally noisy until the reference is revisited.
- Mahalanobis contributions are exact but signed (cross-terms); they rank
  evidence, they do not partition blame.
- PCA T²/Q thresholds are marginally tight (train scored in-sample).
- The statistical detector treats sensors independently; multivariate
  evidence comes from the other detectors.

## 8. Deferred (not implemented — do not present as such)

- LOF benchmarking
- One-Class SVM benchmarking
- temporal forecasting
- residual anomaly detection
- LSTM autoencoders
- predictive-maintenance targets
- streaming inference
- alert delivery
- operator dashboard integration
