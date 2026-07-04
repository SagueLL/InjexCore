"""FastAPI application factory for the InjexCore read-only dashboard API."""

from __future__ import annotations

from fastapi import FastAPI

from src.api import API_VERSION
from src.api.routes.dashboard import router as dashboard_router
from src.api.routes.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="InjexCore API", version=API_VERSION)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    return app


app = create_app()
