"""Response schema for GET /api/v1/dashboard/meta (run identity + lineage gate)."""

from __future__ import annotations

from src.api.schemas import CamelModel
from src.api.services.lineage_gate import ApiLineageResult


class DashboardMeta(CamelModel):
    contract_version: str
    run_id: str
    bom_run_id: str
    data_generated_at: str
    train_window_end: str
    lineage: ApiLineageResult
    required_warnings: list[str]
