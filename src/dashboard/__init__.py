"""Read-only consumption contract for the Technical Validation Dashboard.

This package is the executable half of ``docs/dashboard/dashboard_data_contract.md``.
It exposes the canonical run pins, the component registry, and a strictly
read-only lineage validator (:func:`validate_dashboard_chain`) a future
dashboard can use to refuse stale / non-canonical / broken chains. Nothing here
writes, refits, approves a quarantine, or mutates an artifact or score.
"""

from __future__ import annotations

from src.dashboard.contract import (
    CANONICAL_BOM_RUN_ID,
    CANONICAL_RUN_ID,
    ComponentSpec,
    ComponentStatus,
    DashboardChainValidation,
    LineageEdge,
    component_specs,
)
from src.dashboard.lineage import validate_dashboard_chain

__all__ = [
    "CANONICAL_RUN_ID",
    "CANONICAL_BOM_RUN_ID",
    "ComponentSpec",
    "ComponentStatus",
    "LineageEdge",
    "DashboardChainValidation",
    "component_specs",
    "validate_dashboard_chain",
]
