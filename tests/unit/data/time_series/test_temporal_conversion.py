"""Stage 1 — temporal conversion behaviour."""
from __future__ import annotations

import pandas as pd

from src.data.time_series import temporal_conversion


def test_already_datetime_is_noop(tiny_frame_factory, ts_policy, groups):
    df = tiny_frame_factory(n_rows=10)
    findings = temporal_conversion.detect(df, ts_policy, groups)
    assert any(f.finding_type == "already_datetime" for f in findings)
    out = temporal_conversion.apply(df, findings, ts_policy, groups)
    assert out["timestamp"].dtype == df["timestamp"].dtype


def test_string_timestamps_get_coerced(tiny_frame_factory, ts_policy, groups):
    df = tiny_frame_factory(n_rows=10)
    df["timestamp"] = df["timestamp"].astype(str)
    findings = temporal_conversion.detect(df, ts_policy, groups)
    assert any(f.finding_type == "coerce_datetime" for f in findings)
    out = temporal_conversion.apply(df, findings, ts_policy, groups)
    assert pd.api.types.is_datetime64_any_dtype(out["timestamp"])
    assert out["timestamp"].notna().all()
