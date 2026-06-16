# Pre-Dashboard Contract & Lineage Cleanup — Sprint Report

**Repo:** InjexCore · **Branch:** `refactor/v1-architecture-stabilization` · **Date:** 2026-06-16
**Canonical chain:** `remat-v1-20260616T102558Z` · **BOM run:** `20260612T124909Z`

---

## A. Executive summary

The cleanup sprint **succeeded**. All six pre-dashboard items (DASH-01, DASH-02,
LINEAGE-01, PROV-01, CTX-01, DOC-01) are implemented, tested, and documented. The
full quality suite is green: **575 tests pass** (up from 552), `ruff`, `ruff
format --check`, and `mypy src` all clean.

The work is strictly a contract/lineage hardening pass — no dashboard UI, no
FastAPI, no streaming, no quarantine approval, no Reference v2, no model refit,
and no mutation of artifacts or original scores. Per the agreed decision, the
existing canonical real-data manifests were **not regenerated**; the new
behaviour-provenance fields land in code and are proven by synthetic-manifest
tests, while the dashboard validator degrades the (pre-PROV-01) canonical chain
to a *warning* rather than failing it.

The system is ready for **technical validation dashboard planning, not
production deployment**.

---

## B. Fix matrix

| ID | Item | Status | Files changed | Tests added/updated | Remaining limitations |
|---|---|---|---|---|---|
| **DASH-01** | Dashboard data contract | ✅ Done | `docs/dashboard/dashboard_data_contract.md` (new) | n/a (doc) | Forensic-addendum + behaviour-provenance caveats documented in the contract |
| **DASH-02** | Run-selector lineage safety | ✅ Done | `src/dashboard/{__init__,contract,lineage}.py` (new) | `tests/unit/dashboard/test_lineage.py` (+9) | Validator is the contract; a UI run-selector still has to consult it |
| **LINEAGE-01** | `expected_component` coverage | ✅ Done | `drift/incidents/reference/scoring_experiment/run_*.py`, `anomaly/run_anomaly.py`, `context/{operational,bom}/run_*.py` | boundary tests in incidents + drift; fixed incidents conftest fixture | `forensic` upstream intentionally not component-checked (non-compliant writer) |
| **PROV-01** | `behaviour_run_id` in leaf manifests | ✅ Done | `_common/upstream.py`, `correlation/pca/anomaly/sensor_health/run_*.py` | manifest assertions in all 4 leaf run tests | Existing canonical manifests predate the fields → refresh on next remat |
| **CTX-01** | Operational + BOM addendum overrides | ✅ Done | `context/operational/run_operational_context.py`, `context/bom/run_bom_context.py` | `tests/unit/context/operational/test_run_operational_context.py` (+6, new); +6 in bom run test | Addendum not auto-regenerated; base forensic run remains non-compliant |
| **DOC-01** | Stale docs refresh | ✅ Done | `CLAUDE.md`, `docs/architecture/intelligence_dataflow.md`, `docs/README.md`, `README.md` | n/a (docs) | Historical `MASTER_VERSION_*` snapshots intentionally left unchanged |

---

## C. Dashboard contract summary

[`docs/dashboard/dashboard_data_contract.md`](../../docs/dashboard/dashboard_data_contract.md)
is the first official consumption contract; [`src/dashboard/`](../../src/dashboard/)
is its executable half.

- **Canonical run:** `remat-v1-20260616T102558Z` (intelligence + operational) /
  BOM `20260612T124909Z`, pinned in `src/dashboard/contract.py`.
- **Allowed artifacts (11 groups):** scoring_experiments, forensics/reference_decision,
  incidents, sensor_health, drift, operational, anomaly, reference, behaviour,
  correlation, pca — each documented with purpose / safe fields / unsafe-or-misleading
  fields / required warning.
- **Forbidden MVP views:** legacy fixed-path behaviour artifacts; non-canonical
  runs without a lineage warning; the operational forensic addendum for `remat`
  unless regenerated; Reference v2 / quarantine-approval / model-refit / auto
  sensor-exclusion controls; plant-record claims; causal explanations.
- **Required warnings:** the exact 7-line copy (read-only; original scores
  unchanged; adjusted severity is interpretive; quarantine pending; healthy-only
  is a proxy; relationships associative not causal; plant records still required).
- **Boundaries:** no write / approval / quarantine-application / Reference v2 /
  refit / retraining / production-alerting.

---

## D. Run-selector safety summary

`validate_dashboard_chain(run_id, bom_run_id)` ([lineage.py](../../src/dashboard/lineage.py))
is **strictly read-only** (a test snapshots the tmp tree before/after and asserts
no writes). For every registry component it resolves the pinned run by reusing
`runs.is_completed_run` (parse + required fields + `completion_status` +
`run_id == dir name` + `expected_component`). It returns
`DashboardChainValidation` (`is_valid`, `severity`, `warnings`,
`component_statuses`, `lineage_edges`, `canonical_match`).

**Stale-run handling (the selector rule):**
- A **missing / malformed / wrong-component / wrong-run-id** manifest → component
  `severity="invalid"` → chain `is_valid=False`.
- A **valid but non-canonical** completed chain → `is_valid=True`,
  `canonical_match=False`, `severity="warning"` + an explicit "not the canonical
  chain; surface only as non-canonical/stale" warning. Only `is_valid and
  canonical_match` is shown as authoritative; MVP pins the canonical run.
- A **legacy fixed-path** behaviour artifact on disk → warning.

Validated against the **real** canonical chain on disk: `is_valid=True`,
`canonical_match=True`, `severity="warning"` (the four pre-PROV-01 leaves warn
about missing behaviour provenance; a legacy fixed-path behaviour artifact was
also detected and warned). Synthetic-manifest unit tests cover canonical-valid,
wrong-run-id-invalid, non-canonical-warning, missing-manifest-invalid,
wrong-component-invalid, BOM-mismatch-invalid, and missing-provenance-warning.

---

## E. Manifest provenance summary

Leaf manifests (correlation, pca, anomaly, sensor_health) now record explicit
behaviour provenance via the shared `behaviour_provenance()` helper in
[`_common/upstream.py`](../../src/intelligence/_common/upstream.py):
`behaviour_run_id`, `behaviour_manifest_path`, `behaviour_created_at`,
`behaviour_fit_timestamp`, `behaviour_master_dataset_sha256`. The run directory
is resolved with `resolve_behaviour_dir(labels_path)` (latest run, or the labels'
grandparent), mirroring the existing sensor-health pattern. Each leaf's run test
asserts all five fields against a run-versioned synthetic behaviour layout.

Downstream lineage no longer infers behaviour from a timestamp: the dashboard
validator reads `behaviour_run_id` directly to build behaviour→leaf edges (and
`pca_run_id` for the pca→anomaly edge). **The existing canonical manifests
predate this change** (Decision: do not regenerate now); the validator reports
them as a warning, and the next rematerialization will refresh them.

---

## F. Operational + BOM addendum override summary

Both `src/context/operational/run_operational_context.py` and
`src/context/bom/run_bom_context.py` gained `--anomaly-run` / `--forensic-run`
CLI flags for the forensic addendum:

- **Override beats config pin** (`args.<x>_run or <policy pin>`), so the addendum
  can be regenerated against the canonical chain.
- **Fail-closed:** a shared `_resolve_addendum_run(...)` wraps `resolve_run` and,
  on `FileNotFoundError`, raises the component's blocker error with an actionable
  message naming the run, the root, and the override flag — never silently
  consuming a stale/pre-hardening run.
- **`--skip-addendum`** bypasses addendum resolution entirely (no override needed).
- The anomaly run is component-checked (`expected_component="anomaly"`); the base
  `forensic_manifest.json` run is intentionally **not** component-checked — its
  one-off writer emits `component:"forensics"` and omits `run_id`/`completion_status`,
  so it is not a run-versioning-compliant run (documented as a known limitation).
- The addendum is **not** auto-regenerated by this sprint.

Tests (operational: new file; bom: extended) cover override-parsed,
override-beats-pin, skip-exempt, stale-pin-fails-closed, and valid-override-selects-path.

---

## G. QA results

Quality gates (system Python, `python -m`):

| Gate | Result |
|---|---|
| `pytest` | **575 passed in 46.27s** (baseline was 552) |
| `ruff check .` | All checks passed! |
| `ruff format --check .` | 323 files already formatted |
| `mypy src` | Success: no issues found in 187 source files |

**qa-agent:** could not complete — two launches both returned a transient
server-side `500 Internal server error` (the first after 15 tool calls, the
second before any work). Rather than retry indefinitely, an **equivalent inline
QA validation** was performed: all four gates were run and captured above; each
of the six focus areas was verified directly (read-only validation against the
real canonical chain; `expected_component=` confirmed present across all 7
consumer run files plus the behaviour resolver; provenance fields asserted by the
four leaf run tests; override/fail-closed behaviour asserted by the new
operational/bom tests; documentation cross-checked for the 575 count and the
read-only / pending-quarantine / deferred-Reference-v2 wording). No defects
found. A fresh qa-agent pass can be re-run when the service recovers.

---

## H. Remaining risks

**Must fix before dashboard implementation**
- None. The contract, validator, lineage enforcement, provenance schema, and
  addendum overrides are in place and tested.

**Should fix during dashboard implementation**
- **Behaviour provenance on the canonical chain** — the live manifests lack the
  new fields (validator warns). Refresh on the next rematerialization so the
  dashboard shows real provenance instead of a warning.
- **Forensic addendum for `remat`** — the operational/BOM forensic addenda are
  not present for the canonical chain and the base `forensic_manifest.json` run
  is not run-versioning-compliant. Regenerating requires a compliant forensic run
  (and the new `--anomaly-run`/`--forensic-run` overrides).

**Can defer**
- A legacy fixed-path behaviour artifact exists at
  `data/intelligence/behaviour/behaviour_fit_manifest.json` (outside `runs/`); the
  validator warns. Remove or archive it when convenient.
- Approved Reference v2 and a true PCA/Mahalanobis rescoring remain explicitly
  deferred and human-gated (unchanged by this sprint).

---

## I. Recommended next action

```
Implement the read-only Technical Validation Dashboard MVP over the canonical rematerialized run.
```
