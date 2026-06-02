"""Energy dataset projection.

Selects the columns from master relevant to *energetic optimisation
and industrial efficiency* — raw power and production signals,
cumulative kWh, kWh-per-kg windows, energy-balance ratios, plus
operational load context (running-fraction windows). Targets
energy-efficiency studies, kWh-budget modelling and load-shifting
analysis.

Rules live in ``configs/specialized_datasets.yaml`` under the
``energy`` key; this module is a thin wrapper around
:func:`src.preprocessing.datasets.selectors.project`.
"""

from __future__ import annotations

import pandas as pd

from src.preprocessing.datasets.column_groups import ColumnGroups
from src.preprocessing.datasets.policy import SpecializedDatasetsPolicy
from src.preprocessing.datasets.reporting import Finding
from src.preprocessing.datasets.selectors import project

CHECK_NAME = "energy"


def run(
    master: pd.DataFrame,
    policy: SpecializedDatasetsPolicy,
    groups: ColumnGroups,
) -> tuple[pd.DataFrame, list[Finding]]:
    return project(master, policy.energy, groups, check_name=CHECK_NAME)
