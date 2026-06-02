<img width="2644" height="1288" alt="LOGO_ESLOGAN" src="https://github.com/user-attachments/assets/ddd9e719-f237-44ba-8026-fc236bce2421" />


**AI-powered predictive maintenance for plastic injection machines**

---

## Project Overview

InjexCore is a predictive-maintenance system for plastic injection moulding
machines. It analyses production telemetry, detects anomalous behaviour, and
classifies each production cycle as `normal`, `warning`, or `anomaly` to
anticipate machine degradation before failures occur — reducing downtime,
scrap, and operational cost.

The project follows a practical, incremental approach (CRISP-DM): the MVP works
with synthetic data and a real pellet-granulation line dataset; real-time
machine integration is planned for a later phase.

---

## Problem Statement

Plants operating injection machines face unexpected downtime, production
defects, high energy consumption, and reactive maintenance. InjexCore shifts
from **reactive to predictive** maintenance by surfacing abnormal patterns
early from sensor/telemetry data.

---

## Architecture

A linear, modular data layer — one package per preprocessing stage — feeds the
(planned) modeling and serving layers:

```
data_generation → cleaning → time_series → feature_engineering → datasets → [models] → [api]
```

| Stage | Package | Responsibility |
|---|---|---|
| Cleaning | `src/data/cleaning/` | Detect + remediate (timestamps, duplicates, physical ranges, frozen sensors, state consistency, missing values). |
| Time-series | `src/data/time_series/` | Temporal conversion/index, optional resampling, rolling windows, temporal & state features. |
| Feature engineering | `src/data/feature_engineering/` | Temporal derivatives, stability, physical ratios, energetic / operative / statistical-anomaly features. |
| Specialized datasets | `src/data/datasets/` | Promote a canonical master dataset + project anomaly-detection / forecasting / energy datasets. |

Cross-stage contracts (`Finding`, `Severity`, `ColumnGroups`, report writers,
the strict Pydantic base) live in the neutral `src/data/_common/` package.
Project paths are centralized in `src/config.py`; per-stage policy lives in
`configs/*.yaml`.

See the stage reference docs under [docs/pipeline/](docs/pipeline/):
`data_cleaning.md`, `time_series_engineering.md`, `feature_engineering.md`,
`specialized_datasets.md` ([docs/README.md](docs/README.md) is the full map).

---

## Project Structure

```text
InjexCore/
├── configs/                 # Per-stage YAML policy + schema_lock.json contract
├── data/                    # raw / processed / features / datasets (git-ignored)
├── docs/                    # Stage references, master version, session notes
├── notebooks/               # Exploratory EDA only (git-ignored)
├── scripts/                 # One-off build/EDA tooling (dictionary, classification, EDA notebook)
├── src/
│   ├── config.py            # Central project paths
│   ├── data_generation.py   # Synthetic dataset generator
│   ├── preprocessing.py     # CLI shim dispatching --stage
│   └── data/
│       ├── _common/         # Shared contracts (Finding, Severity, ColumnGroups, StrictModel)
│       ├── cleaning/
│       ├── time_series/
│       ├── feature_engineering/
│       └── datasets/
├── tests/                   # pytest unit tests mirroring src/data/
├── pyproject.toml           # Packaging, dependencies, ruff/mypy/pytest config
├── requirements.txt         # Pinned runtime mirror
└── requirements-dev.txt     # Pinned dev tooling mirror
```

---

## Installation

Requires Python ≥ 3.11.

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
# source .venv/bin/activate                       # Unix

pip install -e ".[dev]"      # editable install + dev tooling
pre-commit install           # enable ruff/mypy/gitleaks hooks
```

The editable install puts `src` on the import path, so `import src...` and the
`python -m src...` commands below work from any working directory — no
`sys.path` manipulation required.

---

## Usage

```bash
# Generate the synthetic dataset → data/raw/dataset_pro.csv
python src/data_generation.py

# Run individual preprocessing stages (append --no-write for diagnostic-only)
python -m src.data.cleaning.run_cleaning
python -m src.data.time_series.run_ts_engineering
python -m src.data.feature_engineering.run_feature_engineering
python -m src.data.datasets.run_datasets

# Or drive stages through the shim
python -m src.preprocessing --stage cleaning      # default
python -m src.preprocessing --stage features      # cleaning → ts → fe
python -m src.preprocessing --stage all           # cleaning → ts → fe → datasets

# Refresh the schema-lock contract after an intentional master-schema change
python -m src.data.datasets.run_datasets --write-schema-lock   # commit configs/schema_lock.json
```

Chained `--stage` modes (`features`, `all`) accept only the universal flags
`--no-write` and `--log-level`; stage-specific flags require a single `--stage`.

### Development

```bash
ruff check .          # lint
ruff format .         # format
mypy src              # type-check (lenient baseline)
pytest                # unit tests
```

---

## Dataset

The MVP uses two data lineages:

* **Synthetic** (`data_generation.py` → `dataset_pro.csv`) — simulated injection
  telemetry (temperatures, pressures, cycle/injection/cooling times, injection
  velocity, screw position, specific volume, energy consumption) with controlled
  anomaly injection. Target: `machine_state` ∈ {normal, warning, anomaly}.
* **Real pellet-granulation line** (`Dades_pellet.csv`) — the dataset the
  preprocessing pipeline runs on end-to-end. Its column schema is documented
  privately (see `.claude/CLAUDE.local.md`).

Raw data is read-only and git-ignored; processed/feature/dataset artifacts are
generated locally by the pipeline.

---

## Tech Stack

Python · pandas · NumPy · pydantic · PyYAML · pyarrow · scikit-learn (modeling
layer) · matplotlib / seaborn · pytest · ruff · mypy · pre-commit.

---

## Status

Preprocessing layer complete (four stages, semantic-driven, with unit tests and
per-stage reference docs). In progress: anomaly-criterion definition. Not
started: the classification/anomaly models (`src/models/`), output API, and
visualization dashboard.

---

## Contributing

Currently a personal project. Contributions may open in later stages.

## Contact

Created by Lluís Sagué — open to collaboration and feedback.
