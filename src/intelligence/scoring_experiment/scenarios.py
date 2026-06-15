"""Scenario catalogue for the Controlled Scoring Experiment.

The ``scenario_definitions`` table is the manifest of *what was run* and how
to read it: which scenarios are interpretive, which operate per-row vs at the
window/diagnostic level, and the explicit promise that none mutate original
scores.
"""

from __future__ import annotations

import pandas as pd

SCENARIO_DEFINITION_COLUMNS = [
    "scenario_id",
    "scenario_type",
    "granularity",
    "mutates_original_scores",
    "is_interpretive",
    "description",
]

_SCENARIOS = [
    {
        "scenario_id": "baseline_v1",
        "scenario_type": "baseline",
        "granularity": "per_row",
        "mutates_original_scores": False,
        "is_interpretive": False,
        "description": ("Original persisted anomaly scores and incidents, unchanged."),
    },
    {
        "scenario_id": "quarantine_inlet_hopper_points_interpretive",
        "scenario_type": "quarantine_aware",
        "granularity": "per_row",
        "mutates_original_scores": False,
        "is_interpretive": True,
        "description": (
            "Hypothetical view using the PENDING (unapproved) quarantine "
            "proposal: rows whose evidence is dominated by the faulty sensor "
            "are flagged and down-ranked for review. Original scores preserved; "
            "this is not model rescoring."
        ),
    },
    {
        "scenario_id": "healthy_only_proxy",
        "scenario_type": "healthy_only_proxy",
        "granularity": "window",
        "mutates_original_scores": False,
        "is_interpretive": True,
        "description": (
            "Drift windows dominated by faulty/quarantined sensors are "
            "down-ranked; residual healthy-sensor drift is preserved. Read from "
            "the drift run's raw-vs-healthy-only comparison — a labeled proxy, "
            "never a PCA/Mahalanobis recomputation."
        ),
    },
    {
        "scenario_id": "candidate_reference_needed",
        "scenario_type": "reference_candidate_diagnostic",
        "granularity": "diagnostic",
        "mutates_original_scores": False,
        "is_interpretive": True,
        "description": (
            "Decides whether residual healthy-only drift is large enough to "
            "recommend DESIGNING a Reference v2. No training; decision-support "
            "only."
        ),
    },
]


def scenario_definitions() -> pd.DataFrame:
    """The four-scenario catalogue as a table."""
    return pd.DataFrame(_SCENARIOS, columns=SCENARIO_DEFINITION_COLUMNS)
