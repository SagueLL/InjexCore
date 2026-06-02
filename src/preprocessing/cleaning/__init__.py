"""Data cleaning package for InjexCore.

Six failure-mode modules (missing values, duplicates, timestamps, frozen
sensors, physical ranges, state consistency) plus an orchestrator that
produces a cleaned dataset and a diagnostic report.

Public entry point: :func:`src.preprocessing.cleaning.run_cleaning.main`.
"""

from src.preprocessing.cleaning.reporting import Finding, Severity

__all__ = ["Finding", "Severity"]
