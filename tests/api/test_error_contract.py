"""API error contract + fail-closed lineage dependency (LINEAGE_INVALID 503)."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from src.api.dependencies import require_valid_dashboard_lineage
from src.api.errors import ApiError
from src.api.exception_handlers import api_error_handler

_LINEAGE_INVALID_BODY = {
    "error": {
        "code": "LINEAGE_INVALID",
        "message": "Dashboard lineage validation failed.",
    }
}


def _protected_app(*, lineage: object | None, present: bool) -> FastAPI:
    # Throwaway app with a dummy protected route — no production dummy route.
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    if present:
        app.state.dashboard_lineage = lineage

    @app.get("/protected", dependencies=[Depends(require_valid_dashboard_lineage)])
    async def _protected() -> dict[str, bool]:
        return {"allowed": True}

    return app


def test_invalid_lineage_returns_503_contract() -> None:
    app = _protected_app(lineage=SimpleNamespace(severity="invalid"), present=True)
    resp = TestClient(app).get("/protected")
    assert resp.status_code == 503
    assert resp.json() == _LINEAGE_INVALID_BODY


def test_missing_lineage_returns_503_contract() -> None:
    app = _protected_app(lineage=None, present=False)
    resp = TestClient(app).get("/protected")
    assert resp.status_code == 503
    assert resp.json() == _LINEAGE_INVALID_BODY


def test_warning_lineage_allows_request() -> None:
    app = _protected_app(lineage=SimpleNamespace(severity="warning"), present=True)
    resp = TestClient(app).get("/protected")
    assert resp.status_code == 200
    assert resp.json() == {"allowed": True}


def test_valid_lineage_allows_request() -> None:
    # The gate blocks only "invalid" (and missing), so any other value passes.
    app = _protected_app(lineage=SimpleNamespace(severity="valid"), present=True)
    resp = TestClient(app).get("/protected")
    assert resp.status_code == 200
    assert resp.json() == {"allowed": True}


def test_ok_lineage_allows_request() -> None:
    # "ok" is the real verbatim value for a passing chain.
    app = _protected_app(lineage=SimpleNamespace(severity="ok"), present=True)
    resp = TestClient(app).get("/protected")
    assert resp.status_code == 200
    assert resp.json() == {"allowed": True}
