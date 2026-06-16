# Post-Iteration-C Hardening Sprint — Report

**Repository:** InjexCore  ·  **Branch:** `refactor/v1-architecture-stabilization`
**Scope:** targeted fixes from the independent Codex architecture & logic review
(*"needs refactor before proceeding → perform targeted fixes first"*). No new
product features; no dashboards, Reference v2, automatic retraining, or new
anomaly models.

---

## A. Executive summary

All eight urgent Codex findings were addressed. Behaviour Intelligence is now
run-versioned and manifest-last with a side-effect-free `--no-write`; run
resolution validates manifest *content* (not mere presence) and run creation is
collision-safe; controlled-scoring suppression requires row-level evidence;
cross-component lineage fails closed; `reference_v1` is seeded from Behaviour
provenance; the quarantine-target identity is derived from proposal records (no
hardcoded sensor); and incident `possibly_explains` is gated on shared sensors.
README + an authoritative dataflow/contracts doc were added.

Quality gates after the fixes: **pytest 551 passed / 0 failed**, **ruff check +
format clean**, **mypy clean (184 files)**. Real-data validation: behaviour
`--no-write` is provably side-effect-free; a behaviour write produces a
run-versioned run with a complete manifest and does not overwrite the legacy
fixed-path artifacts; the reference dry-run consumes the chain and reproduces
the documented outcome; the scoring dry-run **correctly fails closed** against a
pre-hardening anomaly run that lacks the new completion marker.

Verdict: **urgent findings addressed; ready for a second targeted review.**

---

## B. Fix matrix

### ARC-01 — Behaviour run-versioning + manifest-last + true `--no-write`
- **Status:** fixed.
- **Files:** `src/intelligence/behaviour/io.py`, `src/intelligence/behaviour/run_behaviour.py`, `src/intelligence/_common/upstream.py`, `src/intelligence/reference/io.py`; configs `drift_intelligence.yaml`, `operational_context.yaml`, `reference_governance.yaml`; consumers `drift/{policy,run_drift}.py`, `context/operational/{policy,run_operational_context}.py`.
- **What:** Behaviour writes to `data/intelligence/behaviour/runs/<run_id>/` via `create_run_dir`; artifacts first, then the manifest **last**; the manifest now records `component/run_id/completion_status/created_at/master_dataset_path/master_dataset_sha256/train_window/validation_window/row_count/profile_count/generated_files`. `--no-write` returns before any write (no files/dirs/manifests/mtimes). Downstream resolves the **latest completed** behaviour run via `resolve_behaviour_run` (clean cutover; `DEFAULT_*` are `None` sentinels meaning "resolve latest").
- **Why:** brings Behaviour under the same run-versioned, manifest-last contract as every other component and stops `--no-write` leaking artifacts; the manifest now carries the provenance GOV-01 needs.
- **Tests:** `tests/unit/intelligence/behaviour/test_run_behaviour.py` (side-effect-free `--no-write` with tree snapshot; run-versioned layout; manifest-last; latest resolution; `--run-id` collision).
- **Remaining limitation:** old fixed-path artifacts remain on disk as inert legacy (never read, never overwritten).

### ARC-02 — Safe run creation + validated completed-run resolution
- **Status:** fixed.
- **Files:** `src/intelligence/_common/runs.py`, `src/intelligence/_common/manifest.py`; all 10 run-versioned `main()`s wired to `create_run_dir`; the three base-manifest components (anomaly/pca/correlation) now emit `completion_status` via `base_manifest`.
- **What:** `create_run_dir` does an atomic `mkdir(exist_ok=False)` → `RunCollisionError` on any existing id (auto **or** explicit `--run-id`), before any write. `resolve_run`/`list_completed_runs` accept a run only if its manifest parses, carries `component/run_id/completion_status`, reports `completion_status == "complete"`, names a `run_id` equal to its directory, and (optionally) matches the expected component.
- **Why:** an explicit `--run-id` could previously overwrite a completed run, and resolution trusted manifest presence alone (a crashed/half-written run could be picked up as `latest`).
- **Tests:** `tests/unit/intelligence/_common/test_runs.py` (collision rejection; malformed/pending/missing-status/wrong-run-id/wrong-component ignored; valid accepted).
- **Remaining limitation:** none.

### LOG-01 — Controlled-Scoring row-level suppression requires evidence
- **Status:** fixed.
- **Files:** `src/intelligence/scoring_experiment/{scoring,comparison,reporting,decision_report,scenarios,policy,run_scoring_experiment}.py`.
- **What:** the explained-burst path no longer suppresses every non-normal row in the window. Incident-level coverage (`incident_explained_for_review` / `incident_level_explanation_match`) is kept **separate** from row-level suppression (`row_suppressed_for_review`), which requires the row's own evidence (`row_level_evidence_match`: the sensor appears in the row's anomaly `affected_variables`). New schema columns added; consumers + manifest updated.
- **Why:** an unrelated process anomaly inside a long explained-burst window was being hidden.
- **Tests:** `tests/unit/intelligence/scoring_experiment/test_suppression_and_targets.py` (a long faulty-sensor incident; most rows suppressed; one unrelated anomaly in the window stays unsuppressed yet incident-explained).
- **Remaining limitation:** per-row faulty-sensor *context* is window-wide during a fault, so it only *strengthens* an affected-variable match (using it alone would re-introduce over-suppression) — documented in code + docs.

### DAT-01 — Strict transitive lineage (fail closed)
- **Status:** fixed.
- **Files:** new `src/intelligence/_common/lineage.py`; `drift/validation.py`, `incidents/validation.py`, `scoring_experiment/validation.py` (reference already blocked, extended in GOV-01).
- **What:** semantic lineage mismatches are now **blockers**, not warnings: drift blocks on a fingerprint/master-sha/sensor-health-pin mismatch; incidents blocks on a drift-pin divergence; scoring blocks unless the reference run was built from the same sensor-health/drift/incidents chain. Shared assert helpers raise each component's `*BlockerError`.
- **Why:** components previously proceeded with warnings over an incompatible upstream chain.
- **Tests:** `tests/unit/intelligence/_common/test_lineage.py`; fail-closed tests in drift/incidents/scoring; coherent synthetic worlds updated.
- **Remaining limitation:** leaf components (anomaly/pca/correlation) do not yet *re-verify* the whole chain themselves — the behaviour manifest they consume self-reports its run-id/sha, and the four named components fail closed.

### GOV-01 — `reference_v1` provenance from Behaviour
- **Status:** fixed.
- **Files:** `src/intelligence/reference/{registry,validation,run_reference,policy,io}.py`; `configs/reference_governance.yaml`.
- **What:** Reference Governance resolves the latest completed behaviour run and seeds `reference_v1.dataset_sha256` from the behaviour manifest's `master_dataset_sha256` (+ train window, run id). Gate A fails closed if that sha is missing or differs from the current master. The current master sha is never substituted as a fallback.
- **Why:** the baseline could be stamped with the current master sha even if Behaviour was fit on a different file.
- **Tests:** `tests/unit/intelligence/reference/test_reference.py` (uses behaviour sha; missing provenance blocks; behaviour-vs-master mismatch blocks; records `behaviour_run_id`).
- **Remaining limitation:** none.

### GOV-02 — Generic quarantine-target identity
- **Status:** fixed.
- **Files:** `src/intelligence/scoring_experiment/{scoring,scenarios,reporting,decision_report,policy}.py`.
- **What:** scenario ids, decision-matrix actions, plant records and summary text are derived from the proposal records — `quarantine_<sensor>_interpretive` / `approve_quarantine_<sensor>` for one target, `quarantine_proposals_interpretive` / `approve_quarantine_proposed_sensors` for several, and a coherent no-proposal path. No hardcoded `inlet_hopper_points` remains in scoring/decision logic.
- **Why:** the experiment + decision report hardcoded `inlet_hopper_points`, producing wrong wording for any other target.
- **Tests:** `test_suppression_and_targets.py` (different sensor; multiple sensors; no proposal; decision report names the actual sensor; no inlet text when the target differs).
- **Remaining limitation:** forensic-addendum narratives in `incidents/` and `context/` still describe the actual confirmed real event by name — left intentionally (descriptive of a real finding, outside the GOV-02 scope).

### INC-01 — Incident relationship evidence accuracy
- **Status:** fixed.
- **Files:** `src/intelligence/incidents/relationships.py`.
- **What:** `possibly_explains` is emitted only when the incidents **share** at least one sensor (Option A); the `0.1`-no-shared-sensors confidence fallback is removed and the evidence lists the actual shared sensors. Temporal-only pairs are still represented by the base `contains`/`overlaps` row (empty evidence).
- **Why:** `possibly_explains` could fire on interval overlap with no shared sensors while its evidence falsely claimed shared sensors.
- **Tests:** `tests/unit/intelligence/incidents/test_grouping_relationships.py` (overlap without shared sensors → no `possibly_explains`; with shared sensors → emitted with sensors in evidence).
- **Remaining limitation:** none.

### DOC-01 — Documentation
- **Status:** fixed.
- **Files:** `README.md`, new `docs/architecture/intelligence_dataflow.md`, `docs/README.md`, `CLAUDE.md`, and terminology/semantics updates in `docs/intelligence/{controlled_scoring_experiment,reference_governance,incident_aggregation}.md`.
- **What:** README now describes the full architecture (Data Foundation → Intelligence → Context → review/governance → decision); a new authoritative dataflow + contracts doc; doc terminology updated for LOG-01 columns, GOV-01 provenance, INC-01 evidence and the GOV-02 derived id; interpretive-vs-true-rescoring wording verified.
- **Tests:** n/a (docs).
- **Remaining limitation:** older `docs/project-state/` snapshots are point-in-time and intentionally unchanged.

---

## C. Behaviour migration report

| Aspect | Detail |
|---|---|
| **Old output pattern** | Fixed paths: `behaviour/profiles/profile_labels.parquet`, `behaviour/baselines/baselines.parquet`, `behaviour/validation/*.parquet`, `behaviour/behaviour_fit_manifest.json` (manifest written **before** validation tables). |
| **New output pattern** | `behaviour/runs/<run_id>/{profiles,baselines,validation}/…` + reports + `behaviour_fit_manifest.json` written **last**; the manifest records `component/run_id/completion_status/master_dataset_sha256/train_window/validation_window/row_count/profile_count`. |
| **Compatibility strategy** | Clean cutover. Downstream resolves the latest *completed* behaviour run via `resolve_behaviour_run`; `upstream.DEFAULT_*` are `None` sentinels → loaders resolve latest. Drift/operational/reference configs switched to empty path / `behaviour_root` (resolve latest). Old fixed-path files remain as inert legacy. |
| **No-write validation** | Gate C: tree snapshot before/after `--no-write` on the real 167,331×566 master — **0 file changes, no `runs/` directory created**. |
| **Manifest-last validation** | Gate D: a write run produced `runs/<run_id>/` with the manifest present and `completion_status == "complete"`; a crashed-run test confirms a missing manifest is not resolvable. |
| **Downstream compatibility changes** | `_common/upstream.py` (loaders + `resolve_behaviour_run`); reference `io/policy/run_reference`; drift & operational policies/run code + their YAMLs; integration tests updated to the new CLI. |

---

## D. Run immutability report

- **Collision prevention:** `create_run_dir` performs an atomic `mkdir(exist_ok=False)`; an existing run directory (auto id or explicit `--run-id`) raises `RunCollisionError` before any artifact is written. Verified live (Gate D `--run-id dup` collision in unit tests).
- **Atomic directory creation:** `mkdir(parents=True, exist_ok=False)` — no merge, no reuse, no overwrite.
- **Manifest validation rules:** parseable JSON dict; required fields `component/run_id/completion_status`; `completion_status == "complete"`; `run_id` equals the directory name; expected-component match when supplied.
- **Latest-completed resolution:** `list_completed_runs` returns only run ids whose manifest validates; `resolve_run("latest")` returns the greatest such id; malformed/pending/wrong-id/wrong-component manifests are ignored.
- **Tests proving behavior:** `tests/unit/intelligence/_common/test_runs.py` (17 cases).

---

## E. Controlled Scoring correction report

- **Old suppression behavior:** a non-normal row inside a suppressed-duplicate burst window was suppressed unconditionally (`hit = nonnormal & in_window`).
- **New suppression behavior:** burst-window rows are recorded as `incident_explained_for_review`, but `row_suppressed_for_review` is set only when the row carries its own evidence (`row_level_evidence_match`: the explaining/quarantine sensor appears in the row's anomaly `affected_variables`; the pending-target path additionally requires faulty/quarantined context inside the window).
- **Row-level evidence requirements:** affected-variable dominance is the row-discriminating signal; window-wide faulty context only strengthens it.
- **Incident-level vs row-level separation:** explicit columns — `incident_explained_for_review` / `incident_level_explanation_match` (coverage) vs `row_suppressed_for_review` / `row_level_evidence_match` (action).
- **Expected impact on previous scenario counts if rerun:** the previously reported ~91% / 30,096-of-33,186 suppression was incident-window-based and is an **upper bound**. With the row-level gate, suppression can only *decrease or stay equal*: rows whose anomaly evidence does not name the faulty sensor remain in the review backlog. Direction only — **no real-data scoring rerun was performed** (the legacy anomaly run is not lineage-resolvable under the hardened contract; see §F). Re-running the chain is the documented next step to quantify the corrected counts.

---

## F. Lineage validation report

- **Components hardened:** Drift, Incidents, Reference, Controlled Scoring (shared `_common/lineage.py`).
- **Lineage fields verified:** `master_dataset_sha256` (sensor-health/operational/reference/behaviour); projection-invariant `dataset_fingerprint` (anomaly/pca/correlation); pinned run ids (operational→sensor-health for drift; drift→{sensor-health,anomaly,operational} for incidents; reference→{sensor-health,drift,incidents} for scoring); behaviour provenance (run-id + sha) for reference.
- **Failure modes now blocked:** upstream fitted on a different master; projected-fingerprint mismatch; a consumed run pinning a different sub-run than resolved; a reference run built from a different chain; missing behaviour provenance.
- **Tests proving mismatches fail closed:** drift fingerprint + master-sha blockers; incidents drift-pin blocker; scoring reference-chain blocker; `test_lineage.py` unit cases.
- **Real-data observation (Gate E):** the scoring dry-run **failed closed** at a pre-hardening anomaly run that lacks the completion marker — the contract working as designed.

---

## G. Reference provenance report

- **How `reference_v1` obtains Behaviour provenance:** Reference Governance resolves the latest completed behaviour run and reads its manifest; `reference_v1.dataset_sha256 = behaviour_manifest["master_dataset_sha256"]`; the run records `behaviour_run_id`.
- **If Behaviour provenance is missing:** Gate A raises `ReferenceBlockerError` ("no master_dataset_sha256 — cannot establish reference_v1 provenance").
- **If the sha mismatches:** Gate A raises `ReferenceBlockerError` ("Behaviour baseline was fitted on a different master …"); the current master sha is never substituted.
- **Verified live (Gate E):** reference `--no-write` resolved the fresh behaviour run + the existing chain and reproduced the documented outcome (1 reference, 1 quarantine proposal, 3 candidates, `residual_material=False`).

---

## H. Generic quarantine-target report

- **Scenario ids derived:** `quarantine_<sanitized_sensor>_interpretive` (one), `quarantine_proposals_interpretive` (several), none → no quarantine scenario. `sanitize_sensor` makes any sensor name identifier-safe.
- **Decision text generated:** decision-matrix action `approve_quarantine_<sensor>` / `approve_quarantine_proposed_sensors`; plant records, summary step 1 and the recommendation rationale all reference the actual proposed sensor(s).
- **Multi-sensor handling:** a single `quarantine_proposals_interpretive` scenario + `approve_quarantine_proposed_sensors`, with the sensor list surfaced.
- **No-proposal handling:** no quarantine scenario row; a coherent "No pending quarantine proposal" summary; the `approve_quarantine` matrix row is `recommended=False`.
- **Tests proving no hardcoded inlet sensor remains:** `test_suppression_and_targets.py` asserts a different/multiple/no target produces correct wording and **no inlet text**; a repo grep confirms the only remaining `inlet_hopper_points` in scoring is absent (the unused vocabulary constant was genericized).

---

## I. Documentation update summary

- **README:** rewritten Architecture, Project Structure and Status to the full current system; fixed the stale data-generation command and the "models not started" claim.
- **New architecture/dataflow doc:** `docs/architecture/intelligence_dataflow.md` — end-to-end dataflow, package boundaries, artifact locations, run-versioning + manifest-last + lineage contracts, original-vs-interpretive scores, the no-auto-quarantine/refit/exclusion policy, limitations, and where dashboards / Reference v2 fit later.
- **Terminology:** component docs updated for the LOG-01 columns, GOV-01 provenance, INC-01 evidence and the GOV-02 derived id; "controlled rescoring" left only where correctly future/after-approval; healthy-only consistently labeled a proxy.
- **CLAUDE.md:** behaviour command block (run-versioned, manifest-last, true `--no-write`); test count 517 → 551; dataflow doc linked.
- **Remaining docs debt:** older `project-state/` snapshots are intentionally point-in-time; component docs could later gain explicit run-versioning sections.

---

## J. QA results

| Gate | Command | Result |
|---|---|---|
| A (pre-fix baseline) | `pytest` / `ruff check` / `ruff format --check` / `mypy src` | pytest exit 0 (517 tests); ruff clean; format clean (314 files); mypy clean (183 files). |
| B / G (post-fix) | same four | **pytest 551 passed / 0 failed / 0 errors / 0 skipped**; ruff clean; format clean (317 files); mypy clean (184 files). |
| C (behaviour no-write) | `python -m src.intelligence --component behaviour --no-write` | Side-effect-free: 0 file changes on a seeded tree; no `runs/` created. |
| D (behaviour write) | `python -m src.intelligence --component behaviour` | Run-versioned `runs/<run_id>/`; manifest last with full provenance; legacy fixed-path artifacts byte-identical (not overwritten); latest-completed resolution + loaders verified. |
| E (downstream dry-run) | `reference --no-write`, `scoring-experiment --no-write` | reference: **PASS** (reproduced the documented outcome). scoring: **fails closed** at the pre-hardening anomaly run (no completion marker) — correct ARC-02 behavior. |
| G (qa-agent) | qa-agent validation pass | **OVERALL PASS** — 8/8 findings independently verified at source level; full gate green (551 passed, ruff clean, format clean, mypy clean). |

---

## K. Remaining risks

**Must fix before a dashboard / Reference v2:**
- Regenerate the real-data chain (behaviour → correlation/pca → anomaly → sensor-health → drift → incidents → reference → scoring) under the hardened code so anomaly/pca runs carry completion markers and the full chain is lineage-coherent end-to-end. Only then are corrected real-data scoring counts available.

**Should fix soon:**
- Record `behaviour_run_id` in the leaf intelligence manifests (anomaly/pca/correlation/sensor-health) so the *whole* chain's behaviour coherence is independently verifiable, not only the four DAT-01 components.
- Generalize the forensic-addendum narratives (incidents/context) to derive the sensor name from records, matching GOV-02.

**Can defer:**
- A transitional reader for the legacy fixed-path behaviour artifacts (currently inert; not needed once the chain is regenerated).
- Per-component doc sections documenting run-versioning explicitly.

---

## Minimum corrected rerun chain (for reference)

```
behaviour → (correlation, pca) → anomaly → sensor_health → drift → incidents → reference → scoring-experiment
```

Each step consumes the previous via `--component <name>` (or the component CLI),
resolving `latest` completed runs. The hardened lineage checks will fail closed
if any step is stale — by design.
