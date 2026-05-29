"""Re-export the shared :class:`Finding` / :class:`Severity` types and
report writers from :mod:`src.data.cleaning.reporting`.

The feature engineering pipeline emits audit-style ``Finding`` records
(severity ``NORMAL`` / ``AWARE`` / ``IMPORTANT``) describing each generated
feature and any cross-column data-quality issues encountered while
building it. The format is identical to the cleaning and time-series
reports so a single downstream reader can consume all three.
"""
from src.data.cleaning.reporting import (
    Finding,
    Severity,
    write_json,
    write_markdown,
)

__all__ = ["Finding", "Severity", "write_json", "write_markdown"]
