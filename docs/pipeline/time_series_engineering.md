# InjexCore — Time-Series Engineering Phase

Reference document for the time-series engineering pipeline that turns
`data/processed/Dades_pellet_clean.csv` (167,331 rows × 37 cols, 1-min
cadence, 116 days) into a wide feature matrix
`data/features/Dades_pellet_features.parquet` (167,331 rows × ~323 cols)
plus an auditable report.

---

## 1. Why this exists

After cleaning, the dataset is a tidy, evenly-spaced telemetry table — but
none of its columns describe **how things change over time**. Predictive
maintenance signals live in temporal context: a sensor reading is
informative not because of its absolute value, but because of how it
compares to its recent past (drift), its short-term volatility (rolling
std), and the dynamics of nearby state changes (alarm flapping, time
since last activation).

A single black-box `make_features()` call would hide which transforms
fired and why some columns appeared. We mirror the cleaning module's
**detect + apply** design: every stage first emits one informational
`Finding` per feature it intends to generate (the audit trail), then
applies the transform. The report tells you exactly which features were
created, on which columns, with which parameters.

The pipeline is **semantic-driven**: it consults
`data/features/variable_classification.csv` to decide which feature
families apply to which columns. A process sensor gets rolling stats,
lags and velocity; a setpoint only gets a lag (it is stable by
construction); an alarm flag gets specialised flag-aware features
(`tsla`, `edges`) rather than meaningless rolling means of `{0, 1}`.

---

## 2. Outputs

Running the pipeline writes three artefacts:

| File | Purpose |
|---|---|
| `data/features/Dades_pellet_features.parquet` | Wide feature matrix (~323 cols). Parquet because the column count makes CSV slow and bulky. Feed this to modelling. |
| `data/features/ts_engineering_report.json` | Machine-readable list of every emitted feature, grouped by stage. Each entry records column, family, window/lag, and semantic category. |
| `data/features/ts_engineering_report.md` | Same content grouped by severity, human-friendly table. `NORMAL` rows dominate (each is an audit record for a generated feature); `AWARE` flags non-default behaviour like coercion or resampling. |

The cleaned CSV is **not** overwritten — the two stages stay
independently rerunnable.

---

## 3. How to run it

```bash
# Full run (writes feature matrix + both reports)
python -m src.data.time_series.run_ts_engineering

# Diagnostic only — emits the reports, skips the parquet write
python -m src.data.time_series.run_ts_engineering --no-write

# Cleaning + features in one command (via the shim)
python -m src.preprocessing --stage features
```

CLI flags worth knowing:

- `--clean <path>` — override the cleaned-CSV input path.
- `--policy <path>` — point at a different `time_series.yaml`.
- `--out-parquet <path>` — change the feature matrix output location.
- `--out-csv <path>` — also write a CSV mirror (large; opt-in).
- `--log-level DEBUG` — verbose timing per stage.

A full run on the real dataset takes about **4 seconds** end-to-end and
produces ~290 findings (one per generated feature, plus a handful of
stage-status records).

---

## 4. Pipeline shape

Six sequential stages, executed in this order:

```
load_clean → temporal_conversion → temporal_index → resampling
           → rolling_windows → temporal_features → state_features
           → write(parquet, json, md)
```

| Stage | Purpose | Typical effect on the frame |
|---|---|---|
| `temporal_conversion` | Ensure `timestamp` is `datetime64[ns]`. No-op when cleaning already parsed it. | shape unchanged |
| `temporal_index` | Promote `timestamp` to the `DatetimeIndex` (precondition for resampling and time-aware rolling). | one column removed (it becomes the index) |
| `resampling` | Optional. Unify to a single sampling rule when sources arrive at mixed frequencies. Off by default. | row count changes |
| `rolling_windows` | Generate `mean`, `std`, `trend` per configured window for eligible columns. | many columns added |
| `temporal_features` | Generate `lag`, `pctchg`, `velocity` per configured N for eligible columns. | many columns added |
| `state_features` | Specialised families for `{0, 1}` flags: `runfrac`, `tsla`, `edges`. | columns added for state + alarm flags |

Every stage exposes the same pair of functions:

```python
def detect(df, policy, groups) -> list[Finding]: ...
def apply(df, findings, policy, groups) -> pd.DataFrame: ...
```

`detect` is pure: it decides what to do and records the intent in
`Finding` audit records. `apply` performs the transform. If you ever
want to know "what would this pipeline generate without running it?",
call `detect` and read the resulting findings.

---

## 5. Semantic routing — the most important concept

The pipeline never decides "what to do with column X" by hard-coding the
column name. Instead, it asks
`ColumnGroups.semantic_category(col)` to classify the column into one of:

| Category | Examples | Default treatment |
|---|---|---|
| `process_sensor` | `granulator_power`, `inlet_hopper_temp`, `granulator_production_rate` | Full feature set: `mean`, `std`, `trend`, `lag`, `pctchg`, `velocity` |
| `setpoint` | `conditioner_temp_sp`, `granulator_power_sp` | Lag only (setpoints are stable by construction; rolling stats add noise) |
| `state_flag` | `granulator_g2_running`, `feeder_al2_running` | Generic families disabled; `runfrac`, `tsla`, `edges` from `state_features` |
| `alarm` | `granulator_g2_alarm`, `conditioner_me2_alarm` | Generic families disabled; `tsla`, `edges` from `state_features` |
| `control` | `granulator_g2_state_pct`, `conditioner_l2_state_pct` | Reduced set: `mean`, `lag` |

Classification is read from `data/features/variable_classification.csv`
and resolved by `ColumnGroups.semantic_category()` in
`src/data/cleaning/column_groups.py`. Routing order matters there: a
column ending in `_sp` is matched as `setpoint` before falling through
to its parent `control`; an alarm flag is matched as `alarm` before
`state_flag`.

**This is the key debug entry point.** If you ever see a feature that
should have been generated but wasn't, or a feature that should not
exist but does, check:
1. The column's row in `variable_classification.csv`.
2. The output of `groups.semantic_category("your_column")`.
3. The category's entry in `category_defaults` in `time_series.yaml`.
4. Any matching key in `overrides:` in `time_series.yaml`.

---

## 6. Feature naming convention

Predictable names are how downstream code finds features by pattern. The
convention is **`<source_col>_<family>_<param>`** with these short codes:

| Family | Suffix | Param |
|---|---|---|
| Rolling mean | `_mean_<W>` | window in samples |
| Rolling std | `_std_<W>` | window in samples |
| Rolling trend (mean of Δx over W) | `_trend_<W>` | window in samples |
| Lag (`.shift(N)`) | `_lag_<N>` | sample offset |
| Percent change (`.pct_change(N)`) | `_pctchg_<N>` | sample offset |
| Velocity (`.diff(N)`) | `_velocity_<N>` | sample offset |
| Running fraction (flags only) | `_runfrac_<W>` | window in samples |
| Time since last active (flags only) | `_tsla` | — |
| Rising-edge count (flags only) | `_edges_<W>` | window in samples |

Examples from the real run:

- `granulator_power_mean_60` — mean power over the previous 60 samples.
- `granulator_power_velocity_1` — Δpower over one sample (instantaneous rate).
- `granulator_production_rate_mean_240` — note the 240 window, present only because of a per-column override.
- `granulator_g2_alarm_edges_60` — rising edges (alarm activations) in the last 60 samples.
- `granulator_g2_running_runfrac_60` — fraction of the last 60 samples the unit was running.

Windows and lags are expressed in **samples**, never seconds. With
resampling disabled (the default) one sample is 60 seconds, so
`mean_60` is a one-hour rolling mean. If you change the resampling rule
the window's wall-clock meaning changes — adjust the policy accordingly.

---

## 7. Leakage strategy — `closed='left'`

A rolling window at index `t` could include the value at `t` itself
(`closed='right'`, the pandas default) or stop just before
(`closed='left'`). For a target aligned to time `t` ("anomaly at this
cycle"), including the value at `t` is **direct leakage** through the
rolling feature.

The pipeline enforces `closed='left'` by default for every rolling
family. The window at index `t` sees samples `[t - W, t)` only. This is
verified in `tests/unit/data/time_series/test_rolling_windows.py`:

```python
df["granulator_power"] = np.arange(20)
out = rolling_windows.apply(df, findings, policy, groups)
# Mean over previous 5 samples at row 10 = mean(5..9) = 7, NOT mean(6..10) = 8
assert out["granulator_power_mean_5"].iloc[10] == 7
```

The setting is exposed per-family in the YAML
(`closed: left | right | neither | both`) so it can be relaxed for
forecasting tasks where the target lives at `t + k` and leakage is no
longer a concern.

Lag, pct_change, and velocity with `N ≥ 1` are leak-safe by construction
(`.shift(N)` cannot expose future values).

---

## 8. Policy file walkthrough

`configs/time_series.yaml` has four sections.

### 8.1 Stage toggles

```yaml
temporal_conversion: { enabled: true, timestamp_col: timestamp }
temporal_index:      { enabled: true, drop_duplicates_on_index: true }
resampling:
  enabled: false           # cleaning already enforces a 60 s grid
  rule: "1min"
  aggregations:
    process_sensor: mean
    setpoint:       last
    state_flag:     max     # any-on within the window
    alarm:          max
    control:        mean
state_features:
  enabled: true
  running_fraction_windows: [15, 60, 240]
  time_since_active: true
  edge_count_windows: [60, 240]
```

### 8.2 Per-category defaults

Each semantic category gets a `CategoryDefaults` block, one entry per
generic feature family:

```yaml
category_defaults:
  process_sensor:
    rolling_mean:  { enabled: true,  windows: [5, 15, 60], closed: left }
    rolling_std:   { enabled: true,  windows: [5, 15, 60], closed: left }
    rolling_trend: { enabled: true,  windows: [15, 60],    closed: left }
    lag:           { enabled: true,  lags: [1, 5, 15] }
    pct_change:    { enabled: true,  lags: [1, 5] }
    velocity:      { enabled: true,  lags: [1] }
  setpoint:
    lag: { enabled: true, lags: [1] }
    # all other families disabled
  state_flag: { lag: { enabled: true, lags: [1] } }
  alarm:      { lag: { enabled: true, lags: [1] } }
  control:
    rolling_mean: { enabled: true, windows: [15, 60], closed: left }
    lag:          { enabled: true, lags: [1, 5] }
```

To add a new family to every process sensor (e.g. extend
`rolling_mean` to `[5, 15, 60, 240]`), edit this block. No code change.

### 8.3 Per-column overrides

Overrides apply **on top of** the column's category defaults. Two real
examples in use:

```yaml
overrides:
  granulator_production_rate:
    windows: [5, 15, 60, 240]            # widens every rolling family for this column
  inlet_hopper_points:
    disable_families: [pct_change, velocity]  # cumulative counter — diffs are meaningless
```

`windows` / `lags` (when set) **replace** the category values on every
enabled family for that column. `disable_families` /
`enable_families` toggle the `enabled` flag.

The merge logic is `TimeSeriesPolicy.resolve(category, column)` in
`src/data/time_series/policy.py`. When debugging a missing or
unexpected feature, call this function in a REPL — its output is the
exact `CategoryDefaults` that drove the column's feature generation.

---

## 9. Stage reference

### 9.1 `temporal_conversion` — `src/data/time_series/temporal_conversion.py`

Cleaning already parses `timestamp` to `datetime64[ns]`, but
`io.load_clean()` reads the CSV back as strings, so this stage re-parses
it. Emits `NORMAL/already_datetime` when no work was needed and
`AWARE/coerce_datetime` when a parse was applied. Bad cells become
`NaT` — the cleaning stage's own `timestamps` module would have caught
those earlier, so it should not happen on a freshly-cleaned input.

### 9.2 `temporal_index` — `src/data/time_series/temporal_index.py`

Promotes the timestamp column to the index, dropping duplicates first
(keep first) when configured. Resampling and time-aware rolling depend
on this; if it fails, subsequent stages either skip silently
(resampling) or fall back to integer-position windows (rolling). If you
see `temporal_index` emit an `AWARE/duplicate_index` finding, an
upstream cleaning bug is likely — duplicates should have been removed
by the cleaning `duplicates` module.

### 9.3 `resampling` — `src/data/time_series/resampling.py`

Skipped by default. When enabled, each column is aggregated using its
semantic category's rule (`process_sensor → mean`, `state_flag → max`,
etc.). Unknown columns fall back to `last`.

**When to enable.** If real machine data ever arrives at mixed sampling
rates (temperature at 1 s, energy at 5 s, PLC events as ad-hoc rows),
flip `resampling.enabled: true` and set `rule` to your unification
target. The cleaning stage's 60 s grid means this is off for the
current pellet dataset.

### 9.4 `rolling_windows` — `src/data/time_series/rolling_windows.py`

Iterates eligible columns (`process_sensor` + `control`, skipping state
and alarm), resolves the policy, emits one `Finding` per
`(column, family, window)` and applies them all in `apply()`. All
windows use `min_periods=max(2, window // 4)` so the early rows of the
matrix are not full of `NaN` for large windows — they instead carry a
partially-filled estimate as soon as enough samples exist.

To **add a new rolling family** (e.g. rolling median), add a new
`finding_type` constant, wire it into the `_FAMILIES` tuple and the
`apply()` branch, and add it to `CategoryDefaults` in `policy.py`.
About 15 lines.

### 9.5 `temporal_features` — `src/data/time_series/temporal_features.py`

Same shape as `rolling_windows`, but for shift-based features
(`shift`, `pct_change`, `diff`). Lag-of-N rules are leak-safe by
construction.

### 9.6 `state_features` — `src/data/time_series/state_features.py`

Three families that preserve the **physical meaning** of binary flags:

- **`<col>_runfrac_<W>`** — `df[col].rolling(W, closed='left').mean()`
  on running flags. "Fraction of last W samples the unit was on."
  Useful as a soft activity indicator.
- **`<col>_tsla`** — *time since last active*, in samples. `0` while
  the flag is currently `1`; an integer counter while off; `NaN`
  before the first activation has been observed. Implementation walks
  the series once with a counter — `O(N)`, slower than vectorised
  pandas calls, which is why this stage takes ~2 s on the full
  dataset.
- **`<col>_edges_<W>`** — count of `0 → 1` transitions in the last W
  samples. Surfaces alarm flapping and rapid cycle restarts —
  documented predictive-maintenance signals.

If `state_features.enabled: false` the whole stage no-ops and emits a
single `NORMAL/skipped` finding.

---

## 10. Where things live

```
src/data/time_series/
  __init__.py
  policy.py                 # Pydantic schema, load_policy(), .resolve()
  column_groups.py          # re-export of cleaning's loader
  reporting.py              # re-export of Finding / Severity / writers
  io.py                     # load_clean(), write_features(parquet [+csv])
  temporal_conversion.py    # Stage 1
  temporal_index.py         # Stage 2
  resampling.py             # Stage 3
  rolling_windows.py        # Stage 4
  temporal_features.py      # Stage 5
  state_features.py         # Stage 4b (specialised)
  run_ts_engineering.py     # CLI orchestrator

configs/
  time_series.yaml          # all thresholds, windows, overrides

tests/unit/data/time_series/
  test_temporal_conversion.py
  test_temporal_index.py
  test_resampling.py
  test_rolling_windows.py
  test_temporal_features.py
  test_state_features.py
  test_run_ts_engineering.py
```

Shared infrastructure reused from the cleaning module (no fork):

- `Finding`, `Severity`, `write_json`, `write_markdown` — `src/data/cleaning/reporting.py`
- `ColumnGroups`, `load_groups`, `ColumnGroups.semantic_category` — `src/data/cleaning/column_groups.py`
- Test fixtures `tiny_frame_factory`, `groups`, `project_root` — `tests/conftest.py`
- A new session-scoped `ts_policy` fixture is added alongside the existing `policy` fixture.

---

## 11. Common failures and where to look

| Symptom | Most likely cause | Where to look |
|---|---|---|
| A feature you expected is missing | Column not classified in `variable_classification.csv`, or category default has the family disabled | `ColumnGroups.semantic_category()` output for the column; `category_defaults` block in `time_series.yaml` |
| A feature exists but you wanted it disabled | Category default has it on; no override yet | Add an `overrides:` entry with `disable_families: [...]` |
| Window width is wrong | Either category default or per-column override is in samples, not seconds | The window applies *after* resampling; re-read §6 |
| Rolling values look "too good" (overfitting downstream) | `closed` is not `left` somewhere | Check `evidence.closed` in the `ts_engineering_report.json` for the suspicious column |
| `temporal_index` complains about duplicates | Upstream cleaning regression | Re-run cleaning; verify `duplicates` module is firing |
| Resampling produced unexpected row counts | Wrong `rule` or running on data without a `DatetimeIndex` | Check `temporal_index` ran first; confirm `rule` (e.g. `"1min"`, `"5s"`) |
| Parquet write fails | `pyarrow` missing | `pip install -r requirements.txt` |
| State-features stage is slow on big data | `_tsla` walks the series in pure Python | Acceptable on the current 167k-row dataset (~2 s); if it ever becomes a bottleneck, vectorise with the same `cumsum` trick used for `_rising_edges` |

For everything else: the JSON report is the source of truth. Every
generated column has exactly one `Finding` record there, with the
column, the family, the parameter (window or lag), the semantic
category that drove the routing decision, and (for rolling families)
the `closed` setting. Search by `column` to retrace why any specific
feature came out the way it did.
