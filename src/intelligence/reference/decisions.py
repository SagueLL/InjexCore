"""Decision-log seeding.

The decision log is the audit ledger's *starting state*: one ``pending``
row per proposal, recording that nothing has been decided yet. It is never
auto-advanced — a human reviewer updates these rows. This module guarantees
the log opens with every proposal explicitly unresolved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

DECISION_LOG_COLUMNS = [
    "decision_id",
    "target_type",
    "target_id",
    "decision",
    "decided_by",
    "decided_at",
    "status",
    "notes",
]


def build_decision_log(
    proposals: pd.DataFrame, quarantine_proposals: pd.DataFrame
) -> pd.DataFrame:
    """Seed one ``pending`` decision row per proposal (nothing approved)."""
    created = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    for proposal_id in proposals.get("proposal_id", pd.Series(dtype=str)):
        rows.append(_pending_row("reference_proposal", str(proposal_id), created))
    for qid in quarantine_proposals.get("quarantine_proposal_id", pd.Series(dtype=str)):
        rows.append(_pending_row("quarantine_proposal", str(qid), created))
    return pd.DataFrame(rows, columns=DECISION_LOG_COLUMNS)


def _pending_row(target_type: str, target_id: str, created: str) -> dict[str, Any]:
    return {
        "decision_id": f"DL-{target_id}",
        "target_type": target_type,
        "target_id": target_id,
        "decision": "pending",
        "decided_by": "",
        "decided_at": "",
        "status": "pending_review",
        "notes": (
            "Awaiting human review. Reference Governance proposes and tracks "
            "decisions; it never approves or applies them automatically."
        ),
    }
