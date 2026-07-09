# Dashboard v0.2 — Demo Trust Fix Sprint (C1) Summary

**Date:** 2026-07-08 · **Branch:** `phase-c-demo-trust-fixes`
**Scope:** the "Before demo" list of [claude_fable_dashboard_v0_2_review.md](claude_fable_dashboard_v0_2_review.md).

The review's verdict was *"Needs targeted fixes — not because of code quality, but because of
trust."* All nine before-demo items are done. Two of them turned out to be wrong as briefed;
both are documented below rather than quietly reinterpreted.

---

## 1. Findings that changed the work

### The brief's `dataGeneratedAt` value was wrong

The task specified `2026-06-16T10:26:24Z`, the behaviour manifest's `created_at`. Probing all
eleven manifests in the pinned chain showed **behaviour completes first**, not last:

| component | completion | key |
|---|---|---|
| behaviour | `10:26:24` | `created_at` |
| correlation / pca / anomaly | `10:27:01` – `10:28:15` | `fit_timestamp` |
| sensor_health | `14:44:03` | `created_at` |
| operational / drift / incidents / reference | `14:47:01` – `14:51:07` | mixed |
| **scoring_experiment** | **`14:51:48`** | `created_at` |

Every artifact the API actually serves — sensor health, drift, incidents, scoring experiment —
was written 4 h 25 m *after* the behaviour fit. Shipping `10:26:24Z` under the name
`dataGeneratedAt` would have replaced one accuracy bug with a subtler one. **Shipped:
`2026-06-16T14:51:48Z`** (latest completion across the chain), pinned with a `TODO(debt)` noting
that deriving it at startup needs a per-component key map (`created_at` vs `fit_timestamp`).
Guarded by `test_data_generated_at_is_the_chain_completion_time`.

### Recalibrating the timeline threshold was a provable no-op

Task 6 offered "recalibrate the warning threshold" as the safe fallback. It is inert. Measured
against the pinned run: **zero** of 117 days had `p95 >= 0.9` as the *sole* reason for a warning
status. Any threshold — 0.9, 0.99, 1.1 — yields the identical `68 warning / 49 critical / 0 normal`.

The real cause was a single incident: `INC-sensor_warning-recurring-20240614T143032Z-5422`, a
**recurring-pattern envelope** (`evidence` JSON carries `"recurring_pattern": true`,
`n_members=101`) whose `[start, end]` spans 115.7 of the 117 days. Its span is the envelope of 101
*intermittent* member events, not a continuous condition — so treating it as "every day is a
warning day" is a bug in the overlap semantics, and it painted the entire training baseline window
(the window the system itself calls the reference for normal) as abnormal.

So the fix required **both** a metric with dynamic range **and** exclusion of recurring-pattern
envelopes from the day ladder.

---

## 2. What was fixed

| # | Item | Result |
|---|---|---|
| 1 | **Required warnings + notices reach the screen** (CF-03) | `/meta.requiredWarnings` now serves all 7 §5.4 texts in contract order (`REQUIRED_WARNING_KEYS`, explicit tuple — wire order must not depend on dict insertion order). New `NoticeStrip` renders each view's `meta.notices` under its `PageHeader`. All five pages switched from `getXData()` to `getXPayload()`, and the five `.data`-only getters were **deleted** so `meta` can never be silently discarded again. New `TrustBanner` on `/overview` surfaces run identity, lineage severity, the sanitized warnings, and the 7 required warnings. |
| 2 | **Error + loading UI** | Root `app/error.tsx` (Next 16 signature: `{ error, unstable_retry }` — not `reset`) and `app/loading.tsx` skeleton. A stopped backend now throws a typed `DashboardApiError(0, "API_UNREACHABLE", …)` instead of a bare `TypeError: fetch failed`. |
| 3 | **Overview vs Sensor Health contradiction** (CF-02) | `_PROBLEMATIC_SENSOR_COUNT = 17` (the sensor *total*) deleted. `/overview` now derives the value through `sensor_health.problematic_sensor_count()`, reading the sensor-health view's existing `lru_cache` — **zero extra I/O**, and equal to that view's "Review required" KPI by construction. Serves **13**. `/overview` consequently fails closed with `ARTIFACT_UNREADABLE` (correct: a stale pin would be exactly the silent fallback the contract forbids) and its handler became sync `def` so the first-hit parquet read lands in FastAPI's threadpool. |
| 4 | **`/meta` path leak** (CF-04) | New `src/api/redaction.py::redact_paths`, applied in the **API projection** (`lineage_gate.evaluate_lineage`), not the core validator — its verbose paths remain useful for local diagnostics. Component names and failure classes survive verbatim; drive letters, UNC, POSIX absolutes, `data/`, `runs/`, `.parquet`/`.json` are elided. Verified against the live chain: 5 warnings, 0 leaks. |
| 5 | **Incidents ordering** | Frontend `SEVERITY_ORDER` re-sort deleted; the page renders the API order (review-pack priority → source severity → start date). The shipped "still have to review the backend" TODO comment is gone, replaced by a factual note. Verified end-to-end: the rendered DOM order equals the API order for all 88 incidents. |
| 6 | **Timeline metric** (CF-05) | `deviationScore`/`anomalyScore` → **`evidenceShare`** (share of a day's scored rows flagged warning/anomaly — a rate, not a score). Recurring-pattern envelopes excluded from `day_statuses` **and** `incidentCount`. `WARNING_EVIDENCE_SHARE = 0.05`. `daily_p95` / `WARNING_P95_THRESHOLD` deleted; `combined_score` dropped from both services' column projections. `CONTRACT_VERSION` bumped `1.0 → 1.1` (a field rename with new semantics is a breaking wire change; leaving the version would be the same class of trust bug). |
| 7 | **First-impression polish** | `Intl.NumberFormat("en-US")` in `KpiCard` (locale pinned — a floating locale is a hydration-mismatch bug). "Evidence windows" → **"Evidence rows"**; chart bar "Anomaly windows" → **"Anomaly rows"**. Sidebar footer `v0.1` → `v0.2 · Read-only`. `layout.tsx` description no longer claims injection-moulding data. `"automated"` dropped from the sensor-health footer. Timeline footer rewritten (the old copy — "higher deviation scores indicate stronger deviation" — became false under the new metric). `OperationalTimelineChart` gained the empty state its three siblings already had. |
| 8 | **Prewarm** | New `src/api/services/prewarm.py`; `lifespan` warms all five builders via `anyio.to_thread` after the gate passes. Skipped when lineage is invalid (fail-closed) and when `INJEXCORE_API_PREWARM=0`. Never raises — a crashed process would replace a *documented* `503 ARTIFACT_UNREADABLE` with connection-refused and take `/health` down with it. |
| 9 | **Docs** | New [docs/dashboard/running_the_dashboard.md](../dashboard/running_the_dashboard.md) + `apps/dashboard/.env.example`. Both `dashboard_api_contract.md` and `running_the_dashboard.md` added to the docs map. |

### Timeline: before → after (real canonical run)

```
BEFORE   117 days:  68 warning · 49 critical ·  0 normal
         deviationScore p95: min 0.513, median 0.979, max 1.0   (a flat line at the axis top)
         Training baseline window: warning

AFTER    117 days:  11 warning · 49 critical · 57 normal
         evidenceShare:      min 0.000, median 0.008, max 1.0   (27 days at exactly zero)
         Training baseline window: normal
         Peak daily evidence share: 2024-09-18 (the inlet-hopper fault onset)
```

Nothing was fabricated: those 57 normal days genuinely carry <5% non-normal rows and no episodic
incident overlap. The step to 1.0 on 18 Sep *is* the sensor fault, and the chart footer says so.

### Two bugs the sprint's own changes introduced, and caught

- **`unstable_rethrow` (would have broken CI).** Wrapping `fetch` to produce `API_UNREACHABLE`
  swallowed Next's internal `DYNAMIC_SERVER_USAGE` error — the signal a `no-store` fetch throws
  during prerender to opt a route into dynamic rendering. `npm run build` failed. Fixed with
  `unstable_rethrow(cause)` from `next/navigation` before wrapping. The build now emits the five
  view routes as `ƒ (Dynamic)`, which is correct.
- **A false claim in my own doc.** `running_the_dashboard.md` first promised a
  `Prewarmed 5/5 …` startup line. It never appears: uvicorn configures only its own loggers, so
  an app logger's `INFO` records are dropped by the root level, and `--log-level info` does not
  change that. Verified. Partial prewarm now logs at `WARNING` (audible via `logging.lastResort`
  with no handlers at all), and the doc states the real behaviour plus the exact command that does
  show the success line.

---

## 3. Tests run

| Gate | Result |
|---|---|
| `python -m pytest` | **756 passed** (was 675: 590 + 85 API) |
| `python -m pytest tests/api` | **166 passed** (was 85) |
| `python -m ruff check .` | All checks passed |
| `python -m ruff format --check .` | 375 files already formatted |
| `python -m mypy src` | Success, no issues in 221 source files |
| `npm run typecheck` | clean (new script, added this sprint) |
| `npm run lint` | 0 errors, 6 warnings — the same 6 pre-existing ones |
| `npm run build` | ✓ 9/9 pages; the 5 view routes correctly `ƒ (Dynamic)` |

**New test files (6):** `tests/api/conftest.py`, `test_series.py`, `test_lineage_redaction.py`,
`test_dashboard_consistency.py`, `test_notices.py`, `test_prewarm.py`.

Notable coverage added:

- **The recurring-pattern exclusion is load-bearing, not decorative.** The timeline and
  drift-anomaly fixtures each contain a recurring envelope spanning every fixture day. A mutation
  check confirmed that disabling the filter flips `incidentCount` from `[1,1,1,0,1]` to
  `[2,2,2,1,2]` and turns 2024-01-06 from `normal` to `warning` — the locked expectations fail.
- **`is_recurring_pattern` never raises** on malformed / `NaN` / non-string / non-dict evidence,
  and only the literal boolean `true` counts. Unclassifiable evidence is treated as *episodic*
  (kept): over-flagging a day is loud, dropping evidence is silent.
- **`episodic_incidents` raises `KeyError`** without the `evidence` column, inside each loader's
  existing `try`, so an upstream schema change fails closed as `ARTIFACT_UNREADABLE` rather than
  silently disabling the filter.
- **Redaction is a no-op on path-free text** (the four provenance warnings the real chain emits
  pass byte-identical), is idempotent, preserves sentence punctuation, and keeps run ids — which
  are public (`/meta.runId`).
- **Six `@requires_real_run` cross-view tests** pin the overview's remaining constants against the
  endpoints that own the underlying artifacts (13 of 17 sensors, 88 incidents, the contextualised
  and residual funnel numbers, `totalRecords`, `dataGeneratedAt`). All six executed against real
  artifacts, not skipped.
- **`tests/api/conftest.py` autouse `_no_prewarm`.** `with TestClient(app)` runs the lifespan, and
  each test module patches only *its own* loader — an unguarded prewarm would have driven real
  parquet reads for the other four services in ~40 tests.

### End-to-end verification (both processes live, real artifacts)

Verified against a running API + Next server, not inferred:

- `/meta`: `contractVersion 1.1`, `dataGeneratedAt 2026-06-16T14:51:48Z`, 7 required warnings,
  5 lineage warnings, **0 path leaks** (`Legacy fixed-path behaviour artifact present at
  [redacted path]; …`).
- `/overview` HTML: "Problematic sensors **13**", `167,331` and `30,096` thousands-separated,
  notice strip copy present, trust banner showing run id + lineage badge + `[redacted path]`,
  sidebar `Dashboard v0.2`. No `>17<`, no `167331`, no `v0.1`.
- Notices render on all five views (3/2/1/3/3 keys, matching the contract table).
- `/timeline`: 117 days → 57 normal / 11 warning / 49 critical; training window `normal`;
  `deviationScore` absent from the wire; the recurring-exclusion disclosure present in the KPI
  description and the chart footer.
- `/incidents`: DOM order == API order for all 88; the duplicated id renders twice without a React
  key collision.
- Prewarm: `Prewarmed 5/5 dashboard views` in ~1.1 s; second call cached (0.001 s). A broken view
  logs at ERROR + WARNING, startup survives, `/health` stays 200, and the endpoint still returns
  the contract `503 ARTIFACT_UNREADABLE` (loader called twice — exceptions are not cached).
- Production build with the API down: `loading.tsx` skeleton in the initial HTML;
  `error.tsx` present in both the SSR and client chunks; the flight payload carries
  `E{"digest":"4161088874"}` — an error row with a digest and **no message**, which is exactly the
  production redaction documented in `running_the_dashboard.md`. The boundary renders client-side,
  so this was confirmed by inspecting the stream and chunks rather than by pixel.

---

## 4. Deferred — before pilot

| Item | Why deferred |
|---|---|
| **CF-01: incident-ID uniqueness.** `INC-process_drift-20240925T000000Z-8743` names two genuinely different incidents (warning/`conditioner_steam_loop_temp`, anomaly/`granulator_power`); 87 unique ids of 88. `_pack_rank` and `actions_by_incident` silently share one rank and one action set across both. | The fix belongs in `src/intelligence/incidents/` id generation and requires regenerating the pinned run. **Pinned by a test** (`assert len({r["id"] for r in records}) == 87`) so the upstream fix must update it rather than land unnoticed. Do **not** dedupe at the API — that hides a data-integrity defect. |
| The other 7 `overview.py` pins (`_INCIDENT_COUNT`, `_CONTEXTUALISED_ANOMALIES`, `_RESIDUAL_*`, `_TOTAL_RECORDS`, `_CANDIDATE_EVENT_COUNT`, `_REVIEW_PACK_SIZE`, `_NON_NORMAL_ROWS`) | Scoped out by decision. Each is now cross-checked against its owning endpoint by a `@requires_real_run` test, so a divergence fails the suite even though nothing enforces it at runtime. |
| Frontend union drift (`SensorIssueType`, `DetectionMethod`), `statusReason` rendering, OpenAPI-generated types or zod parsing | Nothing switches on those unions today, so nothing crashes — but TypeScript has stopped being a contract guard. |
| Generic `INTERNAL` exception handler for non-`ApiError` exceptions | The error envelope currently holds only for `ApiError`. |
| Sensor material-share threshold calibration | `granulator_power` goes critical on 25 faulty rows of 167,331. Honest but alarmist. |
| Tightening `contextualised` to the scoring-experiment suppression table | The `affected_sensors ∋ inlet_hopper_points` proxy is defensible on this run; it will over-mark a multi-sensor incident that merely touches the channel. |
| ETag / `Cache-Control` / 304 | Contract §1 specifies caching that is not implemented. Implement it or amend §1 — do not let it drift. |
| Frontend tests (notice rendering, order preservation) | No frontend test infra exists; `npm run typecheck` + `next build` cover this sprint's rename. |

## 5. Disclosed, not fixed

- **`TimelineStatus = "drift"` is unreachable on the canonical run.** All 36 days overlapping an
  active/persistent drift event are also overlapped by an anomaly/critical incident, and
  `critical > drift`. True before and after this sprint. `timeline/page.tsx::toBadgeStatus`'s drift
  branch is dead code. Recorded in the contract; the ladder was not bent to make it fire.
- **Every day from 2024-09-04 onward is `critical`** (13/13 post-training validation days, 22/22
  fault-window days), driven by anomaly/critical incidents rather than by the inlet-hopper fault
  (which starts 2024-09-17). A genuine finding — and the second question a reviewer will ask after
  "why was everything warning?".
- **`WARNING_EVIDENCE_SHARE = 0.05` is a new magic number.** It decides only 11 of 117 days, so the
  view is not sensitive to it — but it lives in contract §8 and in the chart footer, or it becomes
  the next pinned `17`.

---

*Sprint C1 — Dashboard v0.2 demo trust fixes.*
