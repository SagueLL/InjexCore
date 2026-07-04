"""Liveness endpoint: HTTP 200 + exact static payload, no data access."""

from __future__ import annotations

from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def test_health_returns_200() -> None:
    assert client.get("/api/v1/health").status_code == 200


def test_health_payload_is_exact() -> None:
    assert client.get("/api/v1/health").json() == {
        "status": "ok",
        "service": "injexcore-api",
        "version": "0.2",
    }
