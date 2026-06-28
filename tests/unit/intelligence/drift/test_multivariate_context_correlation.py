"""Multivariate score shifts, dominance, proxy; context + correlation drift."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from src.intelligence.drift import context as context_mod
from src.intelligence.drift import correlation as correlation_mod
from src.intelligence.drift import multivariate as mv
from src.intelligence.drift.policy import (
    GLOBAL_SCOPE_KEY,
    HEALTHY_ONLY_PROXY_LABEL,
    DriftPolicy,
)


def _world(n: int = 240) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    idx = pd.date_range("2024-06-01", periods=n, freq="1min")
    profiles = np.array(["mid_production"] * n, dtype=object)
    train = np.arange(n) < n // 2
    return idx, profiles, train


def test_assemble_score_frame_reports_missing_columns(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    idx, _, _ = _world()
    policy = policy_factory()
    anomaly = pd.DataFrame(
        {"combined_score": np.zeros(len(idx)), "severity": "normal"}, index=idx
    )
    frame, unsupported = mv.assemble_score_frame(anomaly, pd.DataFrame(), idx, policy)
    assert "combined_score" in frame.columns
    reasons = {u["reason"] for u in unsupported}
    assert "column_missing_in_anomaly_run" in reasons
    assert "column_missing_in_pca_run" in reasons
    assert "severity_flagged" in frame.columns


def test_rate_shift_rows_severity_and_agreement(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    idx, profiles, train = _world()
    policy = policy_factory(
        windows={"granularity": "hourly", "min_rows_per_window": 20},
        profiles={"min_samples_per_profile": 50},
    )
    frame = pd.DataFrame(
        {
            "severity_flagged": np.where(train, 0.0, 1.0),
            "n_triggered_detectors": np.where(train, 0.0, 3.0),
        },
        index=idx,
    )
    rows = mv.rate_shift_rows(frame, profiles, train, policy)
    sev = rows[
        (rows.metric == "severity_rate_shift") & (rows.profile == GLOBAL_SCOPE_KEY)
    ].set_index("window_start")["value"]
    assert sev.iloc[0] < 0.1  # train window ~ train rate
    assert sev.iloc[-1] > 0.8  # validation window all flagged
    agree = rows[rows.metric == "detector_agreement_shift"]
    assert agree["value"].max() > 2.0


def test_window_dominance_rank1_attribution(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    idx, _, _ = _world()
    policy = policy_factory(windows={"granularity": "hourly"})
    half = len(idx) // 2
    anomaly = pd.DataFrame(
        {
            "severity": np.where(np.arange(len(idx)) < half, "normal", "anomaly"),
            "affected_variables": np.where(
                np.arange(len(idx)) < half, "", "bad_sensor|other"
            ),
        },
        index=idx,
    )
    mask = pd.DataFrame(False, index=idx, columns=["bad_sensor", "other"])
    mask.iloc[half:, 0] = True  # bad_sensor excluded in second half
    dominance = mv.window_dominance(pd.DataFrame(), anomaly, mask, policy)
    assert dominance.loc[dominance.index >= idx[half].floor("1h")].min() > 0.9


def test_window_dominance_from_contributions(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    idx, _, _ = _world()
    policy = policy_factory(windows={"granularity": "hourly"})
    contributions = pd.DataFrame(
        {"bad_sensor": np.full(len(idx), 9.0), "other": np.full(len(idx), 1.0)},
        index=idx,
    )
    mask = pd.DataFrame(True, index=idx, columns=["bad_sensor"])
    mask["other"] = False
    dominance = mv.window_dominance(contributions, pd.DataFrame(), mask, policy)
    assert dominance.min() > 0.85  # 9/10 of the mass is on the excluded sensor


def test_healthy_only_proxy_subtracts_excluded_contributions() -> None:
    idx, _, _ = _world(10)
    frame = pd.DataFrame({"q_spe": np.full(10, 5.0)}, index=idx)
    contributions = pd.DataFrame(
        {"bad_sensor": np.full(10, 3.0), "other": np.full(10, 1.0)}, index=idx
    )
    mask = pd.DataFrame({"bad_sensor": [True] * 10, "other": [False] * 10}, index=idx)
    proxy = mv.healthy_only_proxy_series(frame, contributions, mask)
    assert proxy is not None
    assert proxy.name == HEALTHY_ONLY_PROXY_LABEL  # honest labeling, always
    assert (proxy == 2.0).all()  # 5 - 3, never negative

    frame_neg = pd.DataFrame({"q_spe": np.full(10, 1.0)}, index=idx)
    proxy_neg = mv.healthy_only_proxy_series(frame_neg, contributions, mask)
    assert proxy_neg is not None
    assert (proxy_neg == 0.0).all()  # clipped at zero


def test_context_composition_shift_and_split_tables(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    idx, _, train = _world()
    policy = policy_factory(
        windows={"granularity": "hourly", "min_rows_per_window": 20}
    )
    timeline = pd.DataFrame(
        {
            "profile": "mid_production",
            "steam_context": np.where(train, "off", "on"),  # full flip
            "sensor_health_context": "all_sensors_healthy",
            "product_code": np.where(train, "P1", "P9"),  # new category
            "recipe_context_key": "R1",
            "bom_context_status": "matched_single_order",
        },
        index=idx,
    )
    refs = context_mod.composition_references(timeline, train, policy)
    assert refs["steam_context"] == {"off": 1.0}
    rows, table = context_mod.score_windows(timeline, refs, policy)
    last = table[table.window_start == table.window_start.max()]
    steam = last[last.column == "steam_context"].iloc[0]
    assert steam["total_variation"] > 0.9
    assert "on" in steam["new_categories"]
    product = last[last.column == "product_code"].iloc[0]
    assert "P9" in product["new_categories"]
    assert "P1" in product["disappeared_categories"]

    split = context_mod.split_shift_tables(table)
    assert set(split) == {
        "profile_composition_shift",
        "steam_context_shift",
        "sensor_health_context_shift",
        "bom_context_shift",
    }
    assert (split["steam_context_shift"]["column"] == "steam_context").all()
    assert set(split["bom_context_shift"]["column"]) <= {
        "product_code",
        "recipe_context_key",
        "bom_context_status",
    }


def _shift_row(a: str, b: str, train: float, validation: float) -> dict:
    return {
        "profile": "mid_production",
        "feature_a": a,
        "feature_b": b,
        "pearson_train": train,
        "pearson_validation": validation,
        "abs_delta": abs(validation - train),
        "n_valid_train": 100,
        "n_valid_validation": 100,
    }


def test_correlation_classification_and_sensor_awareness(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    policy = policy_factory()
    correlations = pd.DataFrame(
        [
            {
                "profile": "mid_production",
                "feature_a": a,
                "feature_b": b,
                "pearson": p,
                "spearman": p,
                "n_valid": 100,
            }
            for a, b, p in [
                ("s1", "s2", 0.9),
                ("s1", "bad", 0.8),
                ("s3", "s4", 0.5),
                ("s5", "s6", 0.1),
            ]
        ]
    )
    shift = pd.DataFrame(
        [
            _shift_row("s1", "s2", 0.9, 0.1),  # collapsed (healthy pair)
            _shift_row("s1", "bad", 0.8, 0.0),  # collapsed but bad-dominated
            _shift_row("s3", "s4", 0.5, -0.5),  # sign flip
            _shift_row("s5", "s6", 0.1, 0.8),  # newly strong
        ]
    )
    dominated = {"bad": "flatline_zero"}
    classified = correlation_mod.classify_pairs(correlations, shift, dominated, policy)
    by_pair = classified.set_index(["feature_a", "feature_b"])
    assert by_pair.loc[("s1", "s2"), "change_class"] == "collapsed"
    assert by_pair.loc[("s1", "s2"), "classification"] == "process_correlation_break"
    assert by_pair.loc[("s1", "bad"), "classification"] == "sensor_drift_evidence"
    assert by_pair.loc[("s1", "bad"), "dominant_sensor"] == "bad"
    assert by_pair.loc[("s3", "s4"), "change_class"] == "sign_flip"
    assert by_pair.loc[("s5", "s6"), "change_class"] == "newly_strong"


def test_strong_instrumentation_sensors_requires_persistent_coverage(
    policy_factory: Callable[..., DriftPolicy],
) -> None:
    policy = policy_factory()
    val_start = pd.Timestamp("2024-09-03")
    val_end = pd.Timestamp("2024-10-08")
    events = pd.DataFrame(
        [
            {
                "sensor": "bad",
                "issue_types": "flatline_zero",
                "is_persistent": True,
                "start_timestamp": pd.Timestamp("2024-09-10"),
                "end_timestamp": val_end,
            },
            {
                "sensor": "blip",
                "issue_types": "missingness_spike",
                "is_persistent": False,  # transient: never dominates
                "start_timestamp": pd.Timestamp("2024-09-12"),
                "end_timestamp": pd.Timestamp("2024-09-12 02:00"),
            },
        ]
    )
    out = correlation_mod.strong_instrumentation_sensors(
        events, val_start, val_end, policy
    )
    assert set(out) == {"bad"}
