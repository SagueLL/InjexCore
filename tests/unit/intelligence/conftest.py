"""Fixtures for the Intelligence Layer unit tests.

Reuses the session-scoped ``groups`` and ``tiny_frame_factory`` fixtures
from the root ``tests/conftest.py``. ``tiny_frame_factory`` only builds the
~38 columns in ``variable_classification.csv`` — the feature-engineering
operative columns (``n_subsystems_running``, ``time_since_machine_off``,
``time_since_any_alarm``, ``any_alarm_while_running``) are added here by the
``behaviour_frame`` factory so profile/baseline tests have a master-like frame.

Iteration B components (correlation, pca, anomaly) consume *persisted*
behaviour labels, so their tests use ``labeled_frame``: a master-like frame
with randomized (eligible) process sensors plus matching profile labels and
a train mask — the same triple the components receive at runtime.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.intelligence.behaviour.policy import BehaviourPolicy, load_policy
from src.preprocessing._common.column_groups import ColumnGroups


@pytest.fixture(scope="session")
def behaviour_policy() -> BehaviourPolicy:
    """Real policy loaded from configs/behaviour_intelligence.yaml."""
    return load_policy(PROJECT_ROOT / "configs" / "behaviour_intelligence.yaml")


@pytest.fixture
def behaviour_frame(
    tiny_frame_factory: Callable[..., pd.DataFrame],
) -> Callable[..., pd.DataFrame]:
    """Factory returning a timestamp-indexed master-like frame.

    Adds the feature-engineering operative columns the profile rules read,
    defaulting to "machine fully running, no alarms". Tests mutate only the
    columns relevant to the behaviour under test.
    """

    def _make(
        n_rows: int = 40,
        n_subsystems: float = 3.0,
        production: float = 10.0,
    ) -> pd.DataFrame:
        df = tiny_frame_factory(n_rows=n_rows).set_index("timestamp")
        df["n_subsystems_running"] = float(n_subsystems)
        df["time_since_machine_off"] = 0.0
        df["time_since_any_alarm"] = 9999.0
        df["any_alarm_while_running"] = 0
        df["granulator_production_rate"] = float(production)
        return df

    return _make


@pytest.fixture
def labeled_frame(
    behaviour_frame: Callable[..., pd.DataFrame],
    groups: ColumnGroups,
) -> Callable[..., tuple[pd.DataFrame, pd.Series, pd.Series]]:
    """Factory returning ``(df, labels, train_mask)`` for Iteration B tests.

    Process sensors are filled with seeded Gaussian noise so they pass the
    near-constant eligibility gates (the ``tiny_frame_factory`` defaults are
    constants). Profiles interleave row-wise so every profile has both
    training and validation rows. Tests mutate only what they assert on.
    """

    def _make(
        n_rows: int = 40,
        n_profiles: int = 1,
        train_fraction: float = 0.5,
        seed: int = 7,
    ) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
        df = behaviour_frame(n_rows=n_rows)
        rng = np.random.default_rng(seed)
        for col in groups.process:
            if col in df.columns:
                df[col] = rng.normal(50.0, 5.0, n_rows)
        names = [f"profile_{chr(97 + i)}" for i in range(n_profiles)]
        labels = pd.Series(
            [names[i % n_profiles] for i in range(n_rows)], index=df.index
        )
        k = int(round(n_rows * train_fraction))
        train_mask = pd.Series([True] * k + [False] * (n_rows - k), index=df.index)
        return df, labels, train_mask

    return _make
