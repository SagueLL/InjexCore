"""Re-export the shared :class:`Finding` / :class:`Severity` types and
report writers from :mod:`src.preprocessing._common.reporting`.

Behaviour Intelligence emits ``Finding`` records describing profile
coverage, under-sized regimes, low-variance sensors and the documented
non-derivable regimes. The format is identical to the cleaning,
time-series, feature-engineering and specialized-datasets reports so a
single downstream reader can consume them all.
"""

from src.preprocessing._common.reporting import (
    Finding,
    Severity,
    write_json,
    write_markdown,
)

__all__ = ["Finding", "Severity", "write_json", "write_markdown"]
