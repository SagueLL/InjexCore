# InjexCore — Specialized Datasets Phase

Reference document for the final preprocessing stage, which takes the
feature-engineering output
`data/features/Dades_pellet_engineered.parquet` and produces a
canonical **master dataset** plus three downstream
**specialized datasets** tailored to specific model families. Outputs
land in `data/datasets/master/` and `data/datasets/specialized/` along
with one auditable report per dataset.

---

## 1. Why this stage exists (and what it does *not* do)

After three stages of preprocessing, the engineered parquet contains
the full feature surface (~290+ columns: raw signals, rolling stats,
lags, trends, derivatives, stability metrics, energetic features,
physical ratios, statistical anomaly scores). Different downstream
models care about different subsets of that surface — feeding *every*
column to *every* model is wasteful at best and a leakage / curse-of-
dimensionality liability at worst.

This stage answers the question **"what do I hand to each model
family?"** by projecting the engineered matrix into purpose-built
datasets. It also promotes the engineered parquet to a canonical
**master dataset** — the single source of truth that the three
specialized projections are derived from and that downstream code can
join back against.

What this stage **does not** do:

- It does **not** compute new features. Feature math belongs in
  `src/data/feature_engineering/`. If a column is missing here, add it
  upstream — never fabricate it during projection.
- It does **not** fit models. Isolation Forest, LOF, Mahalanobis with
  a covariance fit, LSTM / Transformer / XGBoost trainings all belong
  in `src/models/`.
- It does **not** modify the source engineered parquet — the upstream
  artifact stays independently rerunnable.

---

## 2. Outputs

| File | Purpose |
|---|---|
| `data/datasets/master/master_dataset.parquet` | Canonical master. Engineered matrix promoted after integrity checks. |
| `data/datasets/master/master_dataset_report.{json,md}` | Master integrity findings. |
| `data/datasets/master/schema_lock.json` | Optional schema snapshot (column names + dtypes). Bootstrapped on first run; subsequent runs report drift. |
| `data/datasets/specialized/anomaly_detection_dataset.parquet` | Local-deviation features for Isolation Forest / Autoencoders / DBSCAN. |
| `data/datasets/specialized/forecasting_dataset.parquet` | Predictive temporal structure for LSTM / Transformers / XGBoost forecasting. |
| `data/datasets/specialized/energy_dataset.parquet` | Energetic optimisation & efficiency analysis. |
| `data/datasets/specialized/{anomaly_detection,forecasting,energy}_dataset_report.{json,md}` | One report per specialized dataset describing which columns were selected and why. |

The three projections always include the metadata columns (`timestamp`
and the `Metadata` rows in `variable_classification.csv`) so any
specialized dataset can be joined back to master.

---

## 3. Boundary with `src/data/feature_engineering/` and `src/models/`

| Concern | Belongs in |
|---|---|
| Compute a new derived column | `src/data/feature_engineering/` |
| Pick which columns are visible to a model family | `src/data/datasets/` (this stage) |
| Fit / persist / score a model | `src/models/` |

The projection modules deliberately have *no transform logic*. They
import `select_columns` from `selectors.py` and pass it the relevant
section of the policy. If a projection ever needs a new column, the
fix is to add the feature upstream, not to compute it here.

---

## 4. How to run it

```powershell
# Stand-alone
python -m src.data.datasets.run_datasets                 # full run
python -m src.data.datasets.run_datasets --no-write      # diagnostic only

# Through the shim
python -m src.preprocessing --stage datasets
python -m src.preprocessing --stage all                  # cleaning → ts → fe → datasets
```

The orchestrator reads
`data/features/Dades_pellet_engineered.parquet` by default; override
with `--engineered <path>` to run against an alternate input.

---

## 5. Pipeline shape

```
load_engineered → master_validation
                → anomaly_projection
                → forecasting_projection
                → energy_projection
                → 4 parquet files + 4 JSON/MD report pairs
```

The three projections run sequentially on the master DataFrame
returned by `master_validation` (i.e. after policy-driven column
drops), so any column the master removes is automatically invisible
to all three downstream datasets.

---

## 6. Selector mechanics

Each specialized dataset has its own `SelectorSpec` in
`configs/specialized_datasets.yaml`. The hybrid selector engine
resolves it as follows:

1. **Includes** — union of:
   - regex matches over column names (`include_patterns`)
   - semantic-category matches from `variable_classification.csv`
     (`include_categories`)
   - explicit allow list (`include_columns`)
2. **Metadata** — when `include_metadata: true`, the `timestamp`
   column / index and every metadata column are unconditionally added.
3. **Excludes** — `exclude_patterns` and `exclude_columns` are
   subtracted last.
4. **Deduplication** — the resulting set is materialised in the
   original DataFrame's column order.

Findings emitted per dataset:

- `NORMAL` — one summary per active rule plus a final
  `projection_summary` with source / selected column counts.
- `AWARE` — every name in `include_columns` / `exclude_columns` that
  is not present in the master DataFrame (typo / drift / schema
  change upstream).
- `IMPORTANT` — emitted when the resulting projection is empty.

---

## 7. Per-dataset reference

### 7.1 `anomaly_detection_dataset`

Optimised for unsupervised local-deviation models (Isolation Forest,
Autoencoders, DBSCAN). Captures *how unstable / unusual is the system
right now* without giving the model raw signal trajectories that
would let it overfit to absolute values.

Selected families:

| Source stage | Suffix pattern | Family |
|---|---|---|
| `feature_engineering.stability` | `_cv_<W>`, `_range_<W>`, `_mad_<W>`, `_stdratio_<S>_<L>` | Local variability |
| `feature_engineering.anomaly_features` | `_z_<W>`, `_robust_z_<W>`, `_z_global` | Univariate anomaly scores |
| `feature_engineering.temporal_derivatives` | `_accel_<L>`, `_signchanges_<W>` | Second-order dynamics |
| `time_series.state_features` | `_tsla`, `_edges_<W>` | State evolution |
| `feature_engineering.operative_features` | `time_since_machine_off`, `n_subsystems_running`, `cumulative_starts`, `time_since_any_alarm`, `any_alarm_while_running` | Cross-flag operational state |

### 7.2 `forecasting_dataset`

Optimised for sequence models (LSTM, Transformers) and gradient-boosted
forecasters (XGBoost forecasting). Carries the *predictive temporal
structure* plus raw process-sensor signals as candidate forecasting
targets.

Selected families:

| Source stage | Suffix pattern | Family |
|---|---|---|
| `time_series.temporal_features` | `_lag_<N>`, `_pctchg_<N>`, `_velocity_<N>` | Past-value dependencies |
| `time_series.rolling_windows` | `_mean_<W>`, `_std_<W>`, `_trend_<W>` | Smoothed signal context |
| `time_series.state_features` | `_runfrac_<W>` | Operating regime |
| `feature_engineering.temporal_derivatives` | `_minus_` (SP-PV) | Control deviation |
| `variable_classification.csv` category | `process_sensor` | Raw process signals (forecasting targets) |

### 7.3 `energy_dataset`

Optimised for energy-efficiency studies, kWh-budget modelling and
load-shifting analysis. Pulls every energy / production / load
signal plus the engineered energetic features and the operating
context needed to interpret them.

Selected families:

| Source stage | Pattern / column | Family |
|---|---|---|
| Explicit raw signals | `granulator_power`, `conditioner_l2_power`, `expander_ex2_power`, `extruder_specific_energy`, `granulator_production_rate` | Raw energy & throughput |
| Explicit raw signals | `granulator_g2_state_pct`, `conditioner_l2_state_pct`, `feeder_al2_state_pct` | Machine-load registers |
| Explicit raw signals | `granulator_roller_gap`, `steam_valve_*`, `inlet_hopper_*`, `conditioner_*_temp`, `expander_ex2_outlet_temp` | Aux process context |
| `feature_engineering.energetic_features` | `_cumkwh`, `_cumkwh_day`, `_energy_per_kg_<W>` | Cumulative & windowed kWh |
| `feature_engineering.physical_ratios` | `_kwh_per_kg`, `production_per_steam`, `power_balance_*`, `pressure_ratio_*` | Energy-efficiency ratios |
| `time_series.state_features` | `_runfrac_<W>` | Operational load context |

---

## 8. Master integrity checks

Run by `master_validation.py` before any projection sees the data.

| Check | Severity on failure | Configurable via |
|---|---|---|
| Timestamp monotonicity | `IMPORTANT` | `require_monotonic_timestamps` |
| Timestamp uniqueness | `IMPORTANT` | `require_unique_timestamps` |
| Per-column NaN budget | `IMPORTANT` | `max_nan_fraction_per_column` (default `0.30`) |
| Schema lock drift | `AWARE` | `schema_lock` (compares against `schema_lock.json` when present; bootstraps on first run) |
| Generation-only column drop | `NORMAL` | `drop_columns` (defaults to `["drift"]`) |

The master pass is intentionally lenient on warmup NaNs — long rolling
windows produce a NaN block at the head of the series that the default
budget of 30 % tolerates without flagging.

---

## 9. Policy file walkthrough

`configs/specialized_datasets.yaml` has four top-level sections, each
matching a step in the orchestrator pipeline:

```yaml
master_validation:
  enabled: true
  require_monotonic_timestamps: true
  require_unique_timestamps: true
  max_nan_fraction_per_column: 0.30
  schema_lock: true
  drop_columns: [drift]

anomaly_detection:
  enabled: true
  include_metadata: true
  include_patterns: [ ... ]    # suffix regex families
  include_categories: []
  include_columns: [ ... ]     # explicit overrides
  exclude_patterns: []
  exclude_columns: []

forecasting:
  enabled: true
  include_metadata: true
  include_patterns: [ ... ]
  include_categories: [process_sensor]
  include_columns: []
  exclude_patterns: []
  exclude_columns: []

energy:
  enabled: true
  include_metadata: true
  include_patterns: [ ... ]
  include_categories: []
  include_columns: [ ... ]     # raw energy & production signals
  exclude_patterns: []
  exclude_columns: []
```

Any unknown key is rejected at load time by pydantic, so a typo in the
config file fails fast instead of silently producing the wrong
dataset.
