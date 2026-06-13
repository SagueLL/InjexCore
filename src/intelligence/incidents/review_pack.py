"""Human-review incident pack — compact, prioritized, deduplicated.

One row per reviewable incident with its operational contexts joined from
the persisted timeline. Prioritization (critical -> persistent -> sensor
faults -> healthy-only residual drift -> detector agreement -> context
shifts -> earliest) and temporal deduplication keep the pack small enough
to actually review.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from src.intelligence.incidents.policy import IncidentsPolicy

REVIEW_PACK_COLUMNS = [
    "incident_id",
    "incident_type",
    "start_timestamp",
    "end_timestamp",
    "duration_seconds",
    "status",
    "severity",
    "affected_sensors",
    "affected_profiles",
    "steam_contexts",
    "sensor_health_contexts",
    "product_codes",
    "recipe_context_keys",
    "triggered_detectors",
    "supporting_metrics",
    "evidence",
    "related_incident_ids",
    "recommended_actions",
    "review_status",
]

_SEVERITY_RANK = {"critical": 0, "anomaly": 1, "warning": 2, "info": 3}

_CONTEXT_COLUMNS = {
    "steam_contexts": "steam_context",
    "sensor_health_contexts": "sensor_health_context",
    "product_codes": "product_code",
    "recipe_context_keys": "recipe_context_key",
}


def _interval_contexts(
    timeline: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> dict[str, str]:
    window = timeline.loc[start:end] if len(timeline) else timeline
    out: dict[str, str] = {}
    for field, column in _CONTEXT_COLUMNS.items():
        if column in window.columns and len(window):
            values = sorted(
                v for v in window[column].dropna().astype(str).unique() if v
            )
            out[field] = "|".join(values)
        else:
            out[field] = ""
    return out


def _triggered_detectors(evidence: str) -> str:
    try:
        members = json.loads(evidence).get("member_evidence", [])
    except (json.JSONDecodeError, AttributeError):
        return ""
    detectors: set[str] = set()
    for member in members:
        tokens = str(member.get("triggered_detectors", ""))
        detectors.update(t for t in tokens.split("|") if t)
    return "|".join(sorted(detectors))


def _supporting_metrics(evidence: str) -> str:
    try:
        members = json.loads(evidence).get("member_evidence", [])
    except (json.JSONDecodeError, AttributeError):
        return ""
    for member in members:
        metrics = member.get("supporting_metrics")
        if metrics:
            return str(metrics)
    return ""


def _has_healthy_only_evidence(evidence: str) -> bool:
    try:
        members = json.loads(evidence).get("member_evidence", [])
    except (json.JSONDecodeError, AttributeError):
        return False
    return any(str(m.get("view", "")) == "healthy_only" for m in members)


def build(
    incidents: pd.DataFrame,
    relationships: pd.DataFrame,
    actions: pd.DataFrame,
    timeline: pd.DataFrame,
    policy: IncidentsPolicy,
) -> pd.DataFrame:
    """Assemble, deduplicate, prioritize and truncate the review pack."""
    if not len(incidents):
        return pd.DataFrame(columns=REVIEW_PACK_COLUMNS)

    related: dict[str, set[str]] = {}
    for rel in relationships.itertuples(index=False):
        related.setdefault(str(rel.source_incident_id), set()).add(
            str(rel.target_incident_id)
        )
        related.setdefault(str(rel.target_incident_id), set()).add(
            str(rel.source_incident_id)
        )
    actions_by_incident = (
        actions.groupby("incident_id")["recommended_action"]
        .apply(lambda s: "|".join(sorted(set(s))))
        .to_dict()
        if len(actions)
        else {}
    )

    rows: list[dict[str, Any]] = []
    for _, incident in incidents.iterrows():
        incident_id = str(incident["incident_id"])
        contexts = _interval_contexts(
            timeline, incident["start_timestamp"], incident["end_timestamp"]
        )
        rows.append(
            {
                "incident_id": incident_id,
                "incident_type": str(incident["incident_type"]),
                "start_timestamp": incident["start_timestamp"],
                "end_timestamp": incident["end_timestamp"],
                "duration_seconds": float(incident["duration_seconds"]),
                "status": str(incident["status"]),
                "severity": str(incident["severity"]),
                "affected_sensors": str(incident["affected_sensors"]),
                "affected_profiles": str(incident["affected_profiles"]),
                **contexts,
                "triggered_detectors": _triggered_detectors(str(incident["evidence"])),
                "supporting_metrics": _supporting_metrics(str(incident["evidence"])),
                "evidence": str(incident["evidence"]),
                "related_incident_ids": "|".join(
                    sorted(related.get(incident_id, set()))
                ),
                "recommended_actions": actions_by_incident.get(incident_id, ""),
                "review_status": str(incident["review_status"]),
            }
        )
    pack = pd.DataFrame(rows, columns=REVIEW_PACK_COLUMNS)
    pack = _temporal_dedup(pack, policy)
    pack = _prioritize(pack, incidents)
    return pack.head(policy.review_pack.max_rows).reset_index(drop=True)


def _temporal_dedup(pack: pd.DataFrame, policy: IncidentsPolicy) -> pd.DataFrame:
    """Collapse same-type incidents whose intervals overlap almost entirely.

    The keeper is the highest-severity / earliest one; collapsed ids join its
    ``related_incident_ids``. Collapsed incidents stay in
    ``incidents.parquet`` — only the review pack is thinned.
    """
    if len(pack) < 2:
        return pack
    threshold = policy.review_pack.dedup_overlap_fraction
    pack = pack.sort_values(
        ["severity", "start_timestamp"],
        key=lambda s: s.map(_SEVERITY_RANK) if s.name == "severity" else s,
        kind="stable",
    ).reset_index(drop=True)
    dropped: set[int] = set()
    for i in range(len(pack)):
        if i in dropped:
            continue
        keeper = pack.iloc[i]
        absorbed: list[str] = []
        for j in range(i + 1, len(pack)):
            if j in dropped:
                continue
            other = pack.iloc[j]
            if other["incident_type"] != keeper["incident_type"]:
                continue
            shorter = max(
                min(
                    float(keeper["duration_seconds"]),
                    float(other["duration_seconds"]),
                ),
                1.0,
            )
            overlap = (
                min(keeper["end_timestamp"], other["end_timestamp"])
                - max(keeper["start_timestamp"], other["start_timestamp"])
            ).total_seconds()
            if overlap / shorter >= threshold:
                dropped.add(j)
                absorbed.append(str(other["incident_id"]))
        if absorbed:
            existing = {t for t in str(keeper["related_incident_ids"]).split("|") if t}
            pack.loc[pack.index[i], "related_incident_ids"] = "|".join(
                sorted(existing | set(absorbed))
            )
    return pack.drop(index=[pack.index[j] for j in dropped]).reset_index(drop=True)


def _prioritize(pack: pd.DataFrame, incidents: pd.DataFrame) -> pd.DataFrame:
    """Order: severity, persistence, sensor faults, healthy-only residuals."""
    healthy_only = {
        str(i["incident_id"])
        for _, i in incidents.iterrows()
        if _has_healthy_only_evidence(str(i["evidence"]))
    }
    pack = pack.copy()
    pack["_severity"] = pack["severity"].map(_SEVERITY_RANK).fillna(9)
    pack["_persistent"] = (pack["status"] != "persistent").astype(int)
    pack["_fault"] = (pack["incident_type"] != "sensor_fault").astype(int)
    pack["_healthy"] = (~pack["incident_id"].isin(healthy_only)).astype(int)
    pack["_detectors"] = -pack["triggered_detectors"].str.count(r"\|").fillna(0)
    pack = pack.sort_values(
        [
            "_severity",
            "_persistent",
            "_fault",
            "_healthy",
            "_detectors",
            "start_timestamp",
        ],
        kind="stable",
    )
    return pack.drop(
        columns=["_severity", "_persistent", "_fault", "_healthy", "_detectors"]
    )
