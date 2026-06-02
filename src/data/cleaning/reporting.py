"""Backward-compatible re-export of the shared reporting contracts.

The canonical definitions now live in :mod:`src.data._common.reporting`.
This shim keeps the historical ``src.data.cleaning.reporting`` import path
valid for the cleaning modules and their tests.
"""

from src.data._common.reporting import (
    Finding,
    Severity,
    write_json,
    write_markdown,
)

__all__ = ["Finding", "Severity", "write_json", "write_markdown"]
