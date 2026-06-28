"""Candidate grouping + duplicate suppression.

Candidates merge into one incident when they share the candidate type and
group family, sit within the family's temporal-adjacency gap, and their
affected-sensor sets agree (Jaccard gate; two empty sets agree). Suppression
then removes anomaly-burst incidents already explained by a stronger
sensor-fault incident — transparently, into
``suppressed_duplicate_events.parquet``, never silently.
"""

from __future__ import annotations

import contextlib
import json
import zlib
from typing import Any

import pandas as pd

from src.intelligence.incidents.policy import (
    INCIDENT_SEVERITIES,
    IncidentsPolicy,
)

INCIDENT_COLUMNS = [
    "incident_id",
    "incident_type",
    "group_family",
    "start_timestamp",
    "end_timestamp",
    "duration_seconds",
    "status",
    "severity",
    "affected_sensors",
    "affected_profiles",
    "contexts",
    "n_members",
    "source_event_ids",
    "sources",
    "is_persistent",
    "evidence",
    "review_status",
]

SUPPRESSED_COLUMNS = [
    "suppressed_incident_id",
    "suppressed_by_incident_id",
    "reason",
    "coverage",
    "incident_type",
    "start_timestamp",
    "end_timestamp",
    "source_event_ids",
    "evidence",
]

_SEVERITY_RANK = {name: i for i, name in enumerate(INCIDENT_SEVERITIES)}


def _gap_minutes(candidate_type: str, policy: IncidentsPolicy) -> int:
    cfg = policy.grouping
    if candidate_type in ("sensor_fault", "sensor_warning", "data_quality_issue"):
        return cfg.sensor_health_max_gap_minutes
    if candidate_type == "anomaly_burst":
        return cfg.burst_max_gap_minutes
    if candidate_type == "context_shift":
        return cfg.context_max_gap_minutes
    return cfg.drift_max_gap_minutes


def _tokens(joined: str) -> set[str]:
    return {t for t in str(joined).split("|") if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0  # two entity-less candidates agree
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def _max_severity(severities: list[str]) -> str:
    return max(severities, key=lambda s: _SEVERITY_RANK.get(s, 0))


def group_candidates(
    candidates: pd.DataFrame, policy: IncidentsPolicy, data_end: pd.Timestamp
) -> pd.DataFrame:
    """Sweep-merge candidates into incidents per (type, family)."""
    if not len(candidates):
        return pd.DataFrame(columns=INCIDENT_COLUMNS)
    incidents: list[dict[str, Any]] = []
    ordered = candidates.sort_values("start_timestamp", kind="stable")
    for (candidate_type, family), group in ordered.groupby(
        ["candidate_type", "group_family"], sort=False
    ):
        gap = pd.Timedelta(minutes=_gap_minutes(str(candidate_type), policy))
        open_members: list[pd.Series] = []
        open_end: pd.Timestamp | None = None
        open_sensors: set[str] = set()
        for _, member in group.iterrows():
            sensors = _tokens(member["affected_sensors"])
            if open_members and open_end is not None:
                close_enough = member["start_timestamp"] - open_end <= gap
                agrees = (
                    _jaccard(open_sensors, sensors) >= policy.grouping.affected_jaccard
                )
                if close_enough and agrees:
                    open_members.append(member)
                    open_end = max(open_end, member["end_timestamp"])
                    open_sensors |= sensors
                    continue
                incidents.append(
                    _incident_row(
                        str(candidate_type),
                        str(family),
                        open_members,
                        data_end,
                        policy,
                    )
                )
            open_members = [member]
            open_end = member["end_timestamp"]
            open_sensors = sensors
        if open_members:
            incidents.append(
                _incident_row(
                    str(candidate_type), str(family), open_members, data_end, policy
                )
            )
    frame = pd.DataFrame(incidents, columns=INCIDENT_COLUMNS)
    return frame.sort_values("start_timestamp", kind="stable").reset_index(drop=True)


def _union(members: list[pd.Series], column: str) -> str:
    out: set[str] = set()
    for member in members:
        out |= _tokens(member[column])
    return "|".join(sorted(out))


def _incident_row(
    candidate_type: str,
    family: str,
    members: list[pd.Series],
    data_end: pd.Timestamp,
    policy: IncidentsPolicy,
) -> dict[str, Any]:
    start = min(m["start_timestamp"] for m in members)
    end = max(m["end_timestamp"] for m in members)
    is_persistent = any(bool(m["is_persistent"]) for m in members)
    touches_end = end >= data_end
    if is_persistent:
        status = "persistent"
    elif touches_end:
        status = "open"
    else:
        status = "resolved"
    return {
        "incident_id": (
            f"INC-{candidate_type}-{start.strftime('%Y%m%dT%H%M%SZ')}-"
            f"{zlib.crc32(family.encode('utf-8')) % 10_000:04d}"
        ),
        "incident_type": candidate_type,
        "group_family": family,
        "start_timestamp": start,
        "end_timestamp": end,
        "duration_seconds": float((end - start).total_seconds()),
        "status": status,
        "severity": _max_severity([str(m["severity"]) for m in members]),
        "affected_sensors": _union(members, "affected_sensors"),
        "affected_profiles": _union(members, "affected_profiles"),
        "contexts": _union(members, "contexts"),
        "n_members": len(members),
        "source_event_ids": "|".join(
            sorted(str(m["source_event_id"]) for m in members)
        ),
        "sources": "|".join(sorted({str(m["source"]) for m in members})),
        "is_persistent": is_persistent,
        "evidence": json.dumps(
            {"member_evidence": [json.loads(str(m["evidence"])) for m in members][:10]},
            sort_keys=True,
            separators=(",", ":"),
        ),
        "review_status": "pending_review",
    }


def collapse_recurring(
    incidents: pd.DataFrame, policy: IncidentsPolicy, data_end: pd.Timestamp
) -> pd.DataFrame:
    """Collapse over-recurring (type, family) groups into one incident each.

    98 separate variance-explosion warnings on one sensor (or 145 routine
    BOM order changes) are one *recurring pattern*, not 98 review rows. The
    collapsed incident spans first start -> last end and records the
    recurrence count; nothing is dropped silently.
    """
    if not len(incidents):
        return incidents
    threshold = policy.grouping.recurring_collapse_min
    collapsible = set(policy.grouping.recurring_collapse_types)
    out_rows: list[dict[str, Any]] = []
    for (incident_type, family), group in incidents.groupby(
        ["incident_type", "group_family"], sort=False
    ):
        if str(incident_type) not in collapsible or len(group) <= threshold:
            out_rows.extend(group.to_dict("records"))
            continue
        start = group["start_timestamp"].min()
        end = group["end_timestamp"].max()
        is_persistent = bool(group["is_persistent"].any())
        if is_persistent:
            status = "persistent"
        elif end >= data_end:
            status = "open"
        else:
            status = "resolved"
        ids = sorted(t for joined in group["source_event_ids"] for t in _tokens(joined))
        out_rows.append(
            {
                "incident_id": (
                    f"INC-{incident_type}-recurring-"
                    f"{start.strftime('%Y%m%dT%H%M%SZ')}-"
                    f"{zlib.crc32(str(family).encode('utf-8')) % 10_000:04d}"
                ),
                "incident_type": str(incident_type),
                "group_family": str(family),
                "start_timestamp": start,
                "end_timestamp": end,
                "duration_seconds": float((end - start).total_seconds()),
                "status": status,
                "severity": _max_severity(list(group["severity"].astype(str))),
                "affected_sensors": "|".join(
                    sorted({t for j in group["affected_sensors"] for t in _tokens(j)})
                ),
                "affected_profiles": "|".join(
                    sorted({t for j in group["affected_profiles"] for t in _tokens(j)})
                ),
                "contexts": "|".join(
                    sorted({t for j in group["contexts"] for t in _tokens(j)})
                ),
                "n_members": int(group["n_members"].sum()),
                "source_event_ids": "|".join(ids[:20])
                + (f"|...({len(ids)} total)" if len(ids) > 20 else ""),
                "sources": "|".join(
                    sorted({t for j in group["sources"] for t in _tokens(j)})
                ),
                "is_persistent": is_persistent,
                "evidence": json.dumps(
                    {
                        "recurring_pattern": True,
                        "collapsed_incident_count": int(len(group)),
                        "total_member_events": int(group["n_members"].sum()),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "review_status": "pending_review",
            }
        )
    frame = pd.DataFrame(out_rows, columns=INCIDENT_COLUMNS)
    return frame.sort_values("start_timestamp", kind="stable").reset_index(drop=True)


def merge_cross_source(
    incidents: pd.DataFrame, policy: IncidentsPolicy
) -> pd.DataFrame:
    """Merge same-type, same-sensor incidents that overlap across sources.

    A drift-promoted sensor event and its sensor-health original describe
    one physical episode; the merged incident unions sources, members and
    evidence, keeps the earliest start / latest end and the max severity.
    """
    if len(incidents) < 2:
        return incidents
    threshold = policy.grouping.cross_source_overlap_fraction
    merged_rows: list[dict[str, Any]] = []
    for (incident_type, sensors), group in incidents.groupby(
        ["incident_type", "affected_sensors"], sort=False
    ):
        if len(group) < 2 or not str(sensors):
            merged_rows.extend(group.to_dict("records"))
            continue
        ordered = group.sort_values("start_timestamp", kind="stable")
        clusters: list[list[dict[str, Any]]] = []
        for record in ordered.to_dict("records"):
            placed = False
            for cluster in clusters:
                last = cluster[-1]
                shorter = max(
                    min(
                        float(last["duration_seconds"]),
                        float(record["duration_seconds"]),
                    ),
                    1.0,
                )
                overlap = (
                    min(last["end_timestamp"], record["end_timestamp"])
                    - max(last["start_timestamp"], record["start_timestamp"])
                ).total_seconds()
                if overlap / shorter >= threshold:
                    cluster.append(record)
                    placed = True
                    break
            if not placed:
                clusters.append([record])
        for cluster in clusters:
            if len(cluster) == 1:
                merged_rows.append(cluster[0])
            else:
                merged_rows.append(_merge_cluster(str(incident_type), cluster))
    frame = pd.DataFrame(merged_rows, columns=INCIDENT_COLUMNS)
    return frame.sort_values("start_timestamp", kind="stable").reset_index(drop=True)


def _merge_cluster(incident_type: str, cluster: list[dict[str, Any]]) -> dict[str, Any]:
    start = min(r["start_timestamp"] for r in cluster)
    end = max(r["end_timestamp"] for r in cluster)
    is_persistent = any(bool(r["is_persistent"]) for r in cluster)
    statuses = {str(r["status"]) for r in cluster}
    if is_persistent:
        status = "persistent"
    elif "open" in statuses:
        status = "open"
    else:
        status = "resolved"
    member_evidence: list[Any] = []
    for record in cluster:
        with contextlib.suppress(json.JSONDecodeError):
            member_evidence.extend(
                json.loads(str(record["evidence"])).get("member_evidence", [])
            )
    base = cluster[0]
    return {
        **base,
        "incident_id": (
            f"INC-{incident_type}-{start.strftime('%Y%m%dT%H%M%SZ')}-"
            f"{zlib.crc32(str(base['affected_sensors']).encode('utf-8')) % 10_000:04d}"
        ),
        "group_family": "+".join(sorted({str(r["group_family"]) for r in cluster})),
        "start_timestamp": start,
        "end_timestamp": end,
        "duration_seconds": float((end - start).total_seconds()),
        "status": status,
        "severity": _max_severity([str(r["severity"]) for r in cluster]),
        "affected_profiles": "|".join(
            sorted({t for r in cluster for t in _tokens(r["affected_profiles"])})
        ),
        "contexts": "|".join(
            sorted({t for r in cluster for t in _tokens(r["contexts"])})
        ),
        "n_members": int(sum(int(r["n_members"]) for r in cluster)),
        "source_event_ids": "|".join(
            sorted({t for r in cluster for t in _tokens(r["source_event_ids"])})
        ),
        "sources": "|".join(
            sorted({t for r in cluster for t in _tokens(r["sources"])})
        ),
        "is_persistent": is_persistent,
        "evidence": json.dumps(
            {
                "merged_from": sorted(str(r["incident_id"]) for r in cluster),
                "member_evidence": member_evidence[:10],
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        "review_status": "pending_review",
    }


def suppress_duplicates(
    incidents: pd.DataFrame, policy: IncidentsPolicy
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Remove anomaly bursts already explained by a sensor-fault incident.

    A burst is suppressed when a sensor_fault incident covers its interval by
    at least ``coverage_fraction`` and (configurably) shares affected sensors.
    Returns ``(kept, suppressed)`` — the suppressed table records what was
    removed, by whom and why.
    """
    if not policy.suppression.enabled or not len(incidents):
        return incidents, pd.DataFrame(columns=SUPPRESSED_COLUMNS)
    faults = incidents[incidents["incident_type"] == "sensor_fault"]
    bursts = incidents[incidents["incident_type"] == "anomaly_burst"]
    if not len(faults) or not len(bursts):
        return incidents, pd.DataFrame(columns=SUPPRESSED_COLUMNS)

    suppressed_rows: list[dict[str, Any]] = []
    suppressed_ids: set[str] = set()
    for _, burst in bursts.iterrows():
        duration = max(float(burst["duration_seconds"]), 1.0)
        burst_sensors = _tokens(burst["affected_sensors"])
        for _, fault in faults.iterrows():
            overlap_start = max(burst["start_timestamp"], fault["start_timestamp"])
            overlap_end = min(burst["end_timestamp"], fault["end_timestamp"])
            coverage = (
                max((overlap_end - overlap_start).total_seconds(), 0.0) / duration
            )
            if coverage < policy.suppression.coverage_fraction:
                continue
            fault_sensors = _tokens(fault["affected_sensors"])
            if policy.suppression.require_shared_sensors and not (
                burst_sensors & fault_sensors
            ):
                continue
            suppressed_ids.add(str(burst["incident_id"]))
            suppressed_rows.append(
                {
                    "suppressed_incident_id": str(burst["incident_id"]),
                    "suppressed_by_incident_id": str(fault["incident_id"]),
                    "reason": "burst_explained_by_sensor_fault",
                    "coverage": round(coverage, 4),
                    "incident_type": "anomaly_burst",
                    "start_timestamp": burst["start_timestamp"],
                    "end_timestamp": burst["end_timestamp"],
                    "source_event_ids": str(burst["source_event_ids"]),
                    "evidence": str(burst["evidence"]),
                }
            )
            break
    kept = incidents[~incidents["incident_id"].isin(suppressed_ids)].reset_index(
        drop=True
    )
    return kept, pd.DataFrame(suppressed_rows, columns=SUPPRESSED_COLUMNS)
