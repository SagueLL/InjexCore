# Sensor Health Intelligence (v1)

`src/intelligence/sensor_health/` — Intelligence-Layer component separating
**instrumentation anomalies** from **process anomalies**, so a faulty sensor
cannot silently contaminate process interpretation.

> **Sensor Health Intelligence recommends quarantine but does not
> automatically exclude sensors.** It never refits models, never changes
> anomaly thresholds, and never modifies upstream artifacts. Every
> recommendation carries `approval_required=True, approved=False`.

## 1. Purpose

Detect, score, persist and report sensor-health issues per timestamp and
sensor over the 17-sensor process scope shared with Correlation/PCA/Anomaly
Intelligence. Rule references are computed on behaviour's persisted train
window only (the layer's leakage contract), and the per-timestamp
`sensor_quality_timeline` it emits is the input the Operational Context
Overlay consumes.

## 2. Inputs

Master dataset (column-projected to the sensor scope), behaviour artifacts
at their fixed paths (`profile_labels.parquet` — strict `align_labels` index
equality is the de-facto behaviour fingerprint; `baselines.parquet` for the
per-(profile, sensor) robust scale `iqr/1.349`; `behaviour_fit_manifest.json`
for vocabulary/scope checks). The sensor scope defaults to
`variable_classification.csv` Category "Process" (`FeatureSelectionPolicy`,
`source: process_sensor`) and is cross-checked against the behaviour
manifest's `sensors`.

## 3. Rule families

All windows in rows at the 1-minute master cadence; all references are
train-window-only and **suppression-consistent** (computed under the same
profile-aware exclusions the rules apply).

| Rule | Computation | Self-calibration |
|---|---|---|
| `flatline` | exact-equality runs (non-zero values) | threshold = max(floor, 1.5 × train max constant run) |
| `flatline_zero` | exact-zero runs | threshold = max(floor, 1.5 × train max zero run outside allowed profiles); 15-row floor for *zero-is-abnormal* sensors (< 0.1% train zeros) |
| `variance_collapse` | trailing rolling std vs baseline scale | only fires below 0.5 × the quietest profile-pure train rolling std — cannot contradict its own reference |
| `variance_explosion` | rolling std > 6 × baseline scale | profile-pure windows only |
| `missingness_spike` | rolling NaN fraction (4 h) | threshold = max(0.5, train rate + 0.25, **train max rolling rate + 0.05**) — sensors with routine outage blocks (weekend gaps) never re-flag the same pattern |
| `abrupt_offset` | two adjacent rolling medians, same profile, both windows pure | **warning-capped**: a step alone never drives faulty |
| `saturation_low/high` | stuck at configured physical bounds | no train-minmax fallback; min=0 defers to flatline_zero |
| `counter_reset` | drop-magnitude semantics for `kind: counter` (oscillating counters — diff-sign is useless) | sub-states: reset_detected / reset_to_zero / recovered_after_reset (warning-grade) / persistent_zero_after_reset (faulty-grade) |
| `stale_signal` | rolling distinct-value collapse | only fires below the train minimum unique fraction; weak corroborator |

**Profile-aware suppression**: candidate runs are computed globally, rows in
the sensor's `expected_zero_during_profiles` / `allow_flatline_profiles` are
dropped, and the surviving contiguous segments are re-thresholded
independently. This silences the six sensors that legitimately sit at 0 for
~5,000 consecutive rows during `stopped` (powers, rates, flow, specific
energy). Zeros during `alarm` are deliberately **not** suppressed (alarm is
a running state) and surface as reviewable warnings.

## 4. Scoring and status

`health_score = min(1, max(base × strength) + 0.1 × (n_families − 1))` with
documented base scores (flatline_zero/counter_reset 0.9 … stale 0.3). Status
is rule-derived: **faulty** = strong rule (base ≥ 0.7) active ≥ 120
contiguous rows, OR ≥ 2 corroborating families with score ≥ 0.7, OR
flatline_zero on a zero-is-abnormal sensor; **warning** = any rule active
otherwise; **unknown** = value missing (or trailing availability < 30%) with
no rule active — chronic gaps (`expander_ex2_hydraulic_press`, 71% train
missingness) are honestly `unknown`, never "healthy by absence of evidence";
**healthy** otherwise. Rule-level evidence stays visible (`active_issue_types`
pipe-joined + compact JSON per flagged row).

## 5. Events and quarantine

Consecutive warning/faulty rows merge into events (gaps ≤ 5 rows bridged);
deterministic ids `SH-<sensor>-<startZ>`; `is_persistent` at ≥ 240 rows
(4 h); every new event is `review_status: pending_review` — nothing is
auto-confirmed. Quarantine is recommended iff an event is **faulty AND
persistent AND** carries a trigger issue (flatline_zero, counter_reset,
saturation, missingness_spike). The recommendation table is the only output
— no model input is modified.

## 6. Outputs

```
data/intelligence/sensor_health/runs/<run_id>/      (run-versioned)
├── scores/sensor_health_scores.parquet             167,331 × 17 long form
├── events/sensor_health_events.parquet
├── summaries/{sensor_health_summary, sensor_quality_timeline,
│              quarantine_recommendations, unsupported_sensors}.parquet
├── sensor_health_report.md · sensor_health_findings.json
└── sensor_health_manifest.json                     written LAST
```

## 7. CLI

```bash
python -m src.intelligence --component sensor-health            # via dispatcher
python -m src.intelligence.sensor_health.run_sensor_health      # direct
python -m src.intelligence --component sensor-health --no-write --log-level DEBUG
```

Flags: `--master --classification --config --profile-labels
--behaviour-manifest --baselines --output-root --run-id --no-write
--log-level`. Policy: `configs/sensor_health_intelligence.yaml` (StrictModel;
per-sensor metadata defaults + overrides; effective config snapshotted in
the manifest).

## 8. What the first real run showed (run `20260612T151654Z`)

- **`inlet_hopper_points`**: one faulty event of **30,096 rows from
  2024-09-17 16:23:22** (flatline_zero + counter_reset:persistent_zero_after_reset)
  and **the only quarantine recommendation** — note the onset is one day
  before the forensic "09-18" headline (the daily-aggregation granularity
  explains the difference).
- 141 events total (138 warning / 3 faulty, 1 persistent); the six
  stopped-state zero sensors produced **no** flatline events;
  `steam_valve_flow_me2` is fully inert by design.
- `granulator_roller_gap`: a 144-row faulty `missingness_spike` episode on
  **2024-09-12 10:13–12:36** — temporally adjacent to a forensic precursor
  candidate date.
- `expander_ex2_hydraulic_press`: 118,994 `unknown` rows (chronic gaps),
  zero events, never quarantined.
- Validation-only signals: `abrupt_offset` (207 rows, the September steam
  step), `variance_collapse` (121), `missingness_spike` (280) — zero
  self-contradicting train rows for the self-calibrated rules.

## 9. Limitations

Reference-based rules cannot see a fault present throughout training;
`abrupt_offset` cannot distinguish steps from legitimate setpoint changes
without plant records; statuses describe instrumentation plausibility, not
process quality. Review statuses require a human decision.

## 10. Future use

Drift Intelligence and Reference Governance (Iteration C Part 2+) are the
intended consumers of the event/quarantine tables; promotion of an approved
quarantine into actual scoring scope stays a manual, recorded decision.
