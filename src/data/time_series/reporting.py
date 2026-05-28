"""Re-export the shared :class:`Finding` / :class:`Severity` types and the
JSON / Markdown report writers from :mod:`src.data.cleaning.reporting`.

The time-series engineering pipeline emits audit-style ``Finding`` records
(severity ``NORMAL``/``AWARE``) describing each generated feature; the
report format is identical to the cleaning report so a single downstream
reader can consume both.
"""
from src.data.cleaning.reporting import (
    Finding,
    Severity,
    write_json,
    write_markdown,
)

__all__ = ["Finding", "Severity", "write_json", "write_markdown"]
