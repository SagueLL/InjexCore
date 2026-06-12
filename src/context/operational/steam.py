"""Steam-conditioning context derivation (profile-independent).

A per-row activity indicator (pressure OR loop-temperature above their
activation thresholds; one missing signal lets the other decide) is smoothed
with a centered persistence window — classification is never single-row:

* ``steam_conditioning_on``           — sustained activity (fraction ≥ on)
* ``steam_conditioning_off``          — sustained inactivity (fraction ≤ off)
* ``steam_conditioning_intermittent`` — toggling / unstable activation
* ``unknown``                         — too few valid indicator rows

Steam context is deliberately independent of the operational profile: it is
an instrumentation read; profile × steam cross-tables live in the report.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.context.operational.policy import SteamPolicy

STEAM_CONTEXTS = (
    "steam_conditioning_off",
    "steam_conditioning_intermittent",
    "steam_conditioning_on",
    "unknown",
)


def steam_activity_indicator(df: pd.DataFrame, policy: SteamPolicy) -> pd.Series:
    """Per-row indicator: 1.0 active, 0.0 inactive, NaN when both inputs NaN."""
    pressure = df.get(policy.pressure_sensor)
    temp = df.get(policy.temp_sensor)
    p = pressure if pressure is not None else pd.Series(np.nan, index=df.index)
    t = temp if temp is not None else pd.Series(np.nan, index=df.index)
    known = p.notna() | t.notna()
    active = (p.notna() & (p >= policy.pressure_active_threshold)) | (
        t.notna() & (t >= policy.temp_active_threshold)
    )
    out = pd.Series(np.nan, index=df.index, name="steam_active")
    out[known] = active[known].astype(float)
    return out


def classify_steam_context(
    indicator: pd.Series, df: pd.DataFrame, policy: SteamPolicy
) -> pd.DataFrame:
    """Centered-window persistence classification + confidence + evidence."""
    w = policy.window_rows
    valid_count = indicator.rolling(w, center=True, min_periods=1).count()
    active_frac = indicator.rolling(w, center=True, min_periods=1).mean()

    f = active_frac.to_numpy()
    cnt = valid_count.to_numpy()
    context = np.full(len(indicator), "steam_conditioning_intermittent", dtype=object)
    context[f >= policy.on_fraction] = "steam_conditioning_on"
    context[f <= policy.off_fraction] = "steam_conditioning_off"
    context[cnt < policy.min_valid_rows] = "unknown"

    margin = np.where(
        context == "steam_conditioning_on",
        (f - policy.on_fraction) / (1.0 - policy.on_fraction + 1e-12),
        np.where(
            context == "steam_conditioning_off",
            (policy.off_fraction - f) / (policy.off_fraction + 1e-12),
            np.minimum(f - policy.off_fraction, policy.on_fraction - f)
            / ((policy.on_fraction - policy.off_fraction) / 2.0),
        ),
    )
    confidence = np.clip(margin, 0.0, 1.0) * np.clip(cnt / w, 0.0, 1.0)
    confidence[context == "unknown"] = 0.0

    p_med = _rolling_median(df, policy.pressure_sensor, w)
    t_med = _rolling_median(df, policy.temp_sensor, w)
    evidence = [
        f"f={'' if np.isnan(fv) else format(fv, '.3f')};valid={int(cv)}/{w};"
        f"p_med={_fmt(pm)};t_med={_fmt(tm)}"
        for fv, cv, pm, tm in zip(f, cnt, p_med, t_med, strict=True)
    ]
    return pd.DataFrame(
        {
            "steam_context": context,
            "steam_context_confidence": np.round(confidence, 4),
            "steam_context_evidence": evidence,
        },
        index=indicator.index,
    )


def _rolling_median(df: pd.DataFrame, column: str, window: int) -> np.ndarray:
    if column not in df.columns:
        return np.full(len(df), np.nan)
    return df[column].rolling(window, center=True, min_periods=1).median().to_numpy()


def _fmt(value: float) -> str:
    return "na" if np.isnan(value) else format(value, ".2f")
