# InjexCore — Feature Engineering Phase

Reference document for the feature engineering pipeline that takes the
time-series engineering output
`data/features/Dades_pellet_features.parquet` (~290 cols) and adds
semantically-grounded, cross-column, physically-meaningful features for
the downstream anomaly classifier. Output:
`data/features/Dades_pellet_engineered.parquet` plus an auditable
report.

---

## 1. Why this exists (and what it does *not* do)

The time-series engineering stage produces *generic per-column
statistics* — rolling mean / std / trend, lags, pct_change, velocity,
plus state-flag families (`runfrac`, `tsla`, `edges`). That gets us a
strong baseline of temporal context, but predictive-maintenance signals
typically also depend on:

- **Cross-column relationships** (kWh per kg, ΔT across a heat
  exchanger, setpoint vs process variable deviation).
- **Cumulative quantities** (lifetime energy integrated from power,
  daily restart counters).
- **System-level operational state** (machine-wide restart counter,
  alarm pressure across all subsystems).
- **Statistical anomaly scores** the classifier can use directly
  (rolling z-score, outlier-robust z).

Those features are what this stage adds. It deliberately **stops short
of fitted estimators** (Isolation Forest, LOF, Mahalanobis with a
fitted covariance). Those have hyperparameters, internal state, and
strong train/test boundary requirements — they belong in
`src/models/anomaly/`, not in preprocessing. See §3.

This stage follows the same **detect + apply** contract as the cleaning
and time-series pipelines: every stage first emits one informational
`Finding` per feature it intends to generate (the audit trail), then
applies the transform. The report tells you exactly which features were
created and why.

---

## 2. Outputs

| File | Purpose |
|---|---|
| `data/features/Dades_pellet_engineered.parquet` | Engineered feature matrix. Carries forward all upstream columns plus the new families. |
| `data/features/feature_engineering_report.json` | Machine-readable list of every emitted feature, grouped by stage. |
| `data/features/feature_engineering_report.md` | Human-readable report grouped by severity. |

The upstream `Dades_pellet_features.parquet` is **not** overwritten —
the two stages stay independently rerunnable.

---

## 3. Boundary with `src/models/anomaly/`

Anything with model state, hyperparameters that need cross-validation,
or a fit/predict pair lives in the modelling stage. That includes:

- **Isolation Forest** — has `contamination`, `n_estimators`,
  `max_samples`; fits on training data only.
- **Local Outlier Factor (LOF)** — neighbour graph fit.
- **Mahalanobis distance** — needs a covariance matrix; computing it on
  the full record (train + test) leaks future statistics into the
  preprocessing of past rows.
- **One-class SVM, autoencoders, ensemble scoring** — same reasoning.

What this stage emits instead, by design:

- Rolling **z-score** and **robust z-score** (per-column statistical
  scores, no fitted state).
- A `global_z` option for offline EDA only; **disabled by default**
  with a leakage warning.

When the modelling stage lands it will consume the engineered parquet,
score with Isolation Forest / LOF / Mahalanobis on a proper train/test
split, and write to `models/reports/` separately.

---

## 4. How to run it

```bash
# Full run (writes engineered matrix + reports)
python -m src.data.feature_engineering.run_feature_engineering

# Diagnostic only — emit reports, skip the parquet write
python -m src.data.feature_engineering.run_feature_engineering --no-write

# Feature engineering only via the shim (assumes ts parquet exists)
python -m src.preprocessing --stage fe

# Cleaning + time-series + feature engineering chain
python -m src.preprocessing --stage features
```

CLI flags worth knowing:

- `--features <path>` — override the input parquet path. Accepts a
  cleaned CSV as a fallback when you want to run on top of cleaning
  output directly.
- `--policy <path>` — point at a different `feature_engineering.yaml`.
- `--out-parquet <path>` — change the engineered matrix output
  location.
- `--out-csv <path>` — also write a CSV mirror (large; opt-in).
- `--log-level DEBUG` — verbose timing per stage.

---

## 5. Pipeline shape

Six sequential stages, executed in this order:

```
load_features → temporal_derivatives → stability → physical_ratios
              → energetic_features → operative_features → anomaly_features
              → write(parquet, json, md)
```

| Stage | Adds | Routing |
|---|---|---|
| `temporal_derivatives` | acceleration, sign-change rate, SP–PV deviation | category whitelist + explicit SP–PV pairs |
| `stability` | CV, std-ratio, rolling range, MAD | category whitelist (+ unit whitelist for MAD) |
| `physical_ratios` | cross-column ratios, diffs and scale features | explicit per-feature list |
| `energetic_features` | cumulative kWh (lifetime + daily), windowed kWh/kg | explicit power columns + production column |
| `operative_features` | cross-flag restart, subsystem count, alarm pressure | explicit running + alarm flag lists |
| `anomaly_features` | rolling z, robust z, optional global z | category whitelist |

Every stage exposes the same pair of functions:

```python
def detect(df, policy, groups) -> list[Finding]: ...
def apply(df, findings, policy, groups) -> pd.DataFrame: ...
```

Order rationale: derivatives + stability + ratios first (no
inter-stage dependencies), energetic next (cumulative — needs the
`DatetimeIndex`), operative (cross-flag), anomaly last (consumes
rolling mean/std already present in the input parquet).

---

## 6. Reconciliation with `time_series`

Several feature families this stage emits *look* like things
time_series already produces. The deliberate boundary:

| Family in this stage | Comparable ts output | What this stage adds beyond ts |
|---|---|---|
| Acceleration `_accel_<L>` | `velocity_<L>` is first derivative | Second derivative; not produced by ts |
| Sign-change rate `_signchanges_<W>` | `rolling_std` | Counts oscillation events, not variance |
| Coefficient of variation `_cv_<W>` | `rolling_std` | Scale-free, comparable across units |
| Rolling range `_range_<W>` | `rolling_std` | Robust to noisy distributional shape |
| MAD `_mad_<W>` | `rolling_std` | Outlier-robust |
| Rolling z `_z_<W>` | `rolling_mean` + `rolling_std` | Composed score; reuses upstream cols when present |
| `time_since_machine_off` | `tsla` per flag | Cross-flag (OR of all running flags), restart-edge based |
| `cumulative_starts` | `edges_<W>` | Lifetime (not windowed) |
| `total_alarms_<W>` | `edges_<W>` per alarm | Cross-alarm system pressure |

Whenever there is genuine overlap we either skip (ts wins) or emit a
semantically distinct variant. SP–PV deviation, physical ratios,
cumulative kWh, energy_per_kg, and the cross-flag operative features
have no time_series counterpart at all.

---

## 7. Feature naming convention

`<source>_<family>_<param>` where possible; cross-column features use
descriptive names from the YAML.

| Family | Suffix / name | Param |
|---|---|---|
| Acceleration | `_accel_<L>` | sample lag |
| Sign-change rate | `_signchanges_<W>` | window in samples |
| SP–PV deviation | `<pv>_minus_<sp>` | — |
| Coefficient of variation | `_cv_<W>` | window |
| Std ratio | `_stdratio_<S>_<L>` | short / long window |
| Rolling range | `_range_<W>` | window |
| MAD | `_mad_<W>` | window |
| Ratio / diff / scale | explicit name from YAML | — |
| Cumulative energy | `_cumkwh` / `_cumkwh_day` | — |
| Energy per kg | `_energy_per_kg_<W>` | window |
| Operative cross-flag | `time_since_machine_off`, `n_subsystems_running`, `cumulative_starts`, `total_alarms_<W>`, `time_since_any_alarm`, `any_alarm_while_running` | — |
| Rolling z | `_z_<W>` | window |
| Robust z | `_robust_z_<W>` | window |
| Global z | `_z_global` | — |

---

## 8. Leakage strategy — `closed='left'`

All rolling families inherit `closed='left'` semantics from the
time-series stage. The window at index `t` sees `[t − W, t)`. The
exception is `cumulative_*` and SP–PV deviation, which are
instantaneous transforms with no leakage risk.

`global_z` (using full-record mean / std) **does leak** future
statistics into past rows and is therefore disabled in the default
policy. Enable it only for offline EDA.

---

## 9. Policy file walkthrough

`configs/feature_engineering.yaml` has six top-level sections, one per
family. Sample slices:

```yaml
temporal_derivatives:
  enabled: true
  acceleration:        { enabled: true, lags: [1, 5], categories: [process_sensor] }
  sign_change_rate:    { enabled: true, windows: [15, 60], categories: [process_sensor] }
  sp_pv_deviation:
    enabled: true
    pairs:
      granulator_power_sp: granulator_power
      conditioner_temp_sp: conditioner_steam_loop_temp

physical_ratios:
  enabled: true
  epsilon: 1.0e-6
  nan_rate_warn: 0.50
  ratios:
    - { name: granulator_kwh_per_kg, op: ratio, a: granulator_power, b: granulator_production_rate }
    - { name: extruder_kwh_per_kg,   op: scale, a: extruder_specific_energy, factor: 0.001 }
    - { name: temp_rise_conditioner, op: diff,  a: conditioner_steam_loop_temp, b: conditioner_inlet_temp }

energetic_features:
  enabled: true
  sample_period_s: 60.0
  power_columns: [granulator_power, conditioner_l2_power, expander_ex2_power]
  production_column: granulator_production_rate
  cumulative:    { enabled: true, daily_reset: true }
  energy_per_kg: { enabled: true, windows: [60, 240] }
  per_cycle:     { enabled: false }
```

Pydantic enforces `extra="forbid"` so unknown keys fail loudly at
startup. The aggregate schema lives in
`src/data/feature_engineering/policy.py`.

---

## 10. Stage reference

### 10.1 `temporal_derivatives`

- **`<col>_accel_<L>`** — `df[col].diff(L).diff(L)`. Surfaces rude
  regime changes (start-up shocks, alarm-imminent dynamics).
- **`<col>_signchanges_<W>`** — count of `sign(diff)` flips in a
  rolling window. Surfaces oscillation around a setpoint that
  rolling_std averages out.
- **`<pv>_minus_<sp>`** — pointwise SP–PV deviation for each explicit
  pair in the YAML. `feeder_max_speed_sp` has no obvious PV in the
  current dictionary and is therefore omitted.

A missing SP or PV column yields an `IMPORTANT/sp_pv_deviation_missing`
finding rather than crashing.

### 10.2 `stability`

- **`<col>_cv_<W>`** — `rolling_std / |rolling_mean|`. Comparable
  across °C / bar / %.
- **`<col>_stdratio_<S>_<L>`** — short-window std ÷ long-window std.
  Reuses upstream `_std_<W>` columns from the time-series parquet when
  present, otherwise recomputes.
- **`<col>_range_<W>`** — `rolling_max − rolling_min`.
- **`<col>_mad_<W>`** — rolling median absolute deviation. Restricted
  to a unit whitelist (`C`, `bar` by default) because it is the most
  expensive transform in this stage.

### 10.3 `physical_ratios`

Three ops:

- `ratio` — `a / b` with `np.where(|b| < eps, NaN, ...)`.
- `diff`  — `a - b`.
- `scale` — `a * factor`. Used to canonicalise `extruder_specific_energy`
  from kWh/t to kWh/kg (`factor: 0.001`).

The policy enumerates each ratio explicitly — no auto-combinatorics.
For each ratio, if the actual NaN fraction in the output exceeds
`nan_rate_warn`, an `AWARE/ratio_high_nan_rate` finding is emitted so
you can spot ratios that silently produce mostly nothing.

### 10.4 `energetic_features`

- **`<power>_cumkwh`** —
  `cumsum(power × sample_period_s / 3600)`. **Note on units**: the
  power columns in the current dictionary are recorded as % of
  nominal load, not kW. Therefore `cumkwh` is technically %·h. The
  feature remains useful as a *load-time integral* — downstream code
  that needs physical units can multiply by the nominal rating.
- **`<power>_cumkwh_day`** — same with daily reset
  (`groupby(index.normalize())`).
- **`<power>_energy_per_kg_<W>`** — rolling
  `Σ(power × dt_h) / Σ(production_rate × dt_min)` over W samples.
  Window-level kWh/kg avoids the per-row divide-by-zero pathology of
  raw `power / production` near idle.
- **`per_cycle`** — schema is in place but **disabled by default**.
  Pellet extrusion is continuous; no cycle marker exists yet. Flip to
  `per_cycle.enabled: true` and set `cycle_id_column` once real-machine
  data supplies one.

### 10.5 `operative_features`

Per-flag operative statistics (`runfrac`, `tsla`, `edges`) already live
in `state_features`. This stage adds *cross-flag* features:

- **`time_since_machine_off`** — samples since the last `0 → 1` edge on
  `OR(running_flags)`. Captures full-machine restarts, not per-subsystem
  hand-offs. (Per design decision: restart = `0 → 1` edge on the OR of
  running flags.)
- **`n_subsystems_running`** — instantaneous count of active
  subsystems.
- **`cumulative_starts`** — lifetime cumulative rising edges on
  `OR(running_flags)`.
- **`total_alarms_<W>`** — sum of `*_alarm` rising edges across all
  alarms in a rolling window — system alarm pressure.
- **`time_since_any_alarm`** — samples since the most recent alarm
  anywhere.
- **`any_alarm_while_running`** — boolean
  `(any alarm) AND (any running)` per sample. Surfaces inconsistent
  operational states.

### 10.6 `anomaly_features`

- **`<col>_z_<W>`** — rolling z-score
  `(x − rolling_mean_<W>) / rolling_std_<W>`. Reuses upstream
  time-series columns where applicable.
- **`<col>_robust_z_<W>`** —
  `(x − rolling_median) / (1.4826 × rolling_MAD)`. Outlier-robust.
- **`<col>_z_global`** — global z against full-record mean / std.
  Disabled by default (leakage warning).

Routing is restricted to `process_sensor` only. State / alarm /
setpoint columns are skipped.

---

## 11. Reporting

Per-feature audit records carry:

- `check` = stage name
- `severity` = `NORMAL` for routine features; `AWARE` for high-NaN
  ratios, partial flag sets, or leakage-prone features; `IMPORTANT`
  for missing required input
- `finding_type` = family sub-name (`acceleration`, `cv`, `ratio`,
  `cumulative_energy`, `rolling_z`, …)
- `action_taken` = `add:<new_column_name>` or `skip` / `noop`
- `evidence` = inputs, formulas, windows, thresholds, NaN fractions

The MD title is `Feature Engineering Report`.

---

## 12. Where things live

```
src/data/feature_engineering/
  __init__.py
  policy.py                       # Pydantic schema, load_policy
  column_groups.py                # re-export
  reporting.py                    # re-export
  io.py                           # load_features (parquet/csv), write_engineered
  temporal_derivatives.py         # Family 1
  stability.py                    # Family 2
  physical_ratios.py              # Family 3
  energetic_features.py           # Family 4
  operative_features.py           # Family 5
  anomaly_features.py             # Family 6
  run_feature_engineering.py      # CLI orchestrator

configs/
  feature_engineering.yaml

tests/unit/data/feature_engineering/
  test_temporal_derivatives.py
  test_stability.py
  test_physical_ratios.py
  test_energetic_features.py
  test_operative_features.py
  test_anomaly_features.py
  test_policy.py
  test_run_feature_engineering.py
```

Shared infrastructure reused unchanged:

- `Finding`, `Severity`, JSON / MD writers — `src/data/cleaning/reporting.py`
- `ColumnGroups`, `semantic_category` — `src/data/cleaning/column_groups.py`
- Test fixtures `tiny_frame_factory`, `groups`, `project_root`,
  `ts_policy` — `tests/conftest.py` (plus the new `fe_policy` fixture).

---

## 13. Open questions / follow-ups

- **Per-cycle aggregations.** Disabled until a cycle marker column
  exists on the dataset. Flip `per_cycle.enabled: true` once one does.
- **kWh unit accuracy.** Power columns are % of nominal. To produce
  physical kWh, multiply `cumkwh` features by the per-asset nominal
  rating downstream — or pre-convert the power columns to kW in
  cleaning and re-run.
- **`feeder_max_speed_sp`** has no PV pairing yet; SP–PV deviation
  skips it. If a corresponding process variable is identified in the
  dictionary, add it to `temporal_derivatives.sp_pv_deviation.pairs`.
- **Multivariate anomaly scores** (Isolation Forest, LOF, Mahalanobis)
  land in `src/models/anomaly/` next — with seeded fits, train/test
  separation, and pickled artifacts.
