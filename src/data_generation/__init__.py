"""Synthetic data generation (MVP scaffolding).

Self-contained generator that produces the synthetic injection-moulding
dataset used before real-machine telemetry is wired in. It sits *upstream*
of the preprocessing pipeline and has no dependency on it.

Run it as a module::

    python -m src.data_generation.generate   # → data/raw/dataset_pro.csv

The implementation lives in :mod:`src.data_generation.generate`.
"""
