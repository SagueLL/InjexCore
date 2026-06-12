# Operational Context Overlay

`src/context/operational/` — second component of the external-context layer.
Combines, for every master timestamp: the Behaviour **profile**, a derived
**steam-conditioning context**, the **sensor-health context** and the **BOM
context** into one master-aligned timeline, plus context-transition events
and a read-only context-aware forensic addendum.

> **The Operational Context Overlay enriches interpretation but does not
> modify existing model fitting or scoring.** It never touches the master
> dataset, the BOM artifacts, or any Intelligence-Layer model.

## 1. Inputs (Gate A — hard-gated)

Master timestamps + the two steam sensors (column-projected read); behaviour
labels (`align_labels` strict index equality); a *completed* sensor-health
run's `sensor_quality_timeline.parquet` (default `latest`); a *completed*
BOM run's `bom_context_timeline.parquet` (pinned `20260612T124909Z`);
anomaly run `20260611T173316Z` + forensic run `20260612T101850Z` for the
addendum only. Every timeline must align row-for-row with the master
(`expected_master_rows: 167331`); train-window coherence between behaviour
and the sensor-health run is enforced. Any failure is a blocker — never a
degraded run.

## 2. Steam-conditioning context

Derived only from `steam_valve_pressure_me2` + `conditioner_steam_loop_temp`
(`steam_valve_temp_me2` is evidence-only; the flow signal is excluded —
median 0 even while conditioning). Per-row indicator
`pressure ≥ 1.0 bar OR loop_temp ≥ 60 °C` (one missing signal lets the other
decide), smoothed over a **centered ±2 h persistence window** — never
single-row. States: `steam_conditioning_off / intermittent / on / unknown`
(+ confidence + evidence string per row). Thresholds sit in the verified
dead band (stopped medians 0.18 bar / 34 °C vs running 2.5–2.9 bar /
85–89 °C).

**Honesty note (verified on the real run):** row-level steam context tracks
production activity — production rows classify as *on* even in the train
window, and the steam-on share *within stopped rows* does **not** rise after
2024-09-16 (it falls). The forensic "off → intermittent (09-09) → on (09-16)"
narrative was built on daily medians and is therefore composition-sensitive;
the overlay's steam × profile cross table makes this checkable instead of
asserting it.

## 3. Overlay and transitions

`operational_context_timeline.parquet`: exactly one row per master timestamp
with profile, `is_train`, the 3 steam columns, the 4 sensor-health columns
(sensor lists preserved, never collapsed), all 14 BOM columns **unchanged**
(overlap rows keep every matching order, scalars null — BOM's
no-silent-selection policy is re-validated here), and a deterministic
`context_key` (`profile:steam:health:bom_status` — metadata only, never a
model input). `context_transition_events.parquet` records every change of
the tracked dimensions with multi-valued pipe-joined `transition_types` ∈
{profile_change, steam_context_change, sensor_health_change, product_change,
recipe_change, bom_overlap_start/end, bom_gap_start/end}.

## 4. Outputs

```
data/context/operational/runs/<run_id>/             (run-versioned)
├── timeline/operational_context_timeline.parquet
├── transitions/context_transition_events.parquet
├── summaries/{steam_context_summary, sensor_health_context_summary,
│              bom_context_summary, context_coverage}.parquet
├── operational_context_report.md · operational_context_findings.json
└── operational_context_manifest.json               written LAST

data/intelligence/forensics/context_addenda/<run_id>/
├── anomaly_rates_by_{steam_context, sensor_health_context,
│                     operational_context}.parquet
├── candidate_dates_context_summary.parquet
├── executive_summary.md · limitations.md · figures/*.png (5)
└── context_addendum_manifest.json                  last within its dir
```

## 5. CLI

```bash
python -m src.context.operational --config configs/operational_context.yaml
python -m src.context.operational --no-write --log-level DEBUG
python -m src.context.operational --skip-addendum
```

Flags: `--config --master --sensor-health-run --bom-run --output-root
--addendum-root --run-id --no-write --skip-addendum --log-level`. Policy:
`configs/operational_context.yaml` (StrictModel).

## 6. What the first real run showed (run `20260612T154108Z`)

- 167,331 rows, exact master alignment; steam: 78,087 on / 57,575 off /
  31,669 intermittent (0 unknown); sensor health: 136,320 healthy / 771
  warning / 30,240 faulty rows; 2,575 transitions.
- **Anomaly rates split decisively by sensor-health context, not by steam
  context**: validation anomaly rate **99.5% inside `sensor_faulty` rows vs
  3.9% in `all_sensors_healthy` rows**, while steam contexts are flat
  (61–64%). The instrumentation fault carries the validation anomaly mass.
- 2024-09-16 window: profile/order handovers plus 3 steam-context
  transitions and 2 sensor-health transitions — no BOM recipe/product
  change (consistent with the BOM addendum).
- 2024-09-18 window: the escalation sits inside the
  `inlet_hopper_points` flatline-zero (actual onset 2024-09-17 16:23); a
  `granulator_roller_gap` missingness episode (2024-09-12 10:13) is the
  first `sensor_faulty` context overall — adjacent to a forensic precursor
  date.

## 7. Limitations

Steam context cannot distinguish an intentional operating-mode decision
from an uncommanded valve state; sensor-health context is rule-based
plausibility; the anomaly models were fitted blind to every context shown
here. All addendum statements are temporal associations — see
`limitations.md` per run.

## 8. Future use

The overlay (and `context_key`) is the substrate for Iteration C Part 2
(Drift Intelligence + Incident Aggregation) and, later, Reference
Governance — none of which are implemented yet.
