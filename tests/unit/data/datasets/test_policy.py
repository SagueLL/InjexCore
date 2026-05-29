"""Specialized-datasets policy schema."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.data.datasets.policy import (
    SelectorSpec,
    SpecializedDatasetsPolicy,
)


def test_defaults_are_consistent(datasets_policy: SpecializedDatasetsPolicy):
    assert datasets_policy.master_validation.enabled is True
    assert datasets_policy.anomaly_detection.enabled is True
    assert datasets_policy.forecasting.enabled is True
    assert datasets_policy.energy.enabled is True
    # The default config drops the synthetic drift column.
    assert "drift" in datasets_policy.master_validation.drop_columns
    # Selectors keep metadata for joinability.
    assert datasets_policy.anomaly_detection.include_metadata is True
    assert datasets_policy.forecasting.include_metadata is True
    assert datasets_policy.energy.include_metadata is True


def test_unknown_keys_are_rejected():
    with pytest.raises(ValidationError):
        SpecializedDatasetsPolicy.model_validate({"not_a_real_section": {}})


def test_selector_unknown_keys_rejected():
    with pytest.raises(ValidationError):
        SelectorSpec.model_validate({"not_a_real_field": []})


def test_nan_fraction_bounded():
    with pytest.raises(ValidationError):
        SpecializedDatasetsPolicy.model_validate(
            {"master_validation": {"max_nan_fraction_per_column": 1.5}}
        )
    with pytest.raises(ValidationError):
        SpecializedDatasetsPolicy.model_validate(
            {"master_validation": {"max_nan_fraction_per_column": -0.01}}
        )


def test_forecasting_uses_process_sensor_category(
    datasets_policy: SpecializedDatasetsPolicy,
):
    assert "process_sensor" in datasets_policy.forecasting.include_categories


def test_energy_explicit_raw_signals(
    datasets_policy: SpecializedDatasetsPolicy,
):
    # Raw energy / production columns are pinned as explicit includes.
    for col in (
        "granulator_power",
        "conditioner_l2_power",
        "expander_ex2_power",
        "extruder_specific_energy",
        "granulator_production_rate",
    ):
        assert col in datasets_policy.energy.include_columns
