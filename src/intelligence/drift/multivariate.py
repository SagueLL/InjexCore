"""Multivariate drift — distribution shifts of *persisted* model scores.

Consumes the anomaly run's per-row detector scores and the pca run's
per-profile T2 / Q-SPE / reconstruction-error scores. Nothing is refitted
and no score is recomputed: drift here means "the distribution of what the
fitted models already said has moved" — measured with the same windowed,
train-referenced machinery as univariate sensor drift.

Healthy-only handling has two honest levels:

* Level A (always): drift events whose evidence is dominated by faulty /
  quarantine-recommended sensors are *filtered from the healthy view* — the
  raw view keeps them; the comparison table records the exclusion.
* Level B (optional): a per-row analytical proxy ``q_spe -`` (persisted
  per-feature contributions of excluded sensors), clipped at zero, labeled
  ``healthy_only_proxy``. This is an interpretive approximation, never a
  rescoring of the upstream model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.intelligence.drift import univariate as uni
from src.intelligence.drift import windows as win
from src.intelligence.drift.policy import (
    GLOBAL_SCOPE_KEY,
    HEALTHY_ONLY_PROXY_LABEL,
    DriftPolicy,
)

FLAGGED_SEVERITIES = ("warning", "anomaly")


def assemble_score_frame(
    anomaly_scores: pd.DataFrame,
    pca_scores: pd.DataFrame,
    master_index: pd.DatetimeIndex,
    policy: DriftPolicy,
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    """Aligned per-row score matrix on the master index.

    Columns: the configured anomaly + pca score columns that exist, plus
    ``severity_flagged`` (0/1) and ``n_triggered_detectors``. Rows the pca
    run skipped stay NaN and are reported by the windowed gating, never
    NaN-poisoned into references.
    """
    unsupported: list[dict[str, str]] = []
    frame = pd.DataFrame(index=master_index)

    anomaly_aligned = anomaly_scores.reindex(master_index)
    for col in policy.multivariate.anomaly_score_columns:
        if col in anomaly_aligned.columns:
            frame[col] = pd.to_numeric(anomaly_aligned[col], errors="coerce")
        else:
            unsupported.append(
                {
                    "scope": "multivariate",
                    "view": "raw",
                    "entity": col,
                    "profile": GLOBAL_SCOPE_KEY,
                    "reason": "column_missing_in_anomaly_run",
                }
            )

    pca_aligned = (
        pca_scores.reindex(master_index) if len(pca_scores) else pd.DataFrame()
    )
    for col in policy.multivariate.pca_score_columns:
        if len(pca_aligned) and col in pca_aligned.columns:
            frame[col] = pd.to_numeric(pca_aligned[col], errors="coerce")
        else:
            unsupported.append(
                {
                    "scope": "multivariate",
                    "view": "raw",
                    "entity": col,
                    "profile": GLOBAL_SCOPE_KEY,
                    "reason": "column_missing_in_pca_run",
                }
            )

    if "severity" in anomaly_aligned.columns:
        frame["severity_flagged"] = (
            anomaly_aligned["severity"].isin(FLAGGED_SEVERITIES).astype(float)
        )
    if "triggered_detectors" in anomaly_aligned.columns:
        triggered = anomaly_aligned["triggered_detectors"].fillna("").astype(str)
        frame["n_triggered_detectors"] = (
            triggered.str.split("|")
            .map(lambda ts: sum(1 for t in ts if t))
            .astype(float)
        )
    return frame, unsupported


def score_columns(policy: DriftPolicy) -> list[str]:
    """The continuous score columns evaluated with the windowed machinery."""
    return list(policy.multivariate.anomaly_score_columns) + list(
        policy.multivariate.pca_score_columns
    )


def rate_shift_rows(
    score_frame: pd.DataFrame,
    profile_arr: np.ndarray,
    train_arr: np.ndarray,
    policy: DriftPolicy,
) -> pd.DataFrame:
    """Severity-rate and detector-agreement shifts per window and scope."""
    rate_columns: list[tuple[str, str]] = []
    if policy.multivariate.severity_rate and "severity_flagged" in score_frame:
        rate_columns.append(("severity_flagged", "severity_rate_shift"))
    if (
        policy.multivariate.detector_agreement
        and "n_triggered_detectors" in score_frame
    ):
        rate_columns.append(("n_triggered_detectors", "detector_agreement_shift"))
    if not rate_columns:
        return pd.DataFrame(columns=uni.SCORE_ROW_COLUMNS)

    profiles, _ = uni.supported_profiles(profile_arr, train_arr, policy.profiles)
    window_labels = win.window_starts(
        pd.DatetimeIndex(score_frame.index), policy.windows
    ).to_numpy()
    base = pd.DataFrame(
        {"window": window_labels, "profile": profile_arr}, index=score_frame.index
    )

    rows: list[dict[str, object]] = []
    for column, metric in rate_columns:
        values = score_frame[column]
        scopes: list[tuple[str, pd.Series]] = [
            (GLOBAL_SCOPE_KEY, pd.Series(True, index=score_frame.index))
        ]
        scopes += [
            (p, pd.Series(profile_arr == p, index=score_frame.index)) for p in profiles
        ]
        for scope_key, scope_mask in scopes:
            scoped = values[scope_mask.to_numpy()]
            if not len(scoped):
                continue
            train_rate = float(
                scoped[train_arr[scope_mask.to_numpy()]].mean(skipna=True)
            )
            if np.isnan(train_rate):
                continue
            grouped = scoped.groupby(base.loc[scope_mask, "window"])
            for window, mean_value in grouped.mean().items():
                count = int(grouped.size()[window])
                if count < policy.windows.min_rows_per_window:
                    continue
                rows.append(
                    {
                        "window_start": window,
                        "scope": "multivariate",
                        "view": "raw",
                        "entity": metric.removesuffix("_shift"),
                        "profile": scope_key,
                        "metric": metric,
                        "value": float(mean_value) - train_rate,
                        "n_rows": count,
                        "n_valid": count,
                    }
                )
    return pd.DataFrame(rows, columns=uni.SCORE_ROW_COLUMNS)


def _contribution_dominance(
    contributions: pd.DataFrame,
    exclusion_mask: pd.DataFrame,
    policy: DriftPolicy,
) -> pd.Series:
    """Per-window fraction of pca reconstruction mass on excluded sensors."""
    if not len(contributions):
        return pd.Series(dtype=float)
    sensors = [c for c in contributions.columns if c in exclusion_mask.columns]
    if not sensors:
        return pd.Series(dtype=float)
    contrib = contributions[sensors].abs()
    mask = exclusion_mask.reindex(contrib.index)[sensors].fillna(False)
    total = contrib.sum(axis=1)
    excluded = contrib.where(mask.to_numpy(), 0.0).sum(axis=1)
    valid = total > 0
    ratio = excluded[valid] / total[valid]
    if not len(ratio):
        return pd.Series(dtype=float)
    windows = win.window_starts(pd.DatetimeIndex(ratio.index), policy.windows)
    return ratio.groupby(windows).mean()


def _affected_dominance(
    anomaly_scores: pd.DataFrame,
    exclusion_mask: pd.DataFrame,
    policy: DriftPolicy,
) -> pd.Series:
    """Per-window fraction of flagged rows attributed to excluded sensors.

    Covers detectors whose models include sensors absent from the pca
    feature set. A flagged row counts as excluded-sensor-driven when its
    *primary* attribution (the first ``affected_variables`` token — ranked
    by the anomaly run) is excluded at that timestamp: rank-1 attribution to
    a faulty sensor is precisely the evidence the Level-A filter targets.
    """
    needed = {"severity", "affected_variables"}
    if not len(anomaly_scores) or not needed <= set(anomaly_scores.columns):
        return pd.Series(dtype=float)
    flagged = anomaly_scores[anomaly_scores["severity"].isin(FLAGGED_SEVERITIES)]
    if not len(flagged):
        return pd.Series(dtype=float)
    mask = exclusion_mask.reindex(flagged.index).fillna(False)
    top_token = (
        flagged["affected_variables"].fillna("").astype(str).str.split("|").str[0]
    )
    dominated = np.zeros(len(flagged))
    for sensor in mask.columns:
        hits = (top_token == sensor).to_numpy() & mask[sensor].to_numpy()
        dominated[hits] = 1.0
    series = pd.Series(dominated, index=flagged.index)
    windows = win.window_starts(pd.DatetimeIndex(series.index), policy.windows)
    return series.groupby(windows).mean()


def window_dominance(
    contributions: pd.DataFrame,
    anomaly_scores: pd.DataFrame,
    exclusion_mask: pd.DataFrame,
    policy: DriftPolicy,
) -> pd.Series:
    """Per-window evidence dominance of excluded sensors (Level-A filter).

    The maximum of two complementary estimates: pca reconstruction-mass
    dominance (sensors inside the pca feature set) and anomaly
    ``affected_variables`` dominance (detectors fitted on the full sensor
    scope). Used to exclude healthy-view events whose evidence is dominated
    by faulty/quarantined sensors — recorded transparently, never silent.
    """
    contrib = _contribution_dominance(contributions, exclusion_mask, policy)
    affected = _affected_dominance(anomaly_scores, exclusion_mask, policy)
    if not len(contrib) and not len(affected):
        return pd.Series(dtype=float)
    combined = pd.concat([contrib.rename("c"), affected.rename("a")], axis=1)
    return combined.max(axis=1).rename("dominance")


def healthy_only_proxy_series(
    score_frame: pd.DataFrame,
    contributions: pd.DataFrame,
    exclusion_mask: pd.DataFrame,
) -> pd.Series | None:
    """Level-B analytical proxy: ``q_spe`` minus excluded-sensor contributions.

    Documented approximation (contributions are the persisted per-feature
    reconstruction components of Q-SPE). Clipped at zero. ``None`` when the
    inputs cannot support it. The result is always labeled
    ``healthy_only_proxy`` downstream — never presented as a rescoring.
    """
    if "q_spe" not in score_frame.columns or not len(contributions):
        return None
    sensors = [c for c in contributions.columns if c in exclusion_mask.columns]
    if not sensors:
        return None
    contrib = contributions[sensors].reindex(score_frame.index)
    mask = exclusion_mask[sensors].reindex(score_frame.index).fillna(False)
    removed = contrib.abs().where(mask.to_numpy(), 0.0).sum(axis=1)
    proxy = (score_frame["q_spe"] - removed).clip(lower=0.0)
    proxy[score_frame["q_spe"].isna()] = np.nan
    return proxy.rename(HEALTHY_ONLY_PROXY_LABEL)
