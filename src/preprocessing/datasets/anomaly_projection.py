"""Anomaly-detection dataset projection.

Selects the columns from master that best characterise *local
behavioural deviation* — rolling stability metrics, derivatives,
state-evolution counters and statistical-anomaly scores — for
unsupervised models such as Isolation Forest, Autoencoders and DBSCAN.

The actual selection rules live in
``configs/specialized_datasets.yaml`` under the ``anomaly_detection``
key; this module is a thin wrapper around
:func:`src.preprocessing.datasets.selectors.project`.
"""

from __future__ import annotations

import pandas as pd

from src.preprocessing.datasets.column_groups import ColumnGroups
from src.preprocessing.datasets.policy import SpecializedDatasetsPolicy
from src.preprocessing.datasets.reporting import Finding
from src.preprocessing.datasets.selectors import project

CHECK_NAME = "anomaly_detection"


def run(
    master: pd.DataFrame,
    policy: SpecializedDatasetsPolicy,
    groups: ColumnGroups,
) -> tuple[pd.DataFrame, list[Finding]]:
    return project(master, policy.anomaly_detection, groups, check_name=CHECK_NAME)
