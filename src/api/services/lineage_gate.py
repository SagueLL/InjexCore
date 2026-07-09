"""Lineage gate: evaluate the dashboard chain once, project to an API result.

Wraps the existing ``validate_dashboard_chain`` (src/dashboard/lineage.py) — the
API layer never re-implements lineage logic. Reads only run manifests (JSON),
never parquet. Called once at FastAPI startup; the result is cached on
``app.state.dashboard_lineage``.
"""

from __future__ import annotations

from src.api.schemas import CamelModel
from src.dashboard.contract import Severity
from src.dashboard.lineage import validate_dashboard_chain


class ApiLineageResult(CamelModel):
    """API-facing projection of DashboardChainValidation (camelCase on the wire)."""

    is_valid: bool
    canonical_match: bool
    severity: Severity  # Literal["ok", "warning", "invalid"] — surfaced verbatim
    warnings: list[str]


def evaluate_lineage() -> ApiLineageResult:
    """Run the canonical dashboard-chain validation and project it to the API shape."""
    result = validate_dashboard_chain()
    return ApiLineageResult(
        is_valid=result.is_valid,
        canonical_match=result.canonical_match,
        severity=result.severity,
        warnings=list(result.warnings),
    )
