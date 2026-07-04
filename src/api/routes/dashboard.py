"""Dashboard meta endpoint: run identity + lineage gate.

Returns the approved canonical run identity plus the lineage-gate status
evaluated once at startup (cached on app.state.dashboard_lineage by the
lifespan). Reads no artifacts per request; the identity fields below are still
static pins (sourcing them from manifests is a later slice).
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.api.schemas.dashboard_meta import DashboardMeta
from src.dashboard.contract import CANONICAL_BOM_RUN_ID, CANONICAL_RUN_ID

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Static pins. contractVersion is a literal; dataGeneratedAt and trainWindowEnd
# are pinned to the canonical run and will be sourced from the run manifest /
# behaviour fit-window in a later slice (no artifact reads in this endpoint).
CONTRACT_VERSION = "1.0"
DATA_GENERATED_AT = "2026-06-16T10:25:58Z"
TRAIN_WINDOW_END = "2024-09-03"


@router.get(
    "/meta",
    summary="Dashboard run identity and lineage gate",
    description=(
        "Returns the approved canonical run identity, train-window boundary, and "
        "the lineage-gate status evaluated once at startup. Returns 200 even when "
        "lineage severity is 'warning' or 'invalid' (it is the gate banner "
        "source); data endpoints fail closed on 'invalid' in a later slice."
    ),
)
async def get_dashboard_meta(request: Request) -> DashboardMeta:
    return DashboardMeta(
        contract_version=CONTRACT_VERSION,
        run_id=CANONICAL_RUN_ID,
        bom_run_id=CANONICAL_BOM_RUN_ID,
        data_generated_at=DATA_GENERATED_AT,
        train_window_end=TRAIN_WINDOW_END,
        lineage=request.app.state.dashboard_lineage,
        required_warnings=[],
    )
