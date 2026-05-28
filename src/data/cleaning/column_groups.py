"""Read ``data/features/variable_classification.csv`` and expose helpers
that return the column sets each cleaning module needs (Process,
Control, State, Metadata, running flags, alarm flags, setpoints).

Keeping this in one place means new columns added to the classification
CSV automatically propagate to every module — no hardcoded lists.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CLASSIFICATION = (
    PROJECT_ROOT / "data" / "features" / "variable_classification.csv"
)


@dataclass(frozen=True)
class ColumnGroups:
    """Materialised column sets used across cleaning modules."""

    all_columns: list[str]
    process: list[str]
    control: list[str]
    state: list[str]
    metadata: list[str]
    setpoints: list[str]          # subset of control: ends with _sp
    running_flags: list[str]      # *_running state columns
    alarm_flags: list[str]        # *_alarm state columns
    temperature_cols: list[str]   # process + control temp columns (unit C)
    pressure_cols: list[str]      # process + control pressure columns (unit bar)
    power_cols: list[str]         # *_power / *_state_pct (unit %)
    classification: pd.DataFrame  # raw table, indexed by Variable

    def signal_columns(self) -> list[str]:
        """All non-metadata, non-timestamp numeric columns."""
        return [
            c for c in self.all_columns
            if c not in self.metadata and c != "timestamp"
        ]

    def semantic_category(self, col: str) -> str | None:
        """Route a column to the semantic category used by time-series engineering.

        Returns one of ``"process_sensor" | "setpoint" | "state_flag" |
        "alarm" | "control"``, or ``None`` for metadata / timestamp / unknown
        columns.

        Routing order matters: ``setpoint`` and ``state_flag`` / ``alarm``
        are tested before their parent categories so a ``*_sp`` column is
        not also reported as generic ``control``.
        """
        if col in self.metadata or col == "timestamp":
            return None
        if col in self.alarm_flags:
            return "alarm"
        if col in self.running_flags:
            return "state_flag"
        if col in self.setpoints:
            return "setpoint"
        if col in self.process:
            return "process_sensor"
        if col in self.control:
            return "control"
        if col in self.state:
            return "state_flag"
        return None


def load_groups(
    classification_path: Path = DEFAULT_CLASSIFICATION,
) -> ColumnGroups:
    """Build a :class:`ColumnGroups` from the classification CSV."""
    df = pd.read_csv(classification_path)
    df = df.set_index("Variable", drop=False)

    def by_category(cat: str) -> list[str]:
        return df.index[df["Category"] == cat].tolist()

    process = by_category("Process")
    control = by_category("Control")
    state = by_category("State")
    metadata = by_category("Metadata")

    setpoints = [v for v in control if v.endswith("_sp")]
    running_flags = [v for v in state if v.endswith("_running") or v.endswith("_direct")]
    alarm_flags = [v for v in state if v.endswith("_alarm")]

    temperature_cols = df.index[df["Unity"] == "C"].tolist()
    pressure_cols = df.index[df["Unity"] == "bar"].tolist()
    power_cols = df.index[df["Unity"] == "%"].tolist()

    return ColumnGroups(
        all_columns=df.index.tolist(),
        process=process,
        control=control,
        state=state,
        metadata=metadata,
        setpoints=setpoints,
        running_flags=running_flags,
        alarm_flags=alarm_flags,
        temperature_cols=temperature_cols,
        pressure_cols=pressure_cols,
        power_cols=power_cols,
        classification=df,
    )
