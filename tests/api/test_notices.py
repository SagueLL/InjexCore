"""Notice registry: the §5.4 copy is contract surface, not editorial.

Every text here is asserted byte-identical against the fenced block in
docs/dashboard/dashboard_data_contract.md §5.4 — a paraphrase in either direction
is a contract violation, so the doc is parsed rather than transcribed.
"""

from __future__ import annotations

import re

from src.api.copy.notices import (
    DRIFT_ANOMALY_NOTICE_KEYS,
    INCIDENTS_NOTICE_KEYS,
    NOTICE_TEXT,
    OVERVIEW_NOTICE_KEYS,
    REQUIRED_WARNING_KEYS,
    SENSOR_HEALTH_NOTICE_KEYS,
    TIMELINE_NOTICE_KEYS,
    notices_for,
    required_warnings,
)
from src.config import PROJECT_ROOT

_DATA_CONTRACT = PROJECT_ROOT / "docs" / "dashboard" / "dashboard_data_contract.md"
_PER_VIEW_KEYS = (
    OVERVIEW_NOTICE_KEYS,
    TIMELINE_NOTICE_KEYS,
    SENSOR_HEALTH_NOTICE_KEYS,
    DRIFT_ANOMALY_NOTICE_KEYS,
    INCIDENTS_NOTICE_KEYS,
)


def _contract_required_warnings() -> list[str]:
    """The fenced §5.4 block, verbatim, in document order."""
    text = _DATA_CONTRACT.read_text(encoding="utf-8")
    match = re.search(
        r"## 5\.4 Required warnings \(exact copy\)\s*\n+```\n(.*?)\n```",
        text,
        re.DOTALL,
    )
    assert match is not None, "§5.4 fenced block not found in the data contract"
    return [line for line in match.group(1).splitlines() if line.strip()]


def test_required_warning_keys_cover_the_whole_registry() -> None:
    assert set(REQUIRED_WARNING_KEYS) == set(NOTICE_TEXT)
    assert len(REQUIRED_WARNING_KEYS) == len(set(REQUIRED_WARNING_KEYS)) == 7


def test_required_warnings_match_the_data_contract_verbatim() -> None:
    # Order is contract surface: /meta serves this list as-is.
    assert required_warnings() == _contract_required_warnings()


def test_every_per_view_notice_set_is_a_subset_of_the_required_set() -> None:
    for keys in _PER_VIEW_KEYS:
        assert keys, "a view must never serve an empty notice set"
        assert set(keys) <= set(REQUIRED_WARNING_KEYS)
        assert len(keys) == len(set(keys)), "duplicate notice key in a view set"


def test_notices_for_preserves_order_and_copy() -> None:
    notices = notices_for(DRIFT_ANOMALY_NOTICE_KEYS)
    assert [notice.key for notice in notices] == list(DRIFT_ANOMALY_NOTICE_KEYS)
    assert [notice.text for notice in notices] == [
        NOTICE_TEXT[key] for key in DRIFT_ANOMALY_NOTICE_KEYS
    ]


def test_required_warnings_returns_a_fresh_list() -> None:
    # Callers must not be able to mutate the registry through the wire builder.
    first = required_warnings()
    first.clear()
    assert len(required_warnings()) == 7
