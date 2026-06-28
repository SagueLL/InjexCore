# Dashboard Data Contract (v1)

First official consumption contract for the **Technical Validation Dashboard**.
The dashboard is **read-only, lineage-validated, and decision-support only**. It
visualizes the persisted Intelligence/Context artifacts of the canonical
rematerialized chain; it never writes, refits, approves, or mutates anything.

This document is the **narrative** half of the contract. Its **executable** half
is [`src/dashboard/`](../../src/dashboard/) — `validate_dashboard_chain(run_id,
bom_run_id)` ([lineage.py](../../src/dashboard/lineage.py)) returns a
`DashboardChainValidation` (`is_valid`, `severity`, `warnings`,
`component_statuses`, `lineage_edges`, `canonical_match`) that a run selector
must consult before presenting any run.

---

## 5.1 Canonical run

```
canonical_run_id = remat-v1-20260616T102558Z
bom_run_id        = 20260612T124909Z
```

Pinned in [`src/dashboard/contract.py`](../../src/dashboard/contract.py) as
`CANONICAL_RUN_ID` / `CANONICAL_BOM_RUN_ID`. All Intelligence components **and**
the Operational Context overlay live at `remat-v1-20260616T102558Z`; the BOM
context lives at `20260612T124909Z`.

**Run-selector rule.** Only the canonical, lineage-valid chain (`is_valid and
canonical_match`) may be shown as **valid**. Any other completed run is shown
only as **stale / non-canonical** with explicit warnings, or hidden. For the MVP
the dashboard **pins** the canonical run rather than offering a broad dropdown.

---

## 5.2 Allowed artifact groups

Each group is a run-versioned directory `…/runs/<run_id>/`. Read-only. For each:
**purpose / safe fields / unsafe-or-misleading fields / required warning.**

### `data/intelligence/scoring_experiments/runs/<run_id>/`
- **Purpose:** interpretive review scenarios over persisted scores (baseline,
  quarantine-aware suppression, healthy-only proxy, reference-candidate).
- **Safe:** scenario tables, comparison/recommendation tables, scenario counts.
- **Unsafe/misleading:** treating `adjusted_*`/scenario severity as a *rescored*
  model output. It is **interpretive post-processing**; the original
  `severity`/`combined_score` are never mutated.
- **Required warning:** "Adjusted review severity is interpretive
  post-processing, not model rescoring."

### `data/intelligence/forensics/reference_decision/<run_id>/`
- **Purpose:** the decision report — decision matrix, candidate actions, risk
  assessment, required plant records, summary.
- **Safe:** decision matrix, candidate actions, risk rows, required-records list.
- **Unsafe/misleading:** presenting any action as approved/decided. Every action
  is a **proposal pending human review**.
- **Required warning:** "Quarantine is pending review and not approved. Plant
  records are still required before operational decisions."

### `data/intelligence/incidents/runs/<run_id>/`
- **Purpose:** events → reviewable incidents, relationships, review pack, actions.
- **Safe:** incidents, prioritized review pack, suppressed-duplicate counts.
- **Unsafe/misleading:** reading `relationships` as causal. They are
  **associative** (`causality_status=unknown`). Recommended quarantine actions
  are `approval_required=True, approved=False`.
- **Required warning:** "Incident relationships are associative, not causal."

### `data/intelligence/sensor_health/runs/<run_id>/`
- **Purpose:** per-(timestamp, sensor) instrumentation status, events, quarantine
  recommendations, sensor-quality timeline.
- **Safe:** status timeline, events (`pending_review`), quality timeline.
- **Unsafe/misleading:** presenting quarantine recommendations as applied, or
  implying a sensor was excluded. Nothing is auto-excluded.
- **Required warning:** "Quarantine is pending review and not approved."

### `data/intelligence/drift/runs/<run_id>/`
- **Purpose:** windowed drift vs the behaviour train reference; raw vs
  healthy-only analytical views.
- **Safe:** drift scores/events, raw-view summaries, the labeled `healthy_only`
  comparison.
- **Unsafe/misleading:** reading `healthy_only_proxy` as a true rescoring, or as
  evidence a channel *should* be excluded.
- **Required warning:** "Healthy-only residual drift is a proxy view."

### `data/context/operational/runs/<run_id>/`
- **Purpose:** master-aligned profile + steam + sensor-health + BOM context
  timeline and transitions.
- **Safe:** context timeline, transitions, dimension/coverage summaries.
- **Unsafe/misleading:** treating context columns as model inputs (they are
  analytical only), or reading the BOM overlap columns as resolved.
- **Required warning:** "Contextual/analytical only — never an input to model
  fitting." See **§5.3** on the forensic addendum for `remat`.

### `data/intelligence/anomaly/runs/<run_id>/`
- **Purpose:** per-profile detector scores, combined severity, thresholds.
- **Safe:** `combined_score`, `severity`, per-detector scores, `triggered_detectors`.
- **Unsafe/misleading:** presenting severity as a failure prediction, or editing
  it. These are the **original** scores; the dashboard must not mutate them.
- **Required warning:** "Original anomaly scores are unchanged."

### `data/intelligence/reference/runs/<run_id>/`
- **Purpose:** reference registry + proposals (quarantine / candidate references)
  + decision log.
- **Safe:** registry, proposals (`pending_review`), decision log.
- **Unsafe/misleading:** presenting any proposal as approved or any Reference v2
  as created. All proposals are `approved=False`.
- **Required warning:** "Quarantine is pending review and not approved."

### `data/intelligence/behaviour/runs/<run_id>/`
- **Purpose:** operational-profile labels + per-profile baselines + the fit
  manifest (the leakage contract: `is_train`, train window, master sha).
- **Safe:** profile labels, baselines, train/validation windows, manifest fields.
- **Unsafe/misleading:** consuming the **legacy fixed-path** behaviour artifacts
  (see §5.3). Only the run-versioned run is valid.
- **Required warning:** none beyond the global set; the validator emits a warning
  if a legacy fixed-path artifact is present.

### `data/intelligence/correlation/runs/<run_id>/`
- **Purpose:** per-profile correlation references + shift diagnostics.
- **Safe:** correlation tables, strong/redundant pairs, shift diagnostics.
- **Unsafe/misleading:** reading shift diagnostics as alerts (they are AWARE-only
  findings).
- **Required warning:** none beyond the global set.

### `data/intelligence/pca/runs/<run_id>/`
- **Purpose:** per-profile scaler+PCA models, loadings, T²/Q scores, contributions.
- **Safe:** loadings, explained variance, T²/Q scores, contributions.
- **Unsafe/misleading:** presenting T²/Q as a rescoring on an altered feature
  matrix. A *true* rescoring is explicitly deferred.
- **Required warning:** none beyond the global set.

> **Provenance note (PROV-01 / Decision 1).** The leaf manifests (correlation,
> pca, anomaly, sensor_health) now record explicit behaviour provenance
> (`behaviour_run_id`, `behaviour_manifest_path`, `behaviour_created_at`,
> `behaviour_fit_timestamp`, `behaviour_master_dataset_sha256`). The **current**
> canonical manifests predate this and lack those fields, so
> `validate_dashboard_chain` reports them as a **warning** (the chain stays
> usable). The next rematerialization refreshes the real manifests.

---

## 5.3 Forbidden MVP views

The dashboard MUST NOT surface:

- **Legacy fixed-path Behaviour artifacts** (e.g.
  `data/intelligence/behaviour/behaviour_fit_manifest.json` outside `runs/`) —
  only the run-versioned behaviour run is valid. The validator warns when a
  legacy artifact is present on disk.
- **Old non-canonical runs without a lineage warning** — any run other than the
  canonical chain is stale/non-canonical and must carry the warning.
- **The Operational-Context forensic addendum for `remat`** unless it has been
  regenerated against the canonical chain. It is **not** present for the
  canonical run today; regenerate it with `--anomaly-run`/`--forensic-run`
  (CTX-01) before surfacing it. (The base `forensic_manifest.json` run is not a
  run-versioning-compliant run; see *Remaining limitations*.)
- **Reference v2 controls** — there is no approved Reference v2.
- **Quarantine approval controls** — quarantine stays `approved=False`.
- **Model refit / retraining controls.**
- **Automatic sensor exclusion.**
- **Plant-record claims** — the dashboard does not assert plant records exist.
- **Causal explanations** — relationships are associative only.

---

## 5.4 Required warnings (exact copy)

```
This dashboard is read-only and intended for technical validation.
Original anomaly scores are unchanged.
Adjusted review severity is interpretive post-processing, not model rescoring.
Quarantine is pending review and not approved.
Healthy-only residual drift is a proxy view.
Incident relationships are associative, not causal.
Plant records are still required before operational decisions.
```

---

## 5.5 Dashboard boundaries

```
no write actions
no approval actions
no quarantine application
no Reference v2 creation
no model refit
no retraining
no production alerting
```

---

## Remaining limitations

- **Forensic addendum runs.** The base forensic run consumed by the
  operational/BOM addenda is written by a one-off analysis script
  (`scripts/analysis/forensic_sep_oct.py`) whose `forensic_manifest.json`
  declares `component: "forensics"` but omits the `run_id`/`completion_status`
  fields the run-versioning contract requires. It is therefore **not resolvable**
  by `resolve_run`, and the addendum resolvers intentionally **do not** apply an
  `expected_component` check to it. Regenerating the operational/BOM forensic
  addenda against the canonical chain requires a forensic run that satisfies the
  manifest contract — out of scope for this sprint, flagged for the next
  rematerialization.
- **Behaviour provenance** on the current canonical leaf manifests is absent (see
  §5.2 provenance note); the validator degrades to a warning until the next
  rematerialization refreshes them.

The system is ready for **technical validation dashboard planning, not
production deployment**.
