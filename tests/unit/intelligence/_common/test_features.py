"""Shared eligible-feature selection: routing, exclusions, findings."""

from __future__ import annotations

import pandas as pd
from src.intelligence._common.features import select_features
from src.intelligence._common.policy import FeatureSelectionPolicy


def test_process_sensor_source_selects_catalogue_sensors(
    behaviour_frame, groups
) -> None:
    df = behaviour_frame(n_rows=5)
    fp = FeatureSelectionPolicy()
    features, findings = select_features(df, fp, groups, check="test")
    assert features
    assert set(features) <= set(groups.process)
    assert not findings


def test_exclude_columns_always_applies(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=5)
    all_features, _ = select_features(
        df, FeatureSelectionPolicy(), groups, check="test"
    )
    dropped = all_features[0]
    features, _ = select_features(
        df,
        FeatureSelectionPolicy(exclude_columns=[dropped]),
        groups,
        check="test",
    )
    assert dropped not in features


def test_explicit_source_uses_include_columns(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=5)
    fp = FeatureSelectionPolicy(
        source="explicit", include_columns=["granulator_production_rate", "absent"]
    )
    features, _ = select_features(df, fp, groups, check="test")
    assert features == ["granulator_production_rate"]


def test_non_numeric_feature_skipped_with_finding(behaviour_frame, groups) -> None:
    df = behaviour_frame(n_rows=5)
    target = groups.process[0]
    df[target] = "text"
    features, findings = select_features(
        df, FeatureSelectionPolicy(), groups, check="test"
    )
    assert target not in features
    assert any(f.finding_type == "feature_not_numeric" for f in findings)


def test_no_features_selected_finding() -> None:
    df = pd.DataFrame({"a": [1.0]})
    fp = FeatureSelectionPolicy(source="explicit", include_columns=["absent"])
    features, findings = select_features(df, fp, groups=None, check="test")  # type: ignore[arg-type]
    assert not features
    assert any(f.finding_type == "no_features_selected" for f in findings)
