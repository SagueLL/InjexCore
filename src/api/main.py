"""FastAPI application factory for the InjexCore read-only dashboard API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api import API_VERSION
from src.api.errors import ApiError
from src.api.exception_handlers import api_error_handler
from src.api.routes.dashboard import router as dashboard_router
from src.api.routes.health import router as health_router
from src.api.services import lineage_gate


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Evaluate the dashboard lineage chain once at startup; cache on app.state.
    # Data endpoints (later slice) fail closed when severity == "invalid".
    app.state.dashboard_lineage = lineage_gate.evaluate_lineage()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="InjexCore API", version=API_VERSION, lifespan=lifespan)
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    return app


app = create_app()
