"""Quarantine-target extraction for the controlled scenarios.

Reads the PENDING (unapproved) quarantine proposals from the reference run
and the suppressed-duplicate burst windows from the incident run. These
define *which* sensor evidence Scenario 1 down-ranks for review — they are
never applied, never approved, never used to exclude a sensor from any model.
"""

from __future__ import annotations

import re
from typing import NamedTuple

import pandas as pd


class QuarantineWindow(NamedTuple):
    """A sensor and the timestamp window over which it is faulty."""

    sensor: str
    start: pd.Timestamp
    end: pd.Timestamp


def quarantine_targets(reference_quarantine: pd.DataFrame) -> list[QuarantineWindow]:
    """Pending quarantine proposals → (sensor, start, end) windows."""
    targets: list[QuarantineWindow] = []
    for row in reference_quarantine.itertuples(index=False):
        targets.append(
            QuarantineWindow(
                sensor=str(row.sensor),
                start=pd.Timestamp(row.start_timestamp),
                end=pd.Timestamp(row.end_timestamp),
            )
        )
    return targets


def _contains_token(series: pd.Series, token: str) -> pd.Series:
    pattern = rf"(?:^|\|){re.escape(token)}(?:\||$)"
    return series.fillna("").astype(str).str.contains(pattern, regex=True)


def suppressed_burst_windows(
    suppressed: pd.DataFrame, incidents: pd.DataFrame
) -> list[QuarantineWindow]:
    """Suppressed anomaly-burst windows mapped to their explaining sensor.

    Each suppressed duplicate burst is explained by a stronger sensor-fault
    incident; the burst window inherits that incident's affected sensor.
    """
    windows: list[QuarantineWindow] = []
    if not len(suppressed):
        return windows
    by_id = (
        incidents.set_index("incident_id")["affected_sensors"].astype(str).to_dict()
        if len(incidents)
        else {}
    )
    for row in suppressed.itertuples(index=False):
        sensor = str(by_id.get(str(row.suppressed_by_incident_id), "")).split("|")[0]
        windows.append(
            QuarantineWindow(
                sensor=sensor,
                start=pd.Timestamp(row.start_timestamp),
                end=pd.Timestamp(row.end_timestamp),
            )
        )
    return windows
