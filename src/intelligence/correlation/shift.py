"""Train-vs-validation correlation-shift diagnostics.

Recomputes Pearson on the *validation* rows for every pair in the fitted
training reference and reports the absolute delta. This is a diagnostic of
relationship stability — pairs that behave differently out-of-window are
surfaced as AWARE findings, never as operational alerts (alerting belongs
to Anomaly Intelligence, with thresholds of its own).
"""

from __future__ import annotations

import pandas as pd

from src.intelligence._common.policy import GLOBAL_PROFILE
from src.intelligence._common.reporting import Finding, Severity
from src.intelligence.correlation.policy import CorrelationPolicy

CHECK = "correlation_shift"

_SHIFT_COLUMNS = [
    "profile",
    "feature_a",
    "feature_b",
    "pearson_train",
    "pearson_validation",
    "abs_delta",
    "n_valid_train",
    "n_valid_validation",
]


def diagnose(
    df: pd.DataFrame,
    labels: pd.Series,
    policy: CorrelationPolicy,
    train_correlations: pd.DataFrame,
    *,
    train_mask: pd.Series,
) -> tuple[pd.DataFrame, list[Finding]]:
    """Compare validation-window correlations against the training reference."""
    if not policy.shift.enabled or train_correlations.empty:
        return pd.DataFrame(columns=_SHIFT_COLUMNS), []

    min_periods = policy.thresholds.min_valid_observations
    val_df = df.loc[~train_mask]
    val_labels = labels.loc[~train_mask]

    rows: list[dict[str, object]] = []
    for profile, group in train_correlations.groupby("profile", sort=True):
        sub = (
            val_df
            if profile == GLOBAL_PROFILE
            else val_df.loc[val_labels == str(profile)]
        )
        features = sorted(set(group["feature_a"]) | set(group["feature_b"]))
        X = sub[features].astype(float)
        pearson_val = X.corr(min_periods=min_periods)
        notna = X.notna().astype(int)
        counts = notna.T @ notna

        for rec in group.itertuples(index=False):
            rows.append(
                {
                    "profile": str(profile),
                    "feature_a": rec.feature_a,
                    "feature_b": rec.feature_b,
                    "pearson_train": float(rec.pearson),
                    "pearson_validation": float(
                        pearson_val.loc[rec.feature_a, rec.feature_b]
                    ),
                    "n_valid_train": int(rec.n_valid),
                    "n_valid_validation": int(counts.loc[rec.feature_a, rec.feature_b]),
                }
            )

    shift = pd.DataFrame(rows)
    shift["abs_delta"] = (shift["pearson_validation"] - shift["pearson_train"]).abs()
    shift = shift[_SHIFT_COLUMNS].sort_values(
        "abs_delta", ascending=False, na_position="last"
    )
    shift = shift.reset_index(drop=True)

    findings: list[Finding] = []
    flagged = shift[shift["abs_delta"] >= policy.shift.delta_threshold].head(
        policy.shift.top_k
    )
    for rec in flagged.itertuples(index=False):
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.AWARE,
                finding_type="correlation_shift",
                column=f"{rec.feature_a}~{rec.feature_b}",
                action_taken="diagnostic_only",
                evidence={
                    "profile": rec.profile,
                    "pearson_train": round(rec.pearson_train, 4),
                    "pearson_validation": round(rec.pearson_validation, 4),
                    "abs_delta": round(rec.abs_delta, 4),
                },
            )
        )
    findings.append(
        Finding(
            check=CHECK,
            severity=Severity.NORMAL,
            finding_type="shift_diagnostics_built",
            count=len(shift),
            action_taken="diagnostic_only",
            evidence={
                "n_flagged": int(len(flagged)),
                "delta_threshold": policy.shift.delta_threshold,
            },
        )
    )
    return shift, findings
