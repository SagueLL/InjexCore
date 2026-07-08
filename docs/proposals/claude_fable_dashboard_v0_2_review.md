# Claude Fable 5 Dashboard v0.2 Review

**Produced by Claude Fable 5** (Anthropic, `claude-fable-5`) — Phase C independent technical review, 2026-07-08.
Scope: architecture, product/demo readiness, and implementation quality of Dashboard v0.1 (UI polish) + v0.2 (real data connection). Read-only review; no source files were modified. Several findings were grounded with read-only probes against the pinned canonical run (`remat-v1-20260616T102558Z`) rather than inferred from code alone.

---

## 1. Executive Summary

The Dashboard v0.2 backend is genuinely well-built. The FastAPI service is a real presentation boundary: thin routes, artifact reads isolated in services, a startup lineage gate that fails closed, honest curated copy with numbers interpolated from artifacts, and a notice registry that quotes the required §5.4 warnings verbatim. The industrial-honesty discipline (evidence-not-failure, pending-approval quarantine, associative-not-causal) is consistently enforced *server-side*, including in tests that assert forbidden phrasings never appear.

The dashboard is **not yet demo-ready**, for four reasons that are about trust rather than code quality:

1. **The mandated warnings never reach the screen.** The backend serves per-view notices; the frontend drops them (`data-access.ts` convenience getters strip `meta`), no page or layout renders them, and `/dashboard/meta.requiredWarnings` is an empty list. The contract's central honesty mechanism is dead end-to-end.
2. **Two views contradict each other numerically.** The overview serves a pinned "Problematic sensors: 17"; the sensor-health endpoint computes 13 from the same run's artifacts (verified by probe). A stakeholder navigating from `/overview` to `/sensor-health` sees the system disagree with itself.
3. **The canonical run contains a duplicated incident ID served as two different incidents** (verified by probe), which the frontend papered over with an index-based React key instead of surfacing as the upstream data defect it is.
4. **A lineage warning leaks an absolute local filesystem path through `/dashboard/meta`**, violating the API's own "no run folders, no internals" principle.

All four are fixable in days, not weeks. Separately, the timeline's deviation-score metric is saturated by construction (117 days served: 68 warning, 49 critical, **zero normal**; daily p95 median 0.979 on a 0–1 axis) — a product-level design issue that will make the flagship chart read as both alarmist and uninformative in a demo.

**Verdict: Needs targeted fixes** (see §12). The architecture is the right foundation for the next phase; the fixes are localized and none require re-architecting.

---

## 2. What Was Reviewed

- **Contracts:** [docs/dashboard/dashboard_api_contract.md](../dashboard/dashboard_api_contract.md), [docs/dashboard/dashboard_data_contract.md](../dashboard/dashboard_data_contract.md). (The task prompt named `dashboard_api_contracts_v0_2.md`; that file does not exist — the approved contract is `dashboard_api_contract.md`.)
- **Backend:** all of `src/api/` (main, routes, dependencies, errors, exception handlers, schemas, services, copy registries), `src/dashboard/` (contract pins + `lineage.py`).
- **Frontend:** `apps/dashboard/src/lib/dashboard/data-access.ts`, `src/types/*.ts`, all five `src/app/*/page.tsx`, `layout.tsx`, `next.config.ts`, app-shell components, KPI/status/insight components, all four Recharts chart components, `package.json`, `README.md`.
- **Tests:** all of `tests/api/` (10 files), with close reads of the meta, error-contract, and incidents suites.
- **Prior review:** `docs/proposals/codex_dashboard_v0_2_review.md` (for §11 comparison; its claims were independently re-verified, not assumed).
- **Data probes (read-only):** canonical incidents/review-pack/suppressed parquets (ID uniqueness, status-mapping populations), behaviour fit manifest (`created_at`), anomaly scores + drift events through the API's own `_series` helpers (day-status distribution), `sensor_health_summary.parquet` (derived status counts), venv import availability (`fastapi`/`uvicorn`/`httpx`).

Working tree note: `apps/dashboard/src/app/incidents/page.tsx` and `apps/dashboard/next.config.ts` carry uncommitted modifications (the React-key workaround and dev-origin allowlist reviewed here).

---

## 3. Strengths

- **The API is a real presentation boundary.** Routes are thin ([src/api/routes/dashboard.py](../../src/api/routes/dashboard.py)); every view builder lives in a service; artifact reads go through the existing `io` modules and `resolve_run`, never raw paths; column-projected parquet reads; the 2.84M-row sensor-health scores table is deliberately never read. This matches the contract's §8 performance rule exactly.
- **Fail-closed trust model implemented correctly.** Lineage is evaluated once at startup and cached on `app.state`; data endpoints 503 with `LINEAGE_INVALID` on missing/invalid lineage; `/meta` stays available as the gate banner source; artifact read failures become `ARTIFACT_UNREADABLE` with deliberately argument-less exceptions so pyarrow path strings never leak ([src/api/services/timeline.py:92-95](../../src/api/services/timeline.py)). Exceptions are intentionally not cached by `lru_cache`, so transient failures self-recover.
- **Industrial honesty is enforced, not aspirational.** The notices registry quotes §5.4 copy verbatim with a "never paraphrase" rule; `closed` incident status is unreachable by construction; demo-only detectors (`lof`/`ocsvm`) were removed as fabrication; `pca_q` → `pca_residual` mapping is justified in the schema docstring; tests assert forbidden phrasings ("confirmed failure", "exclude from automated scoring") are absent from real responses ([tests/api/test_dashboard_incidents.py:408-411](../../tests/api/test_dashboard_incidents.py)).
- **Curated copy quality is high.** Insight bodies interpolate real numbers from artifacts (drift-anomaly, sensor-health, incidents); the quarantine phrase always keeps "pending"; the sensor-fault story ("flatlined at zero since 17 Sep") is consistent across timeline events, sensor-health insights, and drift-anomaly signal interpretations.
- **Suppressed incidents are filtered at the loader**, so no consumer can ever see them — the right place for that invariant.
- **Test discipline is real.** CamelCase locking, envelope shape, notice order, sorting, severity distribution, cache behavior, fail-closed paths, and one true real-artifact integration test (incidents, all 88). The synthetic-fixture pattern with `monkeypatch` on `_load_artifacts` keeps tests hermetic.
- **The frontend transition was done without silent fallbacks.** Pages fetch through one data-access module; demo fixtures are retained but not imported; errors propagate rather than degrade to fake data. That is the correct failure philosophy for a trust product — it just needs an error boundary to present it (§7).

---

## 4. Critical Risks

### CF-01 — Duplicated incident ID served as two different incidents
- **Severity:** Critical
- **Area:** Data integrity / backend + upstream incident aggregation
- **Finding:** The canonical run's `incidents.parquet` contains `INC-process_drift-20240925T000000Z-8743` **twice**, as two genuinely different incidents (row 73: `warning`, `conditioner_steam_loop_temp`; row 74: `anomaly`, `granulator_power`). Verified by probe. The ID is also in the review pack. The API serves both records with the same `id`; `_pack_rank` and `actions_by_incident` key by `incident_id`, so both rows silently share one pack rank and one action set ([src/api/services/incidents.py:209-214, 317](../../src/api/services/incidents.py)). The frontend "fix" was an index-based React key plus a shipped comment admitting the backend was never checked ([apps/dashboard/src/app/incidents/page.tsx:98](../../apps/dashboard/src/app/incidents/page.tsx)).
- **Why it matters:** The incident ID is the UI's displayed reference for review triage. Two distinct evidence windows sharing one ID means a reviewer cannot unambiguously cite an incident — a direct data-trust failure in the product's core workflow. The React-key patch hides the symptom at the presentation layer while the integrity defect ships.
- **Recommendation:** Fix ID generation in `src/intelligence/incidents/` (the `-8743` suffix does not disambiguate same-type/same-start incidents) and regenerate, or — if the pinned run must stay immutable — disambiguate deterministically at the API (`id`, `id-b`) and disclose it. Add a uniqueness assertion in the incidents pipeline tests **and** in the API real-artifact test. Then remove the frontend index-key workaround and its comment.

### CF-02 — Overview contradicts Sensor Health on the same quantity
- **Severity:** Critical
- **Area:** Cross-view consistency / data honesty
- **Finding:** `/overview` serves pinned constant `_PROBLEMATIC_SENSOR_COUNT = 17` ([src/api/services/overview.py:24](../../src/api/services/overview.py)). The sensor-health service derives per-sensor status from the artifact and gets **critical 3, warning 7, unknown 3, healthy 4 → 13 problematic** (verified by probe against `sensor_health_summary.parquet` using the service's own precedence rule). 17 is the *total* monitored-sensor count, not the problematic count. Similarly, `DATA_GENERATED_AT = "2026-06-16T10:25:58Z"` is the run-id timestamp, not the manifest completion time (`created_at = 2026-06-16T10:26:24Z`, verified).
- **Why it matters:** In a technical demo the audience will see "Problematic sensors: 17" on one page and a distribution summing to 13 problematic / 4 healthy on the next. Nothing undermines an "intelligence layer you can trust" pitch faster than the dashboard disagreeing with itself. This is the concrete failure mode the contract's §8 risk 2 warned about — pinned copy diverging from artifact truth — and there is no startup assertion to catch it.
- **Recommendation:** Replace the overview pins with startup-cached artifact readers (behaviour manifest, incidents run, sensor-health summary, `scenario_anomaly_rate_comparison`) — the loaders already exist in the other four services. If pins must remain for one more slice, add a startup assertion that fails closed when a pin diverges from the artifact-derived value, and fix 17 → 13 and `dataGeneratedAt` now.

### CF-03 — Required warnings are dead end-to-end
- **Severity:** Critical
- **Area:** Trust boundary / contract compliance (frontend + `/meta`)
- **Finding:** Three simultaneous breaks: (a) `/dashboard/meta` returns `required_warnings=[]` ([src/api/routes/dashboard.py:59](../../src/api/routes/dashboard.py)) despite the contract naming it the "full required-warning set" source; (b) the page-facing getters return only `.data`, discarding `meta.notices` ([apps/dashboard/src/lib/dashboard/data-access.ts:116-134](../../apps/dashboard/src/lib/dashboard/data-access.ts)); (c) no layout/page renders any notice — there is no banner/footer slot. The backend registry has all seven §5.4 texts, correct per view, and they go nowhere.
- **Why it matters:** The §5.4 warnings ("Quarantine is pending review and not approved", "Original anomaly scores are unchanged", …) are the contractual mechanism that keeps interpretive views honest. Today a viewer sees "Contextualised anomalies: 30,096" with no visible statement that this is interpretive post-processing over unchanged scores. Notice presence is "part of the contract, not a frontend courtesy" — currently it is neither.
- **Recommendation:** Populate `requiredWarnings` from the existing `NOTICE_TEXT` registry (one-line change), and render `meta.notices` per view — the smallest honest implementation is a compact notice strip under each `PageHeader` fed by the already-fetched payload (switch pages to `get*Payload()`), plus a global read-only banner in the app shell from `/meta`. Add a test asserting `requiredWarnings` equals the full seven-entry set.

### CF-04 — `/dashboard/meta` leaks absolute local filesystem paths
- **Severity:** High
- **Area:** API presentation boundary / information exposure
- **Finding:** `validate_dashboard_chain` formats warnings with raw paths — `f"{spec.name}: no run directory at {run_path}."` ([src/dashboard/lineage.py:82](../../src/dashboard/lineage.py)) and the legacy-artifact warning embeds the full absolute path ([src/dashboard/lineage.py:182-187](../../src/dashboard/lineage.py)). The API projection passes `result.warnings` through verbatim ([src/api/services/lineage_gate.py:32](../../src/api/services/lineage_gate.py)). On this machine the legacy behaviour manifest exists, so the current `/meta` response contains a `C:\Users\...` path.
- **Why it matters:** Violates the contract's own principle ("The API never exposes raw parquet, run folders, … or model internals") on the one endpoint that stays reachable even when lineage is invalid — i.e., exactly when warnings are longest. It leaks deployment layout and reads as unfinished plumbing in any demo where someone opens `/meta`.
- **Recommendation:** Sanitize in `evaluate_lineage()` (the API projection is the right layer; `lineage.py`'s verbose warnings are legitimately useful for local diagnostics): keep component name + failure class, strip paths. Add a regression test that no warning matches drive letters, backslashes, `data/`, `.parquet`, or `runs/<id>` fragments.

### CF-05 — The timeline's headline metric is saturated by construction
- **Severity:** High
- **Area:** Metric design / demo credibility
- **Finding:** Verified by probe through the API's own helpers: across all 117 served days the day-status ladder yields **68 warning + 49 critical, zero normal, zero drift**, and the daily p95 `deviationScore` has min 0.513 / median **0.979** / max 1.0 on a fixed 0–1 axis. This is largely structural: `combined_score` is a conservative-max of per-detector train-ECDF percentiles, so the p95 of a few hundred daily rows is ≈1 almost everywhere — including deep inside the training window. The `WARNING_P95_THRESHOLD = 0.9` therefore fires on most days on its own, and warning-severity incidents overlap every day anyway (acknowledged in [src/api/services/_series.py:14-16](../../src/api/services/_series.py)).
- **Why it matters:** The flagship "Operational behaviour over time" chart will show a line pinned to the top of the axis for four months and a status ladder in which *no day was ever normal — including the baseline period the system itself calls "Training baseline window"*. To a technical stakeholder this reads either as "the plant is always on fire" or "the metric carries no information"; both damage credibility, and it visually contradicts the interpretive-period card describing the training window as the reference for normal.
- **Recommendation:** Before the demo, either (a) change the daily aggregate to something with dynamic range — e.g. share of non-normal rows per day, or p95 of the *pre-ECDF* combined evidence — via the shared `_series.py` rule (one change, both views, contract §6 amendment), or (b) at minimum rescale the Y axis and recalibrate the ladder with the §8 materiality thresholds so that days are marked warning/critical by meaningful overlap, not by any single warning incident. Do not ship the chart as-is into a stakeholder demo.

---

## 5. Product / Narrative Risks

- **"Windows" labels on row counts.** The drift-anomaly page prints `Evidence windows: {evidenceCount}` per detection method ([drift-anomaly/page.tsx:94](../../apps/dashboard/src/app/drift-anomaly/page.tsx)), but the backend counts are *row-level* trigger counts (tens of thousands; the context overlay row alone is 30,096). The evidence chart likewise names its bar "Anomaly windows" for `anomalyCount`, which is non-normal *rows* per day ([anomaly-evidence-chart.tsx:69](../../apps/dashboard/src/components/charts/anomaly-evidence-chart.tsx)). "30,096 windows" materially misstates magnitude semantics; the backend's own KPI labels ("Raw non-normal rows") got this right. Rename to "evidence rows" / "Anomaly evidence (rows)".
- **Unformatted KPI numbers.** The contract moved to raw numbers with `Intl.NumberFormat` formatting in `KpiCard` (§4); the KpiCard change never landed ([kpi-card.tsx:32-34](../../apps/dashboard/src/components/dashboard/kpi-card.tsx)). The overview will display "167331" and "30096" — a small thing that instantly reads as unfinished in a demo.
- **`statusReason` is served but never shown.** The overview badge auditability feature (§3 delta) is dark: the backend composes a careful reason string; the frontend type lacks the field and the page ignores it. Render it as a tooltip/subline on the status badge.
- **13-of-17 sensors flagged problematic, some on ~0.01% of rows.** `granulator_power` goes *critical* on 25 faulty rows of 167,331; several warnings fire on 20–40 rows. Honest but alarmist — this is the contract's own §6/§8 "material-share thresholds" calibration item, and it should land before a pilot audience sees the sensor list.
- **Version/branding inconsistencies.** The sidebar footer still says "Dashboard v0.1" ([app-shell.tsx:33](../../apps/dashboard/src/components/app/app-shell.tsx)); the HTML metadata describes "injection-moulding production data" ([layout.tsx:21-23](../../apps/dashboard/src/app/layout.tsx)) while every view says "Pelletizer line". The overview's limitation copy handles the pelletizer-vs-pilot-cell honesty well — the browser tab shouldn't undercut it.
- **One phrasing wobble.** The sensor-health chart footer says signals should be reviewed "before using them for automated operational decisions" ([sensor-health/page.tsx:81](../../apps/dashboard/src/app/sensor-health/page.tsx)) — the word "automated" implies an automation pathway the product explicitly disclaims (§5.5). Drop "automated".
- **What is *right* and worth protecting:** backend-served insight copy consistently frames evidence-not-failure and pending-approval quarantine; `context_overlay` is explicitly labeled "not a detector"; the four-tier severity truth is preserved in distribution labels; `closed` is never emitted. The narrative layer is the strongest part of this release — once it actually reaches the screen (CF-03).

---

## 6. Architecture / Maintainability Risks

- **Frontend types no longer describe the wire format.** `SensorIssueType` still lists demo values (`noise`, `frozen_signal`, …) while the API serves the 10 real rule families; `DetectionMethod` still contains `lof`/`ocsvm` and lacks `statistical`/`mahalanobis`/`pca_t2`; `DashboardSummary` lacks `statusReason`; `IncidentRecord` lacks the additive source/timestamp fields. Nothing crashes today only because no component switches on those unions — but TypeScript has silently stopped being a contract guard, and the first `switch` on `method` will break. Fix the unions now; adopt OpenAPI-generated types or zod parsing in `data-access.ts` to prevent recurrence (the contract's own §8 risk 6).
- **Pinned constants are duplicated across services.** `_PERIOD_START/_PERIOD_END/_QUARANTINE_ONSET`, asset/dataset names, and the quarantine channel literal are each repeated in 4–5 service modules. When the artifact-reader slice lands (CF-02), centralize them in `view_meta`/a single pins module so the next run repin is a one-file change.
- **Error contract holds only for `ApiError`.** Any non-`ApiError` exception (e.g. an unexpected schema surprise in a build step running outside the loader's `try` — `_parse_sensor_counts` on a malformed `top_remaining_sensors` cell would be one) returns FastAPI's default 500 body, not `{"error": {"code": "INTERNAL"}}`. Register a catch-all handler that logs server-side and returns the envelope; test it.
- **HTTP caching is contract-specified but absent.** No ETag/`Cache-Control`/304 handling exists, and the frontend fetches `no-store`. For a single-user local demo this is fine — but then the contract should be amended to say so, rather than leaving §1's caching design silently unimplemented. Decide; don't drift.
- **`lru_cache(maxsize=1)` on builders is correct for one immutable pinned run** and nothing more. The moment a run selector or repin-without-restart arrives, caching must move to a `(runId, contractVersion, copyVersion)` key as §8 already specifies. Leave a comment breadcrumb now; it will be easy to forget.
- **Placement decision (`src/api/` vs `apps/api/`) is fine** — the service legitimately imports `src.intelligence.*` io modules and the lineage validator; keeping it inside the Python package avoids path gymnastics. The coupling is mediated through io-module constants rather than literal paths, which is the right level.

## 7. Frontend / UX Risks

- **No error or loading UI at all.** There is no `error.tsx`, `loading.tsx`, or `not-found.tsx` anywhere under `src/app/` (verified by glob). A fail-closed 503 — the backend's *designed* behavior — surfaces as Next's raw error screen; a slow first hit (cold parquet build) renders nothing. This is the single worst demo failure mode: the trust model's correct refusal to serve bad data looks like a crash. Add a root `error.tsx` that recognizes `DashboardApiError` (render code + message + run identity) and lightweight `loading.tsx` skeletons.
- **Incidents page destroys the contractual ordering.** The API sorts by review-pack priority → severity → start date (implemented and test-locked); the page re-sorts by UI severity ([incidents/page.tsx:28-30](../../apps/dashboard/src/app/incidents/page.tsx)), collapsing the 4-tier triage order into 3 tiers and burying pack priority. Delete the re-sort; the backend order *is* the product feature.
- **Shipped workaround comment.** Line 98's inline comment ("duplicate key is safe here … still have to review the backend") is a TODO in production clothing — resolve via CF-01 and remove.
- **`getOverviewData`-style getters encourage dropping `meta`.** The data-access layer is otherwise a good abstraction (single fetch path, typed error, no client leakage of `DASHBOARD_API_URL`); once notices render (CF-03), the `.data`-only convenience getters should be deleted so the envelope cannot be silently discarded again.
- **Charts are mostly robust to real payloads:** label-keyed bars tolerate the duplicate-`critical` severity rows; three of four charts have empty states; 117-point series render acceptably. Gaps: `OperationalTimelineChart` lacks the empty state its siblings have, and `timeline.events` uses `key={event.title}` — titles are unique today by construction, but a second "Peak deviation evidence"-style computed anchor would collide.
- **Hardcoded light-theme status colors** (`bg-green-50` etc. in `status-badge.tsx`, hex grid/series colors in charts) are acceptable for the fixed-theme MVP; note them before any dark-mode work.

## 8. Backend / Data Risks

- **The lineage gate matches the intended trust model** — invalid blocks data, warning passes and surfaces, `/meta` always answers, `/health` touches nothing. One documented consequence: lineage is evaluated *once*; artifacts deleted mid-flight are caught by `ARTIFACT_UNREADABLE` on uncached views but a fully cached view keeps serving until restart. Acceptable for an immutable pinned run; document it.
- **`contextualised` status is a proxy, not the contract's definition.** Contract §5 defines it as "suppressed by the quarantine-aware scenario"; the implementation marks any incident whose `affected_sensors` contains `inlet_hopper_points` ([incidents.py:202](../../src/api/services/incidents.py)). Probe result: 5 incidents match, all also in the review pack (so `contextualised` wins precedence over `in_review` for the run's most prominent incidents). On this run the proxy is defensible; it will over-mark the moment a multi-sensor incident merely *touches* the channel. Tighten later against the scoring-experiment suppression table, and note the proxy in the service docstring.
- **Affected-signal terciles run over the persisted top-10 only** (documented as an accepted §8 approximation) and the non-dominant severity assignment ("high contribution → warning") is a curated pin — both fine, both worth revisiting when PCA-contribution ranking (v1.1) lands.
- **Cold-start work is deferred to first click.** Timeline/drift/sensor-health/incidents each do their parquet work on first hit. For a demo, prewarm all five builders at startup (call them in `lifespan` after the gate passes) so artifact failures surface before an audience does.
- **`test_error_contract.py` documents that any non-"invalid" severity passes the gate** (even a nonsense `"valid"`). That is the intended blocklist semantics, but pin it with a `Literal` severity type on `ApiLineageResult` (already present) plus a comment in `dependencies.py` — a future severity value should be a conscious decision, not a silent pass.
- **Real-artifact integration coverage is incidents-only.** Timeline, sensor-health, drift-anomaly and overview have no equivalent of the 88-record lock. CF-02 exists precisely because overview has no artifact-backed assertion. Add one `requires_real_run` test per view asserting the headline numbers against the artifacts.

---

## 9. Missing Documentation or DX Gaps

- **There are no run instructions for the API anywhere.** No document in the repo contains the `uvicorn src.api.main:app` (or equivalent) command — verified by grep across all markdown. A new developer cannot start the backend from docs.
- **The dashboard README is still the default create-next-app README** — no `DASHBOARD_API_URL`, no two-process dev flow, no mention that the backend must be running first and what a 503 means.
- **The local venv cannot run the API today**: `fastapi`, `uvicorn`, `httpx` are declared in `pyproject.toml` but not installed (verified) — `pytest tests/api` fails at import in this environment. `pip install -e ".[dev]"` needs re-running; a one-line "after pulling v0.2, reinstall" note would have prevented this.
- **No `.env.example`** for the dashboard (`DASHBOARD_API_URL=http://127.0.0.1:8000`).
- **`package.json` has no `typecheck` script** and no test script; `tsc --noEmit` should be a one-liner in the quality gate.
- **Undocumented deploy assumptions:** no CORS middleware (correct for server-side fetch, but record it), localhost/trusted-network binding assumption (§8 item 5 says "record at deploy time" — record it now in the README), and the LAN IPs in `next.config.ts` `allowedDevOrigins` are dev-machine-specific and belong in a comment or env.
- Suggested minimal fix: a `docs/dashboard/running_the_dashboard.md` (or README section) with: install, start API, start Next, env vars, where the data comes from (pinned run), what 503 `LINEAGE_INVALID` means, how to run `pytest tests/api` and `npm run lint`.

---

## 10. Recommended Improvements

**Before demo (trust + first impressions; roughly ordered):**
1. Render notices + required warnings (CF-03): populate `/meta.requiredWarnings`, add per-view notice strip + global read-only banner, switch pages to payload getters.
2. Add root `error.tsx` (recognizing `DashboardApiError`) and `loading.tsx` skeletons.
3. Fix the overview/sensor-health contradiction (CF-02): artifact-back overview or startup-assert pins; correct 17 → 13 and `dataGeneratedAt` immediately.
4. Sanitize `/meta` lineage warnings (CF-04) + regression test.
5. Remove the incidents severity re-sort; preserve API order.
6. Decide CF-05 mitigation: recalibrate/replace the daily deviation aggregate, or at minimum re-axis and threshold-calibrate the ladder — the current chart cannot headline a demo.
7. Cosmetics that read as polish: `Intl.NumberFormat` in KpiCard, "windows" → "rows" labels, footer v0.1 → v0.2, metadata description, drop "automated" from the sensor-health footer.
8. Prewarm the five view caches in `lifespan`.
9. Write the run-instructions doc (§9) and reinstall the venv extras.

**Before pilot:**
1. Fix incident-ID uniqueness upstream (CF-01) + uniqueness tests at pipeline and API layers; drop the frontend index-key workaround.
2. Update frontend unions/fields to the v0.2 contract and adopt OpenAPI-generated types or zod parsing; update demo fixtures to the new unions.
3. Generic `INTERNAL` exception handler + test; move build-phase parsing under fail-closed handling.
4. Real-artifact integration tests for overview, timeline, sensor-health, drift-anomaly (mirror the incidents 88-lock).
5. Calibrate sensor material-share thresholds and the timeline warning threshold (§8 items) so flag counts reflect materiality.
6. Tighten `contextualised` to the scoring-experiment suppression table.
7. Resolve the caching contract: implement ETag/304 or amend §1 for the MVP.
8. Centralize per-service pins; add `typecheck`/test scripts; `.env.example`.

**Later / nice to have:**
- Run-selector-ready caching (`(runId, contractVersion, copyVersion)` keys); PCA-contribution signal ranking (v1.1); incident detail route; frontend component tests (notice rendering, order preservation); dark-mode-safe status tokens; empty state for `OperationalTimelineChart`; stable computed-anchor keys for timeline events.

---

## 11. Comparison Notes

I read the Codex review after forming my own file-level pass, then re-verified rather than inherited its claims. Where we overlap, we agree: the path leak (its C-01 = CF-04), dead warnings (C-02 = CF-03), stale frontend types, incidents re-sort, pinned metadata, missing generic handler, missing error boundary, and the DX gaps are all real — I independently confirmed each against source.

What this review adds is mostly **artifact-grounded and product-level**, the classes of issue a static contract audit is structurally likely to underweight:

- **Probing the data changed severities.** Codex listed the React index-key as *Low* frontend hygiene; the probe shows the canonical artifact genuinely contains one ID naming two different incidents, in the review pack — an upstream integrity defect (CF-01, Critical), not a key-collision nit.
- **Cross-view arithmetic.** The overview's "17 problematic sensors" vs the sensor-health endpoint's 13 (CF-02) required computing the derived statuses from the artifact. Codex flagged the *pattern* (pinned constants, H-03) but not the concrete contradiction a demo audience would actually see.
- **Metric behavior, not metric plumbing.** CF-05 (saturated p95-of-ECDF, zero normal days) only appears when you run the API's own aggregation against the real scores. The implementation is contract-*compliant* — the contract's metric is the problem. Strict compliance auditing cannot catch a spec that faithfully produces an uninformative chart.
- **Magnitude-semantics copy** ("Evidence windows: 30,096" for row counts), the branding/tab-metadata mismatch, and the "automated decisions" phrasing are narrative-honesty issues rather than contract violations.
- Conversely, Codex-style strictness surfaces things worth keeping in view that a product lens might deprioritize — the ETag/caching divergence and exhaustive test-gap enumeration are the best examples, and I have folded them into §10 at what I judge to be their true priority (below the trust items, above cosmetics).

Net: the two reviews are complementary, converge on "not yet — but close", and disagree mainly on where the React-key issue and the pinned-constant risk sit on the severity scale (the data probes settle both upward).

---

## 12. Final Verdict

**Needs targeted fixes.**

The backend/frontend split, the lineage-gated fail-closed model, the notice registry, and the honesty discipline in copy and tests are the right foundation, and none of the findings require re-architecting. But the dashboard should not be put in front of a technical audience until the "before demo" list in §10 is done — specifically: warnings actually rendered (CF-03), the cross-view number contradiction removed (CF-02), an error boundary in place, the path leak closed (CF-04), and a decision taken on the saturated timeline metric (CF-05). The duplicate incident ID (CF-01) must be fixed upstream before any pilot in which reviewers reference incidents by ID.

*— Claude Fable 5, Phase C independent review*
