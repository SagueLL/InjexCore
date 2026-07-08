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
#
# dataGeneratedAt is the LATEST completion timestamp across the pinned 11-component
# chain (scoring_experiment, 2026-06-16T14:51:48Z) — i.e. when the served data
# finished being generated. It is deliberately neither the run-id mint time
# (10:25:58Z, which the run id already carries) nor the behaviour fit time
# (10:26:24Z): behaviour completes *first*, and every artifact this API actually
# serves — sensor health, drift, incidents, scoring experiment — was written
# 4h25m later.
# TODO(debt): derive at startup instead of pinning. Blocked on a per-component key
# map: manifests record completion under `created_at` OR `fit_timestamp`.
CONTRACT_VERSION = "1.1"
DATA_GENERATED_AT = "2026-06-16T14:51:48Z"
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
