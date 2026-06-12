"""Per-profile, per-sensor statistical baselines — leakage-safe.

For every operational profile and every selected sensor, computes the
distribution descriptors that define "normal" for that regime: ``count``,
``mean``, ``median``, ``std``, ``min``, ``max``, ``iqr`` (always) plus the
configured percentiles (``pNN``).

Leakage guard: statistics are computed on the **training window only**
(the boolean ``train_mask`` passed in). The result is a long-form table
keyed by ``(profile, sensor)`` plus a ``fit_manifest`` recording exactly
what was fit, so downstream scoring on later data is reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
from pandas.api import types as pdtypes

from src.intelligence.behaviour.column_groups import ColumnGroups
from src.intelligence.behaviour.policy import BehaviourPolicy
from src.intelligence.behaviour.reporting import Finding, Severity

CHECK = "baselines"
_ZERO_VAR_EPS = 1e-9


@dataclass(frozen=True)
class BaselineArtifact:
    """Long-form baseline table + the reproducible fit contract."""

    table: pd.DataFrame  # rows: (profile, sensor, count, mean, median, ...)
    fit_manifest: dict


def _select_sensors(
    df: pd.DataFrame, policy: BehaviourPolicy, groups: ColumnGroups
) -> tuple[list[str], list[Finding]]:
    """Resolve the sensor set and keep only numeric columns present in ``df``."""
    sp = policy.sensors
    if sp.source == "process_sensor":
        candidates = [c for c in groups.process if c in df.columns]
    else:
        candidates = [c for c in sp.include_columns if c in df.columns]
    candidates = [c for c in candidates if c not in set(sp.exclude_columns)]

    findings: list[Finding] = []
    numeric: list[str] = []
    for c in candidates:
        if pdtypes.is_numeric_dtype(df[c]):
            numeric.append(c)
        else:
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.AWARE,
                    finding_type="sensor_not_numeric",
                    column=c,
                    action_taken="skip_sensor",
                )
            )
    if not numeric:
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="no_sensors_selected",
                action_taken="skip_baselines",
                evidence={"source": sp.source},
            )
        )
    return numeric, findings


def _sensor_stats(s: pd.Series, percentiles: list[float]) -> dict[str, float]:
    """Compute the baseline descriptors for one sensor within one profile."""
    q25, q75 = s.quantile(0.25), s.quantile(0.75)
    stats: dict[str, float] = {
        "count": int(s.notna().sum()),
        "mean": float(s.mean()),
        "median": float(s.median()),
        "std": float(s.std()),
        "min": float(s.min()),
        "max": float(s.max()),
        "iqr": float(q75 - q25),
    }
    for q in percentiles:
        stats[f"p{int(q):02d}"] = float(s.quantile(q / 100.0))
    return stats


def fit(
    df: pd.DataFrame,
    labels: pd.Series,
    policy: BehaviourPolicy,
    groups: ColumnGroups,
    *,
    train_mask: pd.Series,
) -> tuple[BaselineArtifact, list[Finding]]:
    """Compute per-(profile, sensor) baselines on the training window."""
    if not policy.baselines.enabled:
        return BaselineArtifact(pd.DataFrame(), {"enabled": False}), [
            Finding(
                check=CHECK,
                severity=Severity.NORMAL,
                finding_type="skipped",
                action_taken="noop",
                evidence={"reason": "disabled"},
            )
        ]

    sensors, findings = _select_sensors(df, policy, groups)
    percentiles = policy.baselines.percentiles
    min_samples = policy.profiles.min_samples_per_profile
    min_nn = policy.sensors.min_non_null_fraction

    train_df = df.loc[train_mask]
    train_labels = labels.loc[train_mask]

    rows: list[dict[str, object]] = []
    fitted: list[str] = []
    skipped: dict[str, int] = {}

    for profile in [p for p in train_labels.unique() if pd.notna(p)]:
        sub = train_df.loc[train_labels == profile]
        n_profile = len(sub)
        if n_profile < min_samples:
            skipped[str(profile)] = n_profile
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.IMPORTANT,
                    finding_type="profile_under_min_samples",
                    column=str(profile),
                    count=n_profile,
                    action_taken="skip_profile",
                    evidence={"min_samples": min_samples},
                )
            )
            continue
        fitted.append(str(profile))
        for sensor in sensors:
            s = sub[sensor]
            nn_frac = (s.notna().sum() / n_profile) if n_profile else 0.0
            if nn_frac < min_nn:
                findings.append(
                    Finding(
                        check=CHECK,
                        severity=Severity.AWARE,
                        finding_type="sensor_too_sparse",
                        column=sensor,
                        action_taken="skip_cell",
                        evidence={
                            "profile": str(profile),
                            "non_null_fraction": round(float(nn_frac), 4),
                            "min_non_null_fraction": min_nn,
                        },
                    )
                )
                continue
            stats = _sensor_stats(s.astype(float), percentiles)
            if stats["std"] < _ZERO_VAR_EPS:
                findings.append(
                    Finding(
                        check=CHECK,
                        severity=Severity.AWARE,
                        finding_type="near_zero_variance",
                        column=sensor,
                        action_taken="recorded",
                        evidence={"profile": str(profile), "std": stats["std"]},
                    )
                )
            rows.append({"profile": str(profile), "sensor": sensor, **stats})

    table = pd.DataFrame(rows)
    manifest = _build_manifest(
        df, train_mask, policy, sensors, fitted, skipped, percentiles
    )
    return BaselineArtifact(table=table, fit_manifest=manifest), findings


def _build_manifest(
    df: pd.DataFrame,
    train_mask: pd.Series,
    policy: BehaviourPolicy,
    sensors: list[str],
    fitted: list[str],
    skipped: dict[str, int],
    percentiles: list[float],
) -> dict:
    """Assemble the reproducible fit contract (extended by run() with edges)."""
    n_train = int(train_mask.sum())
    train_start = train_end = None
    if isinstance(df.index, pd.DatetimeIndex) and n_train:
        train_idx = df.index[train_mask.to_numpy()]
        train_start = str(train_idx.min())
        train_end = str(train_idx.max())
    return {
        "fit_timestamp": datetime.now(UTC).isoformat(),
        "fit_window": {
            "strategy": policy.fit_window.strategy,
            "train_fraction": policy.fit_window.train_fraction,
            "n_train": n_train,
            "n_total": int(len(df)),
            "train_start": train_start,
            "train_end": train_end,
        },
        "sensors": sensors,
        "percentiles": percentiles,
        "min_samples_per_profile": policy.profiles.min_samples_per_profile,
        "min_non_null_fraction": policy.sensors.min_non_null_fraction,
        "profiles_fitted": fitted,
        "profiles_skipped": skipped,
    }
