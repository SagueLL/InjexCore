"""Relationship reports over the fitted correlation reference.

Pure projections of the long-form correlation table — no new statistics are
computed here, so everything stays traceable to the training-window fit.
"""

from __future__ import annotations

import pandas as pd

from src.intelligence.correlation.policy import CorrelationPolicy


def strongest_pairs(
    correlations: pd.DataFrame, policy: CorrelationPolicy
) -> pd.DataFrame:
    """Pairs with |Pearson| at or above the strong threshold, strongest first."""
    if correlations.empty:
        return correlations.assign(sign=pd.Series(dtype=str))
    strong = correlations[
        correlations["pearson"].abs() >= policy.thresholds.strong_threshold
    ].copy()
    strong["sign"] = strong["pearson"].map(
        lambda v: "positive" if v >= 0 else "negative"
    )
    return strong.reindex(
        strong["pearson"].abs().sort_values(ascending=False).index
    ).reset_index(drop=True)


def redundant_pairs(
    correlations: pd.DataFrame, policy: CorrelationPolicy
) -> pd.DataFrame:
    """Pairs redundant under *both* metrics — candidates for feature pruning.

    Requiring Pearson and Spearman to clear the threshold together avoids
    flagging pairs whose linear correlation is inflated by a few extremes.
    """
    if correlations.empty:
        return correlations.copy()
    t = policy.thresholds.redundancy_threshold
    redundant = correlations[
        (correlations["pearson"].abs() >= t) & (correlations["spearman"].abs() >= t)
    ].copy()
    return redundant.reindex(
        redundant["pearson"].abs().sort_values(ascending=False).index
    ).reset_index(drop=True)
