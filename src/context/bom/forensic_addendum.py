"""Stage H — BOM-aware forensic addendum (read-only join).

Joins the master-aligned BOM context timeline with the *persisted* anomaly
scores of a completed Anomaly Intelligence run and the existing forensic
findings. Strictly read-only with respect to upstream artifacts: no fit
procedure is invoked, no thresholds recomputed, nothing upstream modified.
All statements are temporal associations — the BOM layer alone cannot
establish causation.

Outputs land in ``data/intelligence/forensics/bom_addenda/<run_id>/``; the
addendum manifest is written last within that directory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from src.context.bom import io
from src.context.bom.policy import BomContextPolicy
from src.context.bom.validation import BomContextBlockerError

FIGURES = [
    "anomaly_rate_by_product.png",
    "anomaly_rate_by_recipe.png",
    "anomaly_rate_by_order_over_time.png",
    "bom_context_coverage.png",
    "candidate_dates_context_timeline.png",
]

_RATE_TABLES = [
    "anomaly_rates_by_product",
    "anomaly_rates_by_recipe",
    "anomaly_rates_by_bom_signature",
    "anomaly_rates_by_order",
    "anomaly_rates_by_context_status",
    "candidate_dates_bom_context",
    "recipe_transition_anomaly_summary",
]


@dataclass
class AddendumArtifacts:
    """Everything Stage H produces (figures rendered at write time)."""

    tables: dict[str, pd.DataFrame]
    executive_summary: str
    limitations: str
    manifest: dict[str, Any]
    hourly_rates: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)
    daily_status: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)


def _load_scores(anomaly_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    scores = pd.read_parquet(anomaly_dir / "scores" / "anomaly_scores.parquet")
    manifest = json.loads(
        (anomaly_dir / "anomaly_fit_manifest.json").read_text(encoding="utf-8")
    )
    return scores, manifest


def _merge_timeline_scores(
    timeline: pd.DataFrame, scores: pd.DataFrame, train_end: pd.Timestamp
) -> pd.DataFrame:
    """Row-aligned join; raises a blocker on any timestamp mismatch."""
    if (
        len(scores) != len(timeline)
        or not (
            scores["timestamp"].to_numpy() == timeline["timestamp"].to_numpy()
        ).all()
    ):
        raise BomContextBlockerError(
            "Anomaly scores do not align row-for-row with the BOM context "
            f"timeline ({len(scores)} vs {len(timeline)} rows) — wrong "
            "anomaly run for this master dataset?"
        )
    merged = timeline.merge(
        scores[["timestamp", "profile", "severity", "combined_score"]],
        on="timestamp",
        how="inner",
    )
    merged["is_train"] = merged["timestamp"] <= train_end
    merged["is_anomaly"] = merged["severity"] == "anomaly"
    merged["is_warning"] = merged["severity"] == "warning"
    return merged


def _rates_by(merged: pd.DataFrame, key: str | list[str]) -> pd.DataFrame:
    """Train/validation anomaly rates per group, fully vectorized."""
    keys = [key] if isinstance(key, str) else key
    work = merged.assign(
        _train=merged["is_train"].astype(int),
        _val=(~merged["is_train"]).astype(int),
        _anom_train=(merged["is_anomaly"] & merged["is_train"]).astype(int),
        _anom_val=(merged["is_anomaly"] & ~merged["is_train"]).astype(int),
        _warn_val=(merged["is_warning"] & ~merged["is_train"]).astype(int),
        _comb_val=merged["combined_score"].where(~merged["is_train"]),
    )
    grouped = work.groupby(keys, dropna=False)
    out = pd.DataFrame(
        {
            "n_rows": grouped.size(),
            "n_train_rows": grouped["_train"].sum(),
            "n_validation_rows": grouped["_val"].sum(),
        }
    )
    sums = grouped[["_anom_train", "_anom_val", "_warn_val"]].sum()
    out["anomaly_rate_train"] = sums["_anom_train"] / out["n_train_rows"]
    out["anomaly_rate_validation"] = sums["_anom_val"] / out["n_validation_rows"]
    out["warning_rate_validation"] = sums["_warn_val"] / out["n_validation_rows"]
    out["mean_combined_validation"] = grouped["_comb_val"].mean()
    return out.reset_index().sort_values(
        "anomaly_rate_validation", ascending=False, na_position="last"
    )


def _candidate_rates(events: pd.DataFrame, merged: pd.DataFrame) -> pd.DataFrame:
    """Stage G events enriched with in-window anomaly rates."""
    rows: list[dict[str, Any]] = []
    for ev in events.itertuples(index=False):
        window = merged[
            (merged["timestamp"] >= ev.window_start)
            & (merged["timestamp"] < ev.window_end)
        ]
        rows.append(
            {
                **ev._asdict(),
                "window_row_count": len(window),
                "window_anomaly_rate": (
                    float(window["is_anomaly"].mean()) if len(window) else None
                ),
                "window_warning_rate": (
                    float(window["is_warning"].mean()) if len(window) else None
                ),
            }
        )
    return pd.DataFrame(rows)


def _transition_rates(
    transitions: pd.DataFrame, merged: pd.DataFrame, window_hours: int
) -> pd.DataFrame:
    """Anomaly rate before vs after each order transition."""
    window = pd.Timedelta(hours=window_hours)
    rows: list[dict[str, Any]] = []
    for tr in transitions.itertuples(index=False):
        t = tr.transition_timestamp
        before = merged[(merged["timestamp"] >= t - window) & (merged["timestamp"] < t)]
        after = merged[(merged["timestamp"] >= t) & (merged["timestamp"] < t + window)]
        rows.append(
            {
                **tr._asdict(),
                "rows_before": len(before),
                "rows_after": len(after),
                "anomaly_rate_before": (
                    float(before["is_anomaly"].mean()) if len(before) else None
                ),
                "anomaly_rate_after": (
                    float(after["is_anomaly"].mean()) if len(after) else None
                ),
            }
        )
    return pd.DataFrame(rows)


def build_addendum(
    timeline: pd.DataFrame,
    orders: pd.DataFrame,
    transitions: pd.DataFrame,
    events: pd.DataFrame,
    policy: BomContextPolicy,
    run_id: str,
    anomaly_dir: Path,
    forensic_dir: Path,
) -> AddendumArtifacts:
    """Assemble every Stage H table, narrative and the manifest (no writes)."""
    scores, anomaly_manifest = _load_scores(anomaly_dir)
    train_end = pd.Timestamp(anomaly_manifest["fit_window"]["train_end"])
    merged = _merge_timeline_scores(timeline, scores, train_end)
    matched = merged[merged["bom_context_status"] == "matched_single_order"]

    by_order = _rates_by(matched, "order_id").merge(
        orders[["order_id", "start_timestamp", "product_code", "recipe_context_key"]],
        on="order_id",
        how="left",
    )
    tables = {
        "anomaly_rates_by_product": _rates_by(matched, "product_code"),
        "anomaly_rates_by_recipe": _rates_by(
            matched, ["product_code", "recipe_version", "recipe_context_key"]
        ),
        "anomaly_rates_by_bom_signature": _rates_by(matched, "bom_signature"),
        "anomaly_rates_by_order": by_order,
        "anomaly_rates_by_context_status": _rates_by(merged, "bom_context_status"),
        "candidate_dates_bom_context": _candidate_rates(events, merged),
        "recipe_transition_anomaly_summary": _transition_rates(
            transitions, merged, policy.forensic_windows.window_hours
        ),
    }

    hourly = (
        merged.assign(hour=merged["timestamp"].dt.floor("h"))
        .groupby("hour", as_index=False)
        .agg(anomaly_rate=("is_anomaly", "mean"), row_count=("timestamp", "size"))
    )
    daily_status = (
        timeline.assign(day=timeline["timestamp"].dt.floor("D"))
        .groupby(["day", "bom_context_status"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    summary = _executive_summary(tables, merged, orders, transitions, train_end)
    manifest = _addendum_manifest(
        policy, run_id, anomaly_dir, forensic_dir, anomaly_manifest, timeline
    )
    return AddendumArtifacts(
        tables=tables,
        executive_summary=summary,
        limitations=_LIMITATIONS,
        manifest=manifest,
        hourly_rates=hourly,
        daily_status=daily_status,
    )


def _addendum_manifest(
    policy: BomContextPolicy,
    run_id: str,
    anomaly_dir: Path,
    forensic_dir: Path,
    anomaly_manifest: dict[str, Any],
    timeline: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "component": "bom_forensic_addendum",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "read_only": True,
        "statements": [
            "No fit procedure was invoked.",
            "No upstream artifacts were modified or overwritten.",
            "No thresholds, profiles, or reference windows were changed.",
            "All findings are temporal associations, not causal claims.",
        ],
        "upstream": {
            "anomaly_run_id": anomaly_dir.name,
            "anomaly_run_dir": str(anomaly_dir),
            "anomaly_dataset_sha256": anomaly_manifest["dataset_fingerprint"]["sha256"],
            "anomaly_train_end": anomaly_manifest["fit_window"]["train_end"],
            "forensic_run_id": forensic_dir.name,
            "forensic_run_dir": str(forensic_dir),
        },
        "timeline_row_count": int(len(timeline)),
        "config_snapshot": policy.forensic_addendum.model_dump(),
        "generated_files": [],  # filled by write_addendum
        "completion_status": "pending",
    }


# --------------------------------------------------------------------------
# Narratives
# --------------------------------------------------------------------------

_LIMITATIONS = """# Limitations — BOM-aware forensic addendum

* The BOM source is **declarative**: it records planned production orders
  and recipe compositions, not measured material flows. Actual dosing may
  differ from the recorded percentages.
* Order windows come from the same declarative source; clock skew between
  the ERP and the sensor historian cannot be ruled out from this data.
* Overlapping order windows are preserved **unresolved by design** — rows in
  overlap windows are excluded from per-product/per-recipe attribution and
  reported under their own context status instead.
* Percentage totals are reported as found; totals above 100% may reflect
  valid industrial formulation rules and require domain interpretation.
* The Anomaly Intelligence models were fitted **blind to BOM context**; an
  anomaly-rate difference between recipes can reflect either recipe-linked
  process change or coincidental timing. The BOM layer alone cannot
  distinguish these.
* All statements in this addendum are temporal associations. No causal
  claim is made or implied.
"""


def _fmt_rate(value: Any) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{float(value):.1%}"


def _rate_lines(table: pd.DataFrame, key: str, top: int = 10) -> list[str]:
    lines = [
        f"| {key} | validation rows | anomaly rate (validation) |",
        "|---|---|---|",
    ]
    for row in table.head(top).itertuples(index=False):
        rd = row._asdict()
        lines.append(
            f"| {rd[key]} | {rd['n_validation_rows']} | "
            f"{_fmt_rate(rd['anomaly_rate_validation'])} |"
        )
    return lines


def _transitions_near(
    transitions: pd.DataFrame, day: str, days: int = 2
) -> pd.DataFrame:
    center = pd.Timestamp(day)
    lo, hi = center - pd.Timedelta(days=days), center + pd.Timedelta(days=days + 1)
    return transitions[
        (transitions["transition_timestamp"] >= lo)
        & (transitions["transition_timestamp"] < hi)
    ]


def _describe_transition_rows(near: pd.DataFrame) -> str:
    if near.empty:
        return "the BOM data does not show any order transition in this window"
    items = [
        f"{r.transition_timestamp} ({r.transition_type}: "
        f"{r.previous_order_id} -> {r.next_order_id})"
        for r in near.itertuples(index=False)
    ]
    return "; ".join(items)


def _executive_summary(
    tables: dict[str, pd.DataFrame],
    merged: pd.DataFrame,
    orders: pd.DataFrame,
    transitions: pd.DataFrame,
    train_end: pd.Timestamp,
) -> str:
    """Answer the ten addendum questions with cautious, non-causal wording."""
    by_product = tables["anomaly_rates_by_product"]
    by_recipe = tables["anomaly_rates_by_recipe"]
    by_sig = tables["anomaly_rates_by_bom_signature"]
    by_status = tables["anomaly_rates_by_context_status"]

    recipe_changes = transitions[
        transitions["transition_type"].isin(
            ["same_product_recipe_change", "composition_change", "product_change"]
        )
    ]
    sep16 = _transitions_near(transitions, "2024-09-16")
    sep18 = _transitions_near(transitions, "2024-09-18")
    sep16_recipe = _transitions_near(recipe_changes, "2024-09-16")

    val = merged[~merged["is_train"]]
    shift = pd.Timestamp("2024-09-16")
    products_before = set(
        val.loc[val["timestamp"] < shift, "product_code"].dropna().astype(str)
    )
    products_after = set(
        val.loc[val["timestamp"] >= shift, "product_code"].dropna().astype(str)
    )

    sep_orders = orders[
        orders["start_timestamp"].dt.month.eq(9) & orders["is_valid_window"]
    ]
    oct_orders = orders[
        orders["start_timestamp"].dt.month.eq(10) & orders["is_valid_window"]
    ]
    oct_only_keys = set(oct_orders["recipe_context_key"]) - set(
        sep_orders["recipe_context_key"]
    )

    status_lookup = by_status.set_index("bom_context_status")["anomaly_rate_validation"]

    lines = [
        "# Executive summary — BOM-aware forensic addendum",
        "",
        "All statements below are **temporal associations**. The BOM layer "
        "alone cannot distinguish recipe-linked process change from "
        "coincidental timing; no causal claim is made.",
        "",
        f"Train window ends {train_end}; validation rows: {int((~merged['is_train']).sum())}.",
        "",
        "## 1. Does the sustained September shift align with a recipe-version change?",
        f"Order transitions within ±2 days of 2024-09-16 involving a recipe, "
        f"composition or product change: "
        f"{_describe_transition_rows(sep16_recipe)}.",
        "",
        "## 2. Does the shift align with a product change?",
        f"Products active in validation before 2024-09-16: "
        f"{sorted(products_before) or 'none'}; from 2024-09-16 on: "
        f"{sorted(products_after) or 'none'}.",
        "",
        "## 3. Is the shift global across products?",
        "Validation anomaly rates per product (matched single-order rows only):",
        "",
        *_rate_lines(by_product, "product_code"),
        "",
        "## 4. Are anomaly rates materially different across products?",
        f"Validation anomaly rates span "
        f"{_fmt_rate(by_product['anomaly_rate_validation'].min())} to "
        f"{_fmt_rate(by_product['anomaly_rate_validation'].max())} across "
        f"{len(by_product)} products.",
        "",
        "## 5. Are anomaly rates materially different across BOM signatures?",
        f"Validation anomaly rates span "
        f"{_fmt_rate(by_sig['anomaly_rate_validation'].min())} to "
        f"{_fmt_rate(by_sig['anomaly_rate_validation'].max())} across "
        f"{len(by_sig)} signatures. Top signatures:",
        "",
        *_rate_lines(by_sig, "bom_signature", top=5),
        "",
        "## 6. Are the September 9 / 12 precursor events linked to specific orders or recipes?",
        f"Around 2024-09-09: {_describe_transition_rows(_transitions_near(transitions, '2024-09-09'))}. "
        f"Around 2024-09-12: {_describe_transition_rows(_transitions_near(transitions, '2024-09-12'))}. "
        "See candidate_dates_bom_context.parquet for the active orders and "
        "in-window anomaly rates.",
        "",
        "## 7. Does the September 16 sustained change coincide with a BOM transition?",
        f"{_describe_transition_rows(sep16)}.",
        "",
        "## 8. Does the September 18 inlet_hopper_points flatline coincide with a BOM event?",
        f"{_describe_transition_rows(sep18)}. The flatline itself is a "
        "sensor-channel observation; the BOM data records order activity, "
        "not sensor maintenance.",
        "",
        "## 9. Are overlap windows disproportionately anomalous?",
        f"Validation anomaly rate in transition_overlap rows: "
        f"{_fmt_rate(status_lookup.get('transition_overlap'))}; in "
        f"matched_single_order rows: "
        f"{_fmt_rate(status_lookup.get('matched_single_order'))}.",
        "",
        "## 10. Are October recipe versions behaviorally distinct from September versions?",
        f"Recipe context keys first seen in October (absent in September): "
        f"{sorted(oct_only_keys) or 'none'}. Validation anomaly rates per "
        "recipe (top 10):",
        "",
        *_rate_lines(by_recipe, "recipe_context_key"),
        "",
        "## Caveats",
        "Rates by product/recipe/signature use matched single-order rows "
        "only; overlap and uncovered rows are reported separately under "
        "their context status. See limitations.md.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Figures + writing
# --------------------------------------------------------------------------


def _save(fig: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _bar_rate_figure(table: pd.DataFrame, key: str, title: str) -> Any:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    shown = table.head(15)
    ax.bar(
        shown[key].astype(str),
        shown["anomaly_rate_validation"].fillna(0.0),
        color="#b3443c",
    )
    ax.set_title(title)
    ax.set_ylabel("validation anomaly rate")
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    return fig


def _order_time_figure(by_order: pd.DataFrame) -> Any:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for product, sub in by_order.groupby("product_code", dropna=False):
        ax.scatter(
            sub["start_timestamp"],
            sub["anomaly_rate_validation"],
            label=str(product),
            s=18,
        )
    ax.set_title("Per-order validation anomaly rate over order start time")
    ax.set_ylabel("validation anomaly rate")
    ax.legend(title="product", fontsize=7)
    return fig


def _coverage_figure(daily_status: pd.DataFrame) -> Any:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    statuses = [c for c in daily_status.columns if c != "day"]
    ax.stackplot(
        daily_status["day"],
        [daily_status[s] for s in statuses],
        labels=statuses,
    )
    ax.set_title("BOM context status per day (master rows)")
    ax.set_ylabel("rows per day")
    ax.legend(fontsize=7, loc="upper left")
    return fig


def _candidate_figure(hourly: pd.DataFrame, candidates: pd.DataFrame) -> Any:
    n = max(len(candidates), 1)
    fig, axes = plt.subplots(n, 1, figsize=(10, 2.4 * n), sharey=True, squeeze=False)
    for ax, ev in zip(axes.ravel(), candidates.itertuples(index=False), strict=False):
        window = hourly[
            (hourly["hour"] >= ev.window_start) & (hourly["hour"] < ev.window_end)
        ]
        ax.plot(window["hour"], window["anomaly_rate"], color="#b3443c")
        ax.axvline(ev.candidate_timestamp, color="black", linestyle="--", lw=0.8)
        ax.set_title(
            f"{ev.candidate_timestamp.date()} — {ev.context_summary}", fontsize=8
        )
        ax.set_ylabel("anomaly rate")
    fig.tight_layout()
    return fig


def write_addendum(art: AddendumArtifacts, out: Path) -> list[str]:
    """Persist tables, narratives and figures; addendum manifest written last."""
    written: list[str] = []
    for name in _RATE_TABLES:
        io.write_table(art.tables[name], out / f"{name}.parquet")
        written.append(f"{name}.parquet")

    (out / "executive_summary.md").write_text(art.executive_summary, encoding="utf-8")
    (out / "limitations.md").write_text(art.limitations, encoding="utf-8")
    written += ["executive_summary.md", "limitations.md"]

    fig_dir = out / "figures"
    by_order = art.tables["anomaly_rates_by_order"]
    _save(
        _bar_rate_figure(
            art.tables["anomaly_rates_by_product"],
            "product_code",
            "Validation anomaly rate by product",
        ),
        fig_dir / FIGURES[0],
    )
    _save(
        _bar_rate_figure(
            art.tables["anomaly_rates_by_recipe"],
            "recipe_context_key",
            "Validation anomaly rate by recipe (top 15)",
        ),
        fig_dir / FIGURES[1],
    )
    _save(_order_time_figure(by_order), fig_dir / FIGURES[2])
    _save(_coverage_figure(art.daily_status), fig_dir / FIGURES[3])
    _save(
        _candidate_figure(art.hourly_rates, art.tables["candidate_dates_bom_context"]),
        fig_dir / FIGURES[4],
    )
    written += [f"figures/{name}" for name in FIGURES]

    manifest = dict(art.manifest)
    manifest["generated_files"] = written
    manifest["completion_status"] = "complete"
    io.write_manifest(manifest, out / io.ADDENDUM_MANIFEST_NAME)
    written.append(io.ADDENDUM_MANIFEST_NAME)
    return written
