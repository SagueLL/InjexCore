# Dashboard API Contract (v0.2 — contractVersion 1.1)

**Status: implemented.** The read-only FastAPI service lives in `src/api/`; the Next.js
dashboard (`apps/dashboard/`) consumes it through `src/lib/dashboard/data-access.ts`.
This document is the API contract between the Intelligence-Layer artifacts and that
dashboard.

**contractVersion 1.1** (was 1.0) — breaking wire change: the timeline's
`deviationScore` and drift-anomaly's `anomalyScore` were replaced by a single
`evidenceShare` field with a different definition (see §6). Redefining a field's
semantics under an unchanged version string would be the same class of trust bug this
contract exists to prevent, so the version moved with it.

This document governs the **API boundary** only. The artifact-level consumption
contract — canonical run pins, allowed artifact groups, forbidden views, required
warning copy, read-only boundaries — remains
[dashboard_data_contract.md](dashboard_data_contract.md) (referenced below as §5.x);
this contract references it and never overrides it.

**Decisions locked (2026-07-03):**

1. **API host = FastAPI** — a new read-only Python service reading the canonical run
   artifacts, gated by `validate_dashboard_chain`
   ([src/dashboard/lineage.py](../../src/dashboard/lineage.py)).
2. **Narrative copy is backend-served** — insights/limitations/recommendations are
   data, sourced from a curated, versioned backend config.
3. **The API is the presentation boundary** — it maps backend enums to the existing
   frontend vocabularies via the tables in this document; frontend types change
   minimally.

**Principle:** the frontend consumes dashboard-ready responses. The API never exposes
raw parquet, run folders, joblib models, or model internals. The MVP pins the
canonical chain (`remat-v1-20260616T102558Z`, BOM `20260612T124909Z`); there is no run
selector.

---

## 1. Endpoints

All GET, read-only, versioned. The API reads **only** `runs/<CANONICAL_RUN_ID>` paths
(never legacy fixed-path artifacts, even though the lineage validator only warns).

```
GET /api/v1/health                     — service liveness (no data access)
GET /api/v1/dashboard/meta             — run identity + lineage gate + full required-warning set
GET /api/v1/dashboard/overview         — { meta, data: DashboardSummary }
GET /api/v1/dashboard/timeline         — { meta, data: OperationalTimeline }
GET /api/v1/dashboard/sensor-health    — { meta, data: SensorHealthSummary }
GET /api/v1/dashboard/drift-anomaly    — { meta, data: DriftAnomalySummary }
GET /api/v1/dashboard/incidents        — { meta, data: IncidentsSummary }
```

**Lineage gate.** `validate_dashboard_chain` runs once at startup and is cached.
`severity == "invalid"` → every data endpoint returns **503 `LINEAGE_INVALID`** (fail
closed). `severity == "warning"` (the current canonical chain, PROV-01 provenance gap)
→ 200 with the warnings surfaced in `/meta`.

**No pagination** — reserved, rejected for MVP (88 incidents max, immutable pinned
run). All 88 incidents are served, sorted by review-pack priority, then severity, then
`startDate`. Serving only the 39-row review pack while KPIs say 88 would be silently
lossy.

**Errors:** `{ "error": { "code", "message" } }` — `LINEAGE_INVALID` (503),
`ARTIFACT_UNREADABLE` (503, fail closed), `INTERNAL` (500).

**Caching:** the pinned run is immutable ⇒ strong
`ETag = "v1:<runId>:<bomRunId>:<copyVersion>:<appRev>"`,
`Cache-Control: public, max-age=3600`, `304` on `If-None-Match`. The Next.js fetch
`revalidate` policy is recorded at wiring time (B2).

## 2. Response envelope

The five view endpoints wrap the existing frontend view types untouched inside `data`;
unwrapping happens in a thin frontend fetch layer.

```jsonc
{
  "meta": {
    "contractVersion": "1.1",
    "runId": "remat-v1-20260616T102558Z",
    "bomRunId": "20260612T124909Z",
    "dataGeneratedAt": "2026-06-16T14:51:48Z",  // latest completion across the pinned chain; NOT response time
    "notices": [ { "key": "quarantine_pending", "text": "<exact §5.4 copy>" } ]
  },
  "data": { /* the view's existing *Summary shape */ }
}
```

`notices` carry the **exact** §5.4 copy, keyed, scoped per view to the artifact groups
it consumes (§5.2). Notice presence is part of the contract, not a frontend courtesy:

| View | Notice keys |
|---|---|
| overview | `read_only`, `adjusted_interpretive`, `plant_records_required` |
| timeline | `read_only`, `scores_unchanged` |
| sensor-health | `quarantine_pending` |
| drift-anomaly | `healthy_only_proxy`, `scores_unchanged`, `adjusted_interpretive` |
| incidents | `relationships_associative`, `quarantine_pending`, `adjusted_interpretive` |

**`GET /api/v1/dashboard/meta`** (gate + banner source; no view data duplicated):

```jsonc
{
  "contractVersion": "1.1",
  "runId": "…", "bomRunId": "…", "dataGeneratedAt": "…",
  "trainWindowEnd": "2024-09-03",
  "lineage": { "isValid": true, "canonicalMatch": true, "severity": "warning", "warnings": ["…"] },
  "requiredWarnings": [ /* full §5.4 exact-copy set */ ]
}
```

## 3. Per-view response shapes

`data` is the existing frontend type per view
(`apps/dashboard/src/types/{dashboard,timeline,sensor-health,drift-anomaly,incidents}.ts`)
with these deltas only:

- **`DashboardSummary`** (`/overview`): + optional `statusReason: string` (makes the
  status badge auditable). Real period served: `periodEnd` becomes `2024-10-08`.
- **`OperationalTimeline`** (`/timeline`): shapes unchanged; `series` / `periods` /
  `events` are computed (see §6).
- **`SensorHealthSummary`** (`/sensor-health`): `SensorIssueType` union **widened** to
  the 10 true rule families —
  `flatline | flatline_zero | variance_collapse | variance_explosion |
  missingness_spike | abrupt_offset | saturation_low | saturation_high | counter_reset
  | stale_signal` — plus computed `low_coverage`. (The previous 6-value union collapsed
  families dishonestly: step change ≠ drift, clipping ≠ spikes. Renders via the
  existing humanizer, so widening is near-zero cost.)
- **`DriftAnomalySummary`** (`/drift-anomaly`): `DetectionMethod` union **replaced**
  with the real detectors —
  `statistical | mahalanobis | pca_t2 | pca_residual | isolation_forest | context_overlay`.
  `pca_q → pca_residual` (Q/SPE *is* the residual distance); T² is **not** merged into
  residual (in-model distance, a different quantity). `lof` / `ocsvm` are removed —
  they do not exist in the backend; serving them would be fabrication.
  `context_overlay` stays as a row whose description states it is an interpretive
  overlay, not a detector (evidenceCount = suppressed rows), with the
  `adjusted_interpretive` notice.
- **`IncidentRecord`** (`/incidents`): + optional additive `sourceSeverity`,
  `sourceStatus`, `reviewStatus`, `startTimestamp`, `endTimestamp` (full ISO;
  ignored by the v1 UI, available for detail views later).

## 4. Shared conventions

- **Dates:** all existing frontend date fields stay `YYYY-MM-DD` (UTC day) — every
  render site prints them raw and chart axes need day buckets. Sub-day truth is served
  in the additive optional `*Timestamp` fields (ISO-8601 UTC). Day truncation is UTC;
  a short incident may show `startDate == endDate`.
- **Period semantics:** `periodStart` / `periodEnd` = **full manifest coverage**
  (2024-06-14 → 2024-10-08, 167,331 rows — from the behaviour manifest). The v0.1 demo
  end date (2024-09-03) is actually the *train-window* end; the quarantine onset
  (2024-09-17) falls outside it. The train boundary is exposed as
  `meta.trainWindowEnd` plus a `baseline`-type timeline event.
- **Casing:** JSON field names camelCase (pydantic `to_camel` alias generator on all
  response models); enum *values* stay snake_case verbatim.
- **Strings vs numbers:** raw numbers — no preformatted `"167,331"` strings. The
  frontend formats via `Intl.NumberFormat` (small KpiCard change). Strings only for
  genuinely textual values.
- **runId / generatedAt:** in the `meta` envelope on every response.
  `dataGeneratedAt` is the run-manifest completion time (stable, cache-friendly),
  never response build time.

## 5. Enum mappings (the presentation boundary)

| Backend | → UI | Notes |
|---|---|---|
| anomaly `anomaly` | `critical` | Legend copy required: "strongest anomaly evidence, not confirmed failure" |
| anomaly `unscored` | *(excluded)* | Never mapped to `normal`; excluded from aggregates, count disclosed |
| drift/incident `info` | `normal` | Series coloring only; info rows are never counted in "evidence" KPIs or badged lists |
| drift/incident `anomaly`, `critical` | `critical` | Lossy → mitigated by additive `sourceSeverity` + two `severityDistribution` rows (labels "Anomaly evidence" / "Critical", both `severity: "critical"`) preserving the 4-tier truth in labels |
| sensor `faulty` | `critical` | The view is explicitly about instrumentation reliability |
| sensor `unknown` | `unknown` | Passes through |

**Incident `status` mapping** (deterministic, honest, no type change):

| Condition | → UI status |
|---|---|
| Suppressed by the quarantine-aware scenario (`dominant_faulty_sensor` set / suppressed duplicate) | `contextualised` (requires the `adjusted_interpretive` notice) |
| In `incident_review_pack` (39 rows) and not suppressed | `in_review` ("prioritized for review") |
| Everything else (lifecycle `open`/`persistent`/`resolved` — all `review_status='pending_review'`) | `open` |
| — | `closed` is **reserved, never emitted in v1**: backend `resolved` means the evidence window ended, not that a human reviewed it; emitting "closed" would assert review closure (§5.3) |

## 6. Field mapping

**Directly available (straight reads/aggregations):** header fields + `totalRecords`
(behaviour manifest); sensor `distribution` counts (must sum to 17;
`sensor_health_summary`); incident list + severity distribution (`incidents.parquet` +
review pack + scoring-experiment suppression); detection-method `evidenceCount`
(`detector_agreement` / trigger counts — no row scans); anomaly funnel KPIs
(`scenario_anomaly_rate_comparison`); healthy-only drift KPIs (reference manifest /
drift comparison); quarantine/pending states (reference + sensor-health artifacts).

**Computed fields — contract-level rules:**

- `evidenceShare` (timeline **and** drift-anomaly — one rule, two views): **per UTC day,
  the share of scored rows (`severity != 'unscored'`) whose severity ∈ {warning,
  anomaly}**, 3 decimals. A **rate in [0, 1], not a model score**.
  *Replaced `deviationScore` / `anomalyScore` (p95 of `combined_score`) at
  contractVersion 1.1.* `combined_score` is a conservative max over per-detector
  train-ECDF percentiles, so its daily p95 sat at ~1.0 almost everywhere — across the
  117 served days: min 0.513, **median 0.979** — a line pinned to the top of a 0–1 axis,
  carrying no information, including deep inside the training window. `evidenceShare`
  on the same run: 27 days at exactly 0.000, median 0.008, stepping to 1.0 from
  2024-09-18. That step *is* the inlet-hopper sensor fault. Do not rescale or
  log-transform it away — explain it.
- **Recurring-pattern incidents are excluded from every per-day computation.** An
  incident whose `evidence` JSON carries `"recurring_pattern": true` is a *collapsed
  envelope*: its `[start, end]` spans many intermittent member events (one such
  incident collapsed 101 members across 115 of the 117 days), not a continuous
  condition. It remains a full record in `/incidents` and in the timeline's
  `Incident windows` total — only the daily series and day statuses exclude it, and
  that exclusion is disclosed in the KPI description. Malformed or absent `evidence`
  is treated as **episodic** (kept): over-flagging a day is loud, dropping evidence is
  silent.
- `incidentCount`: **episodic** incidents whose `[start, end]` **overlaps** the UTC day
  (active-count semantics, not started-that-day).
- Timeline day `status`, precedence `critical > drift > warning > normal`: critical if
  an unsuppressed, episodic source-severity ∈ {anomaly, critical} incident overlaps the
  day; drift if a drift event with status ∈ {active, persistent} overlaps; warning if an
  episodic warning-severity incident overlaps or day `evidenceShare` ≥
  `WARNING_EVIDENCE_SHARE` (0.05, §8); else normal. Days with zero scored rows are
  omitted (the type has no null slot).
  *Known consequence, disclosed not fixed:* `status == "drift"` is unreachable on the
  canonical run — all 36 days overlapping an active/persistent drift event are also
  overlapped by an anomaly/critical incident, and critical outranks drift.
- `operationalStatus` ladder: `critical` = unsuppressed source-critical incident in
  the last 14 days of the period; `warning` = pending quarantine/reference proposal OR
  unsuppressed anomaly/critical incident OR `residual_material=True`; `normal` = none
  of these; `unknown` = an artifact group unreadable. Current run ⇒ `warning`.
  `statusReason` makes the badge auditable.
- `coveragePct`: **100 × per-sensor non-null share of the sensor's column in
  `master_dataset.parquet` over the full period**, computed once at startup and
  cached. (Schema probe result: `sensor_health_summary` has **no** coverage column —
  see §7 — and `n_unknown / n_rows` is a health-status share, *not* coverage; do not
  substitute `health_score` either.)
- `evidenceSeries.anomalyCount` = non-normal scored rows per UTC day (sums to 33,186);
  `residualCount` = rows of `scenario_scores` with
  `scenario_id = 'quarantine_inlet_hopper_points_interpretive'` and
  `row_suppressed_for_review == False`, per UTC day (sums to 3,090). Join key
  verified: `scenario_scores.timestamp` (see §7).
- `affectedSignals.contribution`: frequency of the sensor in `affected_variables` over
  **unsuppressed** non-normal rows (excluding suppressed rows prevents
  `inlet_hopper_points` swamping the ranking); tercile cutoffs over sensors with
  nonzero counts. The dominant faulty sensor is listed separately with a
  sensor-dominated interpretation. (PCA-contribution-magnitude ranking is better
  fidelity — deferred to v1.1.)
- "Problematic sensors" population: per-sensor overall status ∈ {warning, faulty,
  unknown} derived from `sensor_health_summary` count columns +
  `quarantine_recommended`. Default precedence: faulty if `n_faulty > 0` or
  `quarantine_recommended`; else warning if `n_warning > 0`; else unknown if
  `n_unknown > 0`; else healthy. Material-share thresholds (to avoid over-flagging on
  a handful of rows) are a B2 calibration item (§8).

**Needs curation (backend config, not artifacts):** sensor `displayName` registry (17
entries); incident `title` templates per `incident_type` (8 types); per-view
insights/limitations copy with computed numbers interpolated via placeholders (§8,
risk 2); timeline `periods` / `events`: **computed anchors** (train boundary,
quarantine onset 2024-09-17, drift-event starts, top review-pack incidents) with
templated titles — purely hand-written periods would be un-audited narrative.

**Frontend changes required (small, enumerated for B2+):** thin fetch layer unwrapping
`{meta, data}` + env-driven API base URL (`DASHBOARD_API_URL`); `SensorIssueType`
union widened; `DetectionMethod` union replaced; optional additive fields on
`IncidentRecord` + `statusReason` on `DashboardSummary`; KpiCard `Intl.NumberFormat`;
a render slot (global banner/footer in the layout) for `meta.notices` / §5.4 required
warnings; demo fixtures updated to the new unions (kept as dev/fallback fixtures).

## 7. Verified schema probes (B1, read-only)

Probed via pyarrow against the canonical run on 2026-07-03:

**`sensor_health/runs/<id>/summaries/sensor_health_summary.parquet`** (17 rows):
`sensor`, `kind`, `n_rows`, `n_healthy`, `n_warning`, `n_faulty`, `n_unknown`,
`n_warning_train`, `n_faulty_train`, `issue_row_counts` (JSON string), `n_events`,
`n_persistent_events`, `first_faulty_row`, `quarantine_recommended`.
→ **No coverage/missingness column** — `coveragePct` uses the master-dataset non-null
share rule (§6).

**`scoring_experiments/runs/<id>/scenario_scores.parquet`** (66,372 rows = 2 scenarios
× 33,186 baseline-non-normal rows): joins on **`timestamp`** (`timestamp[us]`);
scenario ids `baseline_v1` and `quarantine_inlet_hopper_points_interpretive`; fields
include `original_severity`, `adjusted_review_severity`, `original_combined_score`,
`row_suppressed_for_review`, `dominant_faulty_sensor`, plus context columns.

**`scenario_anomaly_rate_comparison.parquet`** (2 rows) confirms the funnel:
suppressed 30,096 (90.7%); residual 3,090 = 1,887 warning + 1,203 anomaly;
`healthy_only_residual_count` = 23.

## 8. Risks & open items before B2

1. **Perf**: sensor-health scores ≈ 2.84M rows — never scan per request. Build all
   five view models once at startup (or first hit), cache in-process keyed by
   `(runId, contractVersion, copyVersion)`; prefer the persisted summary tables over
   row scans.
2. **Curated copy numbers**: the demo insight bodies hardcode numbers that contradict
   the real run (17 vs 88 incidents; 23 vs 17 sensors; 82-day vs 116-day window). Use
   template placeholders filled from computed values, or a startup assertion that copy
   numbers match computed KPIs. All copy re-audited against §5.3 (e.g. the demo's
   "exclude from automated scoring" implies auto-exclusion — forbidden framing; real
   recommendations derive from `recommended_actions` with pending-approval phrasing).
3. **Unscored/unknown handling**: disclose the unscored row count; `unknown` passes
   through.
4. **Service placement + deps**: `apps/api/` vs `src/dashboard/api/`; add
   fastapi/uvicorn to pyproject; import `src.dashboard` from the monorepo root.
5. **CORS/env**: Server Components fetch server-side ⇒ CORS likely moot for MVP;
   `DASHBOARD_API_URL` env on the Next side; no auth for MVP — the service binds to
   localhost / a trusted network only (record the assumption at deploy time).
6. **Type-drift prevention**: generate TS types from OpenAPI or zod-parse in the fetch
   layer; golden-payload snapshot tests per view against the canonical run.
7. **Calibration items**: ~~timeline-day `warning` p95 threshold~~ **RESOLVED at
   contractVersion 1.1**; material-share thresholds for the per-sensor overall status
   (§6) remain open.
   *Finding.* The p95 warning arm was **never binding**: across 117 days there were
   **zero** days where `p95 >= 0.9` was the sole reason for a `warning` status.
   Recalibrating the threshold — to any value — would have changed nothing. The real
   cause of "68 warning + 49 critical + **zero normal** days" was a single 115.7-day
   recurring-pattern `sensor_warning` incident overlapping all 117 days, so the ladder
   marked every day (including the whole training baseline window) as at least warning.
   Fixing the metric (`evidenceShare`) *and* excluding recurring-pattern envelopes
   yields **57 normal / 11 warning / 49 critical**, with the training baseline window
   correctly modal-`normal`.
   `WARNING_EVIDENCE_SHARE = 0.05` decides only 11 of 117 days (the rest are decided by
   episodic incident overlap or by carrying no evidence at all), so the view is not
   sensitive to it — but it is a magic number and must stay visible here and in the
   chart footer, or it becomes the next pinned `17`.
   *Second finding, disclosed not fixed:* every day from 2024-09-04 onward is
   `critical` (13/13 post-training validation days, 22/22 fault-window days), driven by
   anomaly/critical incidents rather than by the inlet-hopper fault (which starts
   2024-09-17). Genuine, and a likely demo question.
8. **Timeline periods/events provenance**: computed anchors recommended — confirm at
   implementation review.
9. **Period-semantics UX**: the real period extends ~5 weeks past the demo's;
   late-period content (quarantine onset, validation window) appears for the first
   time — expected, flag in the demo→real cutover review.

## 9. Compliance (§5.2–§5.5)

- Read-only GET surface; no approval/refit/alert semantics anywhere (§5.5).
- `incident_relationships` are not exposed in v1 — the causal trap is avoided; if
  counts ever surface, the `relationships_associative` notice attaches (§5.3).
- "Contextualised anomalies 30,096" and "healthy-only 23 windows" KPIs are served
  only with their notices attached (§5.2).
- `closed` incident status and any approved/applied quarantine framing are never
  emitted (§5.3).
- The API refuses legacy fixed-path behaviour artifacts even though the validator
  only warns (§5.3).
