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
python src/data_generation.py

# Run the data-cleaning pipeline on data/raw/Dades_pellet.csv
#   → data/processed/Dades_pellet_clean.csv
#   → data/features/cleaning_report.{json,md}
python -m src.data.cleaning.run_cleaning            # full run
python -m src.data.cleaning.run_cleaning --no-write # diagnostic only

# Run the time-series engineering pipeline on the cleaned CSV
#   → data/features/Dades_pellet_features.parquet
#   → data/features/ts_engineering_report.{json,md}
python -m src.data.time_series.run_ts_engineering            # full run
python -m src.data.time_series.run_ts_engineering --no-write # diagnostic only

# Run the feature engineering pipeline on the ts parquet
#   → data/features/Dades_pellet_engineered.parquet
#   → data/features/feature_engineering_report.{json,md}
python -m src.data.feature_engineering.run_feature_engineering            # full run
python -m src.data.feature_engineering.run_feature_engineering --no-write # diagnostic only

# Run the specialized-datasets stage on the engineered parquet
#   → data/datasets/master/master_dataset.parquet (+ report)
#   → data/datasets/specialized/{anomaly_detection,forecasting,energy}_dataset.parquet (+ reports)
python -m src.data.datasets.run_datasets            # full run
python -m src.data.datasets.run_datasets --no-write # diagnostic only
python -m src.data.datasets.run_datasets --write-schema-lock # refresh configs/schema_lock.json (commit it)

# Combined preprocessing via the shim (chained modes accept only --no-write / --log-level)
python -m src.preprocessing                  # cleaning only (default)
python -m src.preprocessing --stage ts       # time-series only
python -m src.preprocessing --stage fe       # feature engineering only
python -m src.preprocessing --stage features # cleaning → ts → feature engineering
python -m src.preprocessing --stage datasets # specialized datasets only
python -m src.preprocessing --stage all      # cleaning → ts → fe → datasets

# Quality tooling
ruff check . && ruff format --check .
mypy src
pytest
```

Quality tooling is wired up: `ruff` (lint + format), `mypy src` (lenient baseline — pandas treated as untyped for now), and `pytest`, gated locally by `.pre-commit-config.yaml` and in CI by `.github/workflows/ci.yml`. All tool config lives in `pyproject.toml`. Unit tests live under `tests/unit/data/{cleaning,time_series,feature_engineering,datasets}/` and run with `pytest` (136 tests, ~10 s).

Reference docs for each preprocessing stage: [docs/pipeline/data_cleaning.md](docs/pipeline/data_cleaning.md), [docs/pipeline/time_series_engineering.md](docs/pipeline/time_series_engineering.md), [docs/pipeline/feature_engineering.md](docs/pipeline/feature_engineering.md), [docs/pipeline/specialized_datasets.md](docs/pipeline/specialized_datasets.md). See [docs/README.md](docs/README.md) for the full documentation map.

---

## Architecture

Linear pipeline, one package per preprocessing stage:

```
data_generation.py → data/cleaning/ → data/time_series/ → data/feature_engineering/ → data/datasets/ → [src/models/] → [src/visualization/]
```

Project paths are centralized in `src/config.py`; cross-stage contracts live in the neutral `src/data/_common/` package.

| Module | Status | Responsibility |
|---|---|---|
| `src/data_generation.py` | Done | Generates 2,000 synthetic cycles with drift and 3% anomaly injection |
| `src/data/cleaning/` | Done | Six-module detect+remediate cleaning pipeline for `Dades_pellet.csv`; outputs cleaned CSV + JSON/MD report. Policy in `configs/cleaning.yaml`. |
| `src/data/time_series/` | Done | Six-stage feature pipeline (temporal conversion → index → optional resampling → rolling windows → temporal features → specialised state features). Semantic-driven routing from `variable_classification.csv`; per-column overrides in `configs/time_series.yaml`. Output: `Dades_pellet_features.parquet` (~290 cols). |
| `src/data/feature_engineering/` | Done | Six-family pipeline (temporal derivatives → stability → physical ratios → energetic → operative → statistical anomaly). Cross-column / derived features layered on the ts parquet. Policy in `configs/feature_engineering.yaml`. Output: `Dades_pellet_engineered.parquet`. Fitted estimators (IF, LOF, Mahalanobis) deferred to `src/models/anomaly/`. |
| `src/data/datasets/` | Done | Selection + validation stage. Promotes the engineered parquet to a canonical master and projects three model-family-specific datasets (anomaly detection, forecasting, energy) via a hybrid regex + category + explicit-override selector. Policy in `configs/specialized_datasets.yaml`. Outputs in `data/datasets/{master,specialized}/`. Schema-lock contract tracked at `configs/schema_lock.json` (refresh via `--write-schema-lock`). No new features, no fitted models. |
| `src/config.py` | Done | Central project paths (`PROJECT_ROOT`, `RAW/PROCESSED/FEATURES/DATASETS` dirs, `CONFIGS_DIR`); every io/run module imports paths from here instead of recomputing `parents[N]`. |
| `src/data/_common/` | Done | Neutral shared contracts: `Finding`, `Severity`, `write_json`/`write_markdown`, `ColumnGroups`/`load_groups`, and the `StrictModel` Pydantic base (`extra="forbid"`). All four stages re-export from here; `cleaning` is no longer the de-facto base. |
| `scripts/` | Done | One-off build/EDA tooling, outside the importable package: `build_pellet_dictionary.py`, `build_variable_classification.py`, `build_eda_notebook.py`, `analyze_temporal_quality.py`. |
| `src/preprocessing.py` | Shim | Dispatches `--stage cleaning\|ts\|fe\|features\|datasets\|all`; defaults to cleaning. Chained modes (`features`/`all`) forward only universal flags (`--no-write`, `--log-level`). |
| `src/models/` | Planned | scikit-learn anomaly/classification models (Isolation Forest, LOF, Mahalanobis). Will consume contracts from `src/data/_common/`. Replaces the former flat `anomaly_detection.py` placeholder. |
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

- **Done:** Synthetic data generation; data cleaning pipeline (6 modules); time-series engineering pipeline (6 stages, semantic-driven); feature engineering pipeline (6 families, semantic-driven, cross-column ratios, energetic / operative / statistical anomaly features); specialized-datasets stage (master + anomaly_detection + forecasting + energy projections, hybrid regex/category/explicit selectors); unit-test scaffolding under `tests/unit/data/` (136 tests); reference docs for all four preprocessing stages. Architecture stabilization: installable package (`pyproject.toml`, `pip install -e .`), centralized paths (`src/config.py`), neutral shared contracts (`src/data/_common/`), uniform `extra="forbid"` config validation, tracked `configs/schema_lock.json`, and quality tooling (`ruff`, `mypy`, pre-commit, GitHub Actions CI).
- **In progress:** Anomaly criterion definition (real-machine thresholds in `.claude/CLAUDE.local.md`).
- **Not started:** Classification/anomaly models (`src/models/`) — will host fitted multivariate anomaly models (Isolation Forest, LOF, Mahalanobis with covariance fit) explicitly excluded from the feature_engineering stage; output API; visualization dashboard (`src/visualization/`).
