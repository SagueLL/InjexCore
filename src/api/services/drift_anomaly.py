"""Drift & Anomaly view builder — the evidence-funnel artifact reader.

Serves anomaly/drift evidence and residual review candidates from the pinned
canonical run (API contract §6): the evidence funnel KPIs and affected-signal
ranking come from the persisted scoring-experiment comparison table, the daily
evidence series from the persisted anomaly scores plus the quarantine-aware
scenario scores, and per-detector counts from the persisted trigger tokens.
Artifacts are read once at the first hit and the built response is cached
in-process (§8 risk 1 — the pinned run is immutable). Raw parquet paths, run
folders and model internals are never exposed. Nothing here claims a confirmed
failure or an exact failure prediction — this view is evidence for review.
"""

from __future__ import annotations

from functools import lru_cache
from typing import NamedTuple

import numpy as np
import pandas as pd

from src.api.copy.notices import DRIFT_ANOMALY_NOTICE_KEYS
from src.api.copy.sensors import display_name_for
from src.api.errors import ArtifactUnreadableError
from src.api.schemas.common import Envelope
from src.api.schemas.drift_anomaly import (
    AffectedSignal,
    AnomalyEvidencePoint,
    ContributionLevel,
    DetectionMethodSummary,
    DriftAnomalyInsight,
    DriftAnomalyKpi,
    DriftAnomalySeverity,
    DriftAnomalySummary,
)
from src.api.services._series import daily_evidence, day_statuses, episodic_incidents
from src.api.services.view_meta import build_view_meta
from src.dashboard.contract import CANONICAL_RUN_ID
from src.intelligence._common.runs import resolve_run
from src.intelligence.anomaly import io as anomaly_io
from src.intelligence.drift import io as drift_io
from src.intelligence.incidents import io as incidents_io
from src.intelligence.scoring_experiment import io as scoring_io

# TODO(debt): pins on the canonical run (API contract §4/§8), mirroring the
# timeline pins; the quarantine onset should later come from the
# sensor-health/reference artifacts.
_PERIOD_START = "2024-06-14"
_PERIOD_END = "2024-10-08"
_QUARANTINE_ONSET = "2024-09-17"

_ASSET_NAME = "Pelletizer line"
_DATASET_NAME = "Real industrial dataset"

_QUARANTINE_SCENARIO_ID = "quarantine_inlet_hopper_points_interpretive"
_DOMINANT_FAULTY_SENSOR = "inlet_hopper_points"

# combined_score is deliberately absent: no served field derives from it any more
# (the daily p95 it fed was saturated — see services/_series.py).
_SCORE_COLUMNS = ["timestamp", "severity", "triggered_detectors"]
_SCENARIO_COLUMNS = ["timestamp", "scenario_id", "row_suppressed_for_review"]
_RATE_COLUMNS = [
    "scenario_id",
    "original_warning_count",
    "original_anomaly_count",
    "suppressed_count",
    "remaining_warning_count",
    "remaining_anomaly_count",
    "healthy_only_residual_count",
    "top_remaining_sensors",
]

# The §6 day ladder is shared with the timeline view; this type has no
# "drift" slot, so drift-status days read as warning.
_STATUS_TO_SEVERITY: dict[str, DriftAnomalySeverity] = {
    "critical": "critical",
    "drift": "warning",
    "warning": "warning",
    "normal": "normal",
}


class _Artifacts(NamedTuple):
    scores: pd.DataFrame
    incidents: pd.DataFrame
    #: `incidents` minus the recurring-pattern envelopes; drives the day ladder.
    episodic_incidents: pd.DataFrame
    drift_events: pd.DataFrame
    scenario_scores: pd.DataFrame
    rate_row: pd.Series


def _load_artifacts() -> _Artifacts:
    """Read the pinned run's evidence artifacts (scores, incidents, scenarios)."""
    try:
        anomaly_run = resolve_run(
            anomaly_io.ANOMALY_DIR,
            CANONICAL_RUN_ID,
            anomaly_io.MANIFEST_NAME,
            "anomaly",
        )
        incidents_run = resolve_run(
            incidents_io.INCIDENTS_DIR,
            CANONICAL_RUN_ID,
            incidents_io.MANIFEST_NAME,
            "incidents",
        )
        drift_run = resolve_run(
            drift_io.DRIFT_DIR, CANONICAL_RUN_ID, drift_io.MANIFEST_NAME, "drift"
        )
        scoring_run = resolve_run(
            scoring_io.SCORING_DIR,
            CANONICAL_RUN_ID,
            scoring_io.MANIFEST_NAME,
            "controlled_scoring_experiment",
        )
        scores = pd.read_parquet(
            anomaly_run / anomaly_io.SCORES_FILE, columns=_SCORE_COLUMNS
        )
        incidents = pd.read_parquet(incidents_run / incidents_io.INCIDENTS_FILE)
        suppressed = pd.read_parquet(incidents_run / incidents_io.SUPPRESSED_FILE)
        drift_events = pd.read_parquet(drift_run / drift_io.EVENTS_FILE)
        scenario_scores = pd.read_parquet(
            scoring_run / scoring_io.SCENARIO_SCORES_FILE, columns=_SCENARIO_COLUMNS
        )
        rate = pd.read_parquet(
            scoring_run / scoring_io.ANOMALY_RATE_COMPARISON_FILE,
            columns=_RATE_COLUMNS,
        )
        # Filter suppression here so no consumer ever sees suppressed incidents.
        unsuppressed = incidents[
            ~incidents["incident_id"].isin(suppressed["suppressed_incident_id"])
        ].reset_index(drop=True)
        # Inside the try: a missing `evidence` column is a schema change, and must
        # fail closed rather than silently disable the recurring-pattern filter.
        episodic = episodic_incidents(unsuppressed)
    except (OSError, ValueError, KeyError) as exc:
        # Argument-less on purpose: resolve_run/pyarrow messages embed
        # filesystem paths the API must never expose.
        raise ArtifactUnreadableError() from exc
    quarantine = rate[rate["scenario_id"] == _QUARANTINE_SCENARIO_ID]
    if quarantine.empty:
        # A rate table without the quarantine scenario cannot back this view's
        # funnel — fail closed rather than serving partial data.
        raise ArtifactUnreadableError()
    return _Artifacts(
        scores,
        unsuppressed,
        episodic,
        drift_events,
        scenario_scores,
        quarantine.iloc[0],
    )


def _parse_sensor_counts(value: str) -> list[tuple[str, int]]:
    """Parse the persisted ``sensor:count|sensor:count`` ranking string."""
    pairs: list[tuple[str, int]] = []
    for token in value.split("|"):
        name, _, count = token.rpartition(":")
        pairs.append((name, int(count)))
    return pairs


def _funnel_kpis(rate_row: pd.Series) -> list[DriftAnomalyKpi]:
    """The §6 evidence funnel, straight from the persisted comparison table."""
    raw_total = int(
        rate_row["original_warning_count"] + rate_row["original_anomaly_count"]
    )
    residual_warning = int(rate_row["remaining_warning_count"])
    residual_anomaly = int(rate_row["remaining_anomaly_count"])
    return [
        DriftAnomalyKpi(
            label="Raw non-normal rows",
            value=raw_total,
            description="Scored rows with warning or anomaly evidence, unfiltered.",
        ),
        DriftAnomalyKpi(
            label="Contextualised for review",
            value=int(rate_row["suppressed_count"]),
            description=(
                "Rows down-ranked for review as dominated by the pending "
                "inlet-hopper instrumentation fault. Original anomaly scores "
                "are unchanged."
            ),
        ),
        DriftAnomalyKpi(
            label="Residual review backlog",
            value=residual_warning + residual_anomaly,
            description=(
                f"Review candidates remaining after contextual filtering "
                f"({residual_warning} warning / {residual_anomaly} anomaly rows)."
            ),
        ),
        DriftAnomalyKpi(
            label="Healthy-only drift windows",
            value=int(rate_row["healthy_only_residual_count"]),
            description=(
                "Residual drift windows in the healthy-only proxy view — an "
                "analytical approximation, not a rescoring."
            ),
        ),
    ]


def _evidence_series(
    scores: pd.DataFrame,
    episodic: pd.DataFrame,
    drift_events: pd.DataFrame,
    scenario_scores: pd.DataFrame,
) -> list[AnomalyEvidencePoint]:
    """Per-UTC-day evidence points over the scored-day universe (§6).

    Counts are reindexed onto the scored days: scored days without residual
    scenario rows serve 0; scenario rows on days without any scored row are
    dropped with the day (the §6 omission rule). ``anomalyCount`` is the absolute
    numerator of ``evidenceShare``, so both come from one aggregation.
    """
    evidence = daily_evidence(scores)
    days = pd.DatetimeIndex(evidence.index)
    residual = scenario_scores[
        (scenario_scores["scenario_id"] == _QUARANTINE_SCENARIO_ID)
        & ~scenario_scores["row_suppressed_for_review"]
    ]
    residual_counts = (
        residual.groupby(residual["timestamp"].dt.floor("D"))
        .size()
        .reindex(days, fill_value=0)
    )
    severities = [
        _STATUS_TO_SEVERITY[status]
        for status in day_statuses(
            days, evidence["evidence_share"], episodic, drift_events
        )
    ]
    return [
        AnomalyEvidencePoint(
            date=day.strftime("%Y-%m-%d"),
            evidence_share=float(row.evidence_share),
            anomaly_count=int(row.non_normal_rows),
            residual_count=int(residual_count),
            severity=severity,
        )
        for (day, row), residual_count, severity in zip(
            evidence.iterrows(), residual_counts, severities, strict=True
        )
    ]


def _detection_methods(
    scores: pd.DataFrame, rate_row: pd.Series
) -> list[DetectionMethodSummary]:
    """Per-detector trigger counts over non-normal rows, plus the overlay row."""
    non_normal = scores[scores["severity"].isin(["warning", "anomaly"])]
    tokens = non_normal["triggered_detectors"].dropna().str.split("|").explode()
    triggers = tokens[tokens != ""].value_counts()

    def count(detector: str) -> int:
        return int(triggers.get(detector, 0))

    return [
        DetectionMethodSummary(
            method="statistical",
            label="Statistical baseline deviation",
            evidence_count=count("statistical"),
            description=(
                "Deviation from the per-profile statistical baselines fitted "
                "on the training window."
            ),
        ),
        DetectionMethodSummary(
            method="mahalanobis",
            label="Mahalanobis distance",
            evidence_count=count("mahalanobis"),
            description=(
                "Multivariate distance from the training-window covariance "
                "structure of each operational profile."
            ),
        ),
        DetectionMethodSummary(
            method="pca_t2",
            label="PCA T² (in-model distance)",
            evidence_count=count("pca_t2"),
            description=(
                "Distance inside the learned correlation structure — a "
                "different quantity from the reconstruction residual."
            ),
        ),
        DetectionMethodSummary(
            method="pca_residual",
            label="PCA residual (Q/SPE)",
            # The backend detector id is pca_q; Q/SPE is the residual
            # distance, served as pca_residual (contract §3).
            evidence_count=count("pca_q"),
            description=(
                "Reconstruction residual: rows that break the correlation "
                "structure learned on the training window."
            ),
        ),
        DetectionMethodSummary(
            method="isolation_forest",
            label="Isolation Forest",
            evidence_count=count("isolation_forest"),
            description=(
                "Seeded ensemble isolation score; contributes no per-sensor "
                "attributions."
            ),
        ),
        DetectionMethodSummary(
            method="context_overlay",
            label="Operational context overlay",
            evidence_count=int(rate_row["suppressed_count"]),
            description=(
                "Interpretive review overlay, not a detector: counts evidence "
                "rows down-ranked for review as dominated by the pending "
                "inlet-hopper instrumentation fault. Original anomaly scores "
                "are unchanged."
            ),
        ),
    ]


def _affected_signals(rate_row: pd.Series) -> list[AffectedSignal]:
    """Signals ranked by residual-evidence frequency (§6).

    Frequencies come from the persisted ``top_remaining_sensors`` ranking of
    the quarantine-aware scenario — frequency over unsuppressed non-normal
    rows. Tercile cutoffs are computed over the persisted top-10 ranking, an
    accepted approximation of "sensors with nonzero counts" (§8 risk 1 prefers
    persisted aggregates over row scans).
    """
    counts = dict(_parse_sensor_counts(str(rate_row["top_remaining_sensors"])))
    dominant_count = counts.pop(_DOMINANT_FAULTY_SENSOR, 0)
    signals = [
        AffectedSignal(
            sensor_id=_DOMINANT_FAULTY_SENSOR,
            display_name=display_name_for(_DOMINANT_FAULTY_SENSOR),
            contribution="high",
            severity="critical",
            interpretation=(
                f"Instrumentation-fault channel flatlining at zero since "
                f"{_QUARANTINE_ONSET}; still appears in {dominant_count} "
                f"residual review rows. Its quarantine recommendation is "
                f"pending human review and has not been applied."
            ),
        )
    ]
    rest = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    if not rest:
        return signals
    q1, q2 = np.quantile([count for _, count in rest], [1 / 3, 2 / 3])
    for sensor_id, sensor_count in rest:
        contribution: ContributionLevel
        if sensor_count >= q2:
            contribution = "high"
        elif sensor_count >= q1:
            contribution = "medium"
        else:
            contribution = "low"
        # Curated pin: only the instrumentation fault is asserted critical;
        # high-contribution process signals read as warning, the rest normal.
        severity: DriftAnomalySeverity = (
            "warning" if contribution == "high" else "normal"
        )
        signals.append(
            AffectedSignal(
                sensor_id=sensor_id,
                display_name=display_name_for(sensor_id),
                contribution=contribution,
                severity=severity,
                interpretation=(
                    f"Appears in {sensor_count} unsuppressed non-normal rows; "
                    f"residual review evidence, not a confirmed fault."
                ),
            )
        )
    return signals


def _insights(rate_row: pd.Series) -> list[DriftAnomalyInsight]:
    """Curated copy with every number interpolated from the artifacts (§8)."""
    raw_total = int(
        rate_row["original_warning_count"] + rate_row["original_anomaly_count"]
    )
    suppressed = int(rate_row["suppressed_count"])
    residual = int(
        rate_row["remaining_warning_count"] + rate_row["remaining_anomaly_count"]
    )
    top = _parse_sensor_counts(str(rate_row["top_remaining_sensors"]))[:3]
    concentration = ", ".join(
        f"{display_name_for(sensor_id)} ({count} rows)" for sensor_id, count in top
    )
    return [
        DriftAnomalyInsight(
            title="Contextual filtering narrowed the raw evidence",
            body=(
                f"Of {raw_total} raw non-normal evidence rows, {suppressed} "
                f"were down-ranked for review as dominated by the pending "
                f"inlet-hopper instrumentation fault, leaving {residual} "
                f"residual review candidates. Original anomaly scores are "
                f"unchanged."
            ),
        ),
        DriftAnomalyInsight(
            title="Residual evidence concentrates on a few signals",
            body=(
                f"The remaining review candidates concentrate on "
                f"{concentration}. Review them by period and operational "
                f"profile before drawing conclusions."
            ),
        ),
        DriftAnomalyInsight(
            title="Evidence for review, not confirmation",
            body=(
                "Anomaly and drift outputs are early deviation evidence for "
                "prioritized review — not confirmed failures and not exact "
                "failure predictions. Plant records and operator judgement "
                "remain required before operational decisions."
            ),
        ),
    ]


def _build_summary(artifacts: _Artifacts) -> DriftAnomalySummary:
    return DriftAnomalySummary(
        asset_name=_ASSET_NAME,
        dataset_name=_DATASET_NAME,
        period_start=_PERIOD_START,
        period_end=_PERIOD_END,
        summary_kpis=_funnel_kpis(artifacts.rate_row),
        evidence_series=_evidence_series(
            artifacts.scores,
            artifacts.episodic_incidents,
            artifacts.drift_events,
            artifacts.scenario_scores,
        ),
        detection_methods=_detection_methods(artifacts.scores, artifacts.rate_row),
        affected_signals=_affected_signals(artifacts.rate_row),
        insights=_insights(artifacts.rate_row),
    )


@lru_cache(maxsize=1)
def build_drift_anomaly_response() -> Envelope[DriftAnomalySummary]:
    """Build the ``{meta, data}`` drift-anomaly response; cached after first hit.

    Exceptions are intentionally not cached by ``lru_cache``, so a transient
    read failure self-recovers on the next request.
    """
    artifacts = _load_artifacts()
    return Envelope[DriftAnomalySummary](
        meta=build_view_meta(DRIFT_ANOMALY_NOTICE_KEYS),
        data=_build_summary(artifacts),
    )
