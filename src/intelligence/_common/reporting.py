"""Shim: shared Finding/report contracts for Intelligence-Layer components.

Same idiom as :mod:`src.intelligence.behaviour.reporting` — the canonical
implementations live in the neutral ``src/preprocessing/_common/`` package.
"""

from __future__ import annotations

from src.preprocessing._common.reporting import (
    Finding,
    Severity,
    write_json,
    write_markdown,
)

__all__ = ["Finding", "Severity", "write_json", "write_markdown"]
