"""Source normalization — every upstream signal becomes one candidate shape.

Each loader emits candidate events with the same columns so grouping,
suppression and relationships reason over one frame regardless of origin.
Missing or empty upstream sources are recorded in
``unsupported_incident_sources.parquet``, never silently skipped.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from src.intelligence.incidents.policy import (
    DRIFT_TYPE_TO_INCIDENT,
    IncidentsPolicy,
)

CANDIDATE_COLUMNS = [
    "source",
    "source_event_id",
    "candidate_type",
    "group_family",
    "start_timestamp",
    "end_timestamp",
    "severity",
    "affected_sensors",
    "affected_profiles",
    "contexts",
    "is_persistent",
    "evidence",
]

_STRONG_FAMILIES = ("flatline_zero", "counter_reset", "missingness_spike")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=CANDIDATE_COLUMNS)


def _families(issue_types: str) -> list[str]:
    return sorted({t.split(":")[0] for t in issue_types.split("|") if t})


def from_sensor_health(events: pd.DataFrame) -> pd.DataFrame:
    """Sensor-health episodes -> sensor_fault / sensor_warning / data_quality."""
    if not len(events):
        return _empty()
    rows: list[dict[str, Any]] = []
    for event in events.itertuples(index=False):
        families = _families(str(event.issue_types))
        if str(event.status) == "warning":
            candidate_type = "sensor_warning"
            severity = "warning"
        elif families == ["missingness_spike"]:
            candidate_type = "data_quality_issue"
            severity = "anomaly"
        else:
            candidate_type = "sensor_fault"
            severity = (
                "critical"
                if bool(event.is_persistent) and set(families) & set(_STRONG_FAMILIES)
                else "anomaly"
            )
        rows.append(
            {
                "source": "sensor_health",
                "source_event_id": str(event.sensor_health_event_id),
                "candidate_type": candidate_type,
                "group_family": f"{event.sensor}:{'|'.join(families)}",
                "start_timestamp": pd.Timestamp(event.start_timestamp),
                "end_timestamp": pd.Timestamp(event.end_timestamp),
                "severity": severity,
                "affected_sensors": str(event.sensor),
                "affected_profiles": str(event.affected_profiles),
                "contexts": "",
                "is_persistent": bool(event.is_persistent),
                "evidence": json.dumps(
                    {
                        "issue_types": str(event.issue_types),
                        "max_health_score": float(event.max_health_score),
                        "recommended_action": str(event.recommended_action),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)


def from_drift(drift_events: pd.DataFrame) -> pd.DataFrame:
    """Drift events -> incident candidates (both views; grouped later)."""
    if not len(drift_events):
        return _empty()
    rows: list[dict[str, Any]] = []
    for event in drift_events.itertuples(index=False):
        candidate_type = DRIFT_TYPE_TO_INCIDENT.get(str(event.drift_type), "unknown")
        rows.append(
            {
                "source": "drift",
                "source_event_id": str(event.drift_event_id),
                "candidate_type": candidate_type,
                "group_family": f"{event.scope}:{event.drift_type}",
                "start_timestamp": pd.Timestamp(event.start_timestamp),
                "end_timestamp": pd.Timestamp(event.end_timestamp),
                "severity": str(event.severity),
                "affected_sensors": str(event.affected_sensors),
                "affected_profiles": str(event.affected_profiles),
                "contexts": str(event.affected_contexts),
                "is_persistent": bool(event.is_persistent),
                "evidence": json.dumps(
                    {
                        "view": str(event.view),
                        "temporal_shape": str(event.temporal_shape),
                        "supporting_metrics": str(event.supporting_metrics),
                        "drift_evidence": str(event.evidence),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)


def anomaly_bursts(
    anomaly_scores: pd.DataFrame, policy: IncidentsPolicy
) -> pd.DataFrame:
    """Sustained high anomaly-severity rates -> anomaly_burst candidates."""
    cfg = policy.bursts
    needed = {"severity"}
    if (
        not cfg.enabled
        or not len(anomaly_scores)
        or not needed <= set(anomaly_scores.columns)
    ):
        return _empty()
    flagged = anomaly_scores["severity"].isin(["warning", "anomaly"]).astype(float)
    buckets = flagged.resample(cfg.bucket_freq)
    rate = buckets.mean()
    count = buckets.size()
    active = ((rate >= cfg.rate_threshold) & (count > 0)).to_numpy()
    bucket_len = pd.Timedelta(cfg.bucket_freq)

    segments = _merged_runs(active, cfg.gap_merge_buckets)
    rows: list[dict[str, Any]] = []
    for i, j in segments:
        start = rate.index[i]
        end = rate.index[j - 1] + bucket_len
        if (end - start) < pd.Timedelta(minutes=cfg.min_duration_minutes):
            continue
        window = anomaly_scores.loc[start : end - pd.Timedelta("1ns")]
        window_flagged = window[window["severity"].isin(["warning", "anomaly"])]
        top_sensors = _top_affected(window_flagged)
        profiles = (
            "|".join(sorted(window["profile"].astype(str).unique()))
            if "profile" in window.columns
            else ""
        )
        detectors = _detector_union(window_flagged)
        rows.append(
            {
                "source": "anomaly",
                "source_event_id": f"AB-{start.strftime('%Y%m%dT%H%M%SZ')}",
                "candidate_type": "anomaly_burst",
                "group_family": "anomaly_burst",
                "start_timestamp": start,
                "end_timestamp": end,
                "severity": "anomaly",
                "affected_sensors": top_sensors,
                "affected_profiles": profiles,
                "contexts": "",
                "is_persistent": False,
                "evidence": json.dumps(
                    {
                        "mean_rate": round(float(rate.iloc[i:j].mean()), 4),
                        "n_flagged_rows": int(len(window_flagged)),
                        "triggered_detectors": detectors,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)


def _merged_runs(active: np.ndarray, gap: int) -> list[tuple[int, int]]:
    if len(active) == 0 or not active.any():
        return []
    m = active.astype(np.int8)
    diff = np.diff(m)
    starts = (np.flatnonzero(diff == 1) + 1).tolist()
    ends = (np.flatnonzero(diff == -1) + 1).tolist()
    if m[0]:
        starts = [0, *starts]
    if m[-1]:
        ends = [*ends, len(m)]
    segments = list(zip(starts, ends, strict=True))
    merged = [segments[0]]
    for i, j in segments[1:]:
        if i - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], j)
        else:
            merged.append((i, j))
    return merged


def _top_affected(flagged: pd.DataFrame, k: int = 3) -> str:
    if "affected_variables" not in flagged.columns or not len(flagged):
        return ""
    top = flagged["affected_variables"].fillna("").astype(str).str.split("|").str[0]
    counts = top[top != ""].value_counts()
    return "|".join(counts.head(k).index.tolist())


def _detector_union(flagged: pd.DataFrame) -> str:
    if "triggered_detectors" not in flagged.columns or not len(flagged):
        return ""
    out: set[str] = set()
    for tokens in flagged["triggered_detectors"].fillna("").astype(str):
        out.update(t for t in tokens.split("|") if t)
    return "|".join(sorted(out))


def from_context_transitions(
    transitions: pd.DataFrame, policy: IncidentsPolicy
) -> pd.DataFrame:
    """Operational context transitions -> instantaneous context_shift candidates.

    Only the configured transition types are considered (profile churn is
    routine operation, not an incident); temporal-adjacency grouping later
    merges transition runs into one incident.
    """
    if not len(transitions) or "transition_types" not in transitions.columns:
        return _empty()
    wanted = set(policy.grouping.context_transition_types)
    rows: list[dict[str, Any]] = []
    for idx, event in enumerate(transitions.itertuples(index=False)):
        types = {t for t in str(event.transition_types).split("|") if t} & wanted
        if not types:
            continue
        ts = pd.Timestamp(event.transition_timestamp)
        rows.append(
            {
                "source": "operational_context",
                "source_event_id": f"CT-{idx}-{ts.strftime('%Y%m%dT%H%M%SZ')}",
                "candidate_type": "context_shift",
                "group_family": "context:" + "|".join(sorted(types)),
                "start_timestamp": ts,
                "end_timestamp": ts,
                "severity": "info",
                "affected_sensors": "",
                "affected_profiles": "",
                "contexts": "|".join(sorted(types)),
                "is_persistent": False,
                "evidence": json.dumps(
                    {"transition_types": str(event.transition_types)},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)


def from_bom_transitions(transitions: pd.DataFrame) -> pd.DataFrame:
    """BOM order transitions -> instantaneous context_shift candidates."""
    if not len(transitions) or "transition_timestamp" not in transitions.columns:
        return _empty()
    rows: list[dict[str, Any]] = []
    for idx, event in enumerate(transitions.itertuples(index=False)):
        ts = pd.Timestamp(event.transition_timestamp)
        rows.append(
            {
                "source": "bom_context",
                "source_event_id": f"BT-{idx}-{ts.strftime('%Y%m%dT%H%M%SZ')}",
                "candidate_type": "context_shift",
                "group_family": "context:bom_transition",
                "start_timestamp": ts,
                "end_timestamp": ts,
                "severity": "info",
                "affected_sensors": "",
                "affected_profiles": "",
                "contexts": "bom_transition",
                "is_persistent": False,
                "evidence": json.dumps(
                    {
                        "transition_type": str(getattr(event, "transition_type", "")),
                        "previous_product_code": str(
                            getattr(event, "previous_product_code", "")
                        ),
                        "next_product_code": str(
                            getattr(event, "next_product_code", "")
                        ),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)


def unsupported_sources(missing: list[tuple[str, str]]) -> pd.DataFrame:
    """``(source, reason)`` rows for inputs that contributed nothing."""
    return pd.DataFrame(missing, columns=["source", "reason"])
