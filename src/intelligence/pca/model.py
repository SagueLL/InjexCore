"""Per-profile scaler + PCA fitting — leakage-safe, skip-and-report.

Each supported profile gets its own pipeline fitted on its training rows
only: per-feature eligibility (missingness, near-constant variance) →
train-median imputation → robust/standard scaling → PCA with the component
count chosen by the explained-variance target. Profiles that cannot support
a sound decomposition are recorded in the skip table with a reason —
``do not silently fit an unreliable model`` is the contract.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import RobustScaler, StandardScaler

from src.intelligence._common.column_groups import ColumnGroups
from src.intelligence._common.features import select_features
from src.intelligence._common.policy import GLOBAL_PROFILE
from src.intelligence._common.reporting import Finding, Severity
from src.intelligence.pca.policy import PcaPolicy

CHECK = "pca"

_SKIPPED_COLUMNS = ["profile", "reason", "n_train", "n_features"]
# Heuristic floor for a stable covariance estimate; below it we still fit
# (the gate is min_samples_per_profile) but flag the ratio.
_SAMPLES_PER_FEATURE = 10


@dataclass(frozen=True)
class ProfilePcaModel:
    """Fitted per-profile pipeline + everything scoring needs."""

    profile: str
    features: list[str]  # post-eligibility, order-fixed
    scaler: RobustScaler | StandardScaler
    pca: PCA
    n_components: int
    explained_variance_ratio: list[float]
    train_medians: pd.Series  # imputation reference (train window)
    n_train: int


@dataclass(frozen=True)
class PcaArtifact:
    """All fitted models + frame-level reports."""

    models: dict[str, ProfilePcaModel]
    loadings: pd.DataFrame  # long-form: profile, component, feature, loading
    explained_variance: pd.DataFrame  # profile, component, evr, cumulative_evr
    skipped: pd.DataFrame  # profile, reason, n_train, n_features
    features: list[str]  # frame-level eligible features (pre profile gating)


def _eligible_profile_features(
    X: pd.DataFrame, policy: PcaPolicy, profile: str, findings: list[Finding]
) -> list[str]:
    """Drop features this profile cannot support (sparse / near-constant)."""
    mp = policy.model
    eligible: list[str] = []
    for feature in X.columns:
        s = X[feature]
        missing_fraction = 1.0 - float(s.notna().mean()) if len(s) else 1.0
        if missing_fraction > mp.max_missing_fraction:
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.AWARE,
                    finding_type="feature_too_sparse",
                    column=feature,
                    action_taken="skip_feature",
                    evidence={
                        "profile": profile,
                        "missing_fraction": round(missing_fraction, 4),
                    },
                )
            )
            continue
        std = float(s.std())
        if not np.isfinite(std) or std < mp.near_constant_std:
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.AWARE,
                    finding_type="feature_zero_variance",
                    column=feature,
                    action_taken="skip_feature",
                    evidence={"profile": profile, "std": std},
                )
            )
            continue
        eligible.append(feature)
    return eligible


def _prepare_matrix(
    X: pd.DataFrame, policy: PcaPolicy
) -> tuple[pd.DataFrame, pd.Series]:
    """Resolve missing values per policy; returns (matrix, train_medians)."""
    medians = X.median()
    if policy.model.missing_policy == "median_impute":
        return X.fillna(medians), medians
    return X.dropna(), medians


def fit_profile(
    X_train: pd.DataFrame, policy: PcaPolicy, profile: str
) -> tuple[ProfilePcaModel | None, list[Finding], str | None]:
    """Fit scaler + PCA for one profile on its training rows.

    Returns ``(model, findings, skip_reason)``; ``model`` is ``None`` when
    the profile is skipped (``skip_reason`` says why).
    """
    mp = policy.model
    findings: list[Finding] = []

    eligible = _eligible_profile_features(X_train, policy, profile, findings)
    if len(eligible) < mp.min_features:
        return None, findings, f"insufficient_features ({len(eligible)})"

    X, medians = _prepare_matrix(X_train[eligible].astype(float), policy)
    if len(X) < max(mp.min_features + 1, len(eligible) + 1):
        # drop_rows can hollow a profile out entirely.
        return None, findings, f"excessive_missingness ({len(X)} usable rows)"

    if len(X) < _SAMPLES_PER_FEATURE * len(eligible):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.AWARE,
                finding_type="low_sample_to_feature_ratio",
                column=profile,
                action_taken="fit_anyway",
                evidence={"n_train": len(X), "n_features": len(eligible)},
            )
        )

    scaler = RobustScaler() if mp.scaler == "robust" else StandardScaler()
    Z = scaler.fit_transform(X)
    if not np.isfinite(Z).all():
        return None, findings, "invalid_scaling (non-finite scaled values)"

    # Full decomposition once to read the EVR curve, then refit at the
    # selected k so the persisted estimator is exactly what scoring uses.
    full = PCA(svd_solver="full", random_state=mp.random_state)
    full.fit(Z)
    cumulative = np.cumsum(full.explained_variance_ratio_)
    k = int(np.searchsorted(cumulative, mp.explained_variance_target) + 1)
    k = min(k, len(cumulative))
    if mp.max_components is not None:
        k = min(k, mp.max_components)

    pca = PCA(n_components=k, svd_solver="full", random_state=mp.random_state)
    pca.fit(Z)
    if not np.isfinite(pca.components_).all():
        return None, findings, "invalid_covariance (non-finite components)"

    model = ProfilePcaModel(
        profile=profile,
        features=eligible,
        scaler=scaler,
        pca=pca,
        n_components=k,
        explained_variance_ratio=[float(v) for v in pca.explained_variance_ratio_],
        train_medians=medians,
        n_train=int(len(X)),
    )
    findings.append(
        Finding(
            check=CHECK,
            severity=Severity.NORMAL,
            finding_type="profile_pca_fit",
            column=profile,
            action_taken="fit_on_train",
            evidence={
                "n_train": len(X),
                "n_features": len(eligible),
                "n_components": k,
                "cumulative_evr": round(float(cumulative[k - 1]), 4),
            },
        )
    )
    return model, findings, None


def fit(
    df: pd.DataFrame,
    labels: pd.Series,
    policy: PcaPolicy,
    groups: ColumnGroups,
    *,
    train_mask: pd.Series,
) -> tuple[PcaArtifact, list[Finding]]:
    """Fit one PCA pipeline per supported profile on the training window."""
    features, findings = select_features(df, policy.features, groups, check=CHECK)
    gate = policy.profiles

    models: dict[str, ProfilePcaModel] = {}
    skipped_rows: list[dict[str, object]] = []

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
            if len(sub) < gate.min_samples_per_profile:
                reason = f"insufficient_rows ({len(sub)})"
                skipped_rows.append(
                    {
                        "profile": profile,
                        "reason": reason,
                        "n_train": len(sub),
                        "n_features": len(features),
                    }
                )
                findings.append(
                    Finding(
                        check=CHECK,
                        severity=Severity.IMPORTANT,
                        finding_type="profile_under_min_samples",
                        column=profile,
                        count=len(sub),
                        action_taken="skip_profile",
                        evidence={"min_samples": gate.min_samples_per_profile},
                    )
                )
                continue

            model, prof_findings, skip_reason = fit_profile(sub, policy, profile)
            findings.extend(prof_findings)
            if model is None:
                skipped_rows.append(
                    {
                        "profile": profile,
                        "reason": skip_reason,
                        "n_train": len(sub),
                        "n_features": len(features),
                    }
                )
                findings.append(
                    Finding(
                        check=CHECK,
                        severity=Severity.IMPORTANT,
                        finding_type="profile_pca_skipped",
                        column=profile,
                        action_taken="skip_profile",
                        evidence={"reason": skip_reason},
                    )
                )
                continue
            models[profile] = model

    loadings = _loadings_table(models)
    explained = _explained_variance_table(models)
    skipped = pd.DataFrame(skipped_rows, columns=_SKIPPED_COLUMNS)
    artifact = PcaArtifact(
        models=models,
        loadings=loadings,
        explained_variance=explained,
        skipped=skipped,
        features=features,
    )
    return artifact, findings


def _loadings_table(models: dict[str, ProfilePcaModel]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for profile, model in models.items():
        for j in range(model.n_components):
            for i, feature in enumerate(model.features):
                rows.append(
                    {
                        "profile": profile,
                        "component": f"pc_{j + 1}",
                        "feature": feature,
                        "loading": float(model.pca.components_[j, i]),
                    }
                )
    return pd.DataFrame(rows, columns=["profile", "component", "feature", "loading"])


def _explained_variance_table(models: dict[str, ProfilePcaModel]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for profile, model in models.items():
        cumulative = 0.0
        for j, evr in enumerate(model.explained_variance_ratio):
            cumulative += evr
            rows.append(
                {
                    "profile": profile,
                    "component": f"pc_{j + 1}",
                    "evr": evr,
                    "cumulative_evr": cumulative,
                }
            )
    return pd.DataFrame(rows, columns=["profile", "component", "evr", "cumulative_evr"])
