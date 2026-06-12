# InjexCore — Correlation Intelligence (Iteration B)

Reference document for the second component of the **Intelligence Layer**.
Correlation Intelligence consumes the master dataset plus the *persisted*
Behaviour Intelligence artifacts and characterises how the process signals
move together inside each supported operational profile.

---

## 1. Why this exists (and what it does *not* do)

Sensor relationships are regime-dependent: steam pressure and conditioner
temperature track each other while producing, and decouple while stopped.
Pooling everything into one correlation matrix hides exactly that structure.
So this component, per supported profile:

1. Fits **Pearson + Spearman correlation references on the training window**
   over the eligible process sensors, with pairwise valid-observation counts.
2. Reports the **strongest positive/negative relationships** and **redundant
   pairs** (candidates for feature pruning).
3. Diagnoses **train-vs-validation correlation shifts** — pairs whose
   relationship changed out-of-window.

It does **not** generate operational alerts. Shift findings are
`AWARE`-severity diagnostics; alerting belongs to Anomaly Intelligence,
which fits thresholds of its own. It also fits no estimators — correlation
matrices are descriptive references.

### Upstream contract

The component **never re-derives profiles or recomputes the train split**:
it loads `profile_labels.parquet` (the `profile` + `is_train` columns) and
fails loudly if the master's index no longer matches — that means the master
changed since behaviour ran, and the answer is to re-run behaviour, not to
silently realign.

---

## 2. Outputs

Run-versioned: every execution writes a fresh
`data/intelligence/correlation/runs/<run_id>/` and **never overwrites** an
earlier run. `run_id` defaults to a UTC timestamp; the fit manifest is
written last and marks the run as complete (a crashed run is never resolved
as `latest`).

| File | Purpose |
|---|---|
| `correlations.parquet` | Long-form upper triangle: `(profile, feature_a, feature_b, pearson, spearman, n_valid)` — the fitted training reference. |
| `excluded_features.parquet` | Per-`(profile, feature)` exclusions with reasons (`too_sparse`, `near_constant`). |
| `strong_pairs.parquet` | \|pearson\| ≥ `strong_threshold`, with sign, strongest first. |
| `redundant_pairs.parquet` | Pairs clearing `redundancy_threshold` under **both** metrics (joint requirement avoids outlier-inflated hits). |
| `correlation_shift.parquet` | Per-pair train vs validation Pearson + `abs_delta` — diagnostics only. |
| `correlation_fit_manifest.json` | Component, run id, dataset fingerprint, train-window bounds, config snapshot, per-profile pair counts, profiles fitted/skipped. Written **last**. |
| `correlation_intelligence_report.{json,md}` | `Finding` report (same schema as every stage). |

---

## 3. Leakage-safe fitting

The correlation reference (both matrices, the eligibility decisions and the
strong/redundant reports) is computed on **training rows only**, as marked
by behaviour's persisted `is_train` flag. Validation rows are touched only
by the shift diagnostics — which exist precisely to compare the two windows.
Cells with fewer than `min_valid_observations` joint non-null observations
are `NaN`, never a guess.

---

## 4. How to run it

```bash
python -m src.intelligence --component correlation              # via dispatcher
python -m src.intelligence.correlation.run_correlation          # directly
python -m src.intelligence.correlation.run_correlation --no-write --log-level DEBUG
python -m src.intelligence.correlation.run_correlation --run-id my-experiment
```

Note: Iteration B components take the policy via `--config` (the behaviour
component predates this convention and uses `--policy`). `--no-write` runs
the full pipeline and writes **nothing** — no run directory is created.
`--output-root` redirects the component root (used by the integration
tests). Run behaviour first; the component fails with a clear message
otherwise.

---

## 5. Configuration — `configs/correlation_intelligence.yaml`

| Key | Default | Meaning |
|---|---|---|
| `features.source` | `process_sensor` | The ~17 raw process signals (default). `explicit` + `include_columns` opts into engineered features — expect trivially redundant base↔rolling pairs to dominate in that mode. |
| `profiles.min_samples_per_profile` | `200` | Profiles with fewer training rows are skipped + reported. |
| `profiles.global_fallback` | `false` | Opt-in `__global__` pseudo-profile pooled over all rows (mixes regimes — deliberate choice only). |
| `thresholds.min_valid_observations` | `200` | Pairwise `min_periods`. |
| `thresholds.near_constant_std` | `1e-9` | Per-profile near-constant exclusion. |
| `thresholds.strong_threshold` | `0.8` | Strong-pair report cut. |
| `thresholds.redundancy_threshold` | `0.95` | Redundant-pair cut (both metrics). |
| `thresholds.max_missing_fraction` | `0.3` | Per-profile sparsity exclusion. |
| `shift.delta_threshold` / `shift.top_k` | `0.2` / `20` | AWARE-finding cut for train↔validation deltas. |

All policy models inherit `StrictModel` — a misspelled key raises.

---

## 6. What the first real run showed

On the 167k-row master (7 profiles): 850 pairs fitted, 54 strong, 4
redundant (e.g. `expander_ex2_power` ↔ `extruder_specific_energy` at
ρ≈0.97 across production profiles). The shift diagnostics surfaced large
sign flips (e.g. `steam_valve_pressure_me2` ↔ `conditioner_steam_loop_temp`
from −0.64 to +0.67 in `mid_production`) — consistent with the systematic
post-September drift that Anomaly Intelligence later quantified.

---

## 7. Deferred

- Operational alerting on correlation shifts (Anomaly Intelligence owns alerts).
- Partial correlations / lagged cross-correlations (Temporal Intelligence).
- Engineered-feature redundancy pruning as a default (available via config).
- Moving the shared `load_master`/`write_table` helpers from
  `behaviour.io` into `_common/io.py` proper (currently a re-export shim).
