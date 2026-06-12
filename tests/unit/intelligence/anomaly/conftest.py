"""Anomaly-detector fixtures: baseline tables built from labeled frames."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import pytest


@pytest.fixture
def baselines_factory() -> Callable[..., pd.DataFrame]:
    """Build a behaviour-style baseline table from (df, labels, train_mask).

    Mirrors the schema of ``data/intelligence/behaviour/baselines/
    baselines.parquet``: long-form per-(profile, sensor) statistics computed
    on the training window only.
    """

    def _make(
        df: pd.DataFrame,
        labels: pd.Series,
        train_mask: pd.Series,
        sensors: list[str],
    ) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for profile in sorted(str(p) for p in labels.unique()):
            sub = df.loc[(train_mask & (labels == profile)).to_numpy(), sensors]
            for sensor in sensors:
                s = sub[sensor].astype(float)
                q25, q75 = s.quantile(0.25), s.quantile(0.75)
                rows.append(
                    {
                        "profile": profile,
                        "sensor": sensor,
                        "count": int(s.notna().sum()),
                        "mean": float(s.mean()),
                        "median": float(s.median()),
                        "std": float(s.std()),
                        "min": float(s.min()),
                        "max": float(s.max()),
                        "iqr": float(q75 - q25),
                        "p05": float(s.quantile(0.05)),
                        "p95": float(s.quantile(0.95)),
                    }
                )
        return pd.DataFrame(rows)

    return _make
