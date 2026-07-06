"""Dashboard endpoints: run identity/lineage meta + the overview view.

``/meta`` returns the approved canonical run identity plus the lineage-gate
status evaluated once at startup (cached on app.state.dashboard_lineage by the
lifespan). ``/overview`` is the first ``{meta, data}`` view endpoint and fails
closed on invalid lineage. Neither reads artifacts per request; identity
fields are static pins shared via ``src.api.services.view_meta`` (sourcing
them from manifests is a later slice).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.api.dependencies import require_valid_dashboard_lineage
from src.api.schemas.common import Envelope
from src.api.schemas.dashboard_meta import DashboardMeta
from src.api.schemas.overview import DashboardSummary
from src.api.services.overview import build_overview_response
from src.api.services.view_meta import (
    CONTRACT_VERSION,
    DATA_GENERATED_AT,
    TRAIN_WINDOW_END,
)
from src.dashboard.contract import CANONICAL_BOM_RUN_ID, CANONICAL_RUN_ID

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/meta",
    summary="Dashboard run identity and lineage gate",
    description=(
        "Returns the approved canonical run identity, train-window boundary, and "
        "the lineage-gate status evaluated once at startup. Returns 200 even when "
        "lineage severity is 'warning' or 'invalid' (it is the gate banner "
        "source); data endpoints fail closed on 'invalid'."
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


@router.get(
    "/overview",
    summary="Executive overview summary (enveloped)",
    description=(
        "Returns the {meta, data} envelope for the Executive Overview view. "
        "Fails closed with 503 LINEAGE_INVALID when the startup lineage gate is "
        "missing or invalid; 'ok'/'warning' severities pass. Serves stable "
        "canonical-run values; no artifact reads per request."
    ),
    response_model_exclude_none=True,
    dependencies=[Depends(require_valid_dashboard_lineage)],
)
async def get_dashboard_overview() -> Envelope[DashboardSummary]:
    return build_overview_response()
