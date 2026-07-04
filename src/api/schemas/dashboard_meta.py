"""Response schema for GET /api/v1/dashboard/meta (run identity + lineage gate)."""

from __future__ import annotations

from src.api.schemas import CamelModel
from src.dashboard.contract import Severity


class LineageStatus(CamelModel):
    is_valid: bool
    canonical_match: bool
    severity: Severity
    warnings: list[str]


class DashboardMeta(CamelModel):
    contract_version: str
    run_id: str
    bom_run_id: str
    data_generated_at: str
    train_window_end: str
    lineage: LineageStatus
    required_warnings: list[str]
