"""Incident relationships — associative and temporal, never causal.

Pairwise interval + entity logic over start-sorted incidents, bounded by the
adjacency window. Every emitted row carries ``causality_status = "unknown"``
(hardcoded): a sensor fault that overlaps and shares sensors with an anomaly
burst *possibly explains* it — establishing actual causality is the
reviewer's job, not this module's.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from src.intelligence.incidents.policy import IncidentsPolicy

RELATIONSHIP_COLUMNS = [
    "source_incident_id",
    "target_incident_id",
    "relationship_type",
    "confidence",
    "evidence",
    "causality_status",
]

_EXPLAINABLE_TYPES = ("anomaly_burst", "multivariate_shift", "correlation_break")


def _tokens(joined: str) -> set[str]:
    return {t for t in str(joined).split("|") if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _interval_relation(
    a: pd.Series, b: pd.Series, policy: IncidentsPolicy
) -> tuple[str, float] | None:
    """Strongest interval relation from ``a`` to ``b`` (b starts at/after a)."""
    overlap = (
        min(a["end_timestamp"], b["end_timestamp"])
        - max(a["start_timestamp"], b["start_timestamp"])
    ).total_seconds()
    if (
        a["start_timestamp"] <= b["start_timestamp"]
        and a["end_timestamp"] >= b["end_timestamp"]
    ):
        return "contains", 1.0
    if overlap > 0:
        shorter = max(
            min(float(a["duration_seconds"]), float(b["duration_seconds"])), 1.0
        )
        return "overlaps", min(overlap / shorter, 1.0)
    gap = (b["start_timestamp"] - a["end_timestamp"]).total_seconds()
    if 0 <= gap <= policy.relationships.adjacency_minutes * 60:
        return "temporally_adjacent", 0.5
    if 0 <= gap <= policy.relationships.follows_max_minutes * 60:
        return "follows", 0.3
    return None


def detect(incidents: pd.DataFrame, policy: IncidentsPolicy) -> pd.DataFrame:
    """All pairwise relationships within the configured temporal bounds."""
    if len(incidents) < 2:
        return pd.DataFrame(columns=RELATIONSHIP_COLUMNS)
    ordered = incidents.sort_values("start_timestamp", kind="stable").reset_index(
        drop=True
    )
    horizon = pd.Timedelta(minutes=policy.relationships.follows_max_minutes)
    rows: list[dict[str, Any]] = []
    for i in range(len(ordered) - 1):
        a = ordered.iloc[i]
        for j in range(i + 1, len(ordered)):
            b = ordered.iloc[j]
            if b["start_timestamp"] - a["end_timestamp"] > horizon:
                break
            rows.extend(_pair_rows(a, b, policy))
    return pd.DataFrame(rows, columns=RELATIONSHIP_COLUMNS)


def _pair_rows(
    a: pd.Series, b: pd.Series, policy: IncidentsPolicy
) -> list[dict[str, Any]]:
    interval = _interval_relation(a, b, policy)
    if interval is None:
        return []
    relation, confidence = interval
    sensors_a = _tokens(a["affected_sensors"])
    sensors_b = _tokens(b["affected_sensors"])
    contexts_a = _tokens(a["contexts"])
    contexts_b = _tokens(b["contexts"])
    sensor_jaccard = _jaccard(sensors_a, sensors_b)

    rows = [_row(a, b, relation, confidence, {})]
    if sensors_a & sensors_b:
        rows.append(
            _row(
                a,
                b,
                "shares_sensors",
                sensor_jaccard,
                {"sensors": sorted(sensors_a & sensors_b)},
            )
        )
    if contexts_a & contexts_b:
        rows.append(
            _row(
                a,
                b,
                "shares_context",
                _jaccard(contexts_a, contexts_b),
                {"contexts": sorted(contexts_a & contexts_b)},
            )
        )

    fault, other = None, None
    if (
        str(a["incident_type"]) == "sensor_fault"
        and str(b["incident_type"]) in _EXPLAINABLE_TYPES
    ):
        fault, other = a, b
    elif (
        str(b["incident_type"]) == "sensor_fault"
        and str(a["incident_type"]) in _EXPLAINABLE_TYPES
    ):
        fault, other = b, a
    if (
        fault is not None
        and other is not None
        and relation
        in (
            "contains",
            "overlaps",
        )
    ):
        overlap_confidence = max(
            confidence * max(sensor_jaccard, 0.1 if not sensors_b else 0.0),
            policy.relationships.min_confidence,
        )
        rows.append(
            _row(
                fault,
                other,
                "possibly_explains",
                overlap_confidence,
                {"basis": "interval_overlap_and_shared_sensors"},
            )
        )
    if {str(a["incident_type"]), str(b["incident_type"])} == {
        "sensor_fault"
    } and sensors_a & sensors_b:
        rows.append(
            _row(
                a,
                b,
                "corroborates",
                sensor_jaccard,
                {"sensors": sorted(sensors_a & sensors_b)},
            )
        )
    return rows


def _row(
    a: pd.Series,
    b: pd.Series,
    relation: str,
    confidence: float,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source_incident_id": str(a["incident_id"]),
        "target_incident_id": str(b["incident_id"]),
        "relationship_type": relation,
        "confidence": round(float(confidence), 4),
        "evidence": json.dumps(evidence, sort_keys=True, separators=(",", ":")),
        # Hardcoded: relationships are associative/temporal, never causal.
        "causality_status": "unknown",
    }
