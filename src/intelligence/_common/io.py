"""Shim: generic Intelligence-Layer I/O helpers.

``load_master`` / ``write_table`` / ``write_manifest`` are component-agnostic
but currently live in :mod:`src.intelligence.behaviour.io` (the first
component to need them). Re-exported here so sibling components depend on
``_common`` rather than on behaviour's internals.

TODO(debt): when behaviour is next touched, move the three helpers here and
flip behaviour's imports — one-line cleanup, tracked in the component docs.
"""

from __future__ import annotations

from src.intelligence.behaviour.io import (
    DEFAULT_MASTER_IN,
    load_master,
    write_manifest,
    write_table,
)

__all__ = ["DEFAULT_MASTER_IN", "load_master", "write_manifest", "write_table"]
