"""Shared contract pins and the view-envelope ``meta`` builder.

Single source for the static pins used by ``/dashboard/meta`` and every view
endpoint's envelope. Reads no artifacts.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.api.copy.notices import NoticeKey, notices_for
from src.api.schemas.common import ViewMeta
from src.dashboard.contract import CANONICAL_BOM_RUN_ID, CANONICAL_RUN_ID

# Static pins. contractVersion is a literal; dataGeneratedAt and trainWindowEnd
# are pinned to the canonical run.
# TODO(debt): source dataGeneratedAt / trainWindowEnd from the run manifest /
# behaviour fit-window in the artifact-reader slice (no artifact reads yet).
CONTRACT_VERSION = "1.0"
DATA_GENERATED_AT = "2026-06-16T10:25:58Z"
TRAIN_WINDOW_END = "2024-09-03"


def build_view_meta(notice_keys: Sequence[NoticeKey]) -> ViewMeta:
    """Compose the envelope ``meta`` block for a view endpoint."""
    return ViewMeta(
        contract_version=CONTRACT_VERSION,
        run_id=CANONICAL_RUN_ID,
        bom_run_id=CANONICAL_BOM_RUN_ID,
        data_generated_at=DATA_GENERATED_AT,
        notices=notices_for(notice_keys),
    )
