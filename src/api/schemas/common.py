"""Shared view-endpoint envelope schemas.

Every dashboard view endpoint wraps its payload in the same ``{meta, data}``
envelope (docs/dashboard/dashboard_api_contract.md §2): stable run identity
plus the view's required notices under ``meta``, the view summary under
``data``. The ``/dashboard/meta`` endpoint is deliberately flat and does not
use this envelope.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from src.api.schemas import CamelModel

DataT = TypeVar("DataT")


class Notice(CamelModel):
    """Required contract notice: key plus the exact §5.4 copy, nothing else."""

    key: str
    text: str


class ViewMeta(CamelModel):
    """Envelope ``meta`` block shared by all view endpoints."""

    contract_version: str
    run_id: str
    bom_run_id: str
    data_generated_at: str
    notices: list[Notice]


class Envelope(CamelModel, Generic[DataT]):
    """``{meta, data}`` response envelope for dashboard view endpoints."""

    meta: ViewMeta
    data: DataT
