"""Shared per-UTC-day series helpers (API contract §6).

The daily p95 rule is contractually "one rule, two views" (timeline
``deviationScore`` and drift-anomaly ``anomalyScore``), and the day-status
ladder is reused verbatim by both views — keeping a single implementation
prevents silent contract divergence between them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# TODO(debt): the p95 warning threshold is the §8 calibration open item —
# non-binding on the pinned run (warning-severity incidents overlap every day).
WARNING_P95_THRESHOLD = 0.9


def daily_p95(scores: pd.DataFrame) -> pd.Series:
    """Per-UTC-day p95 of combined_score over scored rows, 3 decimals (§6).

    Days with zero scored rows never appear in the groupby result, which is
    exactly the §6 omission rule.
    """
    scored = scores[scores["severity"] != "unscored"]
    day = scored["timestamp"].dt.floor("D")
    return scored.groupby(day)["combined_score"].quantile(0.95).round(3)


def overlaps(days: pd.DatetimeIndex, frame: pd.DataFrame) -> np.ndarray:
    """Boolean (n_days, n_rows) matrix: row ``[start, end]`` overlaps the UTC day.

    Incident ends are day-rounded upward upstream (e.g. 2024-10-09 00:00), but
    the series never contains a day without scored rows, so no spurious point
    appears past the last scored day.
    """
    day_starts = days.to_numpy()[:, None]
    day_ends = (days + pd.Timedelta(days=1)).to_numpy()[:, None]
    starts = frame["start_timestamp"].to_numpy()[None, :]
    ends = frame["end_timestamp"].to_numpy()[None, :]
    return (starts < day_ends) & (ends >= day_starts)


def day_statuses(
    days: pd.DatetimeIndex,
    p95: pd.Series,
    incidents: pd.DataFrame,
    drift_events: pd.DataFrame,
) -> list[str]:
    """§6 status ladder per day: critical > drift > warning > normal.

    ``info`` incidents count toward incidentCount (§6 is literal about
    overlaps) but never escalate the ladder (§5: info maps to normal). The
    warning threshold compares the rounded/served p95 so the status is
    auditable from the payload.
    """
    critical = overlaps(
        days, incidents[incidents["severity"].isin(["anomaly", "critical"])]
    ).any(axis=1)
    drifting = overlaps(
        days, drift_events[drift_events["status"].isin(["active", "persistent"])]
    ).any(axis=1)
    warning = overlaps(days, incidents[incidents["severity"] == "warning"]).any(
        axis=1
    ) | (p95.to_numpy() >= WARNING_P95_THRESHOLD)
    statuses = np.select(
        [critical, drifting, warning], ["critical", "drift", "warning"], "normal"
    )
    return statuses.tolist()
