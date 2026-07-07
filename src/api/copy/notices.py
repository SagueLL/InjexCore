"""Required-notice copy registry.

Notice presence is part of the API contract, not a frontend courtesy
(docs/dashboard/dashboard_api_contract.md §2). Texts quote the required copy
in docs/dashboard/dashboard_data_contract.md §5.4 exactly — never paraphrase.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from src.api.schemas.common import Notice

NoticeKey = Literal[
    "read_only",
    "scores_unchanged",
    "adjusted_interpretive",
    "quarantine_pending",
    "healthy_only_proxy",
    "relationships_associative",
    "plant_records_required",
]

NOTICE_TEXT: dict[NoticeKey, str] = {
    "read_only": "This dashboard is read-only and intended for technical validation.",
    "scores_unchanged": "Original anomaly scores are unchanged.",
    "adjusted_interpretive": (
        "Adjusted review severity is interpretive post-processing, not model rescoring."
    ),
    "quarantine_pending": "Quarantine is pending review and not approved.",
    "healthy_only_proxy": "Healthy-only residual drift is a proxy view.",
    "relationships_associative": "Incident relationships are associative, not causal.",
    "plant_records_required": (
        "Plant records are still required before operational decisions."
    ),
}

# Per-view notice sets in contract §2 table order (response order is part of
# the contract surface, so views pass these tuples, never the registry dict).
OVERVIEW_NOTICE_KEYS: tuple[NoticeKey, ...] = (
    "read_only",
    "adjusted_interpretive",
    "plant_records_required",
)

TIMELINE_NOTICE_KEYS: tuple[NoticeKey, ...] = (
    "read_only",
    "scores_unchanged",
)

SENSOR_HEALTH_NOTICE_KEYS: tuple[NoticeKey, ...] = ("quarantine_pending",)

INCIDENTS_NOTICE_KEYS: tuple[NoticeKey, ...] = (
    "relationships_associative",
    "quarantine_pending",
    "adjusted_interpretive",
)


def notices_for(keys: Sequence[NoticeKey]) -> list[Notice]:
    """Build notice objects for ``keys``, preserving the given order."""
    return [Notice(key=key, text=NOTICE_TEXT[key]) for key in keys]
