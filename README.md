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

A linear, modular **Data Foundation** feeds an **Intelligence Layer** that
characterises normal behaviour and surfaces deviations, plus a read-only
**External Context Layer**. Predictive models and a serving API are planned:

```
data_generation → cleaning → time_series → feature_engineering → datasets   (Data Foundation)
        → behaviour → correlation·pca → anomaly → sensor_health → drift      (Intelligence Layer)
        → incidents → reference governance → controlled scoring → decision   (review + governance)
        context/{bom, operational} ── read-only joins against the master + scores (interpretation only)
        → [models] → [api]                                                   (planned)
```

| Layer | Package | Responsibility |
|---|---|---|
| Data Foundation | `src/preprocessing/{cleaning,time_series,feature_engineering,datasets}/` | Detect+remediate cleaning → temporal/state features → cross-column features → a canonical master + model-family datasets. Parameter-free. |
| Behaviour Intelligence | `src/intelligence/behaviour/` | Operational profiles + per-profile statistical baselines, fit leakage-safe on a train window; emits the `is_train` contract every downstream component reuses. |
| Correlation · PCA · Anomaly | `src/intelligence/{correlation,pca,anomaly}/` | Per-profile correlation references, RobustScaler+PCA (T²/Q), and four explainable anomaly detectors with a combined severity. |
| Sensor Health | `src/intelligence/sensor_health/` | Instrumentation-anomaly rule families (flatline, variance collapse, …); recommends quarantine, never auto-excludes. |
| Drift | `src/intelligence/drift/` | Windowed univariate/multivariate/context/correlation drift vs the train reference; raw vs honestly-labeled `healthy_only_proxy` views. |
| Incidents | `src/intelligence/incidents/` | Events → reviewable incidents; associative relationships (`causality_status=unknown`); quarantine actions pending human approval. |
| Reference Governance | `src/intelligence/reference/` | Tracks the immutable `reference_v1` baseline + quarantine/candidate proposals — proposes, never approves, refits, or excludes. |
| Controlled Scoring | `src/intelligence/scoring_experiment/` | Interpretive post-processing scenarios over persisted scores (never rescores/refits) + a decision-report addendum. |
| External Context | `src/context/{bom,operational}/` | BOM/operational context joined against the master timeline + persisted scores; analytical only, never a model input. |

Each Intelligence/Context component is **run-versioned** (`runs/<run_id>/`,
manifest written last as the completion marker) and verifies **lineage**
against its upstreams (fail closed on a mismatch). Cross-stage contracts live in
`src/preprocessing/_common/` (+ `src/intelligence/_common/`); project paths in
`src/config.py`; policy in `configs/*.yaml`.

See [docs/architecture/intelligence_dataflow.md](docs/architecture/intelligence_dataflow.md)
for the end-to-end dataflow + contracts, the stage refs under
[docs/pipeline/](docs/pipeline/) and [docs/intelligence/](docs/intelligence/),
and the context refs under [docs/context/](docs/context/)
([docs/README.md](docs/README.md) is the full map).

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
│   ├── data_generation/     # Synthetic dataset generator (generate.py)
│   ├── preprocessing/       # Preprocessing pipeline + combined --stage CLI (__main__.py)
│   │   ├── _common/         # Shared contracts (Finding, Severity, ColumnGroups, StrictModel)
│   │   ├── cleaning/
│   │   ├── time_series/
│   │   ├── feature_engineering/
│   │   └── datasets/
│   ├── intelligence/        # Intelligence Layer (run-versioned; characterises normal + deviation)
│   │   ├── _common/         # Run versioning, lineage checks, manifest, behaviour loaders
│   │   ├── behaviour/       # Operational profiles + statistical baselines (the is_train contract)
│   │   ├── correlation/ pca/ anomaly/    # Per-profile references + explainable detectors
│   │   ├── sensor_health/ drift/         # Instrumentation anomalies + windowed drift
│   │   ├── incidents/ reference/ scoring_experiment/   # Review pack, governance, decision support
│   │   └── __main__.py      # Component dispatcher (--component <name>)
│   └── context/             # External Context Layer (read-only joins; analytical only)
│       ├── bom/             # BOM operational context
│       └── operational/     # Operational context overlay
├── tests/                   # pytest unit + integration tests mirroring src/
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
python -m src.data_generation.generate

# Run individual preprocessing stages (append --no-write for diagnostic-only)
python -m src.preprocessing.cleaning.run_cleaning
python -m src.preprocessing.time_series.run_ts_engineering
python -m src.preprocessing.feature_engineering.run_feature_engineering
python -m src.preprocessing.datasets.run_datasets

# Or drive stages through the shim
python -m src.preprocessing --stage cleaning      # default
python -m src.preprocessing --stage features      # cleaning → ts → fe
python -m src.preprocessing --stage all           # cleaning → ts → fe → datasets

# Refresh the schema-lock contract after an intentional master-schema change
python -m src.preprocessing.datasets.run_datasets --write-schema-lock   # commit configs/schema_lock.json
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

**Done:** the Data Foundation (four preprocessing stages, semantic-driven) and
the Intelligence Layer — Behaviour, Correlation, PCA, Anomaly, Sensor Health,
Drift, Incident Aggregation, Reference Governance and the Controlled Scoring
Experiment — plus the BOM and Operational external-context layers. Every
Intelligence/Context component is run-versioned (manifest-last) with fail-closed
lineage checks, covered by unit + integration tests and per-component reference
docs. A **read-only dashboard consumption contract + lineage validator**
([`src/dashboard/`](src/dashboard/),
[docs/dashboard/dashboard_data_contract.md](docs/dashboard/dashboard_data_contract.md))
pins the canonical rematerialized chain and refuses stale / non-canonical /
broken chains. The system is ready for **technical validation dashboard
planning, not production deployment**.

**In progress:** human review of the Iteration C decision report (the pending
`inlet_hopper_points` quarantine approval and the deferred Reference v2
candidate). **Not started:** the read-only Technical Validation Dashboard MVP
(contract + validator in place; UI not started); an *approved* Reference v2
(human-gated refit) and a true PCA/Mahalanobis rescoring — both explicitly
deferred and gated on the decision report; predictive models (`src/models/`),
output API, and the visualization dashboard.

---

## Contributing

Currently a personal project. Contributions may open in later stages.

## Contact

Created by Lluís Sagué — open to collaboration and feedback.
