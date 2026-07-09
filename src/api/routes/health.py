"""Service liveness endpoint.

Liveness only: confirms the API process is up. Reads no data, artifacts,
configs, manifests, run folders, or lineage, so it stays green even when
downstream artifacts are absent or the dashboard chain is mid-rebuild.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from src.api import API_VERSION, SERVICE_NAME

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get(
    "/health",
    summary="Service liveness check",
    description=(
        "Static liveness payload confirming the API process is running. "
        "Does not access data, artifacts, or lineage."
    ),
)
async def get_health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, version=API_VERSION)
