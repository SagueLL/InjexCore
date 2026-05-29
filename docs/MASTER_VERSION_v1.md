# InjexCore — MASTER_VERSION_v1

## 1. Version Metadata

| Field | Value |
|---|---|
| Version | `v1.0.0` |
| Date | `2026-05-29` |
| Scope label | Data preprocessing layer — first complete version |
| Snapshot author | `master-version-agent` |
| Baseline status | This document is the v1 baseline; every future `MASTER_VERSION_vN` diffs against it. |
| Source-of-truth documents (not replaced) | [CLAUDE.md](../CLAUDE.md), [docs/data_cleaning.md](data_cleaning.md), [docs/time_series_engineering.md](time_series_engineering.md), [docs/feature_engineering.md](feature_engineering.md), [docs/specialized_datasets.md](specialized_datasets.md) |

This snapshot consolidates — it does not rewrite. Where this document
makes a claim, the underlying reference doc remains authoritative.

---

## 2. Executive Summary

- **InjexCore** is a predictive-maintenance system for plastic injection moulding machines that classifies each production cycle as `normal` / `warning` / `anomaly` (see [CLAUDE.md](../CLAUDE.md)).
- **Today (2026-05-29) the data preprocessing layer is complete end to end.** Four stages — cleaning, time-series engineering, feature engineering, and specialized datasets — ship working code, validated configs, audit reports, and tests.
- **A canonical master dataset now exists.** Raw vendor CSVs flow deterministically into `data/datasets/master/master_dataset.parquet` (167,331 rows × 566 columns), plus three model-family projections for anomaly detection, forecasting, and energy analysis.
- **All four stages share the same shape**: one package per stage, semantic-driven column routing from a single classification CSV, pydantic-validated YAML policy, JSON + Markdown audit reports built from a common `Finding` record.
- **No models have been fit yet** — preprocessing emits zero model state by design. Isolation Forest, LOF, Mahalanobis (covariance fit), LSTM, and XGBoost work begins in v2.
- **The next chapter is the Intelligence layer** (`src/models/anomaly/`, then forecasting and energy studies). The v1 → v2 boundary is the reason this snapshot is cut now.

---

## 3. Architecture State

The production pipeline is a strictly linear chain, one package per
preprocessing stage:

```
data_generation.py
  → data/cleaning/
    → data/time_series/
      → data/feature_engineering/
        → data/datasets/
          → [intelligence layer pending: src/models/anomaly/, src/api/, src/visualization.py]
```

### 3.1 Per-package file convention (9-file pattern)

Every preprocessing package under `src/data/<stage>/` is structured the
same way, so a reader who learns one stage can navigate any other:

| File | Role |
|---|---|
| `__init__.py` | Public exports of the stage. |
| `io.py` | Read/write of inputs and artefacts; no business logic. |
| `policy.py` | Pydantic model of the stage's YAML policy (`extra="forbid"`). |
| `column_groups.py` | Resolution of semantic categories against `variable_classification.csv`. |
| `reporting.py` | `Finding` record + JSON/MD report rendering. |
| `<stage-specific modules>` | The actual analytical work, one concern per file. |
| `run_<stage>.py` | CLI entrypoint, also importable as `python -m src.data.<stage>.run_<stage>`. |

Concrete realisations of the pattern:

- `src/data/cleaning/`: `timestamps.py`, `physical_ranges.py`, `frozen_sensors.py`, `duplicates.py`, `state_consistency.py`, `missing_values.py` → `run_cleaning.py`.
- `src/data/time_series/`: `temporal_conversion.py`, `temporal_index.py`, `resampling.py`, `rolling_windows.py`, `temporal_features.py`, `state_features.py` → `run_ts_engineering.py`.
- `src/data/feature_engineering/`: `temporal_derivatives.py`, `stability.py`, `physical_ratios.py`, `energetic_features.py`, `operative_features.py`, `anomaly_features.py` → `run_feature_engineering.py`.
- `src/data/datasets/`: `selectors.py`, `master_validation.py`, `anomaly_projection.py`, `forecasting_projection.py`, `energy_projection.py` → `run_datasets.py`.

The orchestration shim `src/preprocessing.py` dispatches `--stage cleaning|ts|fe|features|datasets|all` to the right package.

---

## 4. Data Flow

| Artefact | Path | Shape (today) |
|---|---|---|
| Raw vendor data | `data/raw/Dades_pellet.csv` | input |
| Cleaned | `data/processed/Dades_pellet_clean.csv` | cleaned schema |
| Time-series engineered | `data/features/Dades_pellet_features.parquet` | ~323 cols |
| Feature engineered | `data/features/Dades_pellet_engineered.parquet` | 167,331 × 566 |
| **Master (canonical)** | `data/datasets/master/master_dataset.parquet` | 167,331 × 566 |
| Specialized — anomaly detection | `data/datasets/specialized/anomaly_detection_dataset.parquet` | 239 cols |
| Specialized — forecasting | `data/datasets/specialized/forecasting_dataset.parquet` | 294 cols |
| Specialized — energy | `data/datasets/specialized/energy_dataset.parquet` | 46 cols |
| Per-stage audit reports | `data/features/{cleaning,ts_engineering,feature_engineering}_report.{json,md}`, `data/datasets/{master,specialized}/*_report.{json,md}` | one pair per stage / dataset |

Master and specialized parquet artefacts confirmed present on disk under `data/datasets/`. Row/column counts above reflect today's run.

---

## 5. Active Systems

- **Pipeline packages** (`src/data/`):
  - [src/data/cleaning/](../src/data/cleaning/) — 6 detect+remediate modules.
  - [src/data/time_series/](../src/data/time_series/) — 6-stage temporal pipeline.
  - [src/data/feature_engineering/](../src/data/feature_engineering/) — 6-family derived-feature pipeline.
  - [src/data/datasets/](../src/data/datasets/) — master validation + 3 projections.
- **Orchestration shim**: [src/preprocessing.py](../src/preprocessing.py) — stages `cleaning | ts | fe | features | datasets | all`.
- **Configuration** — four pydantic-validated YAML policies, all `extra="forbid"`:
  - [configs/cleaning.yaml](../configs/cleaning.yaml)
  - [configs/time_series.yaml](../configs/time_series.yaml)
  - [configs/feature_engineering.yaml](../configs/feature_engineering.yaml)
  - [configs/specialized_datasets.yaml](../configs/specialized_datasets.yaml)
- **Semantic dictionary** — one CSV drives column routing across all four stages: `data/features/variable_classification.csv`.
- **Test suite** — 136 unit tests under `tests/unit/data/{cleaning,time_series,feature_engineering,datasets}/`, ~8 s with `pytest tests/`.
- **Reference docs**:
  - [docs/data_cleaning.md](data_cleaning.md)
  - [docs/time_series_engineering.md](time_series_engineering.md)
  - [docs/feature_engineering.md](feature_engineering.md)
  - [docs/specialized_datasets.md](specialized_datasets.md)
- **Placeholders (not yet implemented)**: `src/anomaly_detection.py`, `src/visualization.py`.

---

## 6. Agent & Skill Ecosystem

The project-local Claude Code tooling under [.claude/agents/](../.claude/agents/)
and `.claude/skills/` was foundational to delivering v1. Per
[CLAUDE.md](../CLAUDE.md), the ecosystem includes **18 agents** and
**52 skills**, auto-discovered via YAML frontmatter.

Agents that materially shaped the preprocessing layer that ships in v1:

- `pipeline-builder-agent`, `feature-engineering-agent`, `time-series-agent` — structural design of the four stages and their shared 9-file pattern.
- `dataset-qa-agent`, `sensor-intelligence-agent`, `machine-cycle-agent` — data-quality decisions baked into cleaning and time-series.
- `anomaly-detection-agent`, `plastics-industry-agent` *(Opus)*, `predictive-maintenance-agent` *(Opus)* — semantic classification and the design constraint that fitted estimators stay out of feature engineering.
- `code-reviewer-agent`, `qa-agent` — test scaffolding and review of each stage.
- `documentation-architect-agent` — the four `docs/*.md` reference documents.
- `repository-architecture-agent`, `day-closing-agent`, `master-version-agent` *(Opus)* — stewardship, drift detection, and this snapshot.

Skill inventory (52 skills across 15 domains) is not enumerated here; see [CLAUDE.md](../CLAUDE.md#skills-52) for the full table.

---

## 7. Technical Decisions

The non-obvious design calls that define v1:

1. **Semantic-driven routing, no hardcoded column lists.** Every stage resolves the columns it touches by joining against `data/features/variable_classification.csv` categories. There is no `COLUMNS = [...]` literal in the production code. Adding or renaming a sensor upstream propagates automatically.
2. **Strict pydantic policies (`extra="forbid"`).** All four YAMLs under `configs/` are bound to pydantic models in each stage's `policy.py`. A typo in config fails at load time, before any data is read.
3. **Uniform `Finding` audit record.** Every stage emits findings tagged `NORMAL` / `AWARE` / `IMPORTANT` / `CRITICAL`. The shape is identical across cleaning, time-series, feature engineering, and datasets — so one downstream consumer can parse all four reports.
4. **Hybrid selector engine** (`src/data/datasets/selectors.py`). Specialized projections compose three rules: regex patterns, semantic categories, and explicit column overrides. This keeps selectors resilient to upstream feature additions while still allowing surgical control over what a given model family sees.
5. **Master is validation-only.** `src/data/datasets/master_validation.py` enforces timestamp monotonicity, a NaN budget, schema lock, and a drop list — it never computes a feature. The boundary "features upstream, selection here, models downstream" is hard-coded into the code's structure.
6. **Fitted estimators deferred to `src/models/anomaly/`.** Isolation Forest, LOF, and Mahalanobis-with-covariance-fit were deliberately excluded from `src/data/feature_engineering/`. Preprocessing emits zero model state; everything that needs `fit()` lives in the (still-to-be-built) intelligence layer.

---

## 8. Risks & Open Questions

- **Anomaly thresholds for real-machine data are still pending.** Criteria live in `.claude/CLAUDE.local.md` (git-ignored) and are not yet finalised. Blocking input for any supervised evaluation in v2.
- **No lint / type / pre-commit toolchain wired up.** `ruff`, `mypy`, and pre-commit hooks are pending. Today's quality bar is "tests pass locally."
- **Schema lock bootstraps on first run.** `data/datasets/master/schema_lock.json` is generated by `master_validation.py` the first time it sees the master parquet. No locked schema has been committed to git yet, so the first checked-in lock will define the reference column set rather than enforce it.
- **No CI.** The 136-test suite only runs on developer machines.
- **Source data scope.** All evidence in v1 is derived from a single vendor CSV (`Dades_pellet.csv`). Generalisation to multi-source ingestion is unverified.

---

## 9. Roadmap from v1 → v2 (Intelligence Layer)

The next chapter is models and anomalies. The boundary established by
v1 dictates where new code lands:

| Concern | Destination | Consumes |
|---|---|---|
| Unsupervised anomaly detection | `src/models/anomaly/` — Isolation Forest, LOF, Mahalanobis (covariance fit) | `data/datasets/specialized/anomaly_detection_dataset.parquet` |
| Forecasting / sequence models | `src/models/forecasting/` — LSTM, Transformer, XGBoost | `data/datasets/specialized/forecasting_dataset.parquet` |
| Energy & efficiency studies | `src/models/energy/` (or notebooks first) | `data/datasets/specialized/energy_dataset.parquet` |
| Output API | `src/api/` (FastAPI per global standards) | trained model artefacts + master |
| Visualization dashboard | `src/visualization.py` (placeholder today) | reports + model outputs |

Design constraints inherited from v1 that v2 must honour:

- Same **9-file package convention** (`io`, `policy`, `column_groups`, `reporting`, `<stage modules>`, `run_<stage>.py`, `__init__.py`).
- Same **pydantic `extra="forbid"` policy** per model family, under `configs/`.
- Same **`Finding`-style JSON + Markdown audit reports** for every training and evaluation run.
- **Semantic-driven** column selection where applicable; never hardcoded lists.
- **Reproducibility**: pinned versions, logged seeds, dataset hashes — per the global ML rules in `~/.claude/rules/ml-pipeline.md`.

Cutting v2 will be appropriate once at least one fitted anomaly model
is trained, evaluated against held-out data, and persisted with
metadata.

---

## 10. Confidence Level

- **High confidence**: pipeline structure, file paths, configs, test count, dataset row/column counts (verified against `data/datasets/` artefacts and [CLAUDE.md](../CLAUDE.md)).
- **Medium confidence**: column counts for specialized datasets (taken from the user-provided snapshot; not independently re-counted in this pass).
- **Lower confidence / explicit uncertainty**: real-machine anomaly thresholds (private, not visible to this snapshot); future model-family decisions in v2 (subject to evaluation results not yet available).

---

## 11. References

- Project guidance: [CLAUDE.md](../CLAUDE.md)
- Pipeline references:
  - [docs/data_cleaning.md](data_cleaning.md)
  - [docs/time_series_engineering.md](time_series_engineering.md)
  - [docs/feature_engineering.md](feature_engineering.md)
  - [docs/specialized_datasets.md](specialized_datasets.md)
- Specialized-datasets policy: [configs/specialized_datasets.yaml](../configs/specialized_datasets.yaml)
- Agent ecosystem: [.claude/agents/](../.claude/agents/)
- Global standards (apply automatically): `~/.claude/CLAUDE.md`, `~/.claude/rules/python.md`, `~/.claude/rules/ml-pipeline.md`, `~/.claude/rules/git.md`

---

*End of MASTER_VERSION_v1. Next snapshot: `MASTER_VERSION_v2` — cut when the first fitted anomaly model lands in `src/models/anomaly/`.*
