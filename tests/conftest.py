"""Shared pytest fixtures for the InjexCore data-layer unit tests.

The package is installed in editable mode (``pip install -e .``), so
``import src...`` resolves without any ``sys.path`` manipulation here.

Fixtures intentionally use the *real* policy YAML and the *real* variable
classification CSV: they are small, version-controlled artefacts whose
contents are part of the contract the modules are tested against.

Synthetic DataFrames are built by the ``tiny_frame_factory`` fixture so no
test reads the large raw dataset from disk.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from src.config import PROJECT_ROOT
from src.data._common.column_groups import ColumnGroups, load_groups
from src.data.cleaning.policy import CleaningPolicy, load_policy
from src.data.datasets.policy import (
    SpecializedDatasetsPolicy,
)
from src.data.datasets.policy import (
    load_policy as load_datasets_policy,
)
from src.data.feature_engineering.policy import (
    FeatureEngineeringPolicy,
)
from src.data.feature_engineering.policy import (
    load_policy as load_fe_policy,
)
from src.data.time_series.policy import (
    TimeSeriesPolicy,
)
from src.data.time_series.policy import (
    load_policy as load_ts_policy,
)


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def policy() -> CleaningPolicy:
    """Real cleaning policy loaded from configs/cleaning.yaml."""
    return load_policy(PROJECT_ROOT / "configs" / "cleaning.yaml")


@pytest.fixture(scope="session")
def groups() -> ColumnGroups:
    """Real column groups loaded from variable_classification.csv."""
    return load_groups(
        PROJECT_ROOT / "data" / "features" / "variable_classification.csv"
    )


@pytest.fixture(scope="session")
def ts_policy() -> TimeSeriesPolicy:
    """Real time-series engineering policy loaded from configs/time_series.yaml."""
    return load_ts_policy(PROJECT_ROOT / "configs" / "time_series.yaml")


@pytest.fixture(scope="session")
def fe_policy() -> FeatureEngineeringPolicy:
    """Real feature engineering policy loaded from configs/feature_engineering.yaml."""
    return load_fe_policy(PROJECT_ROOT / "configs" / "feature_engineering.yaml")


@pytest.fixture(scope="session")
def datasets_policy() -> SpecializedDatasetsPolicy:
    """Real specialized-datasets policy loaded from configs/specialized_datasets.yaml."""
    return load_datasets_policy(PROJECT_ROOT / "configs" / "specialized_datasets.yaml")


_BASE_TS = pd.Timestamp("2025-01-01 00:00:00")


def _default_for(col: str, groups: ColumnGroups) -> float | int | str:
    """Return a sane, in-range default value for a known column."""
    if col == "timestamp":
        return _BASE_TS  # type: ignore[return-value]
    if col in groups.metadata:
        return "x"
    # State flags: 1 = running, 0 = no alarm
    if col in groups.running_flags:
        return 1
    if col in groups.alarm_flags:
        return 0
    # Temperatures: well inside [-20, 350]
    if col in groups.temperature_cols:
        return 50.0
    # Pressures: inside common bound [0, 100]
    if col in groups.pressure_cols:
        return 5.0
    # Power / percent registers: inside [0, 110]
    if col in groups.power_cols:
        return 50.0
    # Anything else numeric: a small positive value.
    return 1.0


@pytest.fixture
def tiny_frame_factory(
    groups: ColumnGroups,
) -> Callable[..., pd.DataFrame]:
    """Factory returning small DataFrames with the project's column schema.

    Parameters of the returned callable:
        n_rows: number of rows (default 20).
        period_s: seconds between consecutive timestamps (default 60).
        start: starting timestamp (default 2025-01-01 00:00:00).

    Each cell is populated with a sane default for its column type so that
    a frame produced with no overrides triggers zero findings across all
    six cleaning modules. Individual tests should mutate only the cells
    relevant to the behaviour under test.
    """

    def _make(
        n_rows: int = 20,
        period_s: float = 60.0,
        start: pd.Timestamp = _BASE_TS,
    ) -> pd.DataFrame:
        timestamps = pd.date_range(
            start=start,
            periods=n_rows,
            freq=pd.Timedelta(seconds=period_s),
        )
        data: dict[str, list[object]] = {}
        for col in groups.all_columns:
            if col == "timestamp":
                data[col] = list(timestamps)
            else:
                data[col] = [_default_for(col, groups)] * n_rows
        df = pd.DataFrame(data)
        # Ensure timestamp dtype is datetime64 even when NaTs are injected later.
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        # Cast numeric defaults to float so NaN injection works.
        for col in df.columns:
            if col == "timestamp" or col in groups.metadata:
                continue
            df[col] = df[col].astype(float)
        return df

    return _make


@pytest.fixture
def empty_frame(groups: ColumnGroups) -> pd.DataFrame:
    """Empty DataFrame with the full project schema (zero rows)."""
    data: dict[str, list[object]] = {c: [] for c in groups.all_columns}
    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for col in df.columns:
        if col == "timestamp" or col in groups.metadata:
            continue
        df[col] = df[col].astype(float)
    return df


# Silence noisy numpy "Mean of empty slice" runtime warnings in tests
# that exercise empty-frame boundaries.
@pytest.fixture(autouse=True)
def _np_errstate() -> None:
    np.seterr(all="ignore")
