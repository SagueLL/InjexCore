"""Operational summary reports over the scored dataset.

Pure projections of the final scored frame — no new statistics, so every
number in a summary traces back to a row in ``anomaly_scores.parquet``.
"""

from __future__ import annotations

import pandas as pd

from src.intelligence.anomaly.combine import DETECTORS, SCORE_COLUMNS
from src.intelligence.anomaly.policy import AnomalyPolicy


def timeline(scored: pd.DataFrame, policy: AnomalyPolicy) -> pd.DataFrame:
    """Severity counts per time bucket (needs a DatetimeIndex)."""
    if not isinstance(scored.index, pd.DatetimeIndex):
        return pd.DataFrame(columns=["bucket", "severity", "count"])
    grouped = (
        scored.groupby([scored.index.floor(policy.summaries.timeline_freq), "severity"])
        .size()
        .reset_index(name="count")
    )
    grouped.columns = ["bucket", "severity", "count"]
    return grouped


def rates_by_profile(scored: pd.DataFrame) -> pd.DataFrame:
    """Per-profile row counts and warning/anomaly rates."""
    rows = []
    for profile, group in scored.groupby("profile", sort=True):
        n = len(group)
        n_warning = int((group["severity"] == "warning").sum())
        n_anomaly = int((group["severity"] == "anomaly").sum())
        rows.append(
            {
                "profile": profile,
                "n_rows": n,
                "n_warning": n_warning,
                "n_anomaly": n_anomaly,
                "warning_rate": round(n_warning / n, 6) if n else 0.0,
                "anomaly_rate": round(n_anomaly / n, 6) if n else 0.0,
            }
        )
    return pd.DataFrame(rows)


def severity_distribution(scored: pd.DataFrame) -> pd.DataFrame:
    """Overall severity counts."""
    vc = scored["severity"].value_counts()
    out = pd.DataFrame({"severity": vc.index, "count": vc.to_numpy()})
    out["pct"] = (out["count"] / len(scored)).round(6) if len(scored) else 0.0
    return out


def top_events(scored: pd.DataFrame, policy: AnomalyPolicy) -> pd.DataFrame:
    """Highest combined scores — the manual-review queue."""
    flagged = scored[scored["severity"].isin(["warning", "anomaly"])]
    top = flagged.nlargest(policy.summaries.top_events, "combined_score")
    columns = [
        "profile",
        "combined_score",
        "severity",
        "triggered_detectors",
        "affected_variables",
        "evidence",
    ]
    return top[columns]


def detector_agreement(scored: pd.DataFrame) -> pd.DataFrame:
    """Pairwise co-trigger counts per profile.

    Agreement between detectors is the main label-free plausibility signal:
    multivariate detectors corroborating the statistical one suggests real
    structure, detectors firing alone suggests noise or scale artifacts.
    """
    triggered = scored["triggered_detectors"].str.split("|")
    flags = {
        d: triggered.map(lambda parts, d=d: d in parts if parts else False)
        for d in DETECTORS
    }
    rows = []
    for profile, group in scored.groupby("profile", sort=True):
        for i, a in enumerate(DETECTORS):
            for b in DETECTORS[i + 1 :]:
                both = int((flags[a][group.index] & flags[b][group.index]).sum())
                rows.append(
                    {
                        "profile": profile,
                        "detector_a": a,
                        "detector_b": b,
                        "n_both_triggered": both,
                    }
                )
    return pd.DataFrame(
        rows, columns=["profile", "detector_a", "detector_b", "n_both_triggered"]
    )


def affected_variable_summary(scored: pd.DataFrame) -> pd.DataFrame:
    """How often each variable appears in flagged-event evidence."""
    flagged = scored[scored["severity"].isin(["warning", "anomaly"])]
    counts: dict[str, int] = {}
    for value in flagged["affected_variables"]:
        for name in str(value).split("|"):
            if name:
                counts[name] = counts.get(name, 0) + 1
    out = pd.DataFrame(
        sorted(counts.items(), key=lambda kv: -kv[1]),
        columns=["variable", "n_flagged_events"],
    )
    return out


# Re-exported for callers building the score column list.
__all__ = [
    "timeline",
    "rates_by_profile",
    "severity_distribution",
    "top_events",
    "detector_agreement",
    "affected_variable_summary",
    "SCORE_COLUMNS",
]
