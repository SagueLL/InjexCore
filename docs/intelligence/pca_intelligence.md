# InjexCore — PCA Intelligence (Iteration B)

Reference document for the third component of the **Intelligence Layer**.
PCA Intelligence models the multivariate structure of *normal* behaviour
inside each supported operational profile and persists reusable, leakage-safe
scaler + PCA models that Anomaly Intelligence consumes.

---

## 1. Why this exists (and what it does *not* do)

Univariate baselines miss combinations: every sensor can sit inside its own
percentile band while the *combination* is unprecedented. Per supported
profile, this component:

1. Fits a **robust scaler + PCA on the training rows only**, retaining the
   smallest component count whose cumulative explained variance reaches the
   target (default 0.95).
2. Reports **dimensionality** (how compressible is each regime), **loadings**
   (which variables dominate each component) and explained variance.
3. Scores **every row of the profile** without refitting: PC scores,
   Hotelling **T²** (distance inside the retained subspace), **Q / SPE**
   (distance from the subspace) and **per-feature reconstruction
   contributions** that sum exactly to Q.

It exposes anomaly-relevant diagnostics but builds **no alert logic** — the
thresholds and severity rules live in Anomaly Intelligence. Training rows
are scored in-sample *on purpose*: the anomaly component fits its T²/Q
thresholds from the training-score distribution.

Profiles that cannot support a sound decomposition are **skipped and
reported** with a reason (`insufficient_rows`, `insufficient_features`,
`zero_variance`, `excessive_missingness`, `invalid_covariance`,
`invalid_scaling`) — never silently fitted.

---

## 2. Outputs

Run-versioned under `data/intelligence/pca/runs/<run_id>/` — never
overwrites an earlier run; the fit manifest is written last and marks the
run as complete.

| File | Purpose |
|---|---|
| `models/<profile>/scaler.joblib` | Fitted per-profile `RobustScaler` (or `StandardScaler`). |
| `models/<profile>/pca.joblib` | Fitted per-profile `PCA` at the selected component count. |
| `models/<profile>/model_meta.json` | Features (order-fixed), k, EVR list, train medians (imputation reference), n_train, sklearn/joblib/python versions. |
| `scores/<profile>/scores.parquet` | `pc_*`, `t2`, `q_spe`, `recon_error`, `is_train` for every row of the profile. |
| `scores/<profile>/contributions.parquet` | Per-feature squared reconstruction residual (rows sum to `q_spe`). |
| `loadings.parquet` | Long-form `(profile, component, feature, loading)`. |
| `explained_variance.parquet` | `(profile, component, evr, cumulative_evr)`. |
| `skipped_profiles.parquet` | `(profile, reason, n_train, n_features)`. |
| `pca_fit_manifest.json` | Component, run id, dataset fingerprint, train bounds, config snapshot, per-profile k/EVR, versions. Written **last**. |
| `pca_intelligence_report.{json,md}` | `Finding` report. |

---

## 3. Leakage-safe fitting

Scaler statistics, imputation medians, PCA components and the
explained-variance curve are all fitted on **training rows only** (the
behaviour `is_train` flag). Scoring applies the frozen pipeline to all rows;
missing values at score time are filled with the *training* medians persisted
on the model. T² only uses components with eigenvalues above a numeric floor
(1e-12), so near-zero directions cannot turn noise into huge scores.

---

## 4. How to run it

```bash
python -m src.intelligence --component pca                # via dispatcher
python -m src.intelligence.pca.run_pca                    # directly
python -m src.intelligence.pca.run_pca --no-write --log-level DEBUG
python -m src.intelligence.pca.run_pca --run-id my-experiment
```

Policy via `--config` (behaviour uses `--policy`; Iteration B follows the
newer convention). `--no-write` writes nothing at all. Run behaviour first.

---

## 5. Configuration — `configs/pca_intelligence.yaml`

| Key | Default | Meaning |
|---|---|---|
| `features.source` | `process_sensor` | Raw process signals; engineered features would feed PCA near-duplicate columns and destroy loading interpretability — opt in deliberately. |
| `profiles.min_samples_per_profile` | `200` | Gate; skipped profiles are reported. |
| `model.explained_variance_target` | `0.95` | Smallest k whose cumulative EVR reaches the target. |
| `model.max_components` | `null` | Optional hard cap on k. |
| `model.min_features` | `3` | Profiles with fewer eligible features are skipped. |
| `model.scaler` | `robust` | Median/IQR scaling — industrial sensors carry outliers that distort mean/std. |
| `model.missing_policy` | `median_impute` | Train-median fill (leakage-safe); `drop_rows` drops incomplete rows. |
| `model.random_state` | `42` | Pinned; the `full` SVD solver is deterministic regardless. |

---

## 6. What the first real run showed

On the 167k-row master, all 7 profiles fitted. Dimensionality tracks the
regime: `stopped` collapses to **3 components over 12 eligible features**
(5 sensors frozen while stopped were excluded per-profile), production
regimes need **6–10 components** for 95 % EVR. The joblib reload round-trip
reproduces the persisted Q scores exactly.

---

## 7. Deferred

- Anomaly thresholds and severity (Anomaly Intelligence owns them).
- Cross-validated / out-of-sample-calibrated T²/Q train scores (v1 scores
  train rows in-sample, which makes the anomaly thresholds marginally tight).
- Kernel/sparse PCA variants; per-component drift tracking over time.
