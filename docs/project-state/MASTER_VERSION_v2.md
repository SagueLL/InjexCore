# InjexCore — MASTER_VERSION_v2

## 1. Version Metadata

| Field | Value |
|---|---|
| Version | `v2.0.0` |
| Date | `2026-06-02` |
| Scope label | Intelligence Layer — Iteration A (Behaviour Intelligence) + package restructure |
| Snapshot author | `master-version-agent` |
| Previous snapshot | [MASTER_VERSION_v1.md](MASTER_VERSION_v1.md) — preprocessing layer baseline (`2026-05-29`) |
| Baseline status | This document diffs against v1; the next `MASTER_VERSION_v3` diffs against this one. |
| Source-of-truth documents (not replaced) | [CLAUDE.md](../../CLAUDE.md), [docs/README.md](../README.md), [docs/intelligence/behaviour_intelligence.md](../intelligence/behaviour_intelligence.md), [docs/pipeline/data_cleaning.md](../pipeline/data_cleaning.md), [docs/pipeline/time_series_engineering.md](../pipeline/time_series_engineering.md), [docs/pipeline/feature_engineering.md](../pipeline/feature_engineering.md), [docs/pipeline/specialized_datasets.md](../pipeline/specialized_datasets.md) |

This snapshot consolidates — it does not rewrite. Where this document
makes a claim, the underlying reference doc remains authoritative. v1
remains the immutable preprocessing-baseline record and is not edited.

---

## 2. Executive Summary

- **InjexCore** is a predictive-maintenance system for plastic injection moulding machines that classifies each production cycle as `normal` / `warning` / `anomaly` (see [CLAUDE.md](../../CLAUDE.md)).
- **Since v1, the project crossed its first architectural boundary.** The preprocessing layer is unchanged in capability but was promoted into a named `src/preprocessing/` package, and a brand-new top-level layer — `src/intelligence/` — landed with its first working component.
- **Behaviour Intelligence (Iteration A) is the headline of v2.** It is the first stage past preprocessing: it characterises what *normal* machine behaviour looks like, per operational profile, fitted **leakage-safe** on a 70% training window. It is *descriptive*, not *predictive* — it fits baseline tables, never scorers.
- **The three-layer boundary is now real in code**: `src/preprocessing/` (parameter-free feature engineering) → `src/intelligence/` (fits DESCRIPTIVE artifacts: operational profiles + statistical baselines of normal) → `src/models/` (still planned; PREDICTIVE estimators that score deviation).
- **The package was restructured** for that boundary: `src/data/` → `src/preprocessing/`; `src/data_generation.py` → `src/data_generation/generate.py`; the `src/preprocessing.py` shim became `src/preprocessing/__main__.py`; tests moved to `tests/unit/preprocessing/`.
- **Quality gates are green.** `ruff` (lint + format), `mypy` over 68 files in `src/` (now with the pydantic plugin enabled), and **165 passing tests** (29 new for behaviour). No fitted predictive model exists yet — by design.
- **The next chapter is Iteration B** (Correlation Intelligence + per-profile PCA) inside `src/intelligence/behaviour/`, followed by the predictive `src/models/` layer that consumes the behaviour fit manifest.

---

## 3. What Changed Since v1 (v1 → v2 diff)

This is the primary lens of this snapshot. v1's scope label was "data
preprocessing layer — first complete version." v2 keeps all of that intact
and adds a layer on top of it.

| Area | v1 (baseline) | v2 (now) |
|---|---|---|
| Top-level layers | `src/data/` (preprocessing) only | `src/preprocessing/` + **new `src/intelligence/`** |
| Preprocessing package | `src/data/{cleaning,time_series,feature_engineering,datasets}` | renamed → `src/preprocessing/{...}`; `_common` kept **nested** at `src/preprocessing/_common/` |
| Data generation | flat `src/data_generation.py` | package `src/data_generation/generate.py` |
| Orchestration shim | `src/preprocessing.py` (`--stage` dispatcher) | promoted to `src/preprocessing/__main__.py` (same `--stage` semantics) |
| Intelligence Layer | none (planned as `src/models/anomaly/`) | **Behaviour Intelligence Iteration A shipped** under `src/intelligence/behaviour/` |
| Intelligence dispatcher | none | new `src/intelligence/__main__.py` (`python -m src.intelligence`) |
| Central paths | `RAW/PROCESSED/FEATURES/DATASETS` + `CONFIGS_DIR` | **adds `INTELLIGENCE_DIR`** in `src/config.py` |
| Configs | 4 stage YAMLs | **adds `configs/behaviour_intelligence.yaml`** (5 total) |
| Tests | 136 under `tests/unit/data/` | **165** under `tests/unit/{preprocessing,intelligence}/` (+29 behaviour) |
| Tooling | `ruff`, `mypy` (lenient), pre-commit, CI all wired | same, **plus pydantic mypy plugin enabled**; mypy now green over 68 `src/` files |

What did **not** change: the four preprocessing stages' contracts, the
semantic-driven routing, the strict pydantic policies, the uniform `Finding`
audit record, the master/specialized dataset shapes. The v1 data flow is
preserved verbatim; v2 is purely additive on top of it plus a rename.

---

## 4. Architecture State

The production pipeline is still a strictly linear chain. v2 makes the
post-preprocessing boundary explicit by introducing a second named layer.

```
src/data_generation/generate.py
  → src/preprocessing/cleaning/
    → src/preprocessing/time_series/
      → src/preprocessing/feature_engineering/
        → src/preprocessing/datasets/                    (master + specialized parquet)
          → src/intelligence/behaviour/                  ← NEW: fits DESCRIPTIVE artifacts
            → [src/models/ pending: PREDICTIVE scorers]
```

### 4.1 The three-layer boundary (codified in v2)

| Layer | Package | Responsibility | Fits? |
|---|---|---|---|
| Preprocessing | `src/preprocessing/` | Cleans + engineers features | No — parameter-free |
| **Intelligence** | `src/intelligence/` | Characterises *normal* behaviour (profiles + baselines) | **Yes — DESCRIPTIVE artifacts only** |
| Models (planned) | `src/models/` | Scores deviation from normal | Yes — PREDICTIVE estimators |

Behaviour Intelligence sits between preprocessing and models: it fits
baseline tables and a reproducible **fit manifest** that the future
modelling stage will consume. `src/preprocessing/` stays parameter-free;
`src/models/` stays reserved for the anomaly/forecasting scorers.

### 4.2 Per-package file convention (carried forward)

The 9-file pattern from v1 is unchanged and was extended to the new layer.
Every preprocessing package under `src/preprocessing/<stage>/` keeps
`__init__.py`, `io.py`, `policy.py`, `column_groups.py`, `reporting.py`, its
stage-specific modules, and `run_<stage>.py`. The behaviour component
mirrors it: `io.py`, `policy.py`, `column_groups.py` (shim →
`src/preprocessing/_common`), `reporting.py` (shim → `_common`),
`profiles.py`, `baselines.py`, `validation.py`, `run_behaviour.py`.

The orchestration shim `src/preprocessing/__main__.py` still dispatches
`--stage cleaning|ts|fe|features|datasets|all`. The Intelligence Layer is
**deliberately not** in that dispatcher (different output contract); it has
its own dispatcher `src/intelligence/__main__.py`.

---

## 5. Data Flow

The preprocessing data flow is unchanged from v1. v2 adds the behaviour
artifact family downstream of the master dataset.

| Artefact | Path | Shape / form |
|---|---|---|
| Raw vendor data | `data/raw/Dades_pellet.csv` | input |
| Cleaned | `data/processed/Dades_pellet_clean.csv` | cleaned schema |
| Time-series engineered | `data/features/Dades_pellet_features.parquet` | ~323 cols |
| Feature engineered | `data/features/Dades_pellet_engineered.parquet` | 167,331 × 566 |
| **Master (canonical)** | `data/datasets/master/master_dataset.parquet` | 167,331 × 566 |
| Specialized — anomaly detection | `data/datasets/specialized/anomaly_detection_dataset.parquet` | 239 cols |
| Specialized — forecasting | `data/datasets/specialized/forecasting_dataset.parquet` | 294 cols |
| Specialized — energy | `data/datasets/specialized/energy_dataset.parquet` | 46 cols |
| **NEW — profile labels** | `data/intelligence/behaviour/profiles/profile_labels.parquet` | per-row regime + `is_train` + `material_change_candidate` |
| **NEW — baselines** | `data/intelligence/behaviour/baselines/baselines.parquet` | long-form per-`(profile, sensor)` stats |
| **NEW — validation** | `data/intelligence/behaviour/validation/{distribution,durations,transitions}.parquet` | profile-quality diagnostics |
| **NEW — fit manifest** | `data/intelligence/behaviour/behaviour_fit_manifest.json` | reproducible fit contract (train bounds, quantile edges, sensors, timestamp) |
| Per-stage audit reports | `data/features/*_report.{json,md}`, `data/datasets/**/*_report.{json,md}`, `data/intelligence/behaviour/behaviour_intelligence_report.{json,md}` | one `Finding` report pair per stage / component |

Preprocessing shapes are carried forward from the v1 snapshot (medium
confidence — not independently re-counted in this pass). The behaviour
artifacts are git-ignored like all of `data/`; their schema is verified
against `src/intelligence/behaviour/io.py`, not row-counted here. The master
dataset is **not** modified by the behaviour stage — it is independently
rerunnable.

---

## 6. Active Systems

- **Preprocessing layer** (`src/preprocessing/`) — unchanged in behaviour, renamed from `src/data/`:
  - [src/preprocessing/cleaning/](../../src/preprocessing/cleaning/) — 6 detect+remediate modules.
  - [src/preprocessing/time_series/](../../src/preprocessing/time_series/) — 6-stage temporal pipeline.
  - [src/preprocessing/feature_engineering/](../../src/preprocessing/feature_engineering/) — 6-family derived-feature pipeline.
  - [src/preprocessing/datasets/](../../src/preprocessing/datasets/) — master validation + 3 projections.
  - [src/preprocessing/_common/](../../src/preprocessing/_common/) — neutral shared contracts (`Finding`, `Severity`, `StrictModel`, `ColumnGroups`, writers), kept **nested** under preprocessing.
- **Intelligence Layer** (`src/intelligence/`) — NEW in v2:
  - [src/intelligence/behaviour/](../../src/intelligence/behaviour/) — Behaviour Intelligence Iteration A: `profiles.py` (operational-regime segmentation), `baselines.py` (per-profile stats, train-only), `validation.py` (profile-quality diagnostics), `run_behaviour.py` (CLI).
  - [src/intelligence/__main__.py](../../src/intelligence/__main__.py) — component dispatcher (`python -m src.intelligence`, default `behaviour`).
- **Data generation** — [src/data_generation/generate.py](../../src/data_generation/generate.py): 2,000 synthetic cycles, drift + 3% anomaly injection (MVP scaffolding).
- **Orchestration shims**:
  - [src/preprocessing/__main__.py](../../src/preprocessing/__main__.py) — `--stage cleaning|ts|fe|features|datasets|all`.
  - [src/intelligence/__main__.py](../../src/intelligence/__main__.py) — `--component behaviour`.
- **Configuration** — five pydantic-validated YAML policies, all `extra="forbid"`:
  - [configs/cleaning.yaml](../../configs/cleaning.yaml), [configs/time_series.yaml](../../configs/time_series.yaml), [configs/feature_engineering.yaml](../../configs/feature_engineering.yaml), [configs/specialized_datasets.yaml](../../configs/specialized_datasets.yaml)
  - **NEW** [configs/behaviour_intelligence.yaml](../../configs/behaviour_intelligence.yaml) — sections `sensors`, `fit_window`, `profiles`, `baselines`.
  - Tracked schema-lock contract: [configs/schema_lock.json](../../configs/schema_lock.json).
- **Central paths** — [src/config.py](../../src/config.py): `PROJECT_ROOT`, `RAW/PROCESSED/FEATURES/DATASETS_DIR`, **new `INTELLIGENCE_DIR`**, `CONFIGS_DIR`.
- **Semantic dictionary** — one CSV drives column routing across stages: `data/features/variable_classification.csv` (the behaviour stage selects its ~17 `process_sensor` columns through it).
- **Test suite** — **165 unit tests** under `tests/unit/preprocessing/{cleaning,time_series,feature_engineering,datasets}/` and `tests/unit/intelligence/behaviour/` (29 new). Run with `pytest`.
- **Reference docs** — the four pipeline docs plus **new** [docs/intelligence/behaviour_intelligence.md](../intelligence/behaviour_intelligence.md). Documentation tree reorganized by purpose: `pipeline/`, `intelligence/`, `project-state/`, `proposals/` (see [docs/README.md](../README.md)).
- **Still placeholders (not yet implemented)**: `src/models/` (predictive scorers), output API, visualization dashboard.

---

## 7. Agent & Skill Ecosystem

The project-local Claude Code tooling under [.claude/agents/](../../.claude/agents/)
and `.claude/skills/` remains the delivery substrate. Per
[CLAUDE.md](../../CLAUDE.md), the ecosystem is **18 agents** and **52 skills**,
auto-discovered via YAML frontmatter. No net change in agent/skill counts
since v1 was observed in this pass.

Agents that materially shaped what ships in v2 (the Intelligence Layer):

- `predictive-maintenance-agent` *(Opus)*, `plastics-industry-agent` *(Opus)* — the definition of "normal per operational regime," and the honesty constraint that non-derivable regimes (`cleaning`, `maintenance`, `recipe_change`) are surfaced as findings, not fabricated.
- `anomaly-detection-agent`, `machine-cycle-agent`, `sensor-intelligence-agent` — operational-profile rules (stopped/startup/shutdown/alarm/production tertiles) and the choice to baseline the interpretable ~17 `process_sensor` columns.
- `time-series-agent` — leakage-safe fitting on a time-ordered 70% training window.
- `repository-architecture-agent` — the `src/data/` → `src/preprocessing/` rename and the `src/intelligence/` layer split.
- `code-reviewer-agent`, `qa-agent` — the 29 new behaviour tests and review of the restructure.
- `documentation-architect-agent` — the new `docs/intelligence/` reference doc and docs-tree reorganization.
- `master-version-agent` *(Opus)* — this snapshot.

Skill inventory (52 skills across 15 domains) is not enumerated here; see
[CLAUDE.md](../../CLAUDE.md#skills-52) for the full table. The four
project-state/master-version skills (`generate-project-state-report`,
`consolidate-project-knowledge`, `track-project-evolution`,
`generate-master-version`) produced this document.

---

## 8. Technical Decisions

The non-obvious design calls that define v2 (v1's six decisions still hold —
semantic-driven routing, strict pydantic policies, uniform `Finding`, hybrid
selector, master-is-validation-only, fitted estimators deferred). New in v2:

1. **Layer split: descriptive vs predictive.** A new top-level `src/intelligence/` layer was introduced specifically so that *characterising normal* (fitting baseline tables) is separated from *scoring deviation* (fitting estimators). Behaviour Intelligence fits DESCRIPTIVE artifacts only; nothing with a predictive `fit()` lives here — that stays for `src/models/`.
2. **Leakage-safe fitting.** Production-rate quantile edges and per-profile baseline statistics are fit on a **training window only** (default `fraction`, `train_fraction: 0.7`, time-ordered), then applied to the whole record. The exact train bounds and quantile edges are persisted to `behaviour_fit_manifest.json` so later data is scored consistently. `strategy: all` exists only as an explicit EDA opt-in that disables the guard.
3. **Honesty about non-derivable regimes.** `cleaning`, `maintenance`, and `recipe_change` are **not derivable** from the available signals. Each is surfaced as an `AWARE` `regime_not_derivable` finding rather than guessed. Material/recipe change is offered only as a separate boolean `material_change_candidate` proxy (from `batch_id` / `batch_quality_id` transitions), never a primary label. This is a deliberate refusal to fabricate state.
4. **Profiles derived from real signals.** The derivable regimes (`stopped`, `startup`, `shutdown`, `alarm`, `low`/`mid`/`high_production`) are computed from signals the data actually supports (`n_subsystems_running`, alarm flags, the `granulator_production_rate` KPI), with a configurable precedence ladder resolving overlap among running rows.
5. **`_common` kept nested, not hoisted.** When `src/data/` became `src/preprocessing/`, the neutral shared contracts stayed at `src/preprocessing/_common/` rather than being promoted to a top-level `src/_common/`. The Intelligence Layer consumes them via thin re-export shims (`column_groups.py`, `reporting.py`), so the behaviour report parses with the same reader as the four preprocessing stages — without a premature top-level package.
6. **Behaviour kept out of the `--stage` dispatcher.** It has a different output contract (descriptive artifacts, not a transformed dataset) and sits past the preprocessing chain, so it gets its own `src/intelligence/__main__.py` component dispatcher instead of being bolted onto preprocessing.
7. **Pydantic mypy plugin enabled.** `pyproject.toml` now loads `pydantic.mypy` so constrained policy submodels (`Field(ge=, le=)`, `default_factory=Model`) are not wrongly flagged as needing constructor arguments. mypy is green over the 68 `src/` files under the lenient (pandas-untyped) baseline.

---

## 9. Roadmap Progress

| Milestone | Status as of v2 |
|---|---|
| Synthetic data generation | Done (MVP scaffolding) |
| Preprocessing layer — 4 stages | Done (v1) — carried forward, renamed to `src/preprocessing/` |
| Architecture stabilization (installable package, central paths, `_common`, CI) | Done (v1) |
| **Intelligence Layer — Behaviour Intelligence Iteration A** | **Done (v2)** — profiles + baselines + validation, leakage-safe |
| Intelligence Layer — Iteration B (correlations + PCA) | **Next** — designed to drop in as new modules + config sections |
| Predictive `src/models/` layer (Isolation Forest, LOF, Mahalanobis) | Not started — consumes the behaviour fit manifest |
| Output API (`src/api/`, FastAPI) | Not started |
| Visualization dashboard (`src/visualization/`) | Not started |

### 9.1 Iteration B (immediate next chapter)

Per [docs/intelligence/behaviour_intelligence.md §11](../intelligence/behaviour_intelligence.md),
the `fit(...)` contract, leakage-safe `train_mask`, and fit manifest are
designed so the next techniques drop in without reworking the foundation:

- **Correlation Intelligence** (`correlations.py`) — per-profile correlation matrices and structural-pair rupture detection.
- **PCA Intelligence** (`pca.py`) — per-profile standardised PCA, loadings, explained variance, reconstruction-error / Mahalanobis "strange sample" flagging. Adds `scikit-learn` + `joblib` (the existing `[models]` extra).

These feed — but do not replace — the predictive estimators planned for `src/models/`.

### 9.2 Predictive layer (after Iteration B)

`src/models/` consumes the behaviour fit manifest and the specialized
datasets. Design constraints inherited from v1/v2 that it must honour: the
9-file package convention, pydantic `extra="forbid"` policies, `Finding`-style
JSON+MD audit reports, semantic-driven selection, and reproducibility (pinned
versions, logged seeds, dataset hashes) per `~/.claude/rules/ml-pipeline.md`.

---

## 10. Risks & Open Questions

- **Anomaly thresholds for real-machine data are still pending.** Criteria live in `.claude/CLAUDE.local.md` (git-ignored) and are not yet finalised. Still blocking any supervised evaluation. (Carried from v1.)
- **Non-derivable regimes remain blind spots.** Closing the `cleaning` / `maintenance` / `recipe_change` gaps requires joining an external maintenance / material log that does not yet exist. Until then, baselines cannot represent those states — an honest, documented limitation rather than a silent one.
- **Baselines are unvalidated against ground truth.** "Normal" is derived from the data's own distribution per profile; there is no labelled confirmation that the train-fitted profiles match real machine states. The validation reports check internal coherence (durations, transitions, coverage), not external correctness.
- **Single-source evidence.** All behaviour profiling is derived from one vendor CSV (`Dades_pellet.csv`). Generalisation to multi-source ingestion is still unverified. (Carried from v1.)
- **Synthetic-vs-real divergence.** The MVP generator and the real pellet-extrusion master have different schemas; behaviour profiles are tuned to the real master's signals. The synthetic path is scaffolding and is not exercised by the behaviour stage.
- **Resolved since v1:** lint/type/pre-commit toolchain (now wired), CI (now present), and schema-lock tracking (`configs/schema_lock.json` now committed). These are no longer open risks.

---

## 11. Current Priorities & Recommended Focus

1. **Iteration B — Correlation Intelligence + per-profile PCA.** The foundation (fit manifest, train mask, per-profile labels) exists; this is the lowest-friction next increment and unlocks reconstruction-error anomaly signals.
2. **Begin the predictive `src/models/` layer** once Iteration B lands — Isolation Forest / LOF / Mahalanobis scoring against the behaviour baselines, consuming `data/datasets/specialized/anomaly_detection_dataset.parquet` and the fit manifest.
3. **Finalise real-machine anomaly thresholds** in `.claude/CLAUDE.local.md` — still the gating input for any supervised evaluation.
4. **Plan external-log integration** to close the non-derivable-regime gaps (maintenance / material-change events), upgrading `material_change_candidate` from proxy to fact.
5. **Validate the master/specialized shapes** independently in a future snapshot (medium-confidence carry-over from v1).

---

## 12. Confidence Level

- **High confidence**: the `src/preprocessing/` ↔ `src/intelligence/` layer split, package/file layout, the behaviour component's modules and CLI, `configs/behaviour_intelligence.yaml` sections, `INTELLIGENCE_DIR` in `src/config.py`, the pydantic mypy plugin, and the **29 new behaviour tests / 165 total** count — all verified against the `src/`, `configs/`, and `tests/` trees in this pass.
- **Medium confidence**: master/specialized dataset row/column shapes (carried from the v1 snapshot, not independently re-counted); the 18-agent / 52-skill ecosystem counts (sourced from `CLAUDE.md`, not re-enumerated).
- **Lower confidence / explicit uncertainty**: real-machine anomaly thresholds (private, not visible to this snapshot); external correctness of the derived behaviour profiles (no ground-truth labels available); Iteration B and `src/models/` design specifics (subject to results not yet produced).

---

## 13. References

- Project guidance: [CLAUDE.md](../../CLAUDE.md)
- Documentation index: [docs/README.md](../README.md)
- Intelligence Layer reference: [docs/intelligence/behaviour_intelligence.md](../intelligence/behaviour_intelligence.md)
- Pipeline references: [data_cleaning.md](../pipeline/data_cleaning.md), [time_series_engineering.md](../pipeline/time_series_engineering.md), [feature_engineering.md](../pipeline/feature_engineering.md), [specialized_datasets.md](../pipeline/specialized_datasets.md)
- Behaviour policy: [configs/behaviour_intelligence.yaml](../../configs/behaviour_intelligence.yaml)
- Previous snapshot: [MASTER_VERSION_v1.md](MASTER_VERSION_v1.md)
- Agent ecosystem: [.claude/agents/](../../.claude/agents/)
- Global standards (apply automatically): `~/.claude/CLAUDE.md`, `~/.claude/rules/python.md`, `~/.claude/rules/ml-pipeline.md`, `~/.claude/rules/git.md`

---

*End of MASTER_VERSION_v2. Next snapshot: `MASTER_VERSION_v3` — cut when Iteration B (Correlation + PCA Intelligence) lands, or when the first fitted predictive model lands in `src/models/`.*
