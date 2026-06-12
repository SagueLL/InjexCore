# InjexCore — Behaviour Intelligence (Iteration A)

Reference document for the first component of the **Intelligence Layer**.
Behaviour Intelligence consumes the schema-locked master dataset
`data/datasets/master/master_dataset.parquet` and characterises what
*normal* machine behaviour looks like — the reference that downstream
anomaly and predictive models will deviate from.

Iteration A delivers **operational-profile segmentation** + **statistical
baselines** + **profile-quality validation reports**, all fitted
**leakage-safe** on a training window. Correlation Intelligence and PCA are
deferred to Iteration B (see §11).

---

## 1. Why this exists (and what it does *not* do)

Before anomalies can be detected, "normal" has to be defined — and "normal"
is not one thing. A pellet-extrusion machine behaves differently when it is
stopped, starting up, running at high throughput, or in alarm. Pooling all
of those into one baseline hides exactly the deviations we care about. So
this stage:

1. **Segments** every row into a derivable operational profile.
2. **Fits per-profile, per-sensor statistical baselines** (mean, median,
   std, percentiles, IQR, …) on a training window only.
3. **Validates** that the derived profiles correspond to meaningful machine
   behaviour (distribution, segment durations, transitions, coverage).

It deliberately **stops short of fitted predictive estimators** (Isolation
Forest, LOF, Mahalanobis scorers) and of **correlation / PCA analysis**
(Iteration B). It is *descriptive*, not *predictive*.

### Layer boundary

```
src/preprocessing/          cleans + engineers features        (no fitting)
src/intelligence/  characterises normal behaviour     (fits DESCRIPTIVE artifacts)  ← this stage
src/models/        scores deviation from normal        (fits PREDICTIVE estimators)  (future)
```

`src/preprocessing/` stays parameter-free preprocessing; `src/models/` stays reserved
for the anomaly/forecasting scorers. Behaviour Intelligence sits between
them: it fits baseline tables and a reproducible fit manifest that the
modelling stage will consume.

---

## 2. Outputs

All under `data/intelligence/behaviour/` (git-ignored, like all of `data/`),
grouped into one subfolder per artifact family — mirroring the
`data/datasets/{master,specialized}/` convention. The component-level fit
manifest and report sit at the behaviour root.

| File | Purpose |
|---|---|
| `profiles/profile_labels.parquet` | Per-row primary regime label, the `is_train` flag, and the optional `material_change_candidate` flag. |
| `baselines/baselines.parquet` | Long-form per-`(profile, sensor)` statistics. |
| `validation/distribution.parquet` | Rows + share per profile. |
| `validation/durations.parquet` | Contiguous-segment run-length stats per profile. |
| `validation/transitions.parquet` | profile → profile transition counts. |
| `behaviour_fit_manifest.json` | Reproducible fit contract: train-window bounds, production quantile edges, sensor list, fit timestamp, profiles fitted/skipped. |
| `behaviour_intelligence_report.{json,md}` | `Finding` report (same schema as every data stage). |

The master dataset is **not** modified — the stage is independently rerunnable.

---

## 3. Leakage-safe fitting

Everything learned is fit on a **training window only**, then applied to the
whole dataset, so the "normal" reference never sees future data:

- **Production quantile edges** (the low/mid/high cut points) are fit on the
  training rows in the production-candidate set.
- **Baseline statistics** are computed on training rows per profile.
- Profile *labels* are assigned across all rows using the train-fitted edges
  (so the validation reports can inspect the full record and reveal
  train↔validation distribution shift).

The window is set by `fit_window` (default `strategy: fraction`,
`train_fraction: 0.7`, time-ordered). `strategy: all` is an explicit EDA-only
opt-in that disables the guard. The exact bounds and edges are persisted to
`behaviour_fit_manifest.json` so later data is scored consistently.

---

## 4. How to run it

```bash
# Full run (writes artifacts + reports)
python -m src.intelligence.behaviour.run_behaviour

# Diagnostic only — emit reports, skip artifact writes
python -m src.intelligence.behaviour.run_behaviour --no-write

# Override inputs / verbosity
python -m src.intelligence.behaviour.run_behaviour \
    --master data/datasets/master/master_dataset.parquet \
    --policy configs/behaviour_intelligence.yaml \
    --log-level DEBUG
```

Equivalently, via the Intelligence-Layer dispatcher (`behaviour` is the
default component; remaining flags are forwarded to the behaviour CLI):

```bash
python -m src.intelligence                          # = behaviour, full run
python -m src.intelligence --component behaviour --no-write
```

This stage is **not** wired into the `python -m src.preprocessing` `--stage`
dispatcher: it fits descriptive artifacts (a different output contract) and
sits past the preprocessing chain. It is a standalone entry point.

---

## 5. Pipeline shape

```
load_master → compute train window (leakage guard)
            → profiles.derive   (operational regimes + material-change candidate)
            → baselines.fit      (per-profile, per-sensor stats — TRAIN only)
            → validation.build   (distribution / durations / transitions / coverage)
            → write artifacts + JSON/MD report
```

`profiles.derive()` runs first; its label Series feeds both `baselines.fit()`
and `validation.build()`.

---

## 6. Operational profiles

A mutually-exclusive **primary regime** is assigned to every row from the
signals the real data actually supports. `machine_on` is taken from
`n_subsystems_running > 0` (falling back to the OR of the running flags).

| Profile | Rule |
|---|---|
| `stopped` | `machine_on == 0` |
| `startup` | running, within `startup.window_samples` after a 0→1 machine-on edge |
| `shutdown` | running, within `shutdown.window_samples` before a 1→0 machine-off edge |
| `alarm` | running and `any_alarm_while_running == 1` or a recent alarm |
| `low` / `mid` / `high_production` | steady running rows bucketed by **train-fitted** tertiles of `granulator_production_rate` |

Among running rows a configurable **precedence** ladder resolves overlap
(default `alarm > startup > shutdown > production`); `stopped` always applies
when the machine is off.

### Honest gaps (not fabricated)

`cleaning`, `maintenance` and `recipe_change` are **not derivable** from the
available signals (there is no wash/CIP, maintenance-mode, or material-change
event). Each is surfaced as an `AWARE` `regime_not_derivable` finding rather
than guessed. Material/recipe change is offered **only** as a separate
boolean `material_change_candidate` column — a proxy from `batch_id` /
`batch_quality_id` transitions, explicitly captioned, never a primary label.
Closing these gaps requires joining an external maintenance / material log
(future work).

---

## 7. Statistical baselines

For every fitted profile and selected sensor, the long-form `baselines.parquet`
row carries: `count`, `mean`, `median`, `std`, `min`, `max`, `iqr` (always),
plus the configured percentiles as `pNN` columns (default `p05 p25 p50 p75
p95`).

- **Sensor set:** the ~17 `process_sensor` columns via the semantic catalogue
  (`sensors.source: process_sensor`) — interpretable and free of the
  566-column engineered collinearity. Use `source: explicit` to hand-pick.
- A profile with fewer than `min_samples_per_profile` (default 200) training
  rows is **skipped** with an `IMPORTANT` finding rather than producing an
  unstable baseline.
- A `(profile, sensor)` cell below `min_non_null_fraction` is skipped
  (`AWARE`); a near-zero-variance cell is still recorded but flagged
  (`AWARE`).

---

## 8. Validation reports

Computed over the full labelled dataset to verify the profiles are
meaningful: per-profile **distribution**, contiguous-segment **durations**,
profile→profile **transitions**, and **coverage** (labelled share, train/val
split sizes, unknown rows). The **unsupported** regime list is echoed for
visibility.

---

## 9. Configuration — `configs/behaviour_intelligence.yaml`

Validated by `src/intelligence/behaviour/policy.py` (Pydantic, `extra="forbid"`
— a misspelled key fails loudly). Sections: `sensors`, `fit_window`,
`profiles`, `baselines`. Windows are in samples (master grid = 60 s). See the
file for the full annotated default policy.

---

## 10. Reporting & where things live

Findings reuse the shared `Finding` / `Severity` schema from
`src/preprocessing/_common/` (re-exported via the local `reporting.py` shim), so the
behaviour report parses with the same reader as the four preprocessing
stages. Severity convention: under-sized profile / unlabelled rows →
`IMPORTANT`; sparse / near-zero-variance sensor, non-derivable regime,
material-change proxy → `AWARE`; informational summaries → `NORMAL`;
machine-state-undeterminable → `CRITICAL`.

```
src/intelligence/
  __init__.py
  behaviour/
    __init__.py
    io.py                 # path constants + load_master() + writers
    policy.py             # BehaviourPolicy (Pydantic StrictModel) + load_policy()
    column_groups.py      # shim → src/preprocessing/_common
    reporting.py          # shim → src/preprocessing/_common
    profiles.py           # derive() — operational regimes
    baselines.py          # fit() — per-profile statistics (train only)
    validation.py         # build() — profile-quality diagnostics
    run_behaviour.py      # CLI: run() + main()
```

Tests: `tests/unit/intelligence/behaviour/` (policy, profiles, baselines,
validation, end-to-end run).

---

## 11. Iteration B roadmap (not built yet)

The `fit(...)` contract, the leakage-safe `train_mask`, and the fit manifest
are designed so the next techniques drop in as new modules + config sections
without reworking the foundation:

- **Correlation Intelligence** (`correlations.py`) — per-profile correlation
  matrices and structural-pair rupture detection.
- **PCA Intelligence** (`pca.py`) — per-profile standardised PCA, loadings,
  explained variance, and reconstruction-error / Mahalanobis "strange sample"
  flagging. Adds `scikit-learn` + `joblib` (the existing `[models]` extra).

These feed, but do not replace, the fitted predictive estimators planned for
`src/models/`.
