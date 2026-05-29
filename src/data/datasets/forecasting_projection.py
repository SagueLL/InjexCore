"""Forecasting dataset projection.

Selects the columns from master that carry *predictive temporal
structure* — lags, percent changes, rolling means / std / trend, runtime
fractions and SP–PV deviations — plus the raw process-sensor signals so
they can be used as forecasting targets. Optimised for LSTM /
Transformer / XGBoost-forecasting workloads.

Rules live in ``configs/specialized_datasets.yaml`` under the
``forecasting`` key; this module is a thin wrapper around
:func:`src.data.datasets.selectors.project`.
"""
from __future__ import annotations

import pandas as pd

from src.data.datasets.column_groups import ColumnGroups
from src.data.datasets.policy import SpecializedDatasetsPolicy
from src.data.datasets.reporting import Finding
from src.data.datasets.selectors import project

CHECK_NAME = "forecasting"


def run(
    master: pd.DataFrame,
    policy: SpecializedDatasetsPolicy,
    groups: ColumnGroups,
) -> tuple[pd.DataFrame, list[Finding]]:
    return project(master, policy.forecasting, groups, check_name=CHECK_NAME)
