# InjexCore

**AI-powered predictive maintenance for plastic injection machines**

---

## Project Overview

InjexCore is an early-stage project focused on building a predictive maintenance system for plastic injection machines.

The goal is to analyze machine data, detect anomalous behavior, and anticipate potential failures before they occur—helping reduce downtime, production defects, and operational costs.

This project follows a practical, incremental approach: starting with simulated data and evolving into a functional, real-world applicable system.

---

## 3-Month MVP Objective

The initial goal is to build a **simple but functional system** that:

* Works with simulated injection machine data
* Detects anomalous behavior
* Outputs a clear machine state (Normal / Warning / Anomaly)
* Provides visual insights into machine performance over time
* Can be presented as a solid technical portfolio project

---

## Problem Statement

Companies operating plastic injection machines often face:

* Unexpected machine downtime
* Production defects (scrap)
* High energy consumption
* Inefficient or reactive maintenance strategies

InjexCore aims to shift from **reactive to predictive maintenance** by identifying abnormal patterns early.

---

## Current Progress

### Completed

* Project structure and repository setup
* Synthetic dataset generation
* Simulation of industrial variables:

  * Temperature
  * Pressure
  * Cycle time
* Initial data visualization:

  * Realistic machine behavior over time
  * Detection of visible anomalous patterns

### In Progress

* Data preprocessing and normalization
* Definition of anomaly criteria

### Next Steps

* Implement anomaly detection model
* Define machine states (Normal / Warning / Anomaly)
* Build clear output system
* Improve visualizations (dashboard-style)

---

## Project Structure

```text
InjexCore/
├── data/
│   ├── raw/
│   │   └──dataset_pro.cvs
│   └── processed/
│
├── images/
│
├── notebooks/
│   ├── comprobacion_dataset.py
│   └── eda.ipynb
│
├── src/
│   ├── data_generation.py
│   ├── preprocessing.py
│   ├── anomaly_detection.py
│   └── visualization.py
│
├── README.md
├── requirements.txt
└── .gitignore
```

---

## Dataset Description

The current system uses **synthetic data** to simulate the behavior of a plastic injection machine.

### Variables:

* Material Temperature
* Mold Temperature
* Injecction Pressure
* Manteinance Pressure
* Cavity Pressure
* Injection Velocity
* Screw Position
* Injection Time
* Cooling Time
* Cycle Time
* Cycle count
* Specific Volume
* Machine stops
* Energy consumption

### Data Characteristics:

* Normal operating patterns are simulated
* Controlled anomalies are introduced manually
* Time-series behavior allows pattern recognition

This approach enables rapid experimentation before integrating real industrial data.

---

## Tech Stack

* Python
* Pandas
* NumPy
* Matplotlib
* Seaborn
* Scikit-learn
* Jupyter Notebook
* Git & GitHub

---

## Roadmap

### Month 1 — Data & Understanding

* Define machine variables
* Generate synthetic dataset
* Explore and clean data
* Identify patterns

### Month 2 — First Functional System

* Implement anomaly detection model
* Generate interpretable outputs
* Build initial visualizations

### Month 3 — Consolidation

* Improve robustness
* Reduce false positives
* Prepare demo
* Finalize documentation

---

## Expected Outcome

> "A small system capable of analyzing injection machine data and detecting anomalies before failures occur."

---

## Long-Term Vision

InjexCore aims to evolve into a **real predictive maintenance platform** for industrial environments, with:

* Real-time data integration
* Advanced machine learning models
* Scalable architecture (SaaS)
* Industrial deployment capabilities

---

## Status

Work in progress — early-stage MVP

---

## Contributing

This is currently a personal project. Contributions may be opened in later stages.

---

## Contact

Created by Lluís Sagué
Feel free to connect or reach out for collaboration or feedback.
