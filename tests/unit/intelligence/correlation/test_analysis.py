"""Strong-pair and redundant-pair extraction from the fitted reference."""

from __future__ import annotations

import pandas as pd
from src.intelligence.correlation.analysis import redundant_pairs, strongest_pairs
from src.intelligence.correlation.policy import CorrelationPolicy

_POLICY = CorrelationPolicy.model_validate(
    {"thresholds": {"strong_threshold": 0.8, "redundancy_threshold": 0.95}}
)


def _table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "profile": ["p"] * 4,
            "feature_a": ["a", "a", "b", "c"],
            "feature_b": ["b", "c", "c", "d"],
            "pearson": [0.99, -0.85, 0.5, 0.97],
            "spearman": [0.98, -0.80, 0.4, 0.60],
            "n_valid": [100] * 4,
        }
    )


def test_strongest_pairs_threshold_and_sign() -> None:
    strong = strongest_pairs(_table(), _POLICY)
    assert len(strong) == 3  # 0.99, -0.85, 0.97 — not 0.5
    assert strong.iloc[0]["pearson"] == 0.99  # sorted by |pearson| desc
    signs = dict(zip(strong["feature_b"], strong["sign"], strict=True))
    assert signs["c"] == "negative"
    assert signs["b"] == "positive"


def test_redundant_pairs_require_both_metrics() -> None:
    redundant = redundant_pairs(_table(), _POLICY)
    # 0.99/0.98 qualifies; 0.97/0.60 fails the Spearman requirement.
    assert len(redundant) == 1
    assert redundant.iloc[0]["feature_a"] == "a"
    assert redundant.iloc[0]["feature_b"] == "b"


def test_empty_input_passthrough() -> None:
    empty = _table().iloc[0:0]
    assert strongest_pairs(empty, _POLICY).empty
    assert redundant_pairs(empty, _POLICY).empty
