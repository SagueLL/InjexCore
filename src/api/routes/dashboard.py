"""Dashboard meta endpoint: run identity + lineage-gate shape (B2.3 foundation).

Returns the approved canonical run identity and a STATIC lineage-status shape.
Real lineage validation (validate_dashboard_chain) is wired in B2.4; this
endpoint reads no artifacts, manifests, or run folders.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas.dashboard_meta import DashboardMeta, LineageStatus
from src.dashboard.contract import CANONICAL_BOM_RUN_ID, CANONICAL_RUN_ID

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# B2.3 pins. contractVersion is a literal; dataGeneratedAt and trainWindowEnd are
# pinned to the canonical run here and will be sourced from the run manifest /
# behaviour fit-window in B2.4+ (no artifact reads in this slice).
CONTRACT_VERSION = "1.0"
DATA_GENERATED_AT = "2026-06-16T10:25:58Z"
TRAIN_WINDOW_END = "2024-09-03"
LINEAGE_STUB_WARNING = (
    "Lineage validation is not yet connected in B2.3. This endpoint returns "
    "the approved canonical run identity only."
)


@router.get(
    "/meta",
    summary="Dashboard run identity and lineage gate",
    description=(
        "Returns the approved canonical run identity, train-window boundary, "
        "and lineage-gate status. B2.3 foundation: lineage is a static "
        "placeholder (real validation lands in B2.4); no artifacts are read."
    ),
)
async def get_dashboard_meta() -> DashboardMeta:
    return DashboardMeta(
        contract_version=CONTRACT_VERSION,
        run_id=CANONICAL_RUN_ID,
        bom_run_id=CANONICAL_BOM_RUN_ID,
        data_generated_at=DATA_GENERATED_AT,
        train_window_end=TRAIN_WINDOW_END,
        lineage=LineageStatus(
            is_valid=True,
            canonical_match=True,
            severity="warning",
            warnings=[LINEAGE_STUB_WARNING],
        ),
        required_warnings=[],
    )
