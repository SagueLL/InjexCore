# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**InjexCore** is a predictive maintenance system for plastic injection machines. It detects anomalous behavior in machine operation by classifying each cycle as `normal`, `warning`, or `anomaly`. The project uses synthetic data during the MVP phase.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Generate synthetic dataset (outputs to data/raw/dataset_pro.csv)
python src/data_generation.py

# Quick dataset validation
python notebooks/comprobación_dataset.py

# Exploratory data analysis
jupyter notebook notebooks/eda.ipynb
```

No test suite or linting tools are configured yet.

## Architecture

The pipeline is modular with four layers, each in a dedicated `src/` file:

```
data_generation.py  →  preprocessing.py  →  anomaly_detection.py  →  visualization.py
```

**`src/data_generation.py`** — Only fully implemented module. Generates 2,000 synthetic records simulating injection machine cycles with 16 features (temperatures, pressures, timing, energy). Includes controlled drift (machine degradation over time) and 3% anomaly injection at three severity levels.

**`src/preprocessing.py`** — Placeholder. Intended for normalization and feature engineering on `data/raw/dataset_pro.csv`.

**`src/anomaly_detection.py`** — Placeholder. Intended for the ML classification model (scikit-learn based).

**`src/visualization.py`** — Placeholder. Intended for dashboard-style plots saved to `images/`.

**`notebooks/`** — Validation scripts and EDA. Not part of the production pipeline.

## Dataset Schema

The generated CSV has these key columns:
- `machine_state` — target label: `normal` / `warning` / `anomaly`
- `drift` — internal degradation variable (used during generation, not a model feature)
- Temperature features: `material_temp`, `mold_temp`
- Pressure features: `injection_pressure`, `maintenance_pressure`, `cavity_pressure`
- Timing features: `injection_time`, `cooling_time`, `cycle_time`
- Other: `injection_velocity`, `screw_position`, `specific_volume`, `energy_consumption`

## Current Status (MVP Month 1–2)

- **Done:** Data generation with physical constraints and anomaly injection
- **In progress:** Preprocessing and anomaly criteria definition
- **Not started:** Anomaly detection model, output system, visualization dashboard
