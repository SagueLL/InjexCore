"""FastAPI application factory for the InjexCore read-only dashboard API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio.to_thread
from fastapi import FastAPI

from src.api import API_VERSION
from src.api.errors import ApiError
from src.api.exception_handlers import api_error_handler
from src.api.routes.dashboard import router as dashboard_router
from src.api.routes.health import router as health_router
from src.api.services import lineage_gate
from src.api.services.prewarm import prewarm_enabled, prewarm_views


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Evaluate the dashboard lineage chain once at startup; cache on app.state.
    # Data endpoints fail closed when severity == "invalid".
    lineage = lineage_gate.evaluate_lineage()
    app.state.dashboard_lineage = lineage
    # Build the view caches now so an artifact failure lands in the log rather than
    # in front of a demo audience. Skipped behind a closed gate (those endpoints
    # 503 regardless) and off when INJEXCORE_API_PREWARM=0. The builders are sync
    # and read parquet, so they run in a worker thread; prewarm_views never raises,
    # and an unbuilt view still answers with its 503 envelope on first request.
    if lineage.severity != "invalid" and prewarm_enabled():
        await anyio.to_thread.run_sync(prewarm_views)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="InjexCore API", version=API_VERSION, lifespan=lifespan)
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    return app


app = create_app()
