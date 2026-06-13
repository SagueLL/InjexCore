"""Context drift — composition shifts of the operational context mix.

Distinguishes real process drift from *observed* drift caused by a different
context composition (more stopped rows, more steam-on rows, more
sensor-faulty rows, different products). Works entirely on the persisted
operational context timeline; references are the train-window category
distributions.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.intelligence.drift import univariate as uni
from src.intelligence.drift import windows as win
from src.intelligence.drift.policy import GLOBAL_SCOPE_KEY, DriftPolicy

SHIFT_TABLE_COLUMNS = [
    "window_start",
    "column",
    "categorical_psi",
    "total_variation",
    "n_rows",
    "new_categories",
    "disappeared_categories",
    "train_top_categories",
    "window_top_categories",
]

#: Which mandated shift table each context column feeds.
SHIFT_TABLE_FOR_COLUMN = {
    "profile": "profile_composition_shift",
    "steam_context": "steam_context_shift",
    "sensor_health_context": "sensor_health_context_shift",
    "product_code": "bom_context_shift",
    "recipe_context_key": "bom_context_shift",
    "bom_context_status": "bom_context_shift",
}


def _category_series(timeline: pd.DataFrame, column: str) -> pd.Series:
    return timeline[column].fillna("__missing__").astype(str)


def composition_references(
    timeline: pd.DataFrame, train_arr: np.ndarray, policy: DriftPolicy
) -> dict[str, dict[str, float]]:
    """Train-window category probabilities per configured context column."""
    refs: dict[str, dict[str, float]] = {}
    for column in policy.context.columns:
        if column not in timeline.columns:
            continue
        counts = _category_series(timeline, column)[train_arr].value_counts()
        total = int(counts.sum())
        if total:
            refs[column] = {str(k): float(v) / total for k, v in counts.items()}
    return refs


def _top_categories(counts: dict[str, int], k: int = 3) -> str:
    total = sum(counts.values()) or 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:k]
    return json.dumps(
        {c: round(n / total, 4) for c, n in top}, sort_keys=True, separators=(",", ":")
    )


def score_windows(
    timeline: pd.DataFrame,
    refs: dict[str, dict[str, float]],
    policy: DriftPolicy,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-window composition metrics for every configured context column.

    Returns ``(metric_rows, shift_table)`` — long-form rows feeding the
    common scoring, and the wide per-(window, column) shift table that the
    mandated context outputs are split from.
    """
    window_labels = win.window_starts(pd.DatetimeIndex(timeline.index), policy.windows)
    metric_rows: list[dict[str, object]] = []
    table_rows: list[dict[str, object]] = []
    for column, ref_probs in refs.items():
        ref_top = {
            c: int(round(p * 1_000_000)) for c, p in ref_probs.items()
        }  # proportional weights for the top-categories rendering
        grouped = _category_series(timeline, column).groupby(window_labels.to_numpy())
        for window, values in grouped:
            counts = {str(k): int(v) for k, v in values.value_counts().items()}
            n_rows = int(sum(counts.values()))
            if n_rows < policy.windows.min_rows_per_window:
                continue
            psi_value = win.categorical_psi(
                ref_probs, counts, policy.context.psi_smoothing
            )
            tv_value = win.total_variation(ref_probs, counts)
            new = sorted(set(counts) - set(ref_probs))
            gone = sorted(set(ref_probs) - set(counts))
            for metric, value in (
                ("categorical_psi", psi_value),
                ("total_variation", tv_value),
            ):
                metric_rows.append(
                    {
                        "window_start": window,
                        "scope": "context",
                        "view": "raw",
                        "entity": column,
                        "profile": GLOBAL_SCOPE_KEY,
                        "metric": metric,
                        "value": value,
                        "n_rows": n_rows,
                        "n_valid": n_rows,
                    }
                )
            table_rows.append(
                {
                    "window_start": window,
                    "column": column,
                    "categorical_psi": psi_value,
                    "total_variation": tv_value,
                    "n_rows": n_rows,
                    "new_categories": "|".join(new),
                    "disappeared_categories": "|".join(gone),
                    "train_top_categories": _top_categories(ref_top),
                    "window_top_categories": _top_categories(counts),
                }
            )
    return (
        pd.DataFrame(metric_rows, columns=uni.SCORE_ROW_COLUMNS),
        pd.DataFrame(table_rows, columns=SHIFT_TABLE_COLUMNS),
    )


def split_shift_tables(shift_table: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split the wide shift table into the four mandated context outputs."""
    out: dict[str, pd.DataFrame] = {
        name: pd.DataFrame(columns=SHIFT_TABLE_COLUMNS)
        for name in (
            "profile_composition_shift",
            "steam_context_shift",
            "sensor_health_context_shift",
            "bom_context_shift",
        )
    }
    if not len(shift_table):
        return out
    for column, group in shift_table.groupby("column"):
        name = SHIFT_TABLE_FOR_COLUMN.get(str(column))
        if name is None:
            continue
        out[name] = (
            pd.concat([out[name], group], ignore_index=True)
            if len(out[name])
            else group.reset_index(drop=True)
        )
    return out
