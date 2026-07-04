"""Reusable FastAPI dependencies for the read-only dashboard API."""

from __future__ import annotations

from fastapi import Request

from src.api.errors import LineageInvalidError


def require_valid_dashboard_lineage(request: Request) -> None:
    """Fail closed unless the startup lineage gate is present and not invalid.

    Attach to data endpoints (later slices) via ``Depends``. The health and meta
    endpoints intentionally do NOT use it. Blocks only missing lineage and
    ``severity == "invalid"``; ``ok``/``warning`` (and any non-invalid state) pass.
    """
    lineage = getattr(request.app.state, "dashboard_lineage", None)
    if lineage is None or lineage.severity == "invalid":
        raise LineageInvalidError()
