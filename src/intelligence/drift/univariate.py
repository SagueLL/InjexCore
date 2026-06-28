"""Univariate sensor drift — windowed metrics against train-only references.

For every configured process sensor a reference is fitted on behaviour's
persisted train window (global + per supported profile) and every tumbling
window is compared against it. Nothing is ever refitted on validation data.

The healthy-only view passes a boolean exclusion mask: masked cells are
removed *before* any metric is computed (numerator and denominator alike),
so ``missingness_shift`` measures genuine missingness only — an analytical
exclusion, never a mutation of upstream data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.intelligence._common.policy import ProfileGatePolicy
from src.intelligence.drift import windows as win
from src.intelligence.drift.policy import (
    GLOBAL_SCOPE_KEY,
    DriftPolicy,
    UnivariatePolicy,
)

_EPS = 1.0e-12

SCORE_ROW_COLUMNS = [
    "window_start",
    "scope",
    "view",
    "entity",
    "profile",
    "metric",
    "value",
    "n_rows",
    "n_valid",
]


@dataclass(frozen=True)
class UnivariateReference:
    """Train-window statistics for one (sensor, scope-key) pair."""

    mean: float
    std: float
    median: float
    iqr: float
    zero_rate: float
    missing_rate: float
    unique_fraction: float
    bin_edges: np.ndarray
    bin_probs: np.ndarray
    sorted_sample: np.ndarray

    @property
    def robust_scale(self) -> float:
        """IQR-derived sigma estimate, falling back to the train std."""
        if self.iqr > _EPS:
            return self.iqr / 1.349
        return self.std


def supported_profiles(
    profile_arr: np.ndarray, train_arr: np.ndarray, gate: ProfileGatePolicy
) -> tuple[list[str], dict[str, str]]:
    """Profiles with enough train rows; mirrors the Iteration B gate."""
    supported: list[str] = []
    skipped: dict[str, str] = {}
    train_profiles = profile_arr[train_arr]
    for profile in sorted({str(p) for p in profile_arr}):
        if profile in set(gate.exclude_profiles):
            skipped[profile] = "excluded_by_policy"
            continue
        n_train = int((train_profiles == profile).sum())
        if n_train < gate.min_samples_per_profile:
            skipped[profile] = f"insufficient_rows ({n_train})"
            continue
        supported.append(profile)
    return supported, skipped


def _fit_reference(
    values: np.ndarray, policy: UnivariatePolicy
) -> UnivariateReference | None:
    """One reference from the train values of a (sensor, scope) pair."""
    if len(values) == 0:
        return None
    missing = np.isnan(values)
    valid = values[~missing]
    if len(valid) < 2:
        return None
    q25, q75 = np.quantile(valid, [0.25, 0.75])
    return UnivariateReference(
        mean=float(valid.mean()),
        std=float(valid.std()),
        median=float(np.median(valid)),
        iqr=float(q75 - q25),
        zero_rate=float((np.abs(valid) <= policy.zero_eps).mean()),
        missing_rate=float(missing.mean()),
        unique_fraction=float(len(np.unique(valid)) / len(valid)),
        bin_edges=win.psi_bin_edges(valid, policy.psi_bins),
        bin_probs=win.bin_probabilities(
            valid, win.psi_bin_edges(valid, policy.psi_bins)
        ),
        sorted_sample=win.downsample_sorted(valid, policy.max_reference_sample),
    )


def train_references(
    df: pd.DataFrame,
    sensors: list[str],
    profile_arr: np.ndarray,
    train_arr: np.ndarray,
    policy: DriftPolicy,
    *,
    scope: str = "sensor",
    report_profile_gaps: bool = True,
) -> tuple[dict[tuple[str, str], UnivariateReference], list[dict[str, str]]]:
    """References per (entity, scope-key); scope keys = global + profiles.

    Returns ``(references, unsupported_rows)``; pairs without enough train
    data are reported, never silently fitted. The same machinery scores the
    persisted multivariate model scores (``scope="multivariate"``) — those
    are *read*, never recomputed.
    """
    profiles, skipped = supported_profiles(profile_arr, train_arr, policy.profiles)
    unsupported: list[dict[str, str]] = (
        [
            {
                "scope": "profile",
                "view": "raw",
                "entity": profile,
                "profile": profile,
                "reason": reason,
            }
            for profile, reason in skipped.items()
        ]
        if report_profile_gaps
        else []
    )
    scope_masks: dict[str, np.ndarray] = {GLOBAL_SCOPE_KEY: train_arr}
    for profile in profiles:
        scope_masks[profile] = train_arr & (profile_arr == profile)

    refs: dict[tuple[str, str], UnivariateReference] = {}
    for sensor in sensors:
        values = df[sensor].to_numpy(dtype=float)
        for scope_key, mask in scope_masks.items():
            ref = _fit_reference(values[mask], policy.univariate)
            if ref is None:
                unsupported.append(
                    {
                        "scope": scope,
                        "view": "raw",
                        "entity": sensor,
                        "profile": scope_key,
                        "reason": "insufficient_train_rows",
                    }
                )
            else:
                refs[(sensor, scope_key)] = ref
    return refs, unsupported


def _window_metrics(
    vals: np.ndarray, ref: UnivariateReference, policy: UnivariatePolicy
) -> dict[str, float]:
    """All enabled univariate metrics for one window slice (mask applied)."""
    missing = np.isnan(vals)
    valid = vals[~missing]
    out: dict[str, float] = {}
    enabled = set(policy.enabled_metrics)

    if "missingness_shift" in enabled:
        out["missingness_shift"] = float(missing.mean()) - ref.missing_rate
    if len(valid) == 0:
        return out

    scale = ref.robust_scale
    if "mean_shift" in enabled:
        out["mean_shift"] = (
            abs(float(valid.mean()) - ref.mean) / ref.std
            if ref.std > _EPS
            else math.nan
        )
    if "median_shift" in enabled:
        out["median_shift"] = (
            abs(float(np.median(valid)) - ref.median) / scale
            if scale > _EPS
            else math.nan
        )
    if "std_shift" in enabled:
        out["std_shift"] = abs(math.log((float(valid.std()) + _EPS) / (ref.std + _EPS)))
    if "iqr_shift" in enabled:
        q25, q75 = np.quantile(valid, [0.25, 0.75])
        out["iqr_shift"] = abs(math.log((float(q75 - q25) + _EPS) / (ref.iqr + _EPS)))
    if "zero_rate_shift" in enabled:
        out["zero_rate_shift"] = (
            float((np.abs(valid) <= policy.zero_eps).mean()) - ref.zero_rate
        )
    if "unique_value_collapse" in enabled:
        fraction = len(np.unique(valid)) / len(valid)
        collapsed = (
            ref.unique_fraction > 0.0
            and fraction < policy.unique_collapse_train_factor * ref.unique_fraction
        )
        out["unique_value_collapse"] = 1.0 if collapsed else 0.0
    if "psi" in enabled:
        out["psi"] = win.psi(ref.bin_probs, ref.bin_edges, valid, policy.psi_smoothing)
    if "ks_statistic" in enabled:
        out["ks_statistic"] = win.ks_statistic(ref.sorted_sample, valid)
    if "wasserstein_distance" in enabled:
        w1 = win.wasserstein_1d(ref.sorted_sample, valid)
        out["wasserstein_distance"] = w1 / scale if scale > _EPS else math.nan
    return out


def score_windows(
    df: pd.DataFrame,
    sensors: list[str],
    profile_arr: np.ndarray,
    refs: dict[tuple[str, str], UnivariateReference],
    policy: DriftPolicy,
    *,
    view: str,
    scope: str = "sensor",
    exclusion_mask: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    """Long-form metric rows for every (window, sensor, scope) triple.

    ``exclusion_mask`` (healthy-only view) is a boolean frame on ``df.index``
    with one column per sensor; ``True`` cells are removed before metrics.
    """
    window_labels = win.window_starts(
        pd.DatetimeIndex(df.index), policy.windows
    ).to_numpy()
    scope_keys = sorted({key for (_, key) in refs})
    group_index: dict[str, dict[object, np.ndarray]] = {}
    frame = pd.DataFrame({"window": window_labels, "profile": profile_arr})
    group_index[GLOBAL_SCOPE_KEY] = {
        k: v.to_numpy() for k, v in frame.groupby("window").groups.items()
    }
    per_profile = frame.groupby(["window", "profile"]).groups

    rows: list[dict[str, object]] = []
    unsupported: list[dict[str, str]] = []
    fully_masked: dict[tuple[str, str], int] = {}
    for sensor in sensors:
        values = df[sensor].to_numpy(dtype=float)
        masked = (
            exclusion_mask[sensor].to_numpy()
            if exclusion_mask is not None and sensor in exclusion_mask.columns
            else None
        )
        for scope_key in scope_keys:
            ref = refs.get((sensor, scope_key))
            if ref is None:
                continue
            if scope_key == GLOBAL_SCOPE_KEY:
                groups: dict[object, np.ndarray] = group_index[GLOBAL_SCOPE_KEY]
            else:
                groups = {
                    w: idx.to_numpy()
                    for (w, p), idx in per_profile.items()
                    if p == scope_key
                }
            for window, idx in groups.items():
                vals = values[idx]
                if masked is not None:
                    keep = ~masked[idx]
                    if not keep.any():
                        key = (sensor, scope_key)
                        fully_masked[key] = fully_masked.get(key, 0) + 1
                        continue
                    vals = vals[keep]
                n_valid = int((~np.isnan(vals)).sum())
                if (
                    len(vals) < policy.windows.min_rows_per_window
                    or n_valid / len(vals) < policy.windows.min_valid_fraction
                ):
                    continue
                for metric, value in _window_metrics(
                    vals, ref, policy.univariate
                ).items():
                    rows.append(
                        {
                            "window_start": window,
                            "scope": scope,
                            "view": view,
                            "entity": sensor,
                            "profile": scope_key,
                            "metric": metric,
                            "value": value,
                            "n_rows": len(vals),
                            "n_valid": n_valid,
                        }
                    )
    for (sensor, scope_key), count in sorted(fully_masked.items()):
        unsupported.append(
            {
                "scope": scope,
                "view": view,
                "entity": sensor,
                "profile": scope_key,
                "reason": f"all_rows_health_excluded ({count} windows)",
            }
        )
    return pd.DataFrame(rows, columns=SCORE_ROW_COLUMNS), unsupported
