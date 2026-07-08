"""Shared per-UTC-day series helpers (API contract §6).

The daily evidence-share rule is contractually "one rule, two views" (timeline and
drift-anomaly both serve it as ``evidenceShare``), and the day-status ladder is
reused verbatim by both — a single implementation prevents silent contract
divergence between them.

Two design notes, both the outcome of measuring the pinned run rather than reading
the code:

* ``evidence_share`` replaced a p95 of ``combined_score``. ``combined_score`` is a
  conservative max over per-detector train-ECDF percentiles, so its daily p95 sat
  at ~1.0 almost everywhere (median 0.979 across 117 days, floor 0.513) — a line
  pinned to the top of a 0–1 axis, carrying no information. The share of a day's
  scored rows that carry warning/anomaly evidence is a **rate**, not a score
  magnitude, and it separates the quiet pre-fault months from the fault window.
* Recurring-pattern incidents are excluded from the day ladder and from
  ``incidentCount``. Their ``[start, end]`` is the *span* of many intermittent
  member events (one such incident collapsed 101 members across 115 of 117 days),
  not a continuous condition. Counting that span as "every day is a warning day"
  is an overlap-semantics bug: it flagged all 117 days, leaving zero normal days —
  including inside the training window the system itself calls the reference for
  normal. They remain full records in the Incidents view; only the *daily* series
  excludes them.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

#: A day is "warning" when at least this share of its scored rows carry warning or
#: anomaly evidence. Calibration pin (API contract §8). On the pinned run this arm
#: decides 11 of 117 days; the rest are decided by episodic incident overlap or by
#: carrying no evidence at all.
WARNING_EVIDENCE_SHARE = 0.05

#: Scored severities that count as evidence. "unscored" rows are excluded from the
#: denominator entirely (§6 omission rule); "normal" rows sit in the denominator.
NON_NORMAL_SEVERITIES = ("warning", "anomaly")


def daily_evidence(scores: pd.DataFrame) -> pd.DataFrame:
    """Per-UTC-day scored / non-normal row counts and their share (3 decimals).

    ``evidence_share`` = non-normal ÷ scored: the fraction of the day's scored rows
    carrying warning or anomaly evidence. It is a **rate**, not a model score.

    Days with zero scored rows never appear in the groupby result, which is exactly
    the §6 omission rule.
    """
    scored = scores[scores["severity"] != "unscored"]
    day = scored["timestamp"].dt.floor("D")
    scored_rows = scored.groupby(day).size()
    non_normal_rows = (
        scored[scored["severity"].isin(NON_NORMAL_SEVERITIES)]
        .groupby(day)
        .size()
        .reindex(scored_rows.index, fill_value=0)
    )
    return pd.DataFrame(
        {
            "scored_rows": scored_rows,
            "non_normal_rows": non_normal_rows,
            "evidence_share": (non_normal_rows / scored_rows).round(3),
        }
    )


def is_recurring_pattern(evidence: object) -> bool:
    """True only for a collapsed recurring-pattern incident (its ``evidence`` JSON).

    Never raises. Missing, non-string, malformed or non-object evidence is treated
    as **episodic** — the incident is kept. Retaining an incident we cannot classify
    risks over-flagging a day (loud); dropping it hides evidence (silent). Prefer
    loud. Note that the incidents pipeline overwrites ``evidence`` when it merges a
    cluster, so a merged recurring incident legitimately loses the flag; the
    keep-on-doubt rule handles that correctly too.
    """
    if not isinstance(evidence, str):
        return False
    try:
        parsed = json.loads(evidence)
    except (json.JSONDecodeError, ValueError):
        return False
    return isinstance(parsed, dict) and parsed.get("recurring_pattern") is True


def episodic_incidents(incidents: pd.DataFrame) -> pd.DataFrame:
    """Incidents minus the collapsed recurring-pattern envelopes.

    Raises ``KeyError`` when ``evidence`` is absent. Callers invoke this inside
    their ``_load_artifacts`` try/except, so an upstream schema change fails closed
    as ``ARTIFACT_UNREADABLE`` rather than silently disabling the filter.
    """
    recurring = incidents["evidence"].map(is_recurring_pattern)
    return incidents[~recurring].reset_index(drop=True)


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
    evidence_share: pd.Series,
    episodic: pd.DataFrame,
    drift_events: pd.DataFrame,
) -> list[str]:
    """§6 status ladder per day: critical > drift > warning > normal.

    ``episodic`` must already exclude recurring-pattern envelopes (see
    :func:`episodic_incidents`). ``info`` incidents count toward incidentCount
    (§6 is literal about overlaps) but never escalate the ladder (§5: info maps to
    normal). The warning threshold compares the rounded/served share so the status
    is auditable straight from the payload.
    """
    critical = overlaps(
        days, episodic[episodic["severity"].isin(["anomaly", "critical"])]
    ).any(axis=1)
    drifting = overlaps(
        days, drift_events[drift_events["status"].isin(["active", "persistent"])]
    ).any(axis=1)
    warning = overlaps(days, episodic[episodic["severity"] == "warning"]).any(
        axis=1
    ) | (evidence_share.to_numpy() >= WARNING_EVIDENCE_SHARE)
    statuses = np.select(
        [critical, drifting, warning], ["critical", "drift", "warning"], "normal"
    )
    return statuses.tolist()
