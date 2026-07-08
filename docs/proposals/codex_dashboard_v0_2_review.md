# Codex Dashboard v0.2 Technical Review

Produced by Codex.

## 1. Executive Summary

Assessment: mostly ready as a backend foundation, but needs fixes before the next phase.

The FastAPI route structure, service split, startup lineage gate, fail-closed dependency, view envelopes, and most artifact-backed endpoint behavior are in good shape. The main blockers are trust and contract issues: `/dashboard/meta` can expose local filesystem paths through lineage warnings, `/dashboard/meta` does not return the full required warning set, and the frontend discards all per-view notices before rendering. There are also high-priority integration gaps around stale frontend types, incidents ordering, generic error envelopes, and hardcoded metadata.

This review inspected the working tree without modifying source code. Tests and builds were not run because this audit was constrained to changing only this report file; `pytest`, `next build`, and lint/typecheck commands can write caches or build artifacts. One read-only import check was run through `.venv` to inspect the current lineage warning projection.

## 2. Review Scope

Inspected:

- `docs/dashboard/dashboard_api_contract.md`
- `docs/dashboard/dashboard_data_contract.md`
- `src/api/`
- `src/dashboard/`
- `apps/dashboard/src/lib/dashboard/data-access.ts`
- `apps/dashboard/src/app/**/page.tsx`
- `apps/dashboard/src/app/layout.tsx`
- `apps/dashboard/src/types/*.ts`
- `apps/dashboard/next.config.ts`
- `apps/dashboard/package.json`
- `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`
- `tests/api/*.py`
- Selected canonical manifests under `data/intelligence/.../runs/remat-v1-20260616T102558Z`

Note: the prompt named `docs/dashboard/dashboard_api_contracts_v0_2.md`, but that file is not present. The available approved API contract is `docs/dashboard/dashboard_api_contract.md`.

## 3. Critical Issues

### C-01

- Severity: Critical
- Area: API security / contract compliance
- Finding: `/api/v1/dashboard/meta` can expose local filesystem paths through lineage warnings.
- Evidence / file references:
  - Contract forbids exposing raw parquet paths, run folders, joblib models, or model internals: `docs/dashboard/dashboard_api_contract.md:26`.
  - The lineage validator formats warning strings with raw `run_path`: `src/dashboard/lineage.py:82`.
  - The legacy fixed-path warning embeds the local path directly: `src/dashboard/lineage.py:185`.
  - The API projection passes `result.warnings` through unchanged: `src/api/services/lineage_gate.py:32`.
  - Current read-only check returned a warning containing `C:\Users\User\Desktop\InjexCore\data\intelligence\behaviour\behaviour_fit_manifest.json`.
- Impact: Leaks local deployment layout and violates the explicit API presentation boundary. This is especially visible because `/meta` is intended to be diagnostic and available even when lineage is warning or invalid.
- Recommendation: Sanitize API-facing lineage warnings before returning them. Keep component names, severity, and relative artifact group identifiers, but do not emit absolute paths or raw run directories. Add a regression test that no warning contains drive letters, backslashes, repository paths, `.parquet`, `.joblib`, or `runs/<id>` internals.

### C-02

- Severity: Critical
- Area: API/frontend trust boundary
- Finding: Required warnings are not fulfilled end-to-end. `/dashboard/meta` returns an empty `requiredWarnings` list, and frontend pages unwrap only `.data`, discarding per-view `meta.notices`.
- Evidence / file references:
  - Contract says `/dashboard/meta` is the source for the full required-warning set: `docs/dashboard/dashboard_api_contract.md:39`, `docs/dashboard/dashboard_api_contract.md:102`.
  - Contract says a frontend render slot is required for `meta.notices` / required warnings: `docs/dashboard/dashboard_api_contract.md:237`.
  - Required warning copy is defined in `docs/dashboard/dashboard_data_contract.md:166` through `docs/dashboard/dashboard_data_contract.md:175`.
  - Implementation returns `required_warnings=[]`: `src/api/routes/dashboard.py:59`.
  - Frontend convenience functions return only `.data`: `apps/dashboard/src/lib/dashboard/data-access.ts:116`, `apps/dashboard/src/lib/dashboard/data-access.ts:120`, `apps/dashboard/src/lib/dashboard/data-access.ts:124`, `apps/dashboard/src/lib/dashboard/data-access.ts:128`, `apps/dashboard/src/lib/dashboard/data-access.ts:132`.
  - Pages call `getOverviewData`, `getTimelineData`, `getSensorHealthData`, `getDriftAnomalyData`, and `getIncidentsData`: for example `apps/dashboard/src/app/overview/page.tsx:9`, `apps/dashboard/src/app/timeline/page.tsx:19`, `apps/dashboard/src/app/sensor-health/page.tsx:23`, `apps/dashboard/src/app/drift-anomaly/page.tsx:20`, `apps/dashboard/src/app/incidents/page.tsx:27`.
- Impact: Interpretive and contextual data can be shown without the mandatory caveats about read-only use, unchanged scores, pending quarantine, proxy views, associative relationships, and required plant records. This directly affects user trust and demo readiness.
- Recommendation: Populate `/dashboard/meta.requiredWarnings` from the exact warning registry, and render a global warning/banner/footer in the dashboard shell. Pages should either consume the full `{ meta, data }` payload or a shared layout should fetch `/dashboard/meta`. Add frontend checks that at least one required warning is visible in rendered pages.

## 4. High Priority Issues

### H-01

- Severity: High
- Area: Frontend type safety
- Finding: Frontend domain types do not match the backend v0.2 contract.
- Evidence / file references:
  - Backend sensor issue union includes real rule families: `src/api/schemas/sensor_health.py:17` through `src/api/schemas/sensor_health.py:28`.
  - Frontend still lists old demo issue types such as `noise`, `frozen_signal`, `drift`, `outlier_spikes`, and `missing_values`: `apps/dashboard/src/types/sensor-health.ts:7` through `apps/dashboard/src/types/sensor-health.ts:13`.
  - Backend detection methods include `statistical`, `mahalanobis`, `pca_t2`, `pca_residual`, `isolation_forest`, and `context_overlay`: `src/api/schemas/drift_anomaly.py:20` through `src/api/schemas/drift_anomaly.py:26`.
  - Frontend still includes demo-only `lof` and `ocsvm`, and lacks several real methods: `apps/dashboard/src/types/drift-anomaly.ts:8` through `apps/dashboard/src/types/drift-anomaly.ts:12`.
  - Backend overview has `statusReason`: `src/api/schemas/overview.py:44`; frontend `DashboardSummary` does not: `apps/dashboard/src/types/dashboard.ts:21` through `apps/dashboard/src/types/dashboard.ts:27`.
  - Backend incident records include additive optional source/timestamp fields: `src/api/schemas/incidents.py:56` through `src/api/schemas/incidents.py:60`; frontend `IncidentRecord` omits them: `apps/dashboard/src/types/incidents.ts:21` through `apps/dashboard/src/types/incidents.ts:45`.
- Impact: TypeScript is no longer a reliable contract guard. The runtime currently casts JSON to these types, so mismatches can pass silently and later break components when they switch on enum values.
- Recommendation: Update the frontend types to the approved v0.2 response shapes and demo fixtures. Prefer generated OpenAPI types or runtime parsing in `data-access.ts` to prevent future drift.

### H-02

- Severity: High
- Area: Frontend data correctness
- Finding: The incidents page re-sorts the API response by UI severity, overriding the backend contract order.
- Evidence / file references:
  - Contract requires all incidents sorted by review-pack priority, then severity, then `startDate`: `docs/dashboard/dashboard_api_contract.md:52`.
  - Backend tests lock pack-first sorting: `tests/api/test_dashboard_incidents.py:48`, `tests/api/test_dashboard_incidents.py:331`.
  - Frontend sorts by `SEVERITY_ORDER` after fetching: `apps/dashboard/src/app/incidents/page.tsx:28` through `apps/dashboard/src/app/incidents/page.tsx:29`.
- Impact: The UI can hide the review-pack priority that the backend intentionally preserves. This weakens triage correctness and can make the demo disagree with the API contract.
- Recommendation: Preserve API order as the default. If sorting controls are added later, make review-pack priority the default and label alternate sorts explicitly.

### H-03

- Severity: High
- Area: Data correctness / metadata honesty
- Finding: `dataGeneratedAt`, `trainWindowEnd`, and overview values are pinned constants rather than sourced from canonical artifacts; at least `dataGeneratedAt` does not match the inspected behaviour manifest.
- Evidence / file references:
  - Contract says `dataGeneratedAt` is the run-manifest completion time, not response time: `docs/dashboard/dashboard_api_contract.md:76`, `docs/dashboard/dashboard_api_contract.md:153`.
  - Implementation has a TODO to source metadata from manifests, but currently pins `DATA_GENERATED_AT = "2026-06-16T10:25:58Z"`: `src/api/services/view_meta.py:17` through `src/api/services/view_meta.py:21`.
  - Canonical behaviour manifest has `created_at = "2026-06-16T10:26:24.236548+00:00"`: `data/intelligence/behaviour/runs/remat-v1-20260616T102558Z/behaviour_fit_manifest.json:5`.
  - Overview uses B1-verified constants with a TODO to replace them with artifact readers: `src/api/services/overview.py:15` through `src/api/services/overview.py:24`.
- Impact: The dashboard can report stale or incorrect metadata while appearing real-data-backed. This is a trust issue even if the pinned numeric values happen to match the current artifacts.
- Recommendation: Load manifest metadata once at startup or first hit and use it consistently in `/meta` and every envelope. Replace overview constants with artifact-backed aggregates or add startup assertions that fail closed when constants diverge from artifacts.

### H-04

- Severity: High
- Area: API error contract
- Finding: The `{ "error": { "code": "INTERNAL", "message": "..." } }` contract is only guaranteed for `ApiError` subclasses, not unhandled exceptions.
- Evidence / file references:
  - Contract lists `INTERNAL` as a 500 error shape: `docs/dashboard/dashboard_api_contract.md:57`.
  - `ApiError` defines `INTERNAL`: `src/api/errors.py:14`.
  - FastAPI registers the contract handler only for `ApiError`: `src/api/main.py:28`.
  - `exception_handlers.py` explicitly says it renders `ApiError`: `src/api/exception_handlers.py:1`, `src/api/exception_handlers.py:13`.
- Impact: Unexpected runtime errors can return FastAPI's default response instead of the approved envelope, and may be harder for the frontend to surface consistently.
- Recommendation: Register a generic exception handler that returns `INTERNAL` without leaking internals, while logging the detailed exception server-side. Add a test using a route that raises a non-`ApiError`.

### H-05

- Severity: High
- Area: Frontend error handling
- Finding: API errors propagate from Server Components without an app-level error boundary or clear dashboard-specific display.
- Evidence / file references:
  - `fetchDashboardApi` throws `DashboardApiError`: `apps/dashboard/src/lib/dashboard/data-access.ts:45` through `apps/dashboard/src/lib/dashboard/data-access.ts:65`.
  - No `apps/dashboard/src/app/error.tsx` file is present.
  - Pages call data getters directly, with no catch or local error state: for example `apps/dashboard/src/app/drift-anomaly/page.tsx:20` and `apps/dashboard/src/app/incidents/page.tsx:27`.
- Impact: A legitimate fail-closed 503 such as `LINEAGE_INVALID` may render as a generic Next.js error instead of a clear diagnostic page. That is risky for demo and operator trust.
- Recommendation: Add an app-level error boundary that recognizes `DashboardApiError` and displays the API code/message. Keep fail-closed behavior, but make the failure understandable.

## 5. Medium / Low Priority Improvements

- Medium: Backend cache headers are not implemented. The contract specifies strong `ETag`, `Cache-Control: public, max-age=3600`, and `304` behavior (`docs/dashboard/dashboard_api_contract.md:60`), but no `ETag`, `Cache-Control`, or `If-None-Match` handling appears under `src/api/`.
- Medium: The frontend fetch layer uses `cache: "no-store"` (`apps/dashboard/src/lib/dashboard/data-access.ts:48`). This avoids build-time freezing, but it also means every page request hits the API. Backend in-process caches reduce the cost, but this diverges from the contract's HTTP caching design.
- Medium: Frontend scripts support `build` and `lint` only (`apps/dashboard/package.json:7`, `apps/dashboard/package.json:9`). There is no explicit `typecheck` or test script for dashboard integration.
- Medium: Only the incidents API has a real-artifact integration assertion for the full 88 records (`tests/api/test_dashboard_incidents.py:391`). Timeline, sensor-health, and drift-anomaly endpoint tests mainly use synthetic frames.
- Low: `apps/dashboard/src/app/incidents/page.tsx:99` uses an index as part of the React key. It avoids the duplicate-key warning, but the stable fix should come from guaranteed unique incident IDs or a backend-provided display key.
- Low: `apps/dashboard/src/components/app/app-shell.tsx` still displays `Dashboard v0.1`; this is confusing during a v0.2 review.
- Low: `apps/dashboard/next.config.ts` includes local development origins/IPs. This is reasonable for local MVP work, but deployment assumptions should be documented and tightened outside dev.
- Low: The dashboard README is still the default Next.js README and does not document `DASHBOARD_API_URL`, the FastAPI dependency, or the local two-process dev flow.

## 6. Contract Compliance Notes

- Endpoint surface: The reviewed dashboard API routes are read-only GET endpoints. No POST/PUT/PATCH/DELETE or accidental write surface was found under `src/api/`.
- Envelope shape: The five view endpoints return `{ meta, data }` and tests assert the envelope shape. This matches the contract.
- CamelCase JSON: Backend response models use a shared camelCase alias base, and API tests assert camelCase fields across endpoints. This matches the contract for the inspected response models.
- Notices: API view endpoint notice keys and copy match the per-view contract table. However, `/dashboard/meta.requiredWarnings` is empty and the frontend discards all view notices. End-to-end notice compliance is not met.
- Lineage behavior: `validate_dashboard_chain` is evaluated once in FastAPI lifespan and cached on `app.state.dashboard_lineage` (`src/api/main.py:22`). Data endpoints use `Depends(require_valid_dashboard_lineage)` and fail closed on missing or invalid lineage (`src/api/dependencies.py:17` through `src/api/dependencies.py:18`). `/health` does not use the dependency and remains liveness-only. `/meta` remains available. This matches the intended lineage behavior except for unsanitized warning strings.
- Error contract: `LINEAGE_INVALID` and `ARTIFACT_UNREADABLE` are implemented through `ApiError` and tested. Generic `INTERNAL` handling is not fully implemented.
- Backend architecture: Routes are thin and delegate view construction to services. Artifact reads are isolated in service loaders rather than duplicated in route handlers.
- Frontend data access boundary: Fetching is centralized in `apps/dashboard/src/lib/dashboard/data-access.ts`. Pages do not duplicate raw fetch logic and do not silently fall back to demo data. However, the convenience getters drop envelope metadata and notices.
- No raw internals exposed: View data endpoints avoid exposing parquet paths, run folders, and model internals. `/dashboard/meta` can expose a local absolute path through lineage warnings, so this is not fully compliant.
- Detector/status honesty: Backend drift-anomaly schemas and tests use real detector IDs and explicitly exclude demo-only `lof`/`ocsvm`. Incident backend tests assert `closed` is not emitted. No backend copy reviewed here asserted confirmed failures or causal incident relationships.
- Date/period semantics: The served period pins match the behaviour manifest's day-level coverage (`2024-06-14` through `2024-10-08`) and the train-window day (`2024-09-03`). The issue is sourcing and auditability, not an observed day-range mismatch.
- CORS/deployment: No API CORS middleware was found. That is reasonable for the current Server Component fetch model, where Next.js talks to FastAPI server-side, but it should be documented before any browser-direct or cross-origin deployment.

## 7. Testing Gaps

- No test asserts that `/dashboard/meta.requiredWarnings` equals the full exact-copy warning set. Current test only checks that it is a list (`tests/api/test_dashboard_meta.py:36`), allowing the current empty list.
- No test asserts that lineage warnings are sanitized before reaching the API.
- No test covers generic non-`ApiError` exceptions returning the `INTERNAL` error envelope.
- No frontend tests verify that notices or required warnings are rendered.
- No frontend test verifies that incident order from the API is preserved.
- No generated type parity, OpenAPI snapshot, or runtime schema validation test protects frontend/backend drift.
- No dashboard-specific `typecheck` or test script is present in `apps/dashboard/package.json`.
- No test asserts that `dataGeneratedAt` is sourced from, and equal to, canonical manifest metadata.
- No real-artifact endpoint integration tests exist for timeline, sensor-health, or drift-anomaly equivalent to the incidents 88-record check.

## 8. Performance / Reliability Notes

- Startup lineage validation is performed once and cached. This is correct.
- Timeline, sensor-health, drift-anomaly, and incidents services use first-hit `lru_cache(maxsize=1)` around built responses. This avoids repeated parquet reads after the first successful request.
- Artifact read failures are converted to `ARTIFACT_UNREADABLE` without exposing underlying filesystem exceptions in the data endpoints. This is correct.
- Sensor health avoids the large sensor-health scores table and reads only the 17-row summary plus selected master columns for coverage. This is reasonable.
- Cold first requests still do parquet work. For demos, consider prewarming these endpoint caches at startup so artifact failures are discovered before the first user click.
- `lru_cache` can compute more than once on concurrent first misses, but this is acceptable for MVP unless demo load is concurrent.
- HTTP cache headers and ETag support are absent despite being in the contract.
- The current local `.venv` could import pydantic-backed code, but a TestClient check failed because `fastapi` is not installed in that environment. `pyproject.toml` and `requirements.txt` declare FastAPI, so this is likely a stale environment rather than a source issue.

## 9. Frontend Integration Notes

- Pages are Server Components by inspection; no reviewed page declares `"use client"`.
- `DASHBOARD_API_URL` is server-side only because it has no `NEXT_PUBLIC_` prefix, and the fetch layer defaults to `http://127.0.0.1:8000`. This is acceptable for local MVP, but deployment should set it explicitly.
- Fetching is centralized in `data-access.ts`; there is no direct page-level `fetch`.
- There is no silent fallback to demo fixtures. Demo fixtures remain in `apps/dashboard/src/lib/dashboard/demo-*.ts`, but pages do not import them.
- API errors are represented as `DashboardApiError`, but there is no visible app-level handling.
- Notices and envelope metadata are not used by pages because the current page calls unwrap only `.data`.
- Frontend type definitions are stale relative to the approved backend response unions and additive fields.
- Incident ordering is changed in the page, which conflicts with backend ordering semantics.
- Build/lint behavior was not run in this audit. `next build` would write `.next`; lint/typecheck may update caches or depend on generated Next types.

## 10. Recommended Next Actions

Must fix before demo:

1. Sanitize API-facing lineage warnings so `/dashboard/meta` never exposes absolute paths or raw artifact internals.
2. Populate `/dashboard/meta.requiredWarnings` with the full exact-copy warning set and render required warnings/notices in the dashboard UI.
3. Preserve backend incident ordering in the frontend default view.
4. Update frontend domain types to the v0.2 contract, including sensor issue families, detection methods, `statusReason`, and incident additive fields.
5. Source `dataGeneratedAt` and `trainWindowEnd` from canonical artifacts, and either artifact-back the overview endpoint or assert pinned constants against artifacts at startup.
6. Add a generic `INTERNAL` exception handler and a frontend error boundary for `DashboardApiError`.

Should fix soon:

1. Add tests for `/meta.requiredWarnings`, warning sanitization, `INTERNAL`, and frontend notice rendering.
2. Add real-artifact integration checks for timeline, sensor-health, and drift-anomaly.
3. Implement the contract's ETag/cache-control behavior or explicitly revise the contract for MVP.
4. Add dashboard `typecheck` and test scripts.
5. Document the two-process dev setup and `DASHBOARD_API_URL` in the dashboard README.

Nice to have:

1. Generate TypeScript API types from OpenAPI or validate payloads with a runtime schema.
2. Prewarm cached view responses at FastAPI startup for demo reliability.
3. Rename or add the expected `dashboard_api_contracts_v0_2.md` reference, or update phase documentation to the actual filename.
4. Update visible footer/version copy from Dashboard v0.1 to v0.2.

## 11. Final Verdict

Needs fixes before next phase.
