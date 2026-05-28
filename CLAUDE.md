# CLAUDE.md

Project-level guidance for Claude Code. Global standards (Python style, ML pipeline rules, Git workflow) are defined in the user-level `~/.claude/CLAUDE.md` and apply automatically — do not repeat them here.

Private context (anomaly criteria, real data schema, client details) lives in `.claude/CLAUDE.local.md`, which is git-ignored.

---

## Project Overview

**InjexCore** is a predictive maintenance system for plastic injection moulding machines. It classifies each production cycle as `normal`, `warning`, or `anomaly` to detect machine degradation before failures occur. The MVP uses synthetic data; real machine data integration is planned for a later phase.

---

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

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

# Combined cleaning + time series via the shim
python -m src.preprocessing                  # cleaning only (default)
python -m src.preprocessing --stage ts       # time-series only
python -m src.preprocessing --stage features # cleaning then time-series
```

Linting / typing tools are not wired up yet (`ruff`, `mypy`, pre-commit pending). Unit tests live under `tests/unit/data/{cleaning,time_series}/` and run with `pytest tests/` (63 tests, ~1 s).

Reference docs for each preprocessing stage: [docs/data_cleaning.md](docs/data_cleaning.md), [docs/time_series_engineering.md](docs/time_series_engineering.md).

---

## Architecture

Linear pipeline, one package per preprocessing stage:

```
data_generation.py → data/cleaning/ → data/time_series/ → anomaly_detection.py → visualization.py
```

| Module | Status | Responsibility |
|---|---|---|
| `src/data_generation.py` | Done | Generates 2,000 synthetic cycles with drift and 3% anomaly injection |
| `src/data/cleaning/` | Done | Six-module detect+remediate cleaning pipeline for `Dades_pellet.csv`; outputs cleaned CSV + JSON/MD report. Policy in `configs/cleaning.yaml`. |
| `src/data/time_series/` | Done | Six-stage feature pipeline (temporal conversion → index → optional resampling → rolling windows → temporal features → specialised state features). Semantic-driven routing from `variable_classification.csv`; per-column overrides in `configs/time_series.yaml`. Output: `Dades_pellet_features.parquet` (~323 cols). |
| `src/preprocessing.py` | Shim | Dispatches `--stage cleaning\|ts\|features` to the right module; defaults to cleaning for backward compatibility |
| `src/anomaly_detection.py` | Placeholder | scikit-learn classification model |
| `src/visualization.py` | Placeholder | Dashboard-style plots saved to `images/` |

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
- Opus is the default only for agents requiring deep reasoning, ambiguity handling, system-level orchestration, or high-risk synthesis (5 of 15). The rest default to Sonnet with escalation when complexity warrants it.

### Agents (15)

| Domain | Agents |
|---|---|
| Orchestration | `workflow-orchestrator-agent` *(Opus)* |
| Research & docs | `researcher-agent` *(Opus)*, `documentation-architect-agent` |
| Code review & QA | `code-reviewer-agent`, `qa-agent` |
| Data & features | `dataset-qa-agent`, `feature-engineering-agent`, `pipeline-builder-agent` |
| Time-series & sensors | `time-series-agent`, `sensor-intelligence-agent`, `machine-cycle-agent` |
| Anomaly & PdM | `anomaly-detection-agent`, `predictive-maintenance-agent` *(Opus)*, `plastics-industry-agent` *(Opus)* |
| Security | `security-reviewer-agent` *(Opus)* |

Agents marked *(Opus)* default to `claude-opus-4-7`; the rest default to `claude-sonnet-4-6`. All can escalate or downgrade dynamically.

### Skills (40)

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

Each `SKILL.md` carries its own trigger phrase in frontmatter — the harness surfaces the right one based on the user's request.

---

## Current Status (MVP — Month 1–2)

- **Done:** Synthetic data generation; data cleaning pipeline (6 modules); time-series engineering pipeline (6 stages, semantic-driven); unit-test scaffolding under `tests/unit/data/`; reference docs for both preprocessing stages.
- **In progress:** Anomaly criterion definition (real-machine thresholds in `.claude/CLAUDE.local.md`).
- **Not started:** Classification model (`src/anomaly_detection.py`), output API, visualization dashboard, lint/type toolchain (`ruff`, `mypy`, pre-commit).
