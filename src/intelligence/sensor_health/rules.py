"""Rule engine for Sensor Health Intelligence.

Every rule family consumes one sensor's values + the per-row profile labels
and returns a :class:`RuleResult` (per-row boolean mask + strength in [0,1]
+ static detail). References are computed on the behaviour **train window
only** — leakage-safe — and respect the same profile-aware suppression the
rules apply, so a sensor that legitimately sits at zero while ``stopped``
calibrates and evaluates against its *abnormal* behaviour only.

Shared suppression mechanic: candidate runs are computed globally, rows in
the sensor's allowed profiles are dropped, and the surviving contiguous
segments are re-thresholded independently — a stopped→startup zero run keeps
only its startup part, which must clear the minimum duration on its own.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import numpy as np
import pandas as pd

from src.intelligence.sensor_health.policy import (
    SensorHealthPolicy,
    SensorMeta,
    resolve_sensor_meta,
)

CHECK = "sensor_health"

#: Per-row counter-reset sub-states (richer vocabulary inside one family).
COUNTER_STATES = (
    "reset_detected",
    "reset_to_zero",
    "recovered_after_reset",
    "persistent_zero_after_reset",
)


@dataclass
class RuleResult:
    """One rule family's per-row verdict for one sensor."""

    issue_type: str
    mask: np.ndarray  # bool [n]
    strength: np.ndarray  # float [n] in [0, 1]
    detail: dict[str, Any] = field(default_factory=dict)
    substates: np.ndarray | None = None  # counter_reset only


@dataclass
class RuleReferences:
    """Train-window references per sensor (+ per-(profile, sensor) scale)."""

    train_max_constant_run: dict[str, int] = field(default_factory=dict)
    train_max_zero_run: dict[str, int] = field(default_factory=dict)
    train_zero_fraction: dict[str, float] = field(default_factory=dict)
    train_nan_fraction: dict[str, float] = field(default_factory=dict)
    train_max_rolling_nan_fraction: dict[str, float] = field(default_factory=dict)
    train_min_roll_std: dict[tuple[str, str], float] = field(default_factory=dict)
    train_min_unique_fraction: dict[str, float] = field(default_factory=dict)
    train_median: dict[str, float] = field(default_factory=dict)
    scale: dict[tuple[str, str], float] = field(default_factory=dict)
    unsupported: list[dict[str, str]] = field(default_factory=list)


def run_segments(mask: np.ndarray) -> list[tuple[int, int]]:
    """Half-open ``[i, j)`` index ranges of True runs."""
    if len(mask) == 0 or not mask.any():
        return []
    m = mask.astype(np.int8)
    diff = np.diff(m)
    starts = (np.flatnonzero(diff == 1) + 1).tolist()
    ends = (np.flatnonzero(diff == -1) + 1).tolist()
    if m[0]:
        starts = [0, *starts]
    if m[-1]:
        ends = [*ends, len(m)]
    return list(zip(starts, ends, strict=True))


def equal_run_segments(values: np.ndarray, eps: float) -> list[tuple[int, int]]:
    """Maximal runs of equal (within ``eps``) consecutive non-NaN values."""
    n = len(values)
    if n == 0:
        return []
    valid = ~np.isnan(values)
    if eps == 0.0:
        same = (values[1:] == values[:-1]) & valid[1:] & valid[:-1]
    else:
        same = (np.abs(np.diff(values)) <= eps) & valid[1:] & valid[:-1]
    boundaries = np.flatnonzero(~same) + 1
    starts = np.concatenate(([0], boundaries))
    ends = np.concatenate((boundaries, [n]))
    return [(int(i), int(j)) for i, j in zip(starts, ends, strict=True) if valid[i]]


def _flag_runs(
    n: int,
    candidate_runs: list[tuple[int, int]],
    suppressed: np.ndarray,
    threshold: int,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, int]]]:
    """Suppress + re-segment candidate runs; threshold surviving segments.

    Strength per surviving segment = ``min(1, rows / (2 * threshold))``.
    """
    mask = np.zeros(n, dtype=bool)
    strength = np.zeros(n, dtype=float)
    kept: list[dict[str, int]] = []
    for i, j in candidate_runs:
        if j - i < threshold:
            continue  # cannot survive suppression either
        for si, sj in run_segments(~suppressed[i:j]):
            rows = sj - si
            if rows < threshold:
                continue
            mask[i + si : i + sj] = True
            strength[i + si : i + sj] = min(1.0, rows / (2 * threshold))
            kept.append(
                {"start": i + si, "end": i + sj, "rows": rows, "orig_rows": j - i}
            )
    return mask, strength, kept


@dataclass
class SensorContext:
    """Everything the rule functions need for one sensor."""

    sensor: str
    values: np.ndarray
    profiles: np.ndarray
    train_mask: np.ndarray
    profile_change: np.ndarray  # bool [n]; [0] = False
    meta: SensorMeta
    refs: RuleReferences
    policy: SensorHealthPolicy

    def profile_in(self, names: list[str]) -> np.ndarray:
        if not names:
            return np.zeros(len(self.values), dtype=bool)
        return np.isin(self.profiles, np.array(names, dtype=object))

    @cached_property
    def scale_row(self) -> np.ndarray:
        """Per-row robust scale from the row's own profile baseline."""
        lookup = {p: s for (p, sn), s in self.refs.scale.items() if sn == self.sensor}
        return pd.Series(self.profiles).map(lookup).astype(float).to_numpy()

    def pure_window(self, window: int) -> np.ndarray:
        """True where the trailing ``window`` rows share one profile."""
        if window <= 1:
            return np.ones(len(self.values), dtype=bool)
        changes = pd.Series(self.profile_change.astype(float))
        summed = changes.rolling(window - 1, min_periods=window - 1).sum()
        return (summed == 0).to_numpy()


def train_references(
    df: pd.DataFrame,
    sensors: list[str],
    profiles: np.ndarray,
    train_mask: np.ndarray,
    baselines: pd.DataFrame,
    policy: SensorHealthPolicy,
) -> RuleReferences:
    """Compute every train-window reference, suppression-consistent."""
    refs = RuleReferences()
    fz_eps = policy.rules.flatline_zero.zero_eps
    nan_window = policy.rules.missingness_spike.window_rows
    for sensor in sensors:
        meta = resolve_sensor_meta(policy, sensor)
        x = df[sensor].to_numpy(dtype=float)[train_mask]
        prof = profiles[train_mask]
        allow_flat = np.isin(prof, np.array(meta.allow_flatline_profiles, object))
        allow_zero = np.isin(prof, np.array(meta.expected_zero_during_profiles, object))
        refs.train_max_constant_run[sensor] = _max_surviving(
            equal_run_segments(x, policy.rules.flatline.eps), allow_flat
        )
        zero_runs = run_segments((np.abs(x) <= fz_eps) & ~np.isnan(x))
        refs.train_max_zero_run[sensor] = _max_surviving(zero_runs, allow_zero)
        outside = ~allow_zero
        n_outside = int(outside.sum())
        refs.train_zero_fraction[sensor] = (
            float(((np.abs(x) <= fz_eps) & ~np.isnan(x) & outside).sum()) / n_outside
            if n_outside
            else float("nan")
        )
        refs.train_nan_fraction[sensor] = float(np.isnan(x).mean()) if len(x) else 1.0
        roll_nan = (
            pd.Series(np.isnan(x).astype(float))
            .rolling(nan_window, min_periods=nan_window)
            .mean()
        )
        refs.train_max_rolling_nan_fraction[sensor] = (
            float(roll_nan.max()) if roll_nan.notna().any() else 0.0
        )
        with np.errstate(all="ignore"):
            refs.train_median[sensor] = (
                float(np.nanmedian(x)) if not np.isnan(x).all() else float("nan")
            )
        _quietness_references(refs, sensor, x, prof, meta, policy)
    data_profiles = {str(p) for p in pd.unique(profiles)}
    _baseline_scales(refs, sensors, baselines, data_profiles)
    return refs


def _quietness_references(
    refs: RuleReferences,
    sensor: str,
    x_train: np.ndarray,
    prof_train: np.ndarray,
    meta: SensorMeta,
    policy: SensorHealthPolicy,
) -> None:
    """Train minima the quietness rules self-calibrate against.

    A row can only flag as collapse/stale when it is *quieter than anything
    the train window ever showed* — by construction the rules cannot
    contradict their own reference data.
    """
    n = len(x_train)
    chg = np.zeros(n, dtype=float)
    chg[1:] = (prof_train[1:] != prof_train[:-1]).astype(float)

    wc = policy.rules.variance_collapse.window_rows
    roll = pd.Series(x_train).rolling(wc, min_periods=wc).std().to_numpy()
    pure = (pd.Series(chg).rolling(wc - 1, min_periods=wc - 1).sum() == 0).to_numpy()
    for p in pd.unique(prof_train):
        sel = (prof_train == p) & pure & np.isfinite(roll)
        if sel.any():
            refs.train_min_roll_std[(str(p), sensor)] = float(roll[sel].min())

    ws = policy.rules.stale_signal.window_rows
    valid = ~np.isnan(x_train)
    changed = np.zeros(n, dtype=float)
    changed[1:] = ((x_train[1:] != x_train[:-1]) & valid[1:] & valid[:-1]).astype(float)
    frac = (
        pd.Series(changed).rolling(ws - 1, min_periods=ws - 1).sum().to_numpy() + 1.0
    ) / ws
    pure_s = (pd.Series(chg).rolling(ws - 1, min_periods=ws - 1).sum() == 0).to_numpy()
    allowed = np.isin(prof_train, np.array(meta.allow_flatline_profiles, object))
    sel = np.isfinite(frac) & valid & pure_s & ~allowed
    if sel.any():
        refs.train_min_unique_fraction[sensor] = float(frac[sel].min())


def _max_surviving(runs: list[tuple[int, int]], suppressed: np.ndarray) -> int:
    """Longest surviving segment after suppression, across all runs."""
    best = 0
    for i, j in runs:
        for si, sj in run_segments(~suppressed[i:j]):
            best = max(best, sj - si)
    return best


def _baseline_scales(
    refs: RuleReferences,
    sensors: list[str],
    baselines: pd.DataFrame,
    data_profiles: set[str],
) -> None:
    """Robust per-(profile, sensor) scale: iqr/1.349, std fallback."""
    seen: dict[str, set[str]] = {s: set() for s in sensors}
    for row in baselines.itertuples(index=False):
        if row.sensor not in seen:
            continue
        seen[row.sensor].add(str(row.profile))
        scale = float(row.iqr) / 1.349 if float(row.iqr) > 0 else float(row.std)
        if not math.isfinite(scale) or scale <= 0:
            refs.unsupported.append(
                {
                    "sensor": row.sensor,
                    "profile": str(row.profile),
                    "reason": "no_usable_scale (iqr and std collapse)",
                }
            )
            continue
        refs.scale[(str(row.profile), row.sensor)] = scale
    all_profiles = set(baselines["profile"].astype(str).unique()) | data_profiles
    for sensor, profiles_seen in seen.items():
        for profile in sorted(all_profiles - profiles_seen):
            refs.unsupported.append(
                {
                    "sensor": sensor,
                    "profile": profile,
                    "reason": "no_baseline (behaviour skipped this pair)",
                }
            )


# ---------------------------------------------------------------------------
# Rule families
# ---------------------------------------------------------------------------


def rule_flatline(ctx: SensorContext) -> RuleResult:
    p = ctx.policy.rules.flatline
    zero_eps = ctx.policy.rules.flatline_zero.zero_eps
    ref = ctx.refs.train_max_constant_run.get(ctx.sensor, 0)
    threshold = max(p.min_run_rows, math.ceil(p.train_run_multiplier * ref))
    runs = [
        (i, j)
        for i, j in equal_run_segments(ctx.values, p.eps)
        if abs(ctx.values[i]) > zero_eps  # zero runs belong to flatline_zero
    ]
    suppressed = ctx.profile_in(ctx.meta.allow_flatline_profiles)
    mask, strength, kept = _flag_runs(len(ctx.values), runs, suppressed, threshold)
    return RuleResult(
        "flatline",
        mask,
        strength,
        {"threshold_rows": threshold, "train_max_run": ref, "segments": kept},
    )


def rule_flatline_zero(ctx: SensorContext) -> RuleResult:
    p = ctx.policy.rules.flatline_zero
    valid = ~np.isnan(ctx.values)
    zero = (np.abs(ctx.values) <= p.zero_eps) & valid
    zfrac = ctx.refs.train_zero_fraction.get(ctx.sensor, float("nan"))
    abnormal = math.isfinite(zfrac) and zfrac < p.abnormal_train_zero_fraction
    min_rows = p.min_run_rows_abnormal if abnormal else p.min_run_rows
    ref = ctx.refs.train_max_zero_run.get(ctx.sensor, 0)
    threshold = max(min_rows, math.ceil(p.train_run_multiplier * ref))
    suppressed = ctx.profile_in(ctx.meta.expected_zero_during_profiles)
    mask, strength, kept = _flag_runs(
        len(ctx.values), run_segments(zero), suppressed, threshold
    )
    return RuleResult(
        "flatline_zero",
        mask,
        strength,
        {
            "threshold_rows": threshold,
            "train_max_zero_run": ref,
            "zero_is_abnormal": abnormal,
            "segments": kept,
        },
    )


def _rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    return pd.Series(values).rolling(window, min_periods=window).std().to_numpy()


def rule_variance_collapse(ctx: SensorContext) -> RuleResult:
    p = ctx.policy.rules.variance_collapse
    roll = _rolling_std(ctx.values, p.window_rows)
    scale = ctx.scale_row
    usable = np.isfinite(roll) & np.isfinite(scale) & (scale > 1e-9)
    mask = usable & (roll < p.collapse_ratio * scale)
    train_min_lookup = {
        prof: m
        for (prof, sn), m in ctx.refs.train_min_roll_std.items()
        if sn == ctx.sensor
    }
    train_min = pd.Series(ctx.profiles).map(train_min_lookup).astype(float).to_numpy()
    mask &= (
        np.isfinite(train_min)
        & (train_min > 0)
        & (roll < p.train_min_factor * train_min)
    )
    if p.require_profile_pure_window:
        mask &= ctx.pure_window(p.window_rows)
    # Quietness is legitimate wherever flatlining is (e.g. stopped power).
    mask &= ~ctx.profile_in(ctx.meta.allow_flatline_profiles)
    strength = np.zeros(len(ctx.values))
    with np.errstate(all="ignore"):
        strength[mask] = np.clip(
            1.0 - roll[mask] / (p.collapse_ratio * scale[mask]), 0.0, 1.0
        )
    return RuleResult("variance_collapse", mask, strength, {"window": p.window_rows})


def rule_variance_explosion(ctx: SensorContext) -> RuleResult:
    p = ctx.policy.rules.variance_explosion
    roll = _rolling_std(ctx.values, p.window_rows)
    scale = ctx.scale_row
    usable = np.isfinite(roll) & np.isfinite(scale) & (scale > 1e-9)
    mask = usable & (roll > p.explosion_ratio * scale)
    if p.require_profile_pure_window:
        mask &= ctx.pure_window(p.window_rows)
    strength = np.zeros(len(ctx.values))
    with np.errstate(all="ignore"):
        strength[mask] = np.clip(
            np.log2(roll[mask] / (p.explosion_ratio * scale[mask])) / 2.0, 0.0, 1.0
        )
    return RuleResult("variance_explosion", mask, strength, {"window": p.window_rows})


def rule_missingness_spike(ctx: SensorContext) -> RuleResult:
    p = ctx.policy.rules.missingness_spike
    nan_frac = (
        pd.Series(np.isnan(ctx.values).astype(float))
        .rolling(p.window_rows, min_periods=p.window_rows)
        .mean()
        .to_numpy()
    )
    train_frac = ctx.refs.train_nan_fraction.get(ctx.sensor, 0.0)
    train_max_roll = ctx.refs.train_max_rolling_nan_fraction.get(ctx.sensor, 0.0)
    threshold = max(
        p.absolute_floor,
        train_frac + p.spike_margin,
        train_max_roll + p.train_max_margin,
    )
    mask = np.isfinite(nan_frac) & (nan_frac > threshold)
    strength = np.where(mask, nan_frac, 0.0)
    return RuleResult(
        "missingness_spike",
        mask,
        strength,
        {
            "threshold": round(threshold, 4),
            "train_nan_fraction": round(train_frac, 4),
            "train_max_rolling_nan_fraction": round(train_max_roll, 4),
        },
    )


def rule_abrupt_offset(ctx: SensorContext) -> RuleResult:
    p = ctx.policy.rules.abrupt_offset
    s = pd.Series(ctx.values)
    med = s.rolling(p.window_rows, min_periods=p.window_rows).median()
    prev = med.shift(p.window_rows)
    scale = ctx.scale_row
    with np.errstate(all="ignore"):
        z = np.abs(med.to_numpy() - prev.to_numpy()) / scale
    same_profile_2w = ctx.pure_window(2 * p.window_rows)
    detect = np.isfinite(z) & (z > p.jump_z_threshold) & same_profile_2w
    detect &= np.isfinite(scale) & (scale > 1e-9)
    mask = (
        pd.Series(detect.astype(float))
        .rolling(p.persistence_rows, min_periods=1)
        .max()
        .to_numpy()
        >= 1.0
    )
    raw_strength = np.where(
        detect, np.clip(z / (2 * p.jump_z_threshold), 0.0, 0.6), 0.0
    )
    strength = (
        pd.Series(raw_strength)
        .rolling(p.persistence_rows, min_periods=1)
        .max()
        .to_numpy()
    )
    return RuleResult("abrupt_offset", mask, strength, {"window": p.window_rows})


def rule_saturation(ctx: SensorContext, claimed_zero: np.ndarray) -> list[RuleResult]:
    p = ctx.policy.rules.saturation
    valid = ~np.isnan(ctx.values)
    suppressed = ctx.profile_in(ctx.meta.allow_flatline_profiles)
    results: list[RuleResult] = []
    bounds = (
        ("saturation_low", ctx.meta.physical_min),
        ("saturation_high", ctx.meta.physical_max),
    )
    for issue, bound in bounds:
        if bound is None:
            continue
        tol = max(p.abs_tolerance, p.rel_tolerance * abs(bound))
        at_bound = (np.abs(ctx.values - bound) <= tol) & valid
        if issue == "saturation_low" and abs(bound) <= tol:
            at_bound &= ~claimed_zero  # zero runs already owned by flatline_zero
        mask, strength, kept = _flag_runs(
            len(ctx.values), run_segments(at_bound), suppressed, p.min_run_rows
        )
        results.append(
            RuleResult(issue, mask, strength, {"bound": bound, "segments": kept})
        )
    return results


def rule_counter_reset(ctx: SensorContext) -> RuleResult | None:
    if ctx.meta.kind != "counter":
        return None
    p = ctx.policy.rules.counter_reset
    med = ctx.refs.train_median.get(ctx.sensor, float("nan"))
    if not math.isfinite(med) or med <= 0:
        return None
    n = len(ctx.values)
    ceiling = p.low_ceiling_fraction * med
    s = pd.Series(ctx.values)
    prev_max = s.shift(1).rolling(p.detect_window_rows, min_periods=1).max()
    detected = (((prev_max - s) > p.drop_fraction * med) & (s <= ceiling)).to_numpy()
    low = (ctx.values <= ceiling) & ~np.isnan(ctx.values)
    zero_eps = ctx.policy.rules.flatline_zero.zero_eps
    mask = np.zeros(n, dtype=bool)
    strength = np.zeros(n)
    substates = np.full(n, "", dtype=object)
    episodes: list[dict[str, Any]] = []
    for i, j in run_segments(low):
        if not detected[i : min(j, i + p.detect_window_rows)].any():
            continue  # low spell not initiated by a reset-magnitude drop
        state, stg = _counter_state(ctx.values, i, j, n, med, zero_eps, p)
        mask[i:j] = True
        strength[i:j] = stg
        substates[i:j] = state
        episodes.append({"start": i, "end": j, "rows": j - i, "state": state})
    return RuleResult(
        "counter_reset",
        mask,
        strength,
        {"train_median": round(med, 3), "episodes": episodes},
        substates=substates,
    )


def _counter_state(
    values: np.ndarray,
    i: int,
    j: int,
    n: int,
    med: float,
    zero_eps: float,
    p: Any,
) -> tuple[str, float]:
    """Classify one reset episode and assign its strength."""
    rows = j - i
    if rows >= p.persistent_zero_rows:
        return "persistent_zero_after_reset", 1.0
    recovered = (
        j < n
        and rows <= p.recovery_window_rows
        and not np.isnan(values[j])
        and values[j] >= p.recovery_floor_fraction * med
    )
    if recovered:
        return "recovered_after_reset", 0.5
    with np.errstate(all="ignore"):
        touches_zero = np.nanmin(np.abs(values[i:j])) <= zero_eps
    return ("reset_to_zero" if touches_zero else "reset_detected"), 0.7


def rule_stale_signal(ctx: SensorContext, claimed_flat: np.ndarray) -> RuleResult:
    p = ctx.policy.rules.stale_signal
    valid = ~np.isnan(ctx.values)
    changed = np.zeros(len(ctx.values), dtype=float)
    changed[1:] = ((ctx.values[1:] != ctx.values[:-1]) & valid[1:] & valid[:-1]).astype(
        float
    )
    uniq_approx = (
        pd.Series(changed)
        .rolling(p.window_rows - 1, min_periods=p.window_rows - 1)
        .sum()
        .to_numpy()
        + 1.0
    )
    frac = uniq_approx / p.window_rows
    mask = np.isfinite(frac) & (frac <= p.max_unique_fraction) & valid
    train_min = ctx.refs.train_min_unique_fraction.get(ctx.sensor)
    if train_min is None:
        mask[:] = False  # no usable train reference -> rule inactive
    else:
        mask &= frac < p.train_min_factor * train_min
    mask &= ~claimed_flat  # flatline / flatline_zero take precedence
    mask &= ~ctx.profile_in(ctx.meta.allow_flatline_profiles)
    mask &= ctx.pure_window(p.window_rows)  # never judge across a regime change
    strength = np.where(mask, 1.0, 0.0)
    return RuleResult("stale_signal", mask, strength, {"window": p.window_rows})


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def evaluate_rules(
    df: pd.DataFrame,
    sensors: list[str],
    profiles: np.ndarray,
    train_mask: np.ndarray,
    refs: RuleReferences,
    policy: SensorHealthPolicy,
) -> dict[str, list[RuleResult]]:
    """Run every enabled, non-disabled rule family per sensor."""
    profile_change = np.zeros(len(df), dtype=bool)
    profile_change[1:] = profiles[1:] != profiles[:-1]
    out: dict[str, list[RuleResult]] = {}
    for sensor in sensors:
        ctx = SensorContext(
            sensor=sensor,
            values=df[sensor].to_numpy(dtype=float),
            profiles=profiles,
            train_mask=train_mask,
            profile_change=profile_change,
            meta=resolve_sensor_meta(policy, sensor),
            refs=refs,
            policy=policy,
        )
        out[sensor] = _evaluate_sensor(ctx)
    return out


def _enabled(ctx: SensorContext, name: str, rule_policy: Any) -> bool:
    return bool(rule_policy.enabled) and name not in set(ctx.meta.disabled_rules)


def _evaluate_sensor(ctx: SensorContext) -> list[RuleResult]:
    rules = ctx.policy.rules
    results: list[RuleResult] = []
    n = len(ctx.values)
    fz_mask = np.zeros(n, dtype=bool)
    flat_mask = np.zeros(n, dtype=bool)

    if _enabled(ctx, "flatline_zero", rules.flatline_zero):
        fz = rule_flatline_zero(ctx)
        results.append(fz)
        fz_mask = fz.mask
    if _enabled(ctx, "flatline", rules.flatline):
        fl = rule_flatline(ctx)
        results.append(fl)
        flat_mask = fl.mask
    if _enabled(ctx, "variance_collapse", rules.variance_collapse):
        results.append(rule_variance_collapse(ctx))
    if _enabled(ctx, "variance_explosion", rules.variance_explosion):
        results.append(rule_variance_explosion(ctx))
    if _enabled(ctx, "missingness_spike", rules.missingness_spike):
        results.append(rule_missingness_spike(ctx))
    if _enabled(ctx, "abrupt_offset", rules.abrupt_offset):
        results.append(rule_abrupt_offset(ctx))
    if _enabled(ctx, "saturation", rules.saturation):
        results.extend(rule_saturation(ctx, fz_mask))
    if _enabled(ctx, "counter_reset", rules.counter_reset):
        cr = rule_counter_reset(ctx)
        if cr is not None:
            results.append(cr)
    if _enabled(ctx, "stale_signal", rules.stale_signal):
        results.append(rule_stale_signal(ctx, fz_mask | flat_mask))
    return results
