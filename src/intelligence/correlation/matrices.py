"""Per-profile correlation matrices — fitted on the training window only.

For every supported profile, computes Pearson and Spearman correlations plus
pairwise valid-observation counts over the eligible features, on the
leakage-safe training rows. Features that are too sparse or near-constant
*within that profile's training rows* are excluded with a recorded reason —
a sensor can be informative while producing and frozen while stopped.

The result is one long-form table keyed by ``(profile, feature_a,
feature_b)`` — the fitted correlation reference that the shift diagnostics
compare validation data against.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.intelligence._common.column_groups import ColumnGroups
from src.intelligence._common.features import select_features
from src.intelligence._common.policy import GLOBAL_PROFILE
from src.intelligence._common.reporting import Finding, Severity
from src.intelligence.correlation.policy import CorrelationPolicy

CHECK = "correlation"

_CORR_COLUMNS = ["profile", "feature_a", "feature_b", "pearson", "spearman", "n_valid"]
_EXCLUDED_COLUMNS = ["profile", "feature", "reason", "detail"]


@dataclass(frozen=True)
class CorrelationArtifact:
    """Fitted correlation reference + eligibility bookkeeping."""

    correlations: pd.DataFrame  # long-form upper triangle, see _CORR_COLUMNS
    excluded: pd.DataFrame  # per-(profile, feature) exclusion reasons
    features: list[str]  # frame-level eligible features (pre profile gating)
    profiles_fitted: list[str]
    profiles_skipped: dict[str, str]  # profile -> reason


def _profile_eligible_features(
    sub: pd.DataFrame,
    features: list[str],
    policy: CorrelationPolicy,
    profile: str,
    excluded_rows: list[dict[str, object]],
) -> list[str]:
    """Per-profile eligibility: drop too-sparse / near-constant features."""
    th = policy.thresholds
    eligible: list[str] = []
    for feature in features:
        s = sub[feature]
        missing_fraction = 1.0 - float(s.notna().mean()) if len(s) else 1.0
        if missing_fraction > th.max_missing_fraction:
            excluded_rows.append(
                {
                    "profile": profile,
                    "feature": feature,
                    "reason": "too_sparse",
                    "detail": f"missing_fraction={missing_fraction:.4f}",
                }
            )
            continue
        std = float(s.std())
        if not np.isfinite(std) or std < th.near_constant_std:
            excluded_rows.append(
                {
                    "profile": profile,
                    "feature": feature,
                    "reason": "near_constant",
                    "detail": f"std={std:.3e}",
                }
            )
            continue
        eligible.append(feature)
    return eligible


def _pair_rows(
    X: pd.DataFrame, profile: str, min_periods: int
) -> list[dict[str, object]]:
    """Melt the upper triangle of the Pearson/Spearman/count matrices."""
    features = list(X.columns)
    pearson = X.corr(min_periods=min_periods)
    spearman = X.corr(method="spearman", min_periods=min_periods)
    notna = X.notna().astype(int)
    counts = notna.T @ notna

    rows: list[dict[str, object]] = []
    for i, a in enumerate(features):
        for j in range(i + 1, len(features)):
            b = features[j]
            rows.append(
                {
                    "profile": profile,
                    "feature_a": a,
                    "feature_b": b,
                    "pearson": float(pearson.iat[i, j]),
                    "spearman": float(spearman.iat[i, j]),
                    "n_valid": int(counts.iat[i, j]),
                }
            )
    return rows


def fit(
    df: pd.DataFrame,
    labels: pd.Series,
    policy: CorrelationPolicy,
    groups: ColumnGroups,
    *,
    train_mask: pd.Series,
) -> tuple[CorrelationArtifact, list[Finding]]:
    """Compute the per-profile correlation reference on the training window."""
    features, findings = select_features(df, policy.features, groups, check=CHECK)
    gate = policy.profiles

    corr_rows: list[dict[str, object]] = []
    excluded_rows: list[dict[str, object]] = []
    fitted: list[str] = []
    skipped: dict[str, str] = {}

    if features:
        train_df = df.loc[train_mask, features]
        train_labels = labels.loc[train_mask]

        profile_names = sorted(
            str(p)
            for p in train_labels.unique()
            if pd.notna(p) and str(p) not in set(gate.exclude_profiles)
        )
        if gate.global_fallback:
            profile_names.append(GLOBAL_PROFILE)

        for profile in profile_names:
            sub = (
                train_df
                if profile == GLOBAL_PROFILE
                else train_df.loc[train_labels == profile]
            )
            n_profile = len(sub)
            if n_profile < gate.min_samples_per_profile:
                skipped[profile] = f"under_min_samples ({n_profile})"
                findings.append(
                    Finding(
                        check=CHECK,
                        severity=Severity.IMPORTANT,
                        finding_type="profile_under_min_samples",
                        column=profile,
                        count=n_profile,
                        action_taken="skip_profile",
                        evidence={"min_samples": gate.min_samples_per_profile},
                    )
                )
                continue

            eligible = _profile_eligible_features(
                sub, features, policy, profile, excluded_rows
            )
            if len(eligible) < 2:
                skipped[profile] = f"insufficient_features ({len(eligible)})"
                findings.append(
                    Finding(
                        check=CHECK,
                        severity=Severity.IMPORTANT,
                        finding_type="profile_insufficient_features",
                        column=profile,
                        count=len(eligible),
                        action_taken="skip_profile",
                        evidence={"n_train": n_profile},
                    )
                )
                continue

            rows = _pair_rows(
                sub[eligible].astype(float),
                profile,
                policy.thresholds.min_valid_observations,
            )
            corr_rows.extend(rows)
            fitted.append(profile)
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.NORMAL,
                    finding_type="profile_correlations_fit",
                    column=profile,
                    count=len(rows),
                    action_taken="fit_on_train",
                    evidence={"n_train": n_profile, "n_features": len(eligible)},
                )
            )

    correlations = pd.DataFrame(corr_rows, columns=_CORR_COLUMNS)
    excluded = pd.DataFrame(excluded_rows, columns=_EXCLUDED_COLUMNS)
    artifact = CorrelationArtifact(
        correlations=correlations,
        excluded=excluded,
        features=features,
        profiles_fitted=fitted,
        profiles_skipped=skipped,
    )
    return artifact, findings
