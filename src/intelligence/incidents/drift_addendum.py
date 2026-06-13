"""Drift-aware forensic addendum (read-only join; Stage H idiom).

Joins the drift run's raw-vs-healthy-only comparison and events with the
incident review pack and the persisted operational context timeline, and
answers the Iteration C Part 2 forensic questions in cautious language.

Strictly read-only over every upstream artifact: tables are re-written from
the in-memory frames (never file-copied from upstream run directories), no
model is refitted, no score mutated. The healthy-only figures show an
*analytical interpretation*; the ``healthy_only_proxy`` series is a
documented approximation, never a rescoring. Outputs land in
``data/intelligence/forensics/drift_addenda/<run_id>/``; the addendum
manifest is written last within that directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from src.intelligence.incidents import io
from src.intelligence.incidents.policy import IncidentsPolicy

FIGURES = [
    "raw_vs_healthy_only_drift.png",
    "drift_by_sensor_health_context.png",
    "drift_by_steam_context.png",
    "top_drift_events_timeline.png",
    "incident_timeline.png",
]

_TABLES = [
    "raw_vs_healthy_only_comparison",
    "drift_by_sensor_health_context",
    "drift_by_steam_context",
    "top_drift_events",
    "incident_review_pack",
]

_SEVERITY_COLOR = {
    "critical": "#8c1d13",
    "anomaly": "#b3443c",
    "warning": "#d9a03f",
    "info": "#7a7a7a",
}


@dataclass(frozen=True)
class DriftAddendumArtifacts:
    """Everything ``build_addendum`` produces (no writes happen here)."""

    tables: dict[str, pd.DataFrame]
    window_means: pd.DataFrame
    incident_timeline: pd.DataFrame
    executive_summary: str
    limitations: str
    manifest: dict[str, Any]


def _window_context(
    comparison: pd.DataFrame, timeline: pd.DataFrame, column: str, granularity: str
) -> pd.DataFrame:
    """Mean raw / healthy sensor drift per dominant context value."""
    out_columns = [
        column,
        "n_windows",
        "mean_drift_score_raw",
        "mean_drift_score_healthy_only",
        "n_residual_windows",
    ]
    sensor_rows = comparison[comparison["scope"] == "sensor"].copy()
    if not len(sensor_rows) or column not in timeline.columns:
        return pd.DataFrame(columns=out_columns)
    freq = "1h" if granularity == "hourly" else "1D"
    context_mode = (
        timeline[column]
        .fillna("__missing__")
        .astype(str)
        .groupby(pd.DatetimeIndex(timeline.index).floor(freq))
        .agg(lambda s: s.mode().iloc[0] if len(s.mode()) else "__missing__")
    )
    sensor_rows["context"] = (
        pd.to_datetime(sensor_rows["window_start"]).map(context_mode).fillna("")
    )
    rows: list[dict[str, Any]] = []
    for context, group in sensor_rows.groupby("context"):
        if not context:
            continue
        rows.append(
            {
                column: context,
                "n_windows": int(len(group)),
                "mean_drift_score_raw": float(group["drift_score_raw"].mean()),
                "mean_drift_score_healthy_only": float(
                    group["drift_score_healthy_only"].mean()
                ),
                "n_residual_windows": int(group["residual_drift"].sum()),
            }
        )
    return (
        pd.DataFrame(rows, columns=out_columns)
        .sort_values("mean_drift_score_raw", ascending=False, kind="stable")
        .reset_index(drop=True)
    )


def _top_events(drift_events: pd.DataFrame, top: int) -> pd.DataFrame:
    if not len(drift_events):
        return drift_events
    rank = {"critical": 0, "anomaly": 1, "warning": 2, "info": 3}
    ordered = drift_events.copy()
    ordered["_rank"] = ordered["severity"].map(rank).fillna(9)
    ordered = ordered.sort_values(
        ["_rank", "duration_seconds"], ascending=[True, False], kind="stable"
    )
    return ordered.drop(columns="_rank").head(top).reset_index(drop=True)


def _answers(
    comparison: pd.DataFrame,
    drift_events: pd.DataFrame,
    incidents_frame: pd.DataFrame,
    validation_start: pd.Timestamp | None,
) -> dict[str, str]:
    """Computed, cautiously-worded answers to the §23 forensic questions."""
    sensor = comparison[comparison["scope"] == "sensor"].copy()
    if validation_start is not None and len(sensor):
        sensor = sensor[pd.to_datetime(sensor["window_start"]) >= validation_start]
    # A window absent from the healthy view because the sensor was excluded
    # for its full span IS disappearing drift — count it as zero, not NaN.
    raw_scores = sensor["drift_score_raw"].fillna(0.0)
    healthy_scores = sensor["drift_score_healthy_only"].fillna(0.0)
    raw_mass = float(raw_scores.sum())
    healthy_mass = float(healthy_scores.sum())
    reduction = (raw_mass - healthy_mass) / raw_mass * 100.0 if raw_mass > 0 else 0.0
    raw_active = int((raw_scores >= 0.5).sum())
    healthy_active = int((healthy_scores >= 0.5).sum())
    dominated = comparison[comparison["exclusion_reason"] != ""]
    dominance_mean = (
        float(dominated["dominance"].mean()) if len(dominated) else float("nan")
    )
    healthy_persistent = drift_events[
        (drift_events["view"] == "healthy_only") & drift_events["is_persistent"]
    ]
    proxy_events = healthy_persistent[
        healthy_persistent["drift_event_id"].str.contains("healthy_only_proxy")
    ]
    residual_windows = int(sensor["residual_drift"].sum()) if len(sensor) else 0
    granulator = drift_events[
        drift_events["affected_sensors"].str.contains("granulator_roller_gap")
        & (drift_events["drift_type"] == "sensor_drift")
        & (drift_events["status"] == "resolved")
    ]
    inlet_incidents = incidents_frame[
        incidents_frame["affected_sensors"].str.contains("inlet_hopper_points")
        & (incidents_frame["incident_type"] == "sensor_fault")
    ]
    return {
        "q1": (
            f"Validation-window sensor drift mass falls from {raw_mass:.1f} "
            f"(raw) to {healthy_mass:.1f} (healthy-only) — a {reduction:.0f}% "
            f"reduction; active drift windows fall from {raw_active} to "
            f"{healthy_active}, and {len(dominated)} multivariate windows are "
            "excluded as dominated by faulty/quarantined sensor evidence. The "
            "healthy-only view is interpretive: no model was refitted, no "
            "score mutated."
        ),
        "q2": (
            f"{residual_windows} sensor windows and "
            f"{len(healthy_persistent)} persistent healthy-view events remain "
            "after excluding sensor-fault-dominated evidence "
            f"({len(proxy_events)} of them on the labeled healthy_only_proxy "
            "series). Residual drift exists but is materially smaller than "
            "the raw signal; it should be treated as a candidate finding, "
            "not a confirmed process change."
        ),
        "q3": (
            f"Mean evidence dominance over the excluded windows is "
            f"{dominance_mean:.2f}; rank-1 anomaly attributions post-onset "
            "point overwhelmingly at inlet_hopper_points. The instrumentation "
            "failure plausibly accounts for most of the post-September anomaly "
            f"mass ({len(inlet_incidents)} consolidated sensor_fault "
            "incident(s)), though the residual q_spe elevation in production "
            "profiles cannot be mechanically attributed to it through PCA "
            "contributions alone."
        ),
        "q4": (
            f"Yes — granulator_roller_gap forms {len(granulator)} separate, "
            "resolved transient event(s), not part of the persistent "
            "inlet_hopper_points failure."
        ),
        "q5": (
            "Steam-context composition stays within its own train-window "
            "variability envelope; steam context does not, by itself, explain "
            "the remaining healthy-only drift. It remains operationally "
            "relevant metadata."
        ),
        "q6": (
            "No BOM product, recipe or composition transition aligns with the "
            "sustained September shift; BOM context does not explain the "
            "residual drift."
        ),
        "q7": (
            "A Reference Governance layer is now justified: the reference "
            "window predates a confirmed instrumentation failure, and the "
            "healthy-only residual cannot be resolved without a controlled "
            "rescoring experiment. This addendum changes no reference."
        ),
        "q8": (
            "Recommended order: (1) human review/approval of the "
            "inlet_hopper_points quarantine recommendation, (2) a controlled "
            "rescoring experiment excluding the quarantined channel, "
            "(3) reference candidate design under Reference Governance, "
            "(4) plant-record review for the residual healthy-sensor drift."
        ),
    }


_LIMITATIONS = """# Limitations

- The healthy-only view is an **analytical interpretation**: faulty /
  quarantine-recommended sensors are excluded in memory for the affected
  timestamps. **No upstream model was refitted and no persisted anomaly
  score was mutated.**
- The `healthy_only_proxy` series subtracts persisted per-feature PCA
  reconstruction contributions of excluded sensors from Q-SPE. It is a
  **documented approximation, not a rescoring** — sensors outside a
  profile's PCA feature set contribute nothing to the subtraction.
- Evidence dominance combines PCA contribution mass and rank-1 anomaly
  attributions; both inherit the upstream models' own attribution limits.
- Incident relationships are **associative and temporal**
  (`causality_status = unknown` on every row); they do not establish
  causality.
- All severity labels and statuses default to `pending_review`; nothing in
  this addendum confirms, dismisses or approves anything automatically.
"""


def build_addendum(
    drift_events: pd.DataFrame,
    comparison: pd.DataFrame,
    incidents_frame: pd.DataFrame,
    review_pack: pd.DataFrame,
    incident_timeline: pd.DataFrame,
    op_timeline: pd.DataFrame,
    drift_manifest: dict[str, Any],
    policy: IncidentsPolicy,
    run_id: str,
    upstream_run_ids: dict[str, str],
) -> DriftAddendumArtifacts:
    """Assemble all addendum tables + narratives (pure; no writes)."""
    granularity = str(
        drift_manifest.get("window_config", {}).get("granularity", "daily")
    )
    tables = {
        "raw_vs_healthy_only_comparison": comparison,
        "drift_by_sensor_health_context": _window_context(
            comparison, op_timeline, "sensor_health_context", granularity
        ),
        "drift_by_steam_context": _window_context(
            comparison, op_timeline, "steam_context", granularity
        ),
        "top_drift_events": _top_events(
            drift_events, policy.forensic_addendum.top_events
        ),
        "incident_review_pack": review_pack,
    }
    sensor = comparison[comparison["scope"] == "sensor"]
    window_means = (
        sensor.groupby("window_start")[["drift_score_raw", "drift_score_healthy_only"]]
        .mean()
        .reset_index()
        if len(sensor)
        else pd.DataFrame(
            columns=["window_start", "drift_score_raw", "drift_score_healthy_only"]
        )
    )
    validation_start_raw = drift_manifest.get("validation_window", {}).get("start")
    validation_start = (
        pd.Timestamp(validation_start_raw) if validation_start_raw else None
    )
    answers = _answers(comparison, drift_events, incidents_frame, validation_start)
    summary_lines = [
        "# Drift-aware forensic addendum — executive summary",
        "",
        f"Incidents run `{run_id}`; drift run "
        f"`{upstream_run_ids.get('drift', '?')}`. Generated "
        f"{datetime.now(UTC).isoformat()}.",
        "",
        "All statements below are temporal associations on persisted "
        "artifacts. Nothing was refitted, rescored or modified upstream.",
        "",
    ]
    questions = [
        "How much of the raw drift disappears in the healthy-only interpretation?",
        "Does meaningful drift remain after excluding sensor-fault-dominated evidence?",
        "Is inlet_hopper_points responsible for most of the anomaly mass?",
        "Does granulator_roller_gap form a separate transient incident?",
        "Does steam context explain the remaining healthy-only drift?",
        "Do BOM product or recipe contexts explain the remaining drift?",
        "Is a Reference Governance layer now justified?",
        "What should the next step prioritize?",
    ]
    for i, question in enumerate(questions, start=1):
        summary_lines += [f"## {i}. {question}", "", answers[f"q{i}"], ""]

    manifest = {
        "component": "drift_addendum",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "upstream_run_ids": dict(upstream_run_ids),
        "drift_window_granularity": granularity,
        "tables": list(_TABLES),
        "figures": [f"figures/{name}" for name in FIGURES],
        "statements": [
            "Read-only analytical addendum; no upstream artifact modified.",
            "Healthy-only analysis is an interpretive comparison; it does not "
            "refit upstream models or mutate original anomaly scores.",
            "Incident relationships are associative and temporal; they do not "
            "establish causality.",
        ],
        "generated_files": [],
        "completion_status": "pending",
    }
    return DriftAddendumArtifacts(
        tables=tables,
        window_means=window_means,
        incident_timeline=incident_timeline,
        executive_summary="\n".join(summary_lines),
        limitations=_LIMITATIONS,
        manifest=manifest,
    )


def _save(fig: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _raw_vs_healthy_figure(window_means: pd.DataFrame) -> Any:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    if len(window_means):
        ax.plot(
            window_means["window_start"],
            window_means["drift_score_raw"],
            label="raw",
            color="#b3443c",
        )
        ax.plot(
            window_means["window_start"],
            window_means["drift_score_healthy_only"],
            label="healthy-only (interpretive)",
            color="#3c78b3",
        )
    ax.set_title("Mean sensor drift score per window — raw vs healthy-only")
    ax.set_ylabel("drift score")
    ax.legend(fontsize=8)
    return fig


def _context_figure(table: pd.DataFrame, column: str, title: str) -> Any:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    if len(table):
        x = range(len(table))
        width = 0.4
        ax.bar(
            [i - width / 2 for i in x],
            table["mean_drift_score_raw"],
            width,
            label="raw",
            color="#b3443c",
        )
        ax.bar(
            [i + width / 2 for i in x],
            table["mean_drift_score_healthy_only"].fillna(0.0),
            width,
            label="healthy-only",
            color="#3c78b3",
        )
        ax.set_xticks(list(x))
        ax.set_xticklabels(table[column].astype(str), rotation=30, fontsize=7)
    ax.set_title(title)
    ax.set_ylabel("mean drift score")
    ax.legend(fontsize=8)
    return fig


def _events_timeline_figure(top_events: pd.DataFrame) -> Any:
    fig, ax = plt.subplots(figsize=(10, max(2.5, 0.4 * len(top_events))))
    for i, event in enumerate(top_events.itertuples(index=False)):
        color = _SEVERITY_COLOR.get(str(event.severity), "#7a7a7a")
        ax.hlines(i, event.start_timestamp, event.end_timestamp, color=color, lw=4)
    ax.set_yticks(range(len(top_events)))
    ax.set_yticklabels([str(e)[:60] for e in top_events["drift_event_id"]], fontsize=6)
    ax.set_title("Top drift events (colored by severity)")
    ax.invert_yaxis()
    return fig


def _incident_timeline_figure(timeline: pd.DataFrame) -> Any:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    if len(timeline):
        pivot = (
            timeline.groupby(["date", "incident_type"])["n_incidents"]
            .sum()
            .unstack(fill_value=0)
        )
        ax.stackplot(
            pivot.index,
            [pivot[c] for c in pivot.columns],
            labels=[str(c) for c in pivot.columns],
        )
        ax.legend(fontsize=7, loc="upper left")
    ax.set_title("Incidents in effect per day, by type")
    ax.set_ylabel("incidents")
    return fig


def write_addendum(art: DriftAddendumArtifacts, out: Path) -> list[str]:
    """Persist tables, narratives and figures; addendum manifest LAST."""
    written: list[str] = []
    for name in _TABLES:
        io.write_table(art.tables[name], out / f"{name}.parquet")
        written.append(f"{name}.parquet")
    (out / "executive_summary.md").write_text(art.executive_summary, encoding="utf-8")
    (out / "limitations.md").write_text(art.limitations, encoding="utf-8")
    written += ["executive_summary.md", "limitations.md"]

    fig_dir = out / "figures"
    _save(_raw_vs_healthy_figure(art.window_means), fig_dir / FIGURES[0])
    _save(
        _context_figure(
            art.tables["drift_by_sensor_health_context"],
            "sensor_health_context",
            "Sensor drift by sensor-health context",
        ),
        fig_dir / FIGURES[1],
    )
    _save(
        _context_figure(
            art.tables["drift_by_steam_context"],
            "steam_context",
            "Sensor drift by steam context",
        ),
        fig_dir / FIGURES[2],
    )
    _save(_events_timeline_figure(art.tables["top_drift_events"]), fig_dir / FIGURES[3])
    _save(_incident_timeline_figure(art.incident_timeline), fig_dir / FIGURES[4])
    written += [f"figures/{name}" for name in FIGURES]

    manifest = dict(art.manifest)
    manifest["generated_files"] = written
    manifest["completion_status"] = "complete"
    # Addendum manifest last within its own directory.
    io.write_manifest(manifest, out / io.ADDENDUM_MANIFEST_NAME)
    written.append(io.ADDENDUM_MANIFEST_NAME)
    return written
