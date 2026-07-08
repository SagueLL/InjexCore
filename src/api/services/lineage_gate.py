"""Lineage gate: evaluate the dashboard chain once, project to an API result.

Wraps the existing ``validate_dashboard_chain`` (src/dashboard/lineage.py) — the
API layer never re-implements lineage logic. Reads only run manifests (JSON),
never parquet. Called once at FastAPI startup; the result is cached on
``app.state.dashboard_lineage``.

Warnings are path-redacted here rather than in the validator: the validator's
verbose paths are useful for local diagnostics, and the API is the layer that
owes the "no run folders, no internals" guarantee. ``/meta`` stays reachable when
lineage is invalid — i.e. exactly when the warning list is longest.
"""

from __future__ import annotations

from src.api.redaction import redact_paths
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
    """Run the canonical dashboard-chain validation and project it to the API shape.

    Component names and failure classes survive redaction; filesystem paths do not.
    """
    result = validate_dashboard_chain()
    return ApiLineageResult(
        is_valid=result.is_valid,
        canonical_match=result.canonical_match,
        severity=result.severity,
        warnings=[redact_paths(warning) for warning in result.warnings],
    )
