"""Profile-quality diagnostics.

Computes the artifacts that let a human verify the derived operational
profiles correspond to meaningful machine behaviour before any higher-level
intelligence is built on top:

* **distribution** — rows and share per profile.
* **durations**    — contiguous-segment run-length statistics per profile
                     (how long the machine typically stays in each regime).
* **transitions**  — profile -> profile transition counts.
* **coverage**     — labelled share, train/val split sizes, unknown rows.
* **unsupported**  — the requested regimes that the signals cannot support.

Diagnostics are computed over the **full** labelled dataset (labels were
assigned to every row using train-fitted edges); only the *fitting* of
baselines is train-only.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.intelligence.behaviour.policy import BehaviourPolicy
from src.intelligence.behaviour.profiles import CANONICAL_ORDER, UNKNOWN
from src.intelligence.behaviour.reporting import Finding, Severity

CHECK = "validation"


@dataclass(frozen=True)
class ValidationArtifact:
    distribution: pd.DataFrame  # profile, n_rows, pct
    durations: pd.DataFrame  # profile, n_segments, mean_len, median_len, max_len
    transitions: pd.DataFrame  # from_profile, to_profile, count
    coverage: dict
    unsupported: list[str]


def _canonical_key(profiles: pd.Series) -> pd.Series:
    """Sort key placing known profiles in canonical order, others last."""
    order = {name: i for i, name in enumerate(CANONICAL_ORDER)}
    return profiles.map(lambda p: order.get(p, len(order)))


def _distribution(labels: pd.Series) -> pd.DataFrame:
    vc = labels.value_counts(dropna=False)
    dist = pd.DataFrame({"profile": vc.index.astype(str), "n_rows": vc.to_numpy()})
    n = len(labels)
    dist["pct"] = (dist["n_rows"] / n).round(6) if n else 0.0
    dist = dist.sort_values("profile", key=_canonical_key).reset_index(drop=True)
    return dist


def _durations(labels: pd.Series) -> pd.DataFrame:
    seg_id = (labels != labels.shift()).cumsum()
    seg = pd.DataFrame(
        {"label": labels.astype(str).to_numpy(), "seg": seg_id.to_numpy()}
    )
    seg_len = seg.groupby("seg").agg(label=("label", "first"), length=("label", "size"))
    dur = (
        seg_len.groupby("label")["length"]
        .agg(n_segments="count", mean_len="mean", median_len="median", max_len="max")
        .reset_index()
        .rename(columns={"label": "profile"})
    )
    dur["mean_len"] = dur["mean_len"].round(2)
    dur = dur.sort_values("profile", key=_canonical_key).reset_index(drop=True)
    return dur


def _transitions(labels: pd.Series) -> pd.DataFrame:
    frm = labels.astype(str)
    to = labels.astype(str).shift(-1)
    mask = (frm != to) & to.notna()
    trans = pd.DataFrame(
        {"from_profile": frm[mask].to_numpy(), "to_profile": to[mask].to_numpy()}
    )
    if trans.empty:
        return pd.DataFrame(columns=["from_profile", "to_profile", "count"])
    return (
        trans.groupby(["from_profile", "to_profile"])
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )


def build(
    labels: pd.Series,
    policy: BehaviourPolicy,
    *,
    train_mask: pd.Series,
) -> tuple[ValidationArtifact, list[Finding]]:
    """Build profile-quality diagnostics over the full labelled dataset."""
    n_total = int(len(labels))
    n_train = int(train_mask.sum())
    n_unknown = int((labels == UNKNOWN).sum())
    coverage = {
        "n_total": n_total,
        "n_train": n_train,
        "n_val": n_total - n_train,
        "n_unknown": n_unknown,
        "labeled_pct": round((n_total - n_unknown) / n_total, 6) if n_total else 0.0,
        "n_profiles": int(labels.nunique(dropna=False)),
    }

    artifact = ValidationArtifact(
        distribution=_distribution(labels),
        durations=_durations(labels),
        transitions=_transitions(labels),
        coverage=coverage,
        unsupported=list(policy.profiles.unsupported_regimes),
    )

    findings = [
        Finding(
            check=CHECK,
            severity=Severity.NORMAL,
            finding_type="coverage",
            action_taken="none",
            evidence=coverage,
        )
    ]
    if n_unknown:
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.IMPORTANT,
                finding_type="unlabeled_rows",
                count=n_unknown,
                action_taken="none",
                evidence={"pct": round(n_unknown / n_total, 6) if n_total else 0.0},
            )
        )
    return artifact, findings
