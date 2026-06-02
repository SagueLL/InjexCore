# InjexCore — Data Cleaning Phase

Reference document for the cleaning pipeline that turns
`data/raw/Dades_pellet.csv` (167,331 rows × 37 cols, 1-min cadence, 116 days)
into `data/processed/Dades_pellet_clean.csv` plus an auditable report.

---

## 1. Why this exists

The dataset comes straight from a PLC export. Five things make raw PLC
telemetry unsafe for modelling:

1. Missing values that mean different things (sensor failure vs. machine
   simply off vs. lost connection vs. maintenance window).
2. Duplicate rows from PLC bursts, retries, or timestamp collisions.
3. Corrupt or unordered timestamps.
4. Stuck (“frozen”) sensors that report the same number for hours.
5. Physically impossible values (negative pressure, > 100 % humidity, …).
6. Cross-signal contradictions (production > 0 while machine flagged off).

A single black-box “clean()” call would hide which of these fired. We
chose a **modular, detect+remediate** design: every check is a separate
module that first **detects** issues (always lossless) and then
**applies** a remediation driven by a YAML policy file. The diagnostic
report tells you which rules fired, on which rows, and what was done.

---

## 2. Outputs

Running the pipeline writes three artefacts:

| File | Purpose |
|---|---|
| `data/processed/Dades_pellet_clean.csv` | Cleaned dataset, dot-decimal, UTF-8, logical column names. Feed this to feature engineering and modelling. |
| `data/features/cleaning_report.json` | Machine-readable findings, grouped by check and severity. Long row-index lists are truncated to a 20-item head/tail sample to stay readable. |
| `data/features/cleaning_report.md` | Same content as the JSON but grouped by severity, in a human-friendly table. |

---

## 3. How to run it

```bash
# Full run (writes cleaned CSV + both reports)
python -m src.data.cleaning.run_cleaning

# Diagnostic only — emits the reports, skips the CSV write
python -m src.data.cleaning.run_cleaning --no-write

# Equivalent legacy entry point (re-export shim):
python -m src.preprocessing
```

CLI flags worth knowing:

- `--raw <path>` — override the raw CSV path.
- `--policy <path>` — point at a different `cleaning.yaml`.
- `--log-level DEBUG` — verbose timing per module.

---

## 4. Pipeline architecture

```
load_raw()
  ↓
timestamps.detect + apply      → drop NaT, sort, tag gaps/jumps
  ↓
duplicates.detect + apply      → drop duplicate timestamps & PLC bursts
  ↓
physical_ranges.detect + apply → mask out-of-bound cells to NaN
  ↓
frozen_sensors.detect + apply  → mask stuck cells on forecasting targets
  ↓
state_consistency.detect       → tag-only (no apply step)
  ↓
missing_values.detect + apply  → classify every remaining NaN and remediate
  ↓
write(processed_csv, report_json, report_md)
```

The order matters. `missing_values` runs **last** on purpose: earlier
modules (`physical_ranges`, `frozen_sensors`) may mask additional cells
to NaN, and we want a single, typed classification of all NaNs at the
end.

Each module exposes the same uniform interface:

```python
def detect(df, policy, groups) -> list[Finding]
def apply(df, findings, policy, groups) -> pd.DataFrame
```

`Finding` (defined in `src/data/cleaning/reporting.py`) is the lingua
franca:

```python
@dataclass
class Finding:
    check: str              # which module produced it
    severity: Severity      # critical | important | aware | normal
    finding_type: str       # e.g. "broken_sensor", "out_of_range"
    column: str | None
    row_range: (int, int) | None
    count: int
    action_taken: str       # what apply() did with this row/cell
    evidence: dict          # debug payload (sample values, thresholds…)
```

---

## 5. Severity taxonomy

The same four labels are used across every module, so you can grep the
report for one severity and see everything urgent in one place.

| Severity   | Meaning                                                  | Default action            |
|------------|----------------------------------------------------------|---------------------------|
| `critical` | Data is unusable; would corrupt models if left untouched | Drop row / mask cell      |
| `important`| Real quality issue requiring a deliberate rule           | Apply configured strategy |
| `aware`    | Suspicious but legitimate (e.g. machine off → NaN)       | Tag, do not modify        |
| `normal`   | Expected behaviour, logged for traceability              | No action                 |

---

## 6. The six modules

### 6.1 `timestamps.py`

| Sub-check | Detection | Severity | Action |
|---|---|---|---|
| Unparseable timestamp | `pd.to_datetime` returns `NaT` | critical | Drop row |
| Non-monotonic | `t[i] < t[i-1]` | critical | Sort once |
| Gap | Δ > `gap_factor × expected_period_s` (default 2×60 s) | important | Tag |
| DST / TZ jump | Δ > `max_legal_jump_s` (default 3600 s) | important | Tag (manual review) |

Example: between `2024-10-04 15:31:13.870` and `2024-10-04 15:33:14.020`
the delta is 120.15 s → flagged as a gap.

### 6.2 `duplicates.py`

| Sub-check | Detection | Severity | Action |
|---|---|---|---|
| Duplicate timestamp | Same `timestamp` repeated | important | Keep first, drop the rest |
| Duplicate payload | Identical signal-column values within a 5-row sliding window | aware | Tag (steady-state is legitimate) |
| PLC burst | ≥ 3 rows whose pairwise delta < `burst_max_delta_s` (default 1 s) | important | Keep the median-positioned row, drop neighbours |

### 6.3 `physical_ranges.py`

For every column listed in `configs/cleaning.yaml` →
`physical_ranges.bounds`, flag cells outside `[min, max]`. Severity is
**per bound** (set in YAML), not per module.

- `critical` → `mask_nan` (cell becomes NaN, then re-classified by
  `missing_values` as `broken_sensor`).
- `important` → if `clip_soft_violations: true`, clip to `[min, max]`;
  otherwise mask to NaN.
- `integer: true` → also flag fractional values in binary state flags
  (e.g. `granulator_g2_running == 0.5`).

Example: `inlet_hopper_humidity` bound `{ min: 0.0, max: 100.0 }`. A
reading of `120.5` becomes `NaN` and surfaces as a `critical
out_of_range` finding with `sample_values: [120.5, …]` in evidence.

### 6.4 `frozen_sensors.py`

A frozen run is `≥ frozen_min_minutes` consecutive non-NaN samples that
are equal — exact for general columns, `|Δ| < epsilon` for rate columns
(`epsilon_rate_cols` in policy: `granulator_production_rate`,
`steam_valve_flow_me2`). Whitelisted columns (`skip_columns`) are
ignored — SCADA `_state_pct` registers are legitimately constant for
long stretches.

Severity rules:

- `critical` if the column's `Potential_Objective` (from
  `variable_classification.csv`) is `temperature_forecasting` or
  `pressure_forecasting` → mask the frozen cells to NaN.
- `aware` if all running flags are 0 during the run (machine off).
- `important` otherwise → tag only (values kept).

### 6.5 `state_consistency.py` (detect-only)

Cross-signal contradictions. `apply()` is a no-op — these findings are
informational only, because the “contradiction” may be the true PLC
state and silently rewriting it would hide a real machine problem.

| Rule | Severity |
|---|---|
| `granulator_g2_running == 0` AND `granulator_production_rate > min_production_kgmin` | important |
| `granulator_g2_running == 1` AND `granulator_power < min_power_pct` | important |
| Any `*_alarm == 0` AND any temperature > `hot_temperature_threshold_c` (default 200 °C) | important |
| `*_alarm == 1` AND corresponding `*_running == 0` for > `alarm_shutdown_window_min` | aware |
| For each (SP, PV) pair: `|SP-PV|/SP > sp_pv_max_drift_pct` sustained > `sp_pv_drift_min_minutes` | aware |

SP/PV pairs are listed at the top of the module
(`_SP_PV_PAIRS`). Add a new pair there if you wire up a new control
loop.

### 6.6 `missing_values.py` (runs last)

The most important module. Walks every NaN run and **classifies why it
is missing** before deciding what to do:

| Type | Rule | Severity | Strategy |
|---|---|---|---|
| `missing_by_design` | Column ∈ `missing_by_design_columns` (`batch_id`, `batch_quality_id`) | normal | Keep NaN |
| `machine_off` | `granulator_g2_running == 0` AND `feeder_al2_running == 0` AND col ∈ Process | aware | Keep NaN |
| `maintenance_window` | Alarm flag transitions 0→1→0 within ±`alarm_alignment_window_min` of the run | aware | Keep NaN |
| `broken_sensor` | Run length > `broken_sensor_min_run` (default 30) AND a running flag = 1 | critical | Tag only — keep NaN as a model-visible signal |
| `lost_communication` | Run length ≤ `interpolation_max_run` (default 5) AND a running flag = 1 | important | Time-based interpolation (`method='time'`) |
| `continuous_sensor` | Single isolated NaN on a Process column | important | Forward-fill 1 step |
| `undeterminable_state` | Running flag itself is NaN | critical | **Drop the row** (we can't tell what the machine was doing) |

Anything not matching the above is tagged `aware /
unclassified_nan / keep_nan` — never silently dropped.

---

## 7. Policy file — `configs/cleaning.yaml`

Single source of truth for thresholds and per-variable physical
bounds. Loaded via `pydantic-settings` into `CleaningPolicy` at startup
— no magic numbers in code. Schema lives in
`src/data/cleaning/policy.py`.

Adding a new bound is a one-liner:

```yaml
physical_ranges:
  bounds:
    new_sensor_name: { min: 0.0, max: 250.0, severity: important }
```

---

## 8. Initial run on `Dades_pellet.csv`

Counters from the live report (`data/features/cleaning_report.json`,
last full run):

| Module | Total | Breakdown |
|---|---:|---|
| `timestamps` | 4 | 4 important (the known sub-2-min gaps) |
| `duplicates` | 0 | — |
| `physical_ranges` | 6 | 3 critical, 3 important |
| `frozen_sensors` | 718 | 42 critical, 565 important, 111 aware |
| `state_consistency` | 728 | 2 important, 726 aware |
| `missing_values` | 1,776 | 139 critical, 8 important, 501 aware, 1,128 normal |
| **Total** | **3,232** | **184 critical, 582 important, 1,338 aware, 1,128 normal** |

Observations:

- The dataset is **structurally** very clean (zero raw NaN on signal
  columns, zero duplicate timestamps, perfect 1-min sync). Most
  remediation pressure comes from physical-bound and frozen-sensor
  rules.
- `expander_ex2_hydraulic_press` reads slightly negative (~−0.09 bar)
  on ~70 % of rows. With the strict `min: 0.0` bound, 119,278 cells
  were masked. **This is almost certainly sensor offset, not a real
  fault** — needs to be re-bounded to ~`-1.0` after talking to the
  domain expert.
- 42 frozen-run criticals on forecasting-target columns — worth a manual
  glance before locking the policy.
- Batch identifiers (`batch_id`, `batch_quality_id`) are NaN on
  53.7 % of rows by design (PLC only writes them at batch
  boundaries). Classified `normal / missing_by_design`, kept as-is.

---

## 9. Code & file map

```
src/
├── data/
│   ├── __init__.py
│   └── cleaning/
│       ├── __init__.py
│       ├── run_cleaning.py       # CLI orchestrator
│       ├── policy.py             # pydantic schema for cleaning.yaml
│       ├── reporting.py          # Finding dataclass, JSON/MD writers
│       ├── io.py                 # Spanish-locale CSV loader (3-row header)
│       ├── column_groups.py      # variable_classification.csv → column sets
│       ├── timestamps.py
│       ├── duplicates.py
│       ├── physical_ranges.py
│       ├── frozen_sensors.py
│       ├── state_consistency.py
│       └── missing_values.py
└── preprocessing.py              # back-compat re-export shim

configs/
└── cleaning.yaml                 # all thresholds, per-variable bounds

tests/unit/data/cleaning/         # 40 unit tests, run with `pytest tests/`

data/
├── raw/Dades_pellet.csv          # source (read-only)
├── processed/Dades_pellet_clean.csv
└── features/
    ├── cleaning_report.json
    ├── cleaning_report.md
    ├── variable_classification.csv     # drives column grouping
    ├── data_pellets_dictionary.csv     # PLC code → logical name
    └── temporal_quality_report.json    # consumed by timestamps.py
```

---

## 10. Troubleshooting cheat-sheet

| Symptom | Where to look |
|---|---|
| New numeric column reads as 100 % NaN | `io.py` — column probably not in the dictionary CSV, so its name didn't get mapped to a logical one. Add the row to `data/features/data_pellets_dictionary.csv`. |
| `ValueError: Expected 'timestamp' column after renaming` | Same root cause — the dictionary doesn't know how to map `Fecha`. |
| YAML parse error on startup | Inline flow mappings in `cleaning.yaml` need a space after `:` (e.g. `key: { min: 0 }`, NOT `key:{ min: 0 }`). |
| One column is masking 70 %+ of its values | Bound in `physical_ranges.bounds` is too tight. Inspect a few raw values, widen the bound, re-run with `--no-write`. |
| Frozen-sensor module flags an obviously-constant control register | Add the column to `frozen_sensors.skip_columns` in `cleaning.yaml`. |
| Missing-values run-time grew a lot | Each NaN run is classified individually — check that no upstream module is shredding a column into thousands of single-NaN runs (likely physical_ranges with an over-aggressive bound). |
| Cleaned CSV is the same row count as raw | Normal on this dataset. Rows only drop when there's an `undeterminable_state` (NaN running flag), `duplicate_timestamp`, `plc_burst`, or `unparseable_timestamp`. |
| Tests fail on `import` | Use `py -3 -m pytest tests/` (the `python` launcher on this machine maps to a Python without pytest). |
| Need to add a new cross-signal rule | Add a `_rule_<name>` helper in `state_consistency.py` and append its findings in `detect()`. Bump policy keys in `cleaning.yaml` if you need new thresholds. |
| Report JSON exploded in size | `_truncate_evidence` in `reporting.py` caps list-valued evidence at 20 entries. If a new finding uses a large dict-of-lists, mirror that pattern. |

---

## 11. What is *not* in this phase (by design)

- No feature engineering — happens after cleaning, on the
  `Dades_pellet_clean.csv` output.
- No model training — out of scope.
- No imputation beyond the two narrow cases (`forward_fill_1` for
  isolated NaN, `interpolate_time` for runs ≤ 5). `broken_sensor` runs
  are kept as NaN deliberately, so a downstream model can use them as
  a feature (“sensor was down”).
- No outlier removal beyond physical bounds — statistical outlier
  handling belongs in feature engineering, with model context.
- The raw CSV is **never** modified. Cleaning is an additive,
  re-runnable transform.

---

## 12. Next steps

1. Domain-expert pass over the bounds in `configs/cleaning.yaml`,
   especially `expander_ex2_hydraulic_press`.
2. Review the 42 frozen-run criticals on forecasting targets — decide
   whether to mask or keep.
3. Lock the policy and copy the agreed thresholds into
   `.claude/CLAUDE.local.md` for posterity.
4. Hand the cleaned CSV to the feature-engineering phase.
