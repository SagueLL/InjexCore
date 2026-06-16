# Incident Aggregation (v1)

`src/intelligence/incidents/` — converts thousands of row-level findings
into a compact set of persistent, contextualized, reviewable operational
incidents, with relationships, recommended actions and a prioritized
human-review pack, plus the **drift-aware forensic addendum**.

Strictly read-only over upstream artifacts. **Incident relationships are
associative and temporal — they do not establish causality**
(`causality_status = "unknown"` on every row, hardcoded). No sensor is ever
excluded automatically and no quarantine recommendation is ever approved
(`approval_required=True, approved=False`, hardcoded). Runs are versioned
under `data/intelligence/incidents/runs/<run_id>/`
(`incidents_manifest.json` written last = completion marker).

## 1. Inputs

Five completed upstream runs (policy pins in
`configs/incidents_intelligence.yaml` → `upstream`, or `--<name>-run` CLI
flags): the **drift** run (events + raw-vs-healthy comparison), the
**sensor-health** run (events + quarantine recommendations), the **anomaly**
run (per-row severities for burst detection), the **operational-context**
run (timeline for context joins + transition events) and the **BOM** run
(order transitions). Gate checks warn when the drift run was built against
different sensor-health/anomaly/operational runs than incidents resolves.

## 2. Sources → candidates

Every input is normalized into one candidate shape (`sources.py`):

* sensor-health events → `sensor_fault` (faulty; `critical` when persistent
  with a strong issue family) / `sensor_warning` / `data_quality_issue`
  (missingness-only episodes);
* drift events → mapped by drift type (`sensor_drift → sensor_fault`,
  `correlation_shift → correlation_break`, …), both views;
* anomaly rows → `anomaly_burst` candidates when the bucketed
  warning/anomaly rate stays ≥ `bursts.rate_threshold` for
  ≥ `min_duration_minutes` (gap-merged);
* operational transitions → `context_shift` (only the configured types —
  profile churn is routine operation, not an incident);
* BOM order transitions → `context_shift`.

Sources that contribute nothing land in
`unsupported_incident_sources.parquet`, never silently skipped.

## 3. Grouping, recurring collapse, cross-source merge, suppression

* **Grouping** — sweep-merge per (candidate type, group family) with a
  per-family temporal-adjacency gap and a Jaccard gate on affected sensors
  (two entity-less candidates agree). Incident = union of members, max
  severity, min start / max end; status `persistent` / `open` (touches data
  end) / `resolved`; `review_status = pending_review` always.
* **Recurring collapse** — when one (type, family) still yields more than
  `recurring_collapse_min` incidents *and* the type is a routine-pattern
  type (`sensor_warning`, `context_shift`, `data_quality_issue`), the whole
  group collapses into ONE incident recording the recurrence count. Bursts
  and faults are never collapsed.
* **Cross-source merge** — same-type incidents on exactly the same sensors
  whose intervals overlap ≥ `cross_source_overlap_fraction` merge across
  sources: a drift-promoted sensor event and its sensor-health original are
  one physical episode (sources unioned, `merged_from` recorded).
* **Suppression** — an `anomaly_burst` covered ≥
  `suppression.coverage_fraction` by a `sensor_fault` incident with shared
  sensors is removed from `incidents.parquet` and recorded in
  `suppressed_duplicate_events.parquet` (id, suppressed_by, reason,
  coverage) — transparent, never silent.

## 4. Relationships

Pairwise over start-sorted incidents bounded by the adjacency window:
interval logic (`contains` / `overlaps` / `temporally_adjacent` /
`follows`), entity logic (`shares_sensors` / `shares_context`),
`possibly_explains` (a sensor fault containing/overlapping a burst,
multivariate shift or correlation break **and sharing at least one affected
sensor** — INC-01: it is never emitted on interval overlap alone, and its
evidence lists the actual shared sensors) and `corroborates` (two sensor
faults on the same sensor). Confidence is interval/Jaccard-derived;
**every row carries `causality_status = "unknown"`**.

## 5. Recommended actions

Per-type action table (`actions.by_type`, configurable) — e.g.
`inspect_sensor_channel`, `inspect_counter_reset` (added when counter-reset
evidence is present), `review_historian_mapping`, `review_maintenance_log`,
`review_setpoint_changes`, `review_operator_notes`,
`compare_healthy_only_drift`, `inspect_product_recipe_context`. Persistent
critical sensor faults additionally get `quarantine_from_process_scoring`
with `approval_required=True, approved=False` — a recommendation requiring
human approval, mirroring the Sensor Health discipline.

## 6. Review pack

`incident_review_pack.parquet`: one compact row per reviewable incident with
its operational contexts (steam / sensor-health / product / recipe) joined
from the persisted timeline, triggered detectors, supporting metrics,
related incident ids and recommended actions. Temporal deduplication
collapses same-type near-identical rows (the keeper records the collapsed
ids; `incidents.parquet` keeps everything); prioritization orders by
severity → persistence → sensor faults → healthy-only residual evidence →
detector agreement → earliest start; truncated at `review_pack.max_rows`.

## 7. Drift-aware forensic addendum

Final stage (skippable with `--skip-addendum`; mirrors the BOM layer's
Stage H). Writes to `data/intelligence/forensics/drift_addenda/<run_id>/`:
`executive_summary.md` (cautious, computed answers to the eight Part 2
forensic questions), `limitations.md`, five parquet tables
(`raw_vs_healthy_only_comparison`, `drift_by_sensor_health_context`,
`drift_by_steam_context`, `top_drift_events`, `incident_review_pack` — all
re-written from in-memory frames, never file-copied) and five figures
(`raw_vs_healthy_only_drift.png`, `drift_by_sensor_health_context.png`,
`drift_by_steam_context.png`, `top_drift_events_timeline.png`,
`incident_timeline.png`); the addendum manifest is written last within its
own directory. matplotlib (Agg) is imported lazily, only when the stage runs.

## 8. Outputs

`data/intelligence/incidents/runs/<run_id>/incidents/`: `incidents.parquet`,
`incident_relationships.parquet`, `incident_review_pack.parquet`,
`incident_timeline.parquet`, `incident_summary.parquet`,
`recommended_actions.parquet`, `suppressed_duplicate_events.parquet`,
`unsupported_incident_sources.parquet`; plus `incidents_report.md`,
`incidents_findings.json` and `incidents_manifest.json` (**last**; records
all consumed run ids, source/incident/relationship/suppressed counts,
addendum status and the no-causality / no-approval statements).

## 9. CLI

```bash
python -m src.intelligence --component incidents             # via dispatcher
python -m src.intelligence --component incidents --no-write --log-level DEBUG
python -m src.intelligence.incidents.run_incidents           # direct
python -m src.intelligence.incidents.run_incidents --skip-addendum
python -m src.intelligence.incidents.run_incidents --drift-run latest \
    --sensor-health-run 20260612T151654Z                     # pin upstream runs
```

## 10. What the first real run showed (run `20260612T222556Z`)

1,038 candidate events from five sources consolidated into **88 incidents**
(3 persistent) with a **39-row review pack**. The expected consolidation
materialized: ONE merged `sensor_fault` incident for `inlet_hopper_points`
(drift + sensor-health sources, persistent, critical, start 2024-09-17
16:23:22, actions `inspect_sensor_channel` + `inspect_counter_reset` +
`quarantine_from_process_scoring` pending approval); the 21-day September
anomaly burst suppressed by it at 0.9999 coverage; the
`granulator_roller_gap` missingness as a separate resolved incident; a
persistent critical `multivariate_shift` (2024-09-12 →) and a persistent
critical `sensor_health_context` shift (2024-09-17 →) as linked secondary
incidents; recurring steam/BOM transition patterns each collapsed to one
info-severity row.

## 11. Limitations / future role

Suppression and relationships inherit the upstream attribution limits;
nothing here establishes root cause. The review pack and the healthy-only
residual evidence are the designed input for Reference Governance
(Iteration C Part 3): quarantine approval → controlled rescoring experiment
→ reference candidate design.
