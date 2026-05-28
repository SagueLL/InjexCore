"""Stage 2 — temporal index behaviour."""
from __future__ import annotations

import pandas as pd

from src.data.time_series import temporal_index


def test_set_index_promotes_timestamp(tiny_frame_factory, ts_policy, groups):
    df = tiny_frame_factory(n_rows=10)
    findings = temporal_index.detect(df, ts_policy, groups)
    out = temporal_index.apply(df, findings, ts_policy, groups)
    assert isinstance(out.index, pd.DatetimeIndex)
    assert "timestamp" not in out.columns
    assert out.index.is_monotonic_increasing


def test_duplicate_index_is_dropped(tiny_frame_factory, ts_policy, groups):
    df = tiny_frame_factory(n_rows=10)
    df.loc[5, "timestamp"] = df.loc[4, "timestamp"]
    findings = temporal_index.detect(df, ts_policy, groups)
    assert any(f.finding_type == "duplicate_index" for f in findings)
    out = temporal_index.apply(df, findings, ts_policy, groups)
    assert len(out) == 9


def test_already_indexed_is_noop(tiny_frame_factory, ts_policy, groups):
    df = tiny_frame_factory(n_rows=5).set_index("timestamp")
    findings = temporal_index.detect(df, ts_policy, groups)
    assert any(f.finding_type == "already_indexed" for f in findings)
    out = temporal_index.apply(df, findings, ts_policy, groups)
    assert out.equals(df)
