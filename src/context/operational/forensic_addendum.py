"""Context-aware forensic addendum (read-only join).

Joins the operational context overlay with the *persisted* anomaly scores of
a completed Anomaly Intelligence run and the existing forensic findings.
Strictly read-only with respect to upstream artifacts: no fit procedure is
invoked, no thresholds recomputed, nothing upstream modified. All statements
are temporal associations — context alone cannot establish causation.

Outputs land in ``data/intelligence/forensics/context_addenda/<run_id>/``;
the addendum manifest is written last within that directory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from src.context.operational import io
from src.context.operational.policy import OperationalContextPolicy
from src.context.operational.reporting import daily_share, transitions_near
from src.context.operational.validation import (
    OperationalContextBlockerError,
    require_timestamp_alignment,
)

FIGURES = [
    "anomaly_rate_by_steam_context.png",
    "anomaly_rate_by_sensor_health_context.png",
    "steam_context_timeline.png",
    "sensor_health_timeline.png",
    "candidate_dates_context_timeline.png",
]

_TABLES = [
    "anomaly_rates_by_steam_context",
    "anomaly_rates_by_sensor_health_context",
    "anomaly_rates_by_operational_context",
    "candidate_dates_context_summary",
]


@dataclass
class AddendumArtifacts:
    """Everything the addendum produces (figures rendered at write time)."""

    tables: dict[str, pd.DataFrame]
    executive_summary: str
    limitations: str
    manifest: dict[str, Any]
    steam_daily: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)
    health_daily: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)
    hourly_rates: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)


def _merge_scores(overlay: pd.DataFrame, anomaly_dir: Path) -> pd.DataFrame:
    scores = pd.read_parquet(anomaly_dir / "scores" / "anomaly_scores.parquet")
    try:
        require_timestamp_alignment(
            "anomaly_scores", scores["timestamp"], overlay["timestamp"]
        )
    except OperationalContextBlockerError as exc:
        raise OperationalContextBlockerError(
            f"Anomaly run {anomaly_dir.name} does not align with the overlay: {exc}"
        ) from exc
    merged = overlay.merge(
        scores[["timestamp", "severity", "combined_score"]], on="timestamp"
    )
    merged["is_anomaly"] = merged["severity"] == "anomaly"
    merged["is_warning"] = merged["severity"] == "warning"
    return merged


def _rates_by(merged: pd.DataFrame, key: str) -> pd.DataFrame:
    """Train/validation anomaly rates per group, fully vectorized."""
    work = merged.assign(
        _train=merged["is_train"].astype(int),
        _val=(~merged["is_train"]).astype(int),
        _anom_train=(merged["is_anomaly"] & merged["is_train"]).astype(int),
        _anom_val=(merged["is_anomaly"] & ~merged["is_train"]).astype(int),
        _warn_val=(merged["is_warning"] & ~merged["is_train"]).astype(int),
    )
    grouped = work.groupby(key, dropna=False)
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
    return out.reset_index().sort_values(
        "anomaly_rate_validation", ascending=False, na_position="last"
    )


def _candidate_summary(
    merged: pd.DataFrame,
    transitions: pd.DataFrame,
    policy: OperationalContextPolicy,
) -> pd.DataFrame:
    window = pd.Timedelta(hours=policy.forensic_addendum.window_hours)
    rows: list[dict[str, Any]] = []
    for date in policy.forensic_addendum.candidate_dates:
        center = pd.Timestamp(date)
        lo, hi = center - window, center + window
        sub = merged[(merged["timestamp"] >= lo) & (merged["timestamp"] < hi)]
        near = transitions_near(
            transitions, date, policy.forensic_addendum.window_hours
        )
        types = (
            "|".join(
                sorted(set(t for ts in near["transition_types"] for t in ts.split("|")))
            )
            if len(near)
            else ""
        )
        rows.append(
            {
                "candidate_timestamp": center,
                "window_start": lo,
                "window_end": hi,
                "steam_contexts": "|".join(sorted(sub["steam_context"].unique())),
                "sensor_health_contexts": "|".join(
                    sorted(sub["sensor_health_context"].unique())
                ),
                "bom_context_statuses": "|".join(
                    sorted(sub["bom_context_status"].unique())
                ),
                "transition_types_in_window": types,
                "n_transitions_in_window": int(len(near)),
                "window_row_count": int(len(sub)),
                "window_anomaly_rate": (
                    float(sub["is_anomaly"].mean()) if len(sub) else None
                ),
            }
        )
    return pd.DataFrame(rows)


def build_addendum(
    overlay: pd.DataFrame,
    transitions: pd.DataFrame,
    policy: OperationalContextPolicy,
    run_id: str,
    anomaly_dir: Path,
    forensic_dir: Path,
) -> AddendumArtifacts:
    """Assemble every addendum table, narrative and manifest (no writes)."""
    merged = _merge_scores(overlay, anomaly_dir)
    tables = {
        "anomaly_rates_by_steam_context": _rates_by(merged, "steam_context"),
        "anomaly_rates_by_sensor_health_context": _rates_by(
            merged, "sensor_health_context"
        ),
        "anomaly_rates_by_operational_context": _rates_by(merged, "context_key"),
        "candidate_dates_context_summary": _candidate_summary(
            merged, transitions, policy
        ),
    }
    hourly = (
        merged.assign(hour=merged["timestamp"].dt.floor("h"))
        .groupby("hour", as_index=False)
        .agg(anomaly_rate=("is_anomaly", "mean"))
    )
    summary = _executive_summary(tables, merged, transitions)
    manifest = {
        "component": "context_forensic_addendum",
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
            "forensic_run_id": forensic_dir.name,
            "forensic_run_dir": str(forensic_dir),
        },
        "timeline_row_count": int(len(overlay)),
        "generated_files": [],  # filled by write_addendum
        "completion_status": "pending",
    }
    return AddendumArtifacts(
        tables=tables,
        executive_summary=summary,
        limitations=_LIMITATIONS,
        manifest=manifest,
        steam_daily=daily_share(overlay, "steam_context"),
        health_daily=daily_share(overlay, "sensor_health_context"),
        hourly_rates=hourly,
    )


_LIMITATIONS = """# Limitations — context-aware forensic addendum

* Steam context is a threshold-and-persistence read of two sensors; it
  cannot distinguish an intentional operating-mode decision from an
  uncommanded valve state. Plant records are required for intent.
* Sensor-health context derives from rule-based plausibility checks; a
  fault present throughout the training window would calibrate the
  references and go unseen.
* The anomaly models were fitted blind to every context dimension shown
  here; a rate difference between contexts can reflect either a real
  process change or coincidental timing. Context alone cannot distinguish
  these.
* BOM context is declarative (planned orders), preserved unresolved in
  overlap windows by design.
* All statements are temporal associations. No causal claim is made or
  implied.
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


def _executive_summary(
    tables: dict[str, pd.DataFrame],
    merged: pd.DataFrame,
    transitions: pd.DataFrame,
) -> str:
    """Answer the five addendum questions with cautious, non-causal wording."""
    by_steam = tables["anomaly_rates_by_steam_context"]
    by_health = tables["anomaly_rates_by_sensor_health_context"]
    candidates = tables["candidate_dates_context_summary"].set_index(
        tables["candidate_dates_context_summary"]["candidate_timestamp"].dt.strftime(
            "%Y-%m-%d"
        )
    )
    faulty_rows = merged[merged["sensor_health_context"] == "sensor_faulty"]
    first_faulty = faulty_rows["timestamp"].min() if len(faulty_rows) else None
    first_faulty_sensors = (
        faulty_rows["faulty_sensors"].iloc[0] if len(faulty_rows) else ""
    )
    steam_changes = transitions[
        transitions["transition_types"].str.contains("steam_context_change")
    ]

    def near(day: str) -> str:
        row = candidates.loc[day] if day in candidates.index else None
        if row is None:
            return "no candidate window configured"
        return (
            f"transitions in ±24 h: {row['transition_types_in_window'] or 'none'}; "
            f"window anomaly rate {_fmt_rate(row['window_anomaly_rate'])}"
        )

    lines = [
        "# Executive summary — context-aware forensic addendum",
        "",
        "All statements below are **temporal associations**. Context alone "
        "cannot distinguish an operational decision from coincidental "
        "timing; no causal claim is made.",
        "",
        "## 1. Anomaly rates by steam-conditioning context",
        "",
        *_rate_lines(by_steam, "steam_context"),
        "",
        "## 2. Anomaly rates by sensor-health context",
        "",
        *_rate_lines(by_health, "sensor_health_context"),
        "",
        "## 3. Does the September 16 drift align with a steam / BOM / sensor-health transition?",
        f"2024-09-16 — {near('2024-09-16')}. The BOM-aware addendum already "
        "established that no recipe-version, composition or product change "
        "occurs at this date; steam-context and sensor-health transitions in "
        "the window are listed above.",
        "",
        "## 4. Does the September 18 escalation align with the inlet_hopper_points flatline-zero?",
        f"First `sensor_faulty` overlay timestamp (any sensor): "
        f"**{first_faulty if first_faulty is not None else 'none'}** "
        f"({first_faulty_sensors or 'n/a'}). The `inlet_hopper_points` "
        "flatline-zero itself begins 2024-09-17 16:23 — one day before the "
        f"forensic 09-18 headline step. 2024-09-18 — {near('2024-09-18')}.",
        "",
        "## 5. Is the drift better explained as operational change, instrumentation fault, or both?",
        "The evidence supports **both, as separable components**: (a) the "
        "steam-conditioning regime becomes persistently active (operational "
        "change — see the daily composition figure and "
        f"{len(steam_changes)} steam-context transitions), and (b) the "
        "`inlet_hopper_points` channel fails to constant zero "
        "(instrumentation fault — quarantine recommended, not executed). "
        "Anomaly rates split by sensor-health context (Q2) show how much of "
        "the validation anomaly mass coincides with the faulty-sensor "
        "window; the remainder coincides with the steam-on regime. The "
        "context layer alone cannot apportion causality between them.",
        "",
        "See limitations.md.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Figures + writing
# ---------------------------------------------------------------------------


def _save(fig: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _bar_figure(table: pd.DataFrame, key: str, title: str) -> Any:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    shown = table.head(15)
    ax.bar(
        shown[key].astype(str),
        shown["anomaly_rate_validation"].fillna(0.0),
        color="#b3443c",
    )
    ax.set_title(title)
    ax.set_ylabel("validation anomaly rate")
    ax.tick_params(axis="x", rotation=30, labelsize=7)
    return fig


def _daily_figure(daily: pd.DataFrame, title: str) -> Any:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    contexts = [c for c in daily.columns if c != "day"]
    ax.stackplot(daily["day"], [daily[c] for c in contexts], labels=contexts)
    ax.set_title(title)
    ax.set_ylabel("daily share of rows")
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
            f"{ev.candidate_timestamp.date()} — steam: {ev.steam_contexts}; "
            f"health: {ev.sensor_health_contexts}",
            fontsize=8,
        )
        ax.set_ylabel("anomaly rate")
    fig.tight_layout()
    return fig


def write_addendum(art: AddendumArtifacts, out: Path) -> list[str]:
    """Persist tables, narratives and figures; addendum manifest last."""
    written: list[str] = []
    for name in _TABLES:
        io.write_table(art.tables[name], out / f"{name}.parquet")
        written.append(f"{name}.parquet")
    (out / "executive_summary.md").write_text(art.executive_summary, encoding="utf-8")
    (out / "limitations.md").write_text(art.limitations, encoding="utf-8")
    written += ["executive_summary.md", "limitations.md"]

    fig_dir = out / "figures"
    _save(
        _bar_figure(
            art.tables["anomaly_rates_by_steam_context"],
            "steam_context",
            "Validation anomaly rate by steam context",
        ),
        fig_dir / FIGURES[0],
    )
    _save(
        _bar_figure(
            art.tables["anomaly_rates_by_sensor_health_context"],
            "sensor_health_context",
            "Validation anomaly rate by sensor-health context",
        ),
        fig_dir / FIGURES[1],
    )
    _save(_daily_figure(art.steam_daily, "Steam context per day"), fig_dir / FIGURES[2])
    _save(
        _daily_figure(art.health_daily, "Sensor-health context per day"),
        fig_dir / FIGURES[3],
    )
    _save(
        _candidate_figure(
            art.hourly_rates, art.tables["candidate_dates_context_summary"]
        ),
        fig_dir / FIGURES[4],
    )
    written += [f"figures/{name}" for name in FIGURES]

    manifest = dict(art.manifest)
    manifest["generated_files"] = written
    manifest["completion_status"] = "complete"
    io.write_manifest(manifest, out / io.ADDENDUM_MANIFEST_NAME)
    written.append(io.ADDENDUM_MANIFEST_NAME)
    return written
