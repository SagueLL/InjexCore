# CLAUDE.md

Project-level guidance for Claude Code. Global standards (Python style, ML pipeline rules, Git workflow) are defined in the user-level `~/.claude/CLAUDE.md` and apply automatically — do not repeat them here.

Private context (anomaly criteria, real data schema, client details) lives in `.claude/CLAUDE.local.md`, which is git-ignored.

---

## Project Overview

**InjexCore** is a predictive maintenance system for plastic injection moulding machines. It classifies each production cycle as `normal`, `warning`, or `anomaly` to detect machine degradation before failures occur. The MVP uses synthetic data; real machine data integration is planned for a later phase.

---

## Commands

```bash
# Install (editable package + dev tooling); puts `src` on the import path
pip install -e ".[dev]"
pre-commit install

# Generate synthetic dataset → data/raw/dataset_pro.csv
python -m src.data_generation.generate

# Run the data-cleaning pipeline on data/raw/Dades_pellet.csv
#   → data/processed/Dades_pellet_clean.csv
#   → data/features/cleaning_report.{json,md}
python -m src.preprocessing.cleaning.run_cleaning            # full run
python -m src.preprocessing.cleaning.run_cleaning --no-write # diagnostic only

# Run the time-series engineering pipeline on the cleaned CSV
#   → data/features/Dades_pellet_features.parquet
#   → data/features/ts_engineering_report.{json,md}
python -m src.preprocessing.time_series.run_ts_engineering            # full run
python -m src.preprocessing.time_series.run_ts_engineering --no-write # diagnostic only

# Run the feature engineering pipeline on the ts parquet
#   → data/features/Dades_pellet_engineered.parquet
#   → data/features/feature_engineering_report.{json,md}
python -m src.preprocessing.feature_engineering.run_feature_engineering            # full run
python -m src.preprocessing.feature_engineering.run_feature_engineering --no-write # diagnostic only

# Run the specialized-datasets stage on the engineered parquet
#   → data/datasets/master/master_dataset.parquet (+ report)
#   → data/datasets/specialized/{anomaly_detection,forecasting,energy}_dataset.parquet (+ reports)
python -m src.preprocessing.datasets.run_datasets            # full run
python -m src.preprocessing.datasets.run_datasets --no-write # diagnostic only
python -m src.preprocessing.datasets.run_datasets --write-schema-lock # refresh configs/schema_lock.json (commit it)

# Combined preprocessing via the shim (chained modes accept only --no-write / --log-level)
python -m src.preprocessing                  # cleaning only (default)
python -m src.preprocessing --stage ts       # time-series only
python -m src.preprocessing --stage fe       # feature engineering only
python -m src.preprocessing --stage features # cleaning → ts → feature engineering
python -m src.preprocessing --stage datasets # specialized datasets only
python -m src.preprocessing --stage all      # cleaning → ts → fe → datasets

# Intelligence Layer — Behaviour Intelligence (consumes master_dataset.parquet)
#   → data/intelligence/behaviour/profiles/profile_labels.parquet
#   → data/intelligence/behaviour/baselines/baselines.parquet
#   → data/intelligence/behaviour/validation/{distribution,durations,transitions}.parquet
#   → data/intelligence/behaviour/behaviour_fit_manifest.json (+ behaviour_intelligence_report.{json,md})
# Standalone (NOT part of the --stage shim): fits descriptive artifacts past the preprocessing chain.
python -m src.intelligence                                    # layer dispatcher → default component (behaviour)
python -m src.intelligence --component behaviour --no-write   # via dispatcher, diagnostic only
python -m src.intelligence.behaviour.run_behaviour            # component directly: full run
python -m src.intelligence.behaviour.run_behaviour --no-write # component directly: reports, no artifacts

# Intelligence Layer — Iteration B components (need sklearn: pip install -e ".[models,dev]").
# All consume behaviour's persisted labels/manifest (run behaviour first) and write
# run-versioned, never-overwritten outputs → data/intelligence/<component>/runs/<run_id>/.
# Iteration B CLIs take the policy via --config (behaviour predates this and uses --policy);
# --no-write writes nothing at all; --run-id defaults to a fresh UTC timestamp.
python -m src.intelligence --component correlation            # per-profile Pearson/Spearman + shift diagnostics
python -m src.intelligence --component pca                    # per-profile scaler+PCA models, T²/Q scores
python -m src.intelligence --component anomaly                # 4 explainable detectors + combined severity
python -m src.intelligence.anomaly.run_anomaly --pca-run latest  # anomaly consumes a completed pca run (default: latest)

# External Context Layer — BOM operational context (consumes the raw BOM CSV
# + master_dataset.parquet read-only; never refits models or touches upstream).
#   → data/context/bom/runs/<run_id>/ (components, orders, overlaps/gaps/
#     transitions, master-aligned bom_context_timeline, reports; manifest LAST)
#   → data/intelligence/forensics/bom_addenda/<run_id>/ (read-only BOM-aware
#     forensic addendum joining the persisted anomaly scores; figures + summary)
python -m src.context.bom --config configs/bom_context.yaml            # full run
python -m src.context.bom --config configs/bom_context.yaml --no-write # diagnostic only
python -m src.context.bom --skip-addendum                              # without Stage H addendum

# Quality tooling
ruff check . && ruff format --check .
mypy src
pytest
```

Quality tooling is wired up: `ruff` (lint + format), `mypy src` (lenient baseline — pandas treated as untyped for now; the pydantic mypy plugin is enabled so `Field(...)` constraints and `default_factory=Model` type-check), and `pytest`, gated locally by `.pre-commit-config.yaml` and in CI by `.github/workflows/ci.yml`. All tool config lives in `pyproject.toml`. Unit tests live under `tests/unit/preprocessing/{cleaning,time_series,feature_engineering,datasets}/`, `tests/unit/intelligence/{_common,behaviour,correlation,pca,anomaly}/` and `tests/unit/context/bom/`, plus the chain contract tests in `tests/integration/`, and run with `pytest` (343 tests, ~60 s).

Reference docs for each preprocessing stage: [docs/pipeline/data_cleaning.md](docs/pipeline/data_cleaning.md), [docs/pipeline/time_series_engineering.md](docs/pipeline/time_series_engineering.md), [docs/pipeline/feature_engineering.md](docs/pipeline/feature_engineering.md), [docs/pipeline/specialized_datasets.md](docs/pipeline/specialized_datasets.md). Intelligence Layer: [docs/intelligence/behaviour_intelligence.md](docs/intelligence/behaviour_intelligence.md), [docs/intelligence/correlation_intelligence.md](docs/intelligence/correlation_intelligence.md), [docs/intelligence/pca_intelligence.md](docs/intelligence/pca_intelligence.md), [docs/intelligence/anomaly_intelligence.md](docs/intelligence/anomaly_intelligence.md). External Context Layer: [docs/context/bom_context.md](docs/context/bom_context.md). See [docs/README.md](docs/README.md) for the full documentation map.

---

## Architecture

Linear pipeline, one package per preprocessing stage, then the Intelligence Layer:

```
data_generation/ → preprocessing/{cleaning → time_series → feature_engineering → datasets} → intelligence/{behaviour → correlation·pca → anomaly} → [src/models/] → [src/visualization/]
                                                                                  context/{bom} ── read-only joins against master + anomaly scores (interpretation only)
```

`src/preprocessing/` is parameter-free preprocessing; `src/intelligence/` characterizes normal behaviour (fits *descriptive* artifacts); `src/context/` turns external sources (BOM/production orders) into contextual datasets joined against the master timeline — analytical only, never an input to model fitting until explicitly promoted; `src/models/` (planned) fits *predictive* estimators that score deviation from normal. Project paths are centralized in `src/config.py`; cross-stage contracts live in the neutral `src/preprocessing/_common/` package (the intelligence layer re-uses them via shims).

| Module | Status | Responsibility |
|---|---|---|
| `src/data_generation/` | Done | Generates 2,000 synthetic cycles with drift and 3% anomaly injection (`generate.py`; run via `python -m src.data_generation.generate`). Standalone MVP scaffolding, upstream of the pipeline. |
| `src/preprocessing/cleaning/` | Done | Six-module detect+remediate cleaning pipeline for `Dades_pellet.csv`; outputs cleaned CSV + JSON/MD report. Policy in `configs/cleaning.yaml`. |
| `src/preprocessing/time_series/` | Done | Six-stage feature pipeline (temporal conversion → index → optional resampling → rolling windows → temporal features → specialised state features). Semantic-driven routing from `variable_classification.csv`; per-column overrides in `configs/time_series.yaml`. Output: `Dades_pellet_features.parquet` (~290 cols). |
| `src/preprocessing/feature_engineering/` | Done | Six-family pipeline (temporal derivatives → stability → physical ratios → energetic → operative → statistical anomaly). Cross-column / derived features layered on the ts parquet. Policy in `configs/feature_engineering.yaml`. Output: `Dades_pellet_engineered.parquet`. Fitted estimators (IF, LOF, Mahalanobis) deferred to `src/models/anomaly/`. |
| `src/preprocessing/datasets/` | Done | Selection + validation stage. Promotes the engineered parquet to a canonical master and projects three model-family-specific datasets (anomaly detection, forecasting, energy) via a hybrid regex + category + explicit-override selector. Policy in `configs/specialized_datasets.yaml`. Outputs in `data/datasets/{master,specialized}/`. Schema-lock contract tracked at `configs/schema_lock.json` (refresh via `--write-schema-lock`). No new features, no fitted models. |
| `src/intelligence/behaviour/` | Done (Iteration A) | First Intelligence-Layer component. Consumes `master_dataset.parquet`; derives operational profiles (stopped/startup/shutdown/alarm/low·mid·high production), fits per-profile statistical baselines (leakage-safe, train-window only), and emits profile-quality validation reports + a reproducible `behaviour_fit_manifest.json`. Policy in `configs/behaviour_intelligence.yaml`. Non-derivable regimes (cleaning, maintenance, recipe change) documented as gaps, not fabricated. Standalone CLI (`run_behaviour`), not part of the `--stage` shim. Its persisted labels/`is_train` flag are the leakage contract every Iteration B component consumes. |
| `src/intelligence/correlation/` | Done | Iteration B. Per-profile Pearson + Spearman correlation references fitted on behaviour's persisted train window; strongest/redundant pair reports; train-vs-validation shift *diagnostics* (AWARE findings only, no alerts). Policy in `configs/correlation_intelligence.yaml`. Run-versioned outputs in `data/intelligence/correlation/runs/<run_id>/`. |
| `src/intelligence/pca/` | Done | Iteration B. Per-profile RobustScaler + PCA fitted leakage-safe (EVR target 0.95); persists joblib models + loadings + T²/Q scores + per-feature reconstruction contributions for every row (`is_train` preserved — anomaly fits thresholds from train scores). Unsupportable profiles skipped + reported. Policy in `configs/pca_intelligence.yaml`. |
| `src/intelligence/anomaly/` | Done (v1) | Four explainable detectors per profile — statistical (vs behaviour baselines), Mahalanobis (Ledoit-Wolf, signed contributions), PCA T²/Q (consumes a completed pca run via `--pca-run`), Isolation Forest (seeded, no fabricated attributions) — plus train-ECDF normalization, conservative-max combined score, and train-percentile severity (normal/warning/anomaly; `unscored` for unsupported profiles). Policy in `configs/anomaly_intelligence.yaml`. No deep learning / forecasting / streaming (explicitly deferred). |
| `src/context/bom/` | Done (v1) | BOM Operational Context Layer. Normalizes the raw BOM CSV (`data/context/bom/raw/`) into components → aggregated orders with deterministic `bom_signature` + `recipe_context_key` → overlap/gap/transition diagnostics → a master-aligned `bom_context_timeline` (one row per master timestamp, overlaps preserved — never silently resolved) → forensic candidate-date windows → a read-only BOM-aware forensic addendum joining the persisted anomaly scores. Policy in `configs/bom_context.yaml`; run-versioned outputs in `data/context/bom/runs/<run_id>/` + `data/intelligence/forensics/bom_addenda/<run_id>/`. Contextual/analytical only: never modifies the master, refits models, or changes thresholds. Doc: [docs/context/bom_context.md](docs/context/bom_context.md). |
| `src/intelligence/_common/` | Done | Shared Iteration B utilities: run versioning (`runs.py`: timestamp run-ids, manifest-as-completion-marker, `latest` resolution), structural dataset fingerprint, behaviour-artifact loaders (`upstream.py`: strict `align_labels`, the leakage contract), feature selection, joblib persistence + versions, base fit manifest; plus shims over `src/preprocessing/_common/` and `behaviour.io`. |
| `src/intelligence/__main__.py` | Done | Component dispatcher (`python -m src.intelligence --component behaviour\|correlation\|pca\|anomaly`); registry maps each component name to its `main`. Defaults to `behaviour`; forwards remaining flags to the component CLI. |
| `src/config.py` | Done | Central project paths (`PROJECT_ROOT`, `RAW/PROCESSED/FEATURES/DATASETS/INTELLIGENCE` dirs, `CONFIGS_DIR`); every io/run module imports paths from here instead of recomputing `parents[N]`. |
| `src/preprocessing/_common/` | Done | Neutral shared contracts: `Finding`, `Severity`, `write_json`/`write_markdown`, `ColumnGroups`/`load_groups`, and the `StrictModel` Pydantic base (`extra="forbid"`). All four preprocessing stages plus `src/intelligence/` re-export from here via thin shims (`src/intelligence/_common/` hosts the intelligence-only utilities on top). |
| `scripts/` | Done | One-off build/EDA tooling, outside the importable package: `build_pellet_dictionary.py`, `build_variable_classification.py`, `build_eda_notebook.py`, `analyze_temporal_quality.py`. |
| `src/preprocessing/__main__.py` | Done | Combined `--stage cleaning\|ts\|fe\|features\|datasets\|all` dispatcher (`python -m src.preprocessing`); defaults to cleaning. Chained modes (`features`/`all`) forward only universal flags (`--no-write`, `--log-level`). |
| `src/models/` | Planned | scikit-learn anomaly/classification models (Isolation Forest, LOF, Mahalanobis). Will consume `src/preprocessing/_common/` contracts plus the Behaviour Intelligence baselines + fit manifest (scoring deviation from the per-profile "normal"). Replaces the former flat `anomaly_detection.py` placeholder. |
| `src/visualization/` | Planned | Dashboard-style plots. Replaces the former flat `visualization.py` placeholder. |

`notebooks/` contains validation scripts and EDA only — no production logic.

---

## Synthetic Dataset Schema (MVP)

Target column: `machine_state` → `normal` / `warning` / `anomaly`

| Group | Columns |
|---|---|
| Temperature | `material_temp`, `mold_temp` |
| Pressure | `injection_pressure`, `maintenance_pressure`, `cavity_pressure` |
| Timing | `injection_time`, `cooling_time`, `cycle_time` |
| Other | `injection_velocity`, `screw_position`, `specific_volume`, `energy_consumption` |
| Internal | `drift` (generation-only, not a model feature) |

The real-machine column schema is documented in `.claude/CLAUDE.local.md`.

---

## Claude Code Agent & Skill Ecosystem

Project-local Claude Code tooling lives in [.claude/agents/](.claude/agents/) and [.claude/skills/](.claude/skills/) — both auto-discovered via YAML frontmatter, no manual registration.

### Conventions

- **Skills:** directory layout `.claude/skills/<name>/SKILL.md` with `name:` + `description:` frontmatter. Add `scripts/` / `references/` / `templates/` subdirs only when actually needed.
- **Agents:** single file `.claude/agents/<name>.md` with `name:`, `description:`, `tools:` frontmatter, then the system prompt. Each agent includes a **`MODEL STRATEGY`** section defining its default model plus dynamic escalation/downgrade conditions (selection is per-invocation, not per-agent).
- Opus is the default only for agents requiring deep reasoning, ambiguity handling, system-level orchestration, or high-risk synthesis (6 of 18). The rest default to Sonnet with escalation when complexity warrants it.

### Agents (18)

| Domain | Agents |
|---|---|
| Orchestration | `workflow-orchestrator-agent` *(Opus)* |
| Research & docs | `researcher-agent` *(Opus)*, `documentation-architect-agent` |
| Code review & QA | `code-reviewer-agent`, `qa-agent` |
| Data & features | `dataset-qa-agent`, `feature-engineering-agent`, `pipeline-builder-agent` |
| Time-series & sensors | `time-series-agent`, `sensor-intelligence-agent`, `machine-cycle-agent` |
| Anomaly & PdM | `anomaly-detection-agent`, `predictive-maintenance-agent` *(Opus)*, `plastics-industry-agent` *(Opus)* |
| Security | `security-reviewer-agent` *(Opus)* |
| Project stewardship | `day-closing-agent`, `repository-architecture-agent`, `master-version-agent` *(Opus)* |

Agents marked *(Opus)* default to `claude-opus-4-7`; the rest default to `claude-sonnet-4-6`. All can escalate or downgrade dynamically.

### Skills (52)

| Domain | Count | Skills |
|---|---|---|
| Research & docs | 5 | `analyze-github-repo`, `compare-frameworks`, `summarize-paper`, `generate-readme`, `generate-architecture-doc` |
| Code & QA | 4 | `review-python-code`, `detect-architecture-issues`, `generate-unit-tests`, `run-test-suite` |
| Data quality | 4 | `validate-dataset`, `detect-missing-values`, `detect-outliers`, `detect-collinearity` |
| Feature engineering | 2 | `generate-time-features`, `rolling-window-analysis` |
| Pipeline construction | 3 | `build-preprocessing-pipeline`, `build-feature-pipeline`, `validate-pipeline-structure` |
| Time-series | 3 | `analyze-temporal-patterns`, `detect-trend-and-seasonality`, `detect-temporal-drift` |
| Sensors & telemetry | 3 | `detect-sensor-drift`, `validate-sensor-consistency`, `detect-sampling-irregularities` |
| Machine cycles | 3 | `analyze-machine-cycles`, `detect-cycle-instability`, `analyze-cycle-phases` |
| Plastics manufacturing | 3 | `analyze-injection-process`, `detect-process-instability`, `interpret-industrial-telemetry` |
| Anomaly & degradation | 3 | `detect-industrial-anomalies`, `analyze-anomaly-severity`, `analyze-degradation-patterns` |
| Security | 4 | `detect-exposed-secrets`, `review-insecure-configurations`, `analyze-bash-security`, `detect-insecure-dependencies` |
| Orchestration | 3 | `decompose-objective`, `route-agent-tasks`, `build-execution-plan` |
| Day-closing & continuity | 4 | `generate-daily-summary`, `evaluate-git-readiness`, `review-project-memory`, `detect-project-drift` |
| Repository architecture | 4 | `analyze-repository-structure`, `detect-organization-drift`, `recommend-repository-layout`, `identify-technical-debt-hotspots` |
| Project state & master version | 4 | `generate-project-state-report`, `consolidate-project-knowledge`, `track-project-evolution`, `generate-master-version` |

Each `SKILL.md` carries its own trigger phrase in frontmatter — the harness surfaces the right one based on the user's request.

---

## Current Status (MVP — Month 1–2)

- **Done:** Synthetic data generation; data cleaning pipeline (6 modules); time-series engineering pipeline (6 stages, semantic-driven); feature engineering pipeline (6 families, semantic-driven, cross-column ratios, energetic / operative / statistical anomaly features); specialized-datasets stage (master + anomaly_detection + forecasting + energy projections, hybrid regex/category/explicit selectors); **Intelligence Layer — Behaviour Intelligence (Iteration A)**: operational-profile segmentation + per-profile statistical baselines (leakage-safe) + validation reports in `src/intelligence/behaviour/`; **Intelligence Layer — Iteration B**: Correlation Intelligence (`src/intelligence/correlation/`), PCA Intelligence (`src/intelligence/pca/`) and **Anomaly Intelligence v1** (`src/intelligence/anomaly/` — statistical / Mahalanobis / PCA-T²·Q / Isolation Forest detectors with combined severity), all per-profile, leakage-safe (consume behaviour's persisted `is_train` contract), with run-versioned non-destructive outputs and shared utilities in `src/intelligence/_common/`; **External Context Layer — BOM Operational Context v1** (`src/context/bom/`): normalized BOM components, aggregated orders with deterministic BOM signatures, overlap/gap/transition diagnostics, master-aligned context timeline and a read-only BOM-aware forensic addendum — contextual/analytical only, no model coupling; unit + integration tests (343 tests); reference docs for all four preprocessing stages + all four Intelligence components + the BOM context layer. Architecture stabilization: installable package (`pyproject.toml`, `pip install -e .`), centralized paths (`src/config.py`), neutral shared contracts (`src/preprocessing/_common/`), uniform `extra="forbid"` config validation (pydantic mypy plugin enabled), tracked `configs/schema_lock.json`, and quality tooling (`ruff`, `mypy`, pre-commit, GitHub Actions CI).
- **In progress:** Anomaly criterion definition (real-machine thresholds in `.claude/CLAUDE.local.md`); manual review of the September–October validation-window drift surfaced by Anomaly Intelligence (see [docs/intelligence/anomaly_intelligence.md](docs/intelligence/anomaly_intelligence.md) §6).
- **Not started:** classification/forecasting models (`src/models/`) — supervised estimators consuming the Intelligence-Layer artifacts; LOF / One-Class SVM benchmarking; temporal forecasting + residual anomaly detection; streaming inference / alert delivery; output API; visualization dashboard (`src/visualization/`).
