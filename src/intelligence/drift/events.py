"""Drift events — scored windows become persistent, reviewable episodes.

Consecutive active windows per (scope, view, entity, profile) are merged
into events with a temporal-shape classification (onset behaviour) and a
status (lifecycle). Strong *faulty* sensor-health events are additionally
*promoted* into ``sensor_drift`` events directly — sub-window instrumentation
episodes (e.g. a 2.4 h missingness outage inside a daily window) are
guaranteed to surface regardless of window granularity. Every event defaults
to ``review_status = "pending_review"``; nothing is auto-confirmed and
``dismissed`` is never auto-assigned.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from src.intelligence.drift.policy import (
    DRIFT_SEVERITIES,
    HEALTHY_ONLY_PROXY_LABEL,
    DriftPolicy,
)

EVENT_COLUMNS = [
    "drift_event_id",
    "scope",
    "view",
    "drift_type",
    "temporal_shape",
    "start_timestamp",
    "end_timestamp",
    "duration_seconds",
    "status",
    "severity",
    "affected_sensors",
    "affected_profiles",
    "affected_contexts",
    "supporting_metrics",
    "evidence",
    "is_persistent",
    "review_status",
]

_SEVERITY_RANK = {name: i for i, name in enumerate(DRIFT_SEVERITIES)}
_GROUP_KEY = ["scope", "view", "entity", "profile"]


def _run_segments(active: np.ndarray) -> list[tuple[int, int]]:
    """Half-open ``[i, j)`` ranges of True runs (mirrors sensor_health)."""
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
    return list(zip(starts, ends, strict=True))


def _merged_segments(
    segments: list[tuple[int, int]], gap: int
) -> list[tuple[int, int]]:
    if not segments:
        return []
    merged = [segments[0]]
    for i, j in segments[1:]:
        last_i, last_j = merged[-1]
        if i - last_j <= gap:
            merged[-1] = (last_i, j)
        else:
            merged.append((i, j))
    return merged


def _temporal_shape(
    scores: np.ndarray,
    n_pre_merge_segments: int,
    is_persistent: bool,
    resolved: bool,
    policy: DriftPolicy,
) -> str:
    """Onset/shape classification (first match wins; see docs for precedence)."""
    cfg = policy.events
    n = len(scores)
    if n < 2:
        return "transient" if resolved and not is_persistent else "unknown"
    peak = float(scores.max())
    if peak <= 0:
        return "unknown"
    # Episodic first: a toggling signal also "starts at its peak", but the
    # toggling is the more informative shape.
    if n_pre_merge_segments >= cfg.episodic_min_segments:
        return "episodic"
    onset = int(np.argmax(scores >= 0.9 * peak)) + 1  # windows to reach ~peak
    if onset <= cfg.abrupt_onset_max_windows:
        return "abrupt"
    if onset >= cfg.progressive_min_onset_windows and _mostly_monotonic(scores[:onset]):
        return "progressive"
    if is_persistent:
        return "persistent"
    if resolved:
        return "transient"
    return "unknown"


def _mostly_monotonic(values: np.ndarray, min_tau: float = 0.6) -> bool:
    """Concordant-pair Kendall-tau check over a short onset ramp."""
    n = len(values)
    if n < 2:
        return False
    concordant = discordant = 0
    for i in range(n - 1):
        diff = values[i + 1 :] - values[i]
        concordant += int((diff > 0).sum())
        discordant += int((diff < 0).sum())
    total = concordant + discordant
    if total == 0:
        return True  # flat ramp — non-decreasing
    return (concordant - discordant) / total >= min_tau


def _status(
    n_windows: int, is_persistent: bool, touches_end: bool, policy: DriftPolicy
) -> str:
    if is_persistent:
        return "persistent"
    if touches_end:
        return "active"
    if n_windows <= policy.events.candidate_max_windows:
        return "candidate"
    return "resolved"


def _top_metrics(metric_scores: list[str], k: int = 3) -> str:
    """Top-k metrics by mean normalized value across the segment windows."""
    norms: dict[str, list[float]] = {}
    for payload in metric_scores:
        for metric, entry in json.loads(payload).items():
            norms.setdefault(metric, []).append(float(entry["norm"]))
    means = {m: sum(v) / len(v) for m, v in norms.items()}
    top = sorted(means.items(), key=lambda kv: -kv[1])[:k]
    return json.dumps(
        {m: round(v, 4) for m, v in top}, sort_keys=True, separators=(",", ":")
    )


def _max_severity(severities: pd.Series) -> str:
    return max(severities, key=lambda s: _SEVERITY_RANK.get(str(s), 0))


def extract_events(
    scored: pd.DataFrame, policy: DriftPolicy, last_window: pd.Timestamp
) -> pd.DataFrame:
    """Merged active-window episodes per (scope, view, entity, profile)."""
    if not len(scored):
        return pd.DataFrame(columns=EVENT_COLUMNS)
    rows: list[dict[str, Any]] = []
    for (scope, view, entity, profile), group in scored.groupby(_GROUP_KEY, sort=False):
        group = group.sort_values("window_start", kind="stable")
        active = group["drift_score"].to_numpy() >= policy.events.active_score_threshold
        raw_segments = _run_segments(active)
        for i, j in _merged_segments(raw_segments, policy.events.gap_merge_windows):
            pre_merge = sum(1 for a, b in raw_segments if a >= i and b <= j)
            rows.append(
                _event_row(
                    group.iloc[i:j],
                    str(scope),
                    str(view),
                    str(entity),
                    str(profile),
                    pre_merge,
                    last_window,
                    policy,
                )
            )
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def _event_row(
    segment: pd.DataFrame,
    scope: str,
    view: str,
    entity: str,
    profile: str,
    n_pre_merge_segments: int,
    last_window: pd.Timestamp,
    policy: DriftPolicy,
) -> dict[str, Any]:
    start = pd.Timestamp(segment["window_start"].iloc[0])
    end = pd.Timestamp(segment["window_end"].iloc[-1])
    n_windows = len(segment)
    is_persistent = n_windows >= policy.events.persistent_min_windows
    touches_end = pd.Timestamp(segment["window_start"].iloc[-1]) >= last_window
    scores = segment["drift_score"].to_numpy(dtype=float)
    overridden = bool(segment["sensor_health_override"].any())
    drift_type = "sensor_drift" if overridden else str(segment["drift_type"].iloc[-1])
    status = _status(n_windows, is_persistent, touches_end, policy)
    return {
        "drift_event_id": (
            f"DR-{scope}-{entity}-{profile}-{start.strftime('%Y%m%dT%H%M%SZ')}"
        ),
        "scope": scope,
        "view": view,
        "drift_type": drift_type,
        "temporal_shape": _temporal_shape(
            scores,
            n_pre_merge_segments,
            is_persistent,
            resolved=status == "resolved",
            policy=policy,
        ),
        "start_timestamp": start,
        "end_timestamp": end,
        "duration_seconds": float((end - start).total_seconds()),
        "status": status,
        "severity": _max_severity(segment["severity"]),
        "affected_sensors": entity if scope == "sensor" else "",
        "affected_profiles": "" if profile == "__global__" else profile,
        "affected_contexts": entity if scope == "context" else "",
        "supporting_metrics": _top_metrics(list(segment["metric_scores"])),
        "evidence": json.dumps(
            {
                "n_windows": n_windows,
                "peak_score": round(float(scores.max()), 4),
                "mean_score": round(float(scores.mean()), 4),
                "n_pre_merge_segments": n_pre_merge_segments,
                "sensor_health_override": overridden,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        "is_persistent": is_persistent,
        "review_status": "pending_review",
    }


def promote_sensor_health_events(
    sensor_health_events: pd.DataFrame, policy: DriftPolicy
) -> pd.DataFrame:
    """Faulty sensor-health events promoted directly into sensor_drift events.

    Guarantees instrumentation episodes surface with their original
    (sub-window) timing. Severity: ``critical`` for persistent events with a
    strong issue family, ``anomaly`` otherwise. Promotion is marked in the
    evidence; nothing upstream is modified.
    """
    if not policy.sensor_health_override.promote_faulty_events or not len(
        sensor_health_events
    ):
        return pd.DataFrame(columns=EVENT_COLUMNS)
    strong = set(policy.sensor_health_override.strong_issue_families)
    rows: list[dict[str, Any]] = []
    faulty = sensor_health_events[sensor_health_events["status"] == "faulty"]
    for event in faulty.itertuples(index=False):
        start = pd.Timestamp(event.start_timestamp)
        end = pd.Timestamp(event.end_timestamp)
        is_persistent = bool(event.is_persistent)
        families = {t.split(":")[0] for t in str(event.issue_types).split("|") if t}
        severity = "critical" if is_persistent and families & strong else "anomaly"
        rows.append(
            {
                "drift_event_id": (
                    f"DR-sensor-{event.sensor}-{start.strftime('%Y%m%dT%H%M%SZ')}-SH"
                ),
                "scope": "sensor",
                "view": "raw",
                "drift_type": "sensor_drift",
                "temporal_shape": "abrupt" if is_persistent else "transient",
                "start_timestamp": start,
                "end_timestamp": end,
                "duration_seconds": float((end - start).total_seconds()),
                "status": "persistent" if is_persistent else "resolved",
                "severity": severity,
                "affected_sensors": str(event.sensor),
                "affected_profiles": str(event.affected_profiles),
                "affected_contexts": "",
                "supporting_metrics": json.dumps(
                    {"max_health_score": float(event.max_health_score)},
                    separators=(",", ":"),
                ),
                "evidence": json.dumps(
                    {
                        "source": "sensor_health_promotion",
                        "sensor_health_event_id": str(event.sensor_health_event_id),
                        "issue_types": str(event.issue_types),
                        "absorbed_event_ids": [],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "is_persistent": is_persistent,
                "review_status": "pending_review",
            }
        )
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def merge_promoted(
    window_events: pd.DataFrame, promoted: pd.DataFrame, policy: DriftPolicy
) -> pd.DataFrame:
    """Absorb window-derived sensor events into overlapping promoted events.

    A window-derived sensor event whose interval is covered by a promoted
    event for the same sensor by at least ``promoted_event_absorb_coverage``
    is absorbed: the promoted event's evidence records the absorbed id and
    its (precise, sub-window) instrumentation timing is kept — one physical
    episode stays one event, with the sensor-health onset as the authority.
    """
    if not len(promoted):
        return window_events
    if not len(window_events):
        return promoted
    coverage_min = policy.events.promoted_event_absorb_coverage
    promoted = promoted.copy().reset_index(drop=True)
    absorbed_ids: set[str] = set()
    for p_idx, p_event in promoted.iterrows():
        candidates = window_events[
            (window_events["scope"] == "sensor")
            & (window_events["affected_sensors"] == p_event["affected_sensors"])
            & (window_events["view"] == p_event["view"])
        ]
        for _, w_event in candidates.iterrows():
            duration = max(float(w_event["duration_seconds"]), 1.0)
            overlap_start = max(p_event["start_timestamp"], w_event["start_timestamp"])
            overlap_end = min(p_event["end_timestamp"], w_event["end_timestamp"])
            overlap = max((overlap_end - overlap_start).total_seconds(), 0.0)
            if overlap / duration < coverage_min:
                continue
            absorbed_ids.add(str(w_event["drift_event_id"]))
            evidence = json.loads(str(p_event["evidence"]))
            evidence["absorbed_event_ids"] = sorted(
                {
                    *evidence.get("absorbed_event_ids", []),
                    str(w_event["drift_event_id"]),
                }
            )
            promoted.loc[p_idx, "evidence"] = json.dumps(
                evidence, sort_keys=True, separators=(",", ":")
            )
    kept = window_events[~window_events["drift_event_id"].isin(absorbed_ids)]
    merged = pd.concat([kept, promoted], ignore_index=True)
    return merged.sort_values("start_timestamp", kind="stable").reset_index(drop=True)


def filter_dominated_events(
    events: pd.DataFrame,
    dominance_by_window: pd.Series,
    policy: DriftPolicy,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Level-A healthy-view filter on multivariate events.

    Healthy-view multivariate events whose member windows carry a mean
    evidence dominance of excluded sensors >= ``evidence_dominance_fraction``
    are removed from the healthy view (the raw view keeps them). Level-B
    ``healthy_only_proxy`` events are exempt — they are constructed to
    answer the healthy-only question and already discount the excluded
    sensors' contribution. Returns ``(kept, excluded)`` — exclusions are
    recorded transparently, never silently dropped.
    """
    if not len(events) or not len(dominance_by_window):
        return events, pd.DataFrame(columns=[*EVENT_COLUMNS, "dominance"])
    target = (
        (events["view"] == "healthy_only")
        & (events["scope"] == "multivariate")
        & ~events["drift_event_id"].str.contains(HEALTHY_ONLY_PROXY_LABEL)
    )
    keep_mask = np.ones(len(events), dtype=bool)
    dominances: list[float] = []
    excluded_rows: list[int] = []
    for pos, (_, event) in enumerate(events.iterrows()):
        if not target.iloc[pos]:
            continue
        in_window = (dominance_by_window.index >= event["start_timestamp"]) & (
            dominance_by_window.index < event["end_timestamp"]
        )
        if not in_window.any():
            continue
        dominance = float(dominance_by_window[in_window].mean())
        if dominance >= policy.healthy_view.evidence_dominance_fraction:
            keep_mask[pos] = False
            excluded_rows.append(pos)
            dominances.append(dominance)
    excluded = events.iloc[excluded_rows].copy()
    excluded["dominance"] = dominances
    return events.iloc[keep_mask].reset_index(drop=True), excluded.reset_index(
        drop=True
    )


def correlation_events(
    classified: pd.DataFrame,
    validation_start: pd.Timestamp,
    validation_end: pd.Timestamp,
    policy: DriftPolicy,
) -> pd.DataFrame:
    """Per-profile correlation events from material process breaks.

    The correlation run persists one train-vs-validation delta (not windowed),
    so these events span the validation window with shape ``unknown``.
    ``sensor_drift_evidence`` pairs never create process events — they feed
    the affected sensor's drift evidence instead.
    """
    if not len(classified):
        return pd.DataFrame(columns=EVENT_COLUMNS)
    breaks = classified[classified["classification"] == "process_correlation_break"]
    rows: list[dict[str, Any]] = []
    for profile, group in breaks.groupby("profile"):
        if len(group) < policy.correlation.min_material_pairs_for_event:
            continue
        top = group.nlargest(policy.correlation.top_k_pairs, "abs_delta")
        pairs = [
            f"{a}~{b}" for a, b in zip(top["feature_a"], top["feature_b"], strict=True)
        ]
        sensors = sorted(set(top["feature_a"]) | set(top["feature_b"]))
        max_delta = float(group["abs_delta"].max())
        severity = (
            "anomaly"
            if max_delta >= 2 * policy.correlation.material_delta
            else "warning"
        )
        rows.append(
            {
                "drift_event_id": (
                    f"DR-correlation-{profile}-"
                    f"{validation_start.strftime('%Y%m%dT%H%M%SZ')}"
                ),
                "scope": "correlation",
                "view": "raw",
                "drift_type": "correlation_shift",
                "temporal_shape": "unknown",
                "start_timestamp": validation_start,
                "end_timestamp": validation_end,
                "duration_seconds": float(
                    (validation_end - validation_start).total_seconds()
                ),
                "status": "active",
                "severity": severity,
                "affected_sensors": "|".join(sensors),
                "affected_profiles": str(profile),
                "affected_contexts": "",
                "supporting_metrics": json.dumps(
                    {
                        "max_abs_delta": round(max_delta, 4),
                        "n_material_pairs": len(group),
                    },
                    separators=(",", ":"),
                ),
                "evidence": json.dumps(
                    {"top_pairs": pairs[:5], "source": "correlation_shift"},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "is_persistent": False,
                "review_status": "pending_review",
            }
        )
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)
