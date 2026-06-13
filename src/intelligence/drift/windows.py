"""Window machinery + pure-numpy distribution-distance metrics.

Drift metrics compare each tumbling observation window against a reference
built from the behaviour train window only. The three distribution distances
(PSI, two-sample KS statistic, Wasserstein-1) are implemented directly on
sorted numpy arrays — closed 1-D ECDF forms, no scipy dependency (scipy is
only a transitive dependency of the optional ``[models]`` extra and drift
must stay importable under the core install).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.intelligence.drift.policy import WindowsPolicy

_FREQ = {"hourly": "1h", "daily": "1D"}


def window_starts(index: pd.DatetimeIndex, policy: WindowsPolicy) -> pd.DatetimeIndex:
    """Tumbling window label (floor of the timestamp) for every row."""
    return index.floor(_FREQ[policy.granularity])


def window_length(policy: WindowsPolicy) -> pd.Timedelta:
    """Nominal duration of one tumbling window."""
    return pd.Timedelta(_FREQ[policy.granularity])


def ks_statistic(ref_sorted: np.ndarray, sample: np.ndarray) -> float:
    """Two-sample Kolmogorov-Smirnov statistic: max |ECDF_ref - ECDF_sample|.

    ``ref_sorted`` must be sorted and NaN-free; ``sample`` is cleaned here.
    Matches ``scipy.stats.ks_2samp(...).statistic``.
    """
    sample = np.sort(sample[~np.isnan(sample)])
    if len(ref_sorted) == 0 or len(sample) == 0:
        return float("nan")
    pooled = np.concatenate([ref_sorted, sample])
    cdf_ref = np.searchsorted(ref_sorted, pooled, side="right") / len(ref_sorted)
    cdf_sample = np.searchsorted(sample, pooled, side="right") / len(sample)
    return float(np.abs(cdf_ref - cdf_sample).max())


def wasserstein_1d(ref_sorted: np.ndarray, sample: np.ndarray) -> float:
    """Wasserstein-1 distance: integral of |ECDF_ref - ECDF_sample|.

    Matches ``scipy.stats.wasserstein_distance``. Returned in the variable's
    own units — callers normalize by a reference scale before scoring.
    """
    sample = np.sort(sample[~np.isnan(sample)])
    if len(ref_sorted) == 0 or len(sample) == 0:
        return float("nan")
    all_values = np.sort(np.concatenate([ref_sorted, sample]))
    deltas = np.diff(all_values)
    if len(deltas) == 0:
        return 0.0
    cdf_ref = np.searchsorted(ref_sorted, all_values[:-1], side="right") / len(
        ref_sorted
    )
    cdf_sample = np.searchsorted(sample, all_values[:-1], side="right") / len(sample)
    return float(np.sum(np.abs(cdf_ref - cdf_sample) * deltas))


def psi_bin_edges(train_values: np.ndarray, bins: int) -> np.ndarray:
    """Quantile bin edges from the train sample (outer edges open to ±inf)."""
    clean = train_values[~np.isnan(train_values)]
    if len(clean) == 0:
        return np.array([])
    edges = np.unique(np.quantile(clean, np.linspace(0.0, 1.0, bins + 1)))
    if len(edges) < 2:  # constant signal — a single degenerate bin
        edges = np.array([edges[0], edges[0]]) if len(edges) else np.array([])
    inner = edges[1:-1]
    return np.concatenate([[-np.inf], inner, [np.inf]])


def bin_probabilities(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Per-bin probability mass of ``values`` under ``edges``."""
    clean = values[~np.isnan(values)]
    if len(clean) == 0 or len(edges) < 2:
        return np.array([])
    counts, _ = np.histogram(clean, bins=edges)
    return counts / len(clean)


def psi(
    ref_probs: np.ndarray, edges: np.ndarray, sample: np.ndarray, smoothing: float
) -> float:
    """Population Stability Index of ``sample`` against the train bins."""
    sample_probs = bin_probabilities(sample, edges)
    if len(ref_probs) == 0 or len(sample_probs) != len(ref_probs):
        return float("nan")
    p = np.clip(ref_probs, smoothing, None)
    q = np.clip(sample_probs, smoothing, None)
    p = p / p.sum()
    q = q / q.sum()
    return float(np.sum((q - p) * np.log(q / p)))


def categorical_psi(
    ref_probs: dict[str, float], sample_counts: dict[str, int], smoothing: float
) -> float:
    """PSI over a categorical vocabulary (union of train + sample categories)."""
    total = sum(sample_counts.values())
    if total == 0:
        return float("nan")
    categories = sorted(set(ref_probs) | set(sample_counts))
    p = np.array([max(ref_probs.get(c, 0.0), smoothing) for c in categories])
    q = np.array([max(sample_counts.get(c, 0) / total, smoothing) for c in categories])
    p = p / p.sum()
    q = q / q.sum()
    return float(np.sum((q - p) * np.log(q / p)))


def total_variation(
    ref_probs: dict[str, float], sample_counts: dict[str, int]
) -> float:
    """Total-variation distance between train and sample category masses."""
    total = sum(sample_counts.values())
    if total == 0:
        return float("nan")
    categories = set(ref_probs) | set(sample_counts)
    return 0.5 * float(
        sum(
            abs(ref_probs.get(c, 0.0) - sample_counts.get(c, 0) / total)
            for c in categories
        )
    )


def downsample_sorted(values: np.ndarray, max_sample: int) -> np.ndarray:
    """Deterministic quantile-spaced downsample of a sorted, NaN-free array."""
    clean = np.sort(values[~np.isnan(values)])
    if len(clean) <= max_sample:
        return clean
    idx = np.linspace(0, len(clean) - 1, max_sample).round().astype(int)
    return clean[idx]
