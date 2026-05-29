"""Re-export the shared :class:`Finding` / :class:`Severity` types and
report writers from :mod:`src.data.cleaning.reporting`.

The specialized-datasets stage emits ``Finding`` records describing
master-dataset integrity checks and the column projection decisions of
each downstream dataset. The format is identical to the cleaning,
time-series and feature-engineering reports so a single downstream
reader can consume all four.
"""
from src.data.cleaning.reporting import (
    Finding,
    Severity,
    write_json,
    write_markdown,
)

__all__ = ["Finding", "Severity", "write_json", "write_markdown"]
