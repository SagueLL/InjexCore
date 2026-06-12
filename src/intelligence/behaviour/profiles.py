"""Operational-profile segmentation.

Derives a mutually-exclusive *primary regime* per row from the signals the
real pellet-extrusion data actually supports, plus an optional
material-change *candidate flag*. The label Series is the shared input to
:mod:`~src.intelligence.behaviour.baselines` and
:mod:`~src.intelligence.behaviour.validation`.

Derivable regimes
-----------------
* ``stopped``                machine off (``running_column == 0``).
* ``startup``                within ``startup.window_samples`` after a
                             ``0 -> 1`` machine-on edge.
* ``shutdown``               within ``shutdown.window_samples`` before a
                             ``1 -> 0`` machine-off edge.
* ``alarm``                  running and an alarm is active / recent.
* ``low|mid|high_production``  steady running rows bucketed by
                             **train-fitted** tertiles of the production rate.

Non-derivable regimes (``cleaning``, ``maintenance``, ``recipe_change``)
are NOT fabricated: each is surfaced as an ``AWARE`` finding. Material /
recipe change is offered only as a separate boolean candidate column
derived from batch-id transitions — a proxy, never a primary label.

Leakage guard: production-rate quantile edges are fit on the training
window only and returned in the artifact so future data is bucketed
consistently.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.intelligence.behaviour.column_groups import ColumnGroups
from src.intelligence.behaviour.policy import BehaviourPolicy
from src.intelligence.behaviour.reporting import Finding, Severity

CHECK = "profiles"

STOPPED = "stopped"
STARTUP = "startup"
SHUTDOWN = "shutdown"
ALARM = "alarm"
LOW_PROD = "low_production"
MID_PROD = "mid_production"
HIGH_PROD = "high_production"
RUNNING = "running"  # generic fallback when production cannot be bucketed
UNKNOWN = "unknown"  # machine-on state itself could not be determined

CANONICAL_ORDER = [
    STOPPED,
    STARTUP,
    SHUTDOWN,
    ALARM,
    LOW_PROD,
    MID_PROD,
    HIGH_PROD,
    RUNNING,
    UNKNOWN,
]


@dataclass(frozen=True)
class ProfileArtifact:
    """Result of profile segmentation."""

    labels: pd.Series  # primary regime per row, aligned to df.index
    material_change: pd.Series | None  # candidate flag, or None when disabled
    production_edges: list[float]  # [q_low, q_high] fit on the train window
    profile_names: list[str]  # labels actually present, canonical order
    machine_on_source: str  # which signal drove the on/off split


# ---------------------------------------------------------------------------
# Edge helpers
# ---------------------------------------------------------------------------


def _machine_on(
    df: pd.DataFrame, policy: BehaviourPolicy, groups: ColumnGroups
) -> tuple[pd.Series | None, str]:
    """Return (boolean machine-on Series, source description).

    Prefers ``profiles.running_column`` (e.g. ``n_subsystems_running``);
    falls back to the OR of the classification's running flags. Returns
    ``(None, reason)`` when neither is available.
    """
    col = policy.profiles.running_column
    if col in df.columns:
        on = df[col].fillna(0).astype(float) > 0
        return on.astype(bool), col

    present = [c for c in groups.running_flags if c in df.columns]
    if present:
        stacked = df[present].fillna(0).astype(float).clip(0, 1)
        on = stacked.sum(axis=1) > 0
        return on.astype(bool), f"OR({'+'.join(present)})"

    return None, "none"


def _time_since_rising_edge(on: pd.Series) -> pd.Series:
    """Samples since the most recent ``0 -> 1`` transition (0 at the edge).

    The first sample counts as an edge if it is already on. ``NaN`` before
    the first edge.
    """
    f = on.astype(float).to_numpy()
    rising = np.empty(len(f), dtype=bool)
    if len(f):
        rising[0] = f[0] > 0
        rising[1:] = (f[1:] - f[:-1]) > 0
    out = np.full(len(f), np.nan)
    counter = -1
    for i in range(len(f)):
        if rising[i]:
            counter = 0
        elif counter >= 0:
            counter += 1
        if counter >= 0:
            out[i] = counter
    return pd.Series(out, index=on.index, dtype="float64")


def _samples_until_falling_edge(on: pd.Series) -> pd.Series:
    """For on-rows, samples until the next ``1 -> 0`` transition.

    ``1`` for the last on-sample before an off, growing backwards. ``NaN``
    for off-rows and for on-rows with no future off.
    """
    off = (~on.astype(bool)).to_numpy()
    n = len(off)
    out = np.full(n, np.nan)
    dist: int | None = None
    for i in range(n - 1, -1, -1):
        if off[i]:
            dist = 0
        elif dist is not None:
            dist += 1
            out[i] = dist
    return pd.Series(out, index=on.index, dtype="float64")


def _alarm_mask(
    df: pd.DataFrame, on: pd.Series, policy: BehaviourPolicy
) -> tuple[pd.Series, list[str]]:
    """Rows that are running and have an active / recent alarm."""
    p = policy.profiles.alarm
    used: list[str] = []
    cond = pd.Series(False, index=df.index)
    if p.any_alarm_column in df.columns:
        cond = cond | (df[p.any_alarm_column].fillna(0).astype(float) > 0)
        used.append(p.any_alarm_column)
    if p.time_since_alarm_column in df.columns:
        tsa = df[p.time_since_alarm_column].astype(float)
        cond = cond | (tsa <= p.window_samples)
        used.append(p.time_since_alarm_column)
    return (cond & on).fillna(False), used


def _material_change_flag(
    df: pd.DataFrame, policy: BehaviourPolicy
) -> tuple[pd.Series | None, list[str]]:
    """Boolean candidate flag: any tracked batch column changed vs prev row."""
    p = policy.profiles.material_change
    if p.mode == "off":
        return None, []
    present = [c for c in p.batch_columns if c in df.columns]
    if not present:
        return None, []
    changed = pd.Series(False, index=df.index)
    for c in present:
        changed = changed | df[c].ne(df[c].shift(1))
    # First row compares against NaN (always "changed") — never a change.
    if len(changed):
        changed.iloc[0] = False
    return changed.astype(bool), present


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def derive(
    df: pd.DataFrame,
    policy: BehaviourPolicy,
    groups: ColumnGroups,
    *,
    train_mask: pd.Series,
) -> tuple[ProfileArtifact, list[Finding]]:
    """Segment ``df`` into operational profiles.

    ``train_mask`` is a boolean Series (aligned to ``df.index``) marking the
    leakage-safe training window; production quantile edges are fit on it.
    """
    findings: list[Finding] = []
    pp = policy.profiles

    on, source = _machine_on(df, policy, groups)
    if on is None:
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.CRITICAL,
                finding_type="machine_state_undeterminable",
                action_taken="label_unknown",
                evidence={
                    "running_column": pp.running_column,
                    "running_flags": groups.running_flags,
                },
            )
        )
        labels = pd.Series(UNKNOWN, index=df.index, dtype=object)
        return ProfileArtifact(labels, None, [], [UNKNOWN], "none"), findings

    findings.append(
        Finding(
            check=CHECK,
            severity=Severity.NORMAL,
            finding_type="machine_on_source",
            action_taken="none",
            evidence={"source": source, "on_fraction": round(float(on.mean()), 4)},
        )
    )

    # Transient + alarm masks (all restricted to on-rows).
    time_since_on = _time_since_rising_edge(on)
    startup = (
        on & (time_since_on < pp.startup.window_samples)
        if pp.startup.enabled
        else pd.Series(False, index=df.index)
    )
    until_off = _samples_until_falling_edge(on)
    shutdown = (
        on & (until_off <= pp.shutdown.window_samples)
        if pp.shutdown.enabled
        else pd.Series(False, index=df.index)
    )
    if pp.alarm.enabled:
        alarm, alarm_cols = _alarm_mask(df, on, policy)
        if not alarm_cols:
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.AWARE,
                    finding_type="alarm_columns_missing",
                    action_taken="skip_alarm_profile",
                    evidence={
                        "expected": [
                            pp.alarm.any_alarm_column,
                            pp.alarm.time_since_alarm_column,
                        ]
                    },
                )
            )
    else:
        alarm = pd.Series(False, index=df.index)

    rule_masks = {ALARM: alarm, STARTUP: startup, SHUTDOWN: shutdown}

    # Assemble labels by precedence.
    labels = pd.Series(UNKNOWN, index=df.index, dtype=object)
    labels[~on] = STOPPED
    assigned = ~on

    edges: list[float] = []
    for rule in pp.precedence:
        if rule == "production":
            labels, assigned, edges, prod_findings = _assign_production(
                df, on, assigned, labels, policy, train_mask
            )
            findings.extend(prod_findings)
        elif rule in rule_masks:
            mask = rule_masks[rule].fillna(False) & on & ~assigned
            labels[mask] = rule
            assigned = assigned | mask

    leftover = on & ~assigned
    if bool(leftover.any()):
        labels[leftover] = RUNNING

    # Material-change candidate flag.
    material, mat_cols = _material_change_flag(df, policy)
    if material is not None:
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.AWARE,
                finding_type="material_change_candidate",
                count=int(material.sum()),
                action_taken="add:material_change_candidate",
                evidence={
                    "source_columns": mat_cols,
                    "note": (
                        "Proxy from batch-id transitions; a new batch is not "
                        "guaranteed to be a material/recipe change. Candidate "
                        "flag only — never a primary profile label."
                    ),
                },
            )
        )

    # Honestly document the regimes the available signals cannot support.
    for regime in pp.unsupported_regimes:
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.AWARE,
                finding_type="regime_not_derivable",
                column=regime,
                action_taken="documented_gap",
                evidence={
                    "note": (
                        f"'{regime}' is not derivable from available signals; "
                        "would require an external maintenance / material log."
                    )
                },
            )
        )

    counts = labels.value_counts().to_dict()
    findings.append(
        Finding(
            check=CHECK,
            severity=Severity.NORMAL,
            finding_type="profile_summary",
            action_taken="none",
            evidence={"counts": {k: int(v) for k, v in counts.items()}},
        )
    )

    names = [n for n in CANONICAL_ORDER if n in set(labels.unique())]
    artifact = ProfileArtifact(
        labels=labels,
        material_change=material,
        production_edges=edges,
        profile_names=names,
        machine_on_source=source,
    )
    return artifact, findings


def _assign_production(
    df: pd.DataFrame,
    on: pd.Series,
    assigned: pd.Series,
    labels: pd.Series,
    policy: BehaviourPolicy,
    train_mask: pd.Series,
) -> tuple[pd.Series, pd.Series, list[float], list[Finding]]:
    """Bucket remaining running rows into low/mid/high production levels.

    Quantile edges are fit on the training window only (leakage guard).
    """
    pp = policy.profiles
    findings: list[Finding] = []
    candidate = on & ~assigned

    if pp.production_column not in df.columns or not bool(candidate.any()):
        if pp.production_column not in df.columns:
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.AWARE,
                    finding_type="production_column_missing",
                    column=pp.production_column,
                    action_taken="skip_production_levels",
                )
            )
        return labels, assigned, [], findings

    prod = df[pp.production_column].astype(float)
    train_vals = prod[train_mask & candidate].dropna()
    if train_vals.empty:
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.AWARE,
                finding_type="production_edges_unfittable",
                column=pp.production_column,
                action_taken="skip_production_levels",
                evidence={"reason": "no training rows in production candidate set"},
            )
        )
        return labels, assigned, [], findings

    edges = [float(q) for q in train_vals.quantile(pp.production_quantiles)]
    q_low, q_high = edges[0], edges[-1]

    low = candidate & (prod < q_low)
    high = candidate & (prod >= q_high)
    mid = candidate & ~low & ~high
    labels[low] = LOW_PROD
    labels[mid] = MID_PROD
    labels[high] = HIGH_PROD
    assigned = assigned | candidate

    findings.append(
        Finding(
            check=CHECK,
            severity=Severity.NORMAL,
            finding_type="production_edges_fit",
            column=pp.production_column,
            action_taken="fit_on_train",
            evidence={
                "quantiles": pp.production_quantiles,
                "edges": edges,
                "n_train_rows": int(train_vals.shape[0]),
            },
        )
    )
    return labels, assigned, edges, findings
