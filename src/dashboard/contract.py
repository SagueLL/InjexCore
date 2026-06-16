"""Canonical dashboard consumption contract (DASH-01 / DASH-02).

Read-only. Declares the canonical rematerialized chain the Technical Validation
Dashboard MVP is pinned to, the component registry the lineage validator walks,
and the validation result model. Importing this module performs no I/O — the
registry is built lazily from the data directories in :mod:`src.config`.

The companion narrative contract lives in
``docs/dashboard/dashboard_data_contract.md``: allowed artifacts, forbidden MVP
views, required warning copy and the read-only / no-approval / no-refit
boundaries. This module is the executable half of that contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field

from src.config import CONTEXT_DIR, INTELLIGENCE_DIR
from src.preprocessing._common.models import StrictModel

#: The one chain the dashboard MVP treats as authoritative. Every other
#: completed run is surfaced only as non-canonical / stale, never as valid.
CANONICAL_RUN_ID = "remat-v1-20260616T102558Z"
CANONICAL_BOM_RUN_ID = "20260612T124909Z"

Severity = Literal["ok", "warning", "invalid"]
RunKind = Literal["canonical", "bom"]


@dataclass(frozen=True)
class ComponentSpec:
    """One run-versioned component the dashboard chain depends on.

    ``component`` is the exact string the manifest writes (these are NOT
    uniform — e.g. ``reference_governance``, ``operational_context``,
    ``bom_context``); ``run_kind`` selects which pinned run id the component is
    expected at; ``is_leaf`` marks the intelligence leaves that carry explicit
    behaviour provenance (PROV-01).
    """

    name: str
    root: Path
    manifest_name: str
    component: str
    run_kind: RunKind
    is_leaf: bool = False


def component_specs(
    intelligence_dir: Path = INTELLIGENCE_DIR, context_dir: Path = CONTEXT_DIR
) -> list[ComponentSpec]:
    """Build the registry rooted at the given data dirs (injectable for tests)."""
    return [
        ComponentSpec(
            "behaviour",
            intelligence_dir / "behaviour",
            "behaviour_fit_manifest.json",
            "behaviour",
            "canonical",
        ),
        ComponentSpec(
            "correlation",
            intelligence_dir / "correlation",
            "correlation_fit_manifest.json",
            "correlation",
            "canonical",
            is_leaf=True,
        ),
        ComponentSpec(
            "pca",
            intelligence_dir / "pca",
            "pca_fit_manifest.json",
            "pca",
            "canonical",
            is_leaf=True,
        ),
        ComponentSpec(
            "anomaly",
            intelligence_dir / "anomaly",
            "anomaly_fit_manifest.json",
            "anomaly",
            "canonical",
            is_leaf=True,
        ),
        ComponentSpec(
            "sensor_health",
            intelligence_dir / "sensor_health",
            "sensor_health_manifest.json",
            "sensor_health",
            "canonical",
            is_leaf=True,
        ),
        ComponentSpec(
            "drift",
            intelligence_dir / "drift",
            "drift_manifest.json",
            "drift",
            "canonical",
        ),
        ComponentSpec(
            "incidents",
            intelligence_dir / "incidents",
            "incidents_manifest.json",
            "incidents",
            "canonical",
        ),
        ComponentSpec(
            "reference",
            intelligence_dir / "reference",
            "reference_governance_manifest.json",
            "reference_governance",
            "canonical",
        ),
        ComponentSpec(
            "scoring_experiment",
            intelligence_dir / "scoring_experiments",
            "controlled_scoring_manifest.json",
            "controlled_scoring_experiment",
            "canonical",
        ),
        ComponentSpec(
            "operational",
            context_dir / "operational",
            "operational_context_manifest.json",
            "operational_context",
            "canonical",
        ),
        ComponentSpec(
            "bom",
            context_dir / "bom",
            "bom_context_manifest.json",
            "bom_context",
            "bom",
        ),
    ]


class ComponentStatus(StrictModel):
    """Per-component resolution detail for one validated chain."""

    name: str
    expected_run_id: str
    present: bool
    manifest_valid: bool
    completion_complete: bool
    component_match: bool
    run_id_match: bool
    resolves: bool
    severity: Severity
    warnings: list[str] = Field(default_factory=list)


class LineageEdge(StrictModel):
    """A recorded upstream pin between two components, and its consistency.

    ``parent_run_id`` is the run id the child's manifest recorded for its
    parent (``None`` when not recorded — e.g. pre-PROV-01 behaviour
    provenance); ``consistent`` is whether it equals the canonical run id.
    """

    parent: str
    child: str
    parent_run_id: str | None
    consistent: bool


class DashboardChainValidation(StrictModel):
    """Result of :func:`src.dashboard.lineage.validate_dashboard_chain`."""

    run_id: str
    bom_run_id: str
    is_valid: bool
    severity: Severity
    canonical_match: bool
    warnings: list[str] = Field(default_factory=list)
    component_statuses: dict[str, ComponentStatus]
    lineage_edges: list[LineageEdge] = Field(default_factory=list)
