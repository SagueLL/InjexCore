"""Shared day-series rules (API contract §6) — pure unit tests, no HTTP.

These lock the two decisions that made the timeline chart honest:
``evidence_share`` is a rate over scored rows, and recurring-pattern envelopes
never colour a day.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from src.api.services._series import (
    WARNING_EVIDENCE_SHARE,
    daily_evidence,
    day_statuses,
    episodic_incidents,
    is_recurring_pattern,
    overlaps,
)

_EMPTY_INCIDENTS = pd.DataFrame(
    {
        "severity": pd.Series(dtype="object"),
        "start_timestamp": pd.Series(dtype="datetime64[ns]"),
        "end_timestamp": pd.Series(dtype="datetime64[ns]"),
    }
)
_EMPTY_DRIFT = pd.DataFrame(
    {
        "status": pd.Series(dtype="object"),
        "start_timestamp": pd.Series(dtype="datetime64[ns]"),
        "end_timestamp": pd.Series(dtype="datetime64[ns]"),
    }
)


def _scores(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime([ts for ts, _ in rows]),
            "severity": [severity for _, severity in rows],
        }
    )


# ---------------------------------------------------------------- daily_evidence


def test_daily_evidence_is_a_rate_over_scored_rows() -> None:
    evidence = daily_evidence(
        _scores(
            [
                ("2024-01-01 01:00", "normal"),
                ("2024-01-01 02:00", "warning"),
                ("2024-01-01 03:00", "anomaly"),
                ("2024-01-01 04:00", "normal"),
            ]
        )
    )
    row = evidence.loc[pd.Timestamp("2024-01-01")]
    assert row["scored_rows"] == 4
    assert row["non_normal_rows"] == 2
    assert row["evidence_share"] == 0.5


def test_daily_evidence_excludes_unscored_rows_from_both_terms() -> None:
    evidence = daily_evidence(
        _scores(
            [
                ("2024-01-01 01:00", "unscored"),
                ("2024-01-01 02:00", "anomaly"),
            ]
        )
    )
    # The unscored row leaves the denominator entirely: 1 of 1, not 1 of 2.
    assert evidence.loc[pd.Timestamp("2024-01-01"), "scored_rows"] == 1
    assert evidence.loc[pd.Timestamp("2024-01-01"), "evidence_share"] == 1.0


def test_daily_evidence_omits_days_with_only_unscored_rows() -> None:
    evidence = daily_evidence(
        _scores(
            [
                ("2024-01-01 01:00", "normal"),
                ("2024-01-02 01:00", "unscored"),
                ("2024-01-03 01:00", "normal"),
            ]
        )
    )
    # §6 omission rule: the type has no null slot, so the day never appears.
    assert list(evidence.index) == [
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2024-01-03"),
    ]


def test_daily_evidence_rounds_the_share_to_three_decimals() -> None:
    rows = [("2024-01-01 00:00", "anomaly")] + [
        (f"2024-01-01 {hour:02d}:00", "normal") for hour in range(1, 8)
    ]
    # 1/8 = 0.125 exactly; 1/3 would round.
    assert daily_evidence(_scores(rows)).loc[
        pd.Timestamp("2024-01-01"), "evidence_share"
    ] == pytest.approx(0.125)
    thirds = [("2024-01-02 00:00", "anomaly")] + [
        (f"2024-01-02 {hour:02d}:00", "normal") for hour in range(1, 3)
    ]
    assert daily_evidence(_scores(thirds)).loc[
        pd.Timestamp("2024-01-02"), "evidence_share"
    ] == pytest.approx(0.333)


def test_daily_evidence_serves_zero_on_a_fully_normal_day() -> None:
    evidence = daily_evidence(_scores([("2024-01-01 01:00", "normal")]))
    assert evidence.loc[pd.Timestamp("2024-01-01"), "evidence_share"] == 0.0


# ------------------------------------------------------------ is_recurring_pattern


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ('{"recurring_pattern": true}', True),
        ('{"recurring_pattern": true, "collapsed_incident_count": 145}', True),
        ('{"recurring_pattern": false}', False),
        # Truthy-but-not-True must not count: only the literal boolean flag does.
        ('{"recurring_pattern": "yes"}', False),
        ('{"recurring_pattern": 1}', False),
        ("{}", False),
        ('{"merged_from": ["a", "b"]}', False),
        # Malformed / wrong-typed evidence is EPISODIC, and must never raise.
        ("{", False),
        ("", False),
        ("[1, 2]", False),
        ("null", False),
        ("not json at all", False),
        (None, False),
        (float("nan"), False),
        (42, False),
    ],
)
def test_is_recurring_pattern_only_accepts_the_literal_flag(
    evidence: object, expected: bool
) -> None:
    assert is_recurring_pattern(evidence) is expected


# ------------------------------------------------------------- episodic_incidents


def _incidents(evidence: list[str]) -> pd.DataFrame:
    n = len(evidence)
    return pd.DataFrame(
        {
            "incident_id": [f"inc-{i}" for i in range(n)],
            "severity": ["warning"] * n,
            "start_timestamp": pd.to_datetime(["2024-01-01"] * n),
            "end_timestamp": pd.to_datetime(["2024-01-02"] * n),
            "evidence": evidence,
        }
    )


def test_episodic_incidents_drops_only_recurring_envelopes() -> None:
    frame = _incidents(['{"recurring_pattern": true}', "{}", "{"])
    episodic = episodic_incidents(frame)
    assert list(episodic["incident_id"]) == ["inc-1", "inc-2"]
    # Index is reset so downstream positional zips stay aligned.
    assert list(episodic.index) == [0, 1]


def test_episodic_incidents_keeps_everything_when_none_are_recurring() -> None:
    frame = _incidents(["{}", '{"merged_from": 2}'])
    assert len(episodic_incidents(frame)) == 2


def test_episodic_incidents_fails_closed_without_the_evidence_column() -> None:
    # Callers run this inside _load_artifacts' try, so a schema change becomes
    # ARTIFACT_UNREADABLE rather than a silently disabled filter.
    frame = _incidents(["{}"]).drop(columns=["evidence"])
    with pytest.raises(KeyError):
        episodic_incidents(frame)


# -------------------------------------------------------------------- day_statuses


def _days(dates: list[str]) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(dates))


def _share(values: list[float], dates: list[str]) -> pd.Series:
    return pd.Series(values, index=_days(dates))


def test_day_statuses_ladder_precedence() -> None:
    days = _days(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    incidents = pd.DataFrame(
        {
            "severity": ["anomaly", "warning", "info"],
            "start_timestamp": pd.to_datetime(
                ["2024-01-01", "2024-01-03", "2024-01-04"]
            ),
            "end_timestamp": pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-04"]),
        }
    )
    drift = pd.DataFrame(
        {
            "status": ["persistent"],
            "start_timestamp": pd.to_datetime(["2024-01-02"]),
            "end_timestamp": pd.to_datetime(["2024-01-02"]),
        }
    )
    statuses = day_statuses(
        days, _share([0.0] * 4, list(days.strftime("%Y-%m-%d"))), incidents, drift
    )
    # critical > drift > warning > normal; `info` never escalates.
    assert statuses == ["critical", "drift", "warning", "normal"]


def test_day_statuses_warning_arm_fires_at_the_threshold() -> None:
    dates = ["2024-01-01", "2024-01-02"]
    days = _days(dates)
    below = WARNING_EVIDENCE_SHARE - 0.001
    statuses = day_statuses(
        days,
        _share([below, WARNING_EVIDENCE_SHARE], dates),
        _EMPTY_INCIDENTS,
        _EMPTY_DRIFT,
    )
    # Inclusive at the threshold, so the served (rounded) value is auditable.
    assert statuses == ["normal", "warning"]


def test_day_statuses_ignores_candidate_and_resolved_drift() -> None:
    dates = ["2024-01-01"]
    drift = pd.DataFrame(
        {
            "status": ["candidate", "resolved"],
            "start_timestamp": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "end_timestamp": pd.to_datetime(["2024-01-01", "2024-01-01"]),
        }
    )
    assert day_statuses(
        _days(dates), _share([0.0], dates), _EMPTY_INCIDENTS, drift
    ) == ["normal"]


def test_overlaps_is_inclusive_of_the_whole_utc_day() -> None:
    days = _days(["2024-01-02"])
    frame = pd.DataFrame(
        {
            "start_timestamp": pd.to_datetime(["2024-01-01 23:59", "2024-01-03 00:01"]),
            "end_timestamp": pd.to_datetime(["2024-01-02 00:01", "2024-01-03 10:00"]),
        }
    )
    assert np.array_equal(overlaps(days, frame), np.array([[True, False]]))
