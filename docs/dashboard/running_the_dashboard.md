# Running the Dashboard

Two processes: a read-only FastAPI service (`src/api/`) that reads the pinned canonical
run's artifacts, and a Next.js dashboard (`apps/dashboard/`) that consumes it. **Start
the API first** — the dashboard has no offline mode and never falls back to demo data.

---

## 1. Install

```bash
# From the repo root. fastapi and uvicorn are core dependencies (there is no
# "api" extra); httpx lives in [dev] and is required by the API tests.
pip install -e ".[dev]"

cd apps/dashboard && npm ci && cd -
```

> After pulling a v0.2 change, re-run `pip install -e ".[dev]"`. The API imports
> `fastapi`/`uvicorn`, which older environments do not have.

## 2. Start the API

```bash
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

At startup the service:

1. validates the pinned dashboard chain once (`validate_dashboard_chain`) and caches
   the result on `app.state`;
2. **prewarms all five view caches** (~1 s) unless lineage is invalid, so an artifact
   failure lands in the log instead of in front of a demo audience.

A **healthy prewarm is silent.** Uvicorn configures only its own loggers, so an
application logger's `INFO` records are dropped by the root level; `--log-level info`
does not change that. Failures are loud regardless — they are logged at `ERROR` /
`WARNING`, which `logging.lastResort` prints to stderr even with no handler configured:

```
Dashboard view 'timeline' failed to prewarm; it will retry on first request …
Prewarmed only 4/5 dashboard views; the rest will 503 until their artifacts become readable.
```

To see the success line too, configure logging before starting the app, e.g.:

```bash
python -c "import logging,uvicorn; logging.basicConfig(level=logging.INFO); \
  uvicorn.run('src.api.main:app', host='127.0.0.1', port=8000)"
# INFO src.api.services.prewarm: Prewarmed 5/5 dashboard views: sensor-health, overview, …
```

Set `INJEXCORE_API_PREWARM=0` to skip the prewarm (faster restarts; the first request
then pays for the parquet reads).

## 3. Start the dashboard

```bash
cd apps/dashboard
cp .env.example .env.local   # then adjust if the API is not on :8000
npm run dev
```

`DASHBOARD_API_URL` has **no** `NEXT_PUBLIC_` prefix, so it never reaches the client
bundle. Only Server Components read it, through `src/lib/dashboard/data-access.ts`.

```
DASHBOARD_API_URL=http://127.0.0.1:8000
```

## 4. Useful URLs

| URL | What it tells you |
|---|---|
| <http://127.0.0.1:8000/api/v1/health> | Liveness only. Reads no artifacts and no lineage — green even when the chain is broken. |
| <http://127.0.0.1:8000/api/v1/dashboard/meta> | Run identity, lineage gate, and the full 7-entry required-warning set. |
| <http://127.0.0.1:8000/docs> | OpenAPI browser. |
| <http://127.0.0.1:3000/overview> | The dashboard landing view. |

---

## What you should expect to see

### `lineage.severity == "warning"` is normal

On the canonical chain, `/dashboard/meta` reports `severity: "warning"` with five
warnings. **This is expected, not a fault.** Four are the PROV-01 provenance gap (the
correlation/pca/anomaly/sensor_health manifests predate explicit `behaviour_run_id`
provenance); the fifth reports a legacy fixed-path behaviour artifact still on disk,
which the API refuses to read. `is_valid` stays `true` and all data endpoints serve.

Lineage warnings are **path-redacted** before they reach the wire: you will see
`[redacted path]`, never a drive letter, run folder or `.parquet` filename.

### The dashboard serves one pinned canonical run

`remat-v1-20260616T102558Z` (BOM `20260612T124909Z`). There is no run selector. The run
is immutable, which is why every view builder caches its response in-process for the
life of the process. `dataGeneratedAt` (`2026-06-16T14:51:48Z`) is the *latest*
completion timestamp across the 11-component chain — not the run-id mint time, and not
the behaviour fit time (behaviour completes first, hours before the artifacts served
here).

### Errors are fail-closed, never faked

| Symptom | Meaning |
|---|---|
| `503 LINEAGE_INVALID` | The startup lineage gate failed (a component's pinned run is missing, incomplete, or the wrong component). Every data endpoint refuses; `/meta` stays up as the banner source. |
| `503 ARTIFACT_UNREADABLE` | A required parquet of the pinned run could not be read. The underlying message is discarded on purpose — it would embed filesystem paths. |
| `API_UNREACHABLE` in the UI | The dashboard could not reach `DASHBOARD_API_URL`. Start the API. |
| A polished "Dashboard data unavailable" page | `app/error.tsx` caught the failure. The dashboard shows nothing rather than something unverified. |

**The dashboard never falls back to demo fixtures.** `src/lib/dashboard/demo-*.ts` are
retained for local component work and are imported by no page.

> **Error detail in production builds.** Next.js redacts errors thrown in Server
> Components before they reach the client: `error.message` becomes a generic string and
> only `error.digest` correlates to the server log. So the API error *code* is visible
> in the error page under `npm run dev` only. In a production build, read the uvicorn
> log or `curl` the endpoint directly.

### Security assumptions (MVP)

- **No authentication and no authorization.** Anyone who can reach the port can read
  every view.
- The service is assumed to bind to **localhost or a trusted network**. Do not expose
  port 8000 publicly.
- No CORS middleware: the Next.js Server Components fetch server-side, so the browser
  never calls the API directly.
- The API is read-only by construction — there is no route that approves a quarantine,
  refits a model, rescores, or mutates any artifact.

---

## 5. Verification

```bash
# Backend (repo root)
python -m pytest tests/api          # API suite
python -m pytest                    # full suite
python -m ruff check . && python -m ruff format --check .
python -m mypy src

# Frontend (apps/dashboard)
npm run typecheck
npm run lint
npm run build
```

The API tests disable the startup prewarm via an autouse fixture
(`tests/api/conftest.py` sets `INJEXCORE_API_PREWARM=0`). Without it, `TestClient(app)`
would run the lifespan and drive real parquet reads in every test.

Several tests are guarded by `@requires_real_run` and skip when the canonical run's
artifacts are absent. They are the ones that pin the real numbers — 13 problematic
sensors of 17, 88 incidents, `dataGeneratedAt` — so run them locally with data present.

---

## Related

- [dashboard_api_contract.md](dashboard_api_contract.md) — endpoints, envelopes, enum
  mappings, computed-field rules (`evidenceShare`, the day-status ladder).
- [dashboard_data_contract.md](dashboard_data_contract.md) — canonical run pins, allowed
  artifacts, forbidden views, the required warning copy (§5.4), read-only boundaries.
