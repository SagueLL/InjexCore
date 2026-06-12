"""Eligible-feature selection shared by Iteration B components.

Mirrors the behaviour stage's sensor selection (semantic-catalogue routing,
explicit opt-in list, exclusions, numeric-only) so every component reasons
over the same feature universe by default. Per-profile eligibility (sparsity,
near-constant variance) stays inside each component — it depends on the
profile's training rows, not on the frame alone.
"""

from __future__ import annotations

import pandas as pd
from pandas.api import types as pdtypes

from src.intelligence._common.column_groups import ColumnGroups
from src.intelligence._common.policy import FeatureSelectionPolicy
from src.intelligence._common.reporting import Finding, Severity


def select_features(
    df: pd.DataFrame,
    policy: FeatureSelectionPolicy,
    groups: ColumnGroups,
    *,
    check: str,
) -> tuple[list[str], list[Finding]]:
    """Resolve the eligible feature set: present, allowed and numeric."""
    if policy.source == "process_sensor":
        candidates = [c for c in groups.process if c in df.columns]
    else:
        candidates = [c for c in policy.include_columns if c in df.columns]
    candidates = [c for c in candidates if c not in set(policy.exclude_columns)]

    findings: list[Finding] = []
    numeric: list[str] = []
    for c in candidates:
        if pdtypes.is_numeric_dtype(df[c]):
            numeric.append(c)
        else:
            findings.append(
                Finding(
                    check=check,
                    severity=Severity.AWARE,
                    finding_type="feature_not_numeric",
                    column=c,
                    action_taken="skip_feature",
                )
            )
    if not numeric:
        findings.append(
            Finding(
                check=check,
                severity=Severity.IMPORTANT,
                finding_type="no_features_selected",
                action_taken="skip_component",
                evidence={"source": policy.source},
            )
        )
    return numeric, findings
