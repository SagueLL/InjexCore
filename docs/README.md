# InjexCore Documentation

Documentation is organized by **purpose**, so each new document has an obvious
home as the project grows from the preprocessing layer into modeling, serving,
and operations.

```
docs/
├── README.md          # this index
├── pipeline/          # technical reference for each pipeline stage (how it works)
├── intelligence/      # Intelligence Layer reference docs (behaviour, anomaly, …)
├── project-state/     # versioned MASTER_VERSION snapshots (point-in-time truth)
└── proposals/         # improvement proposals, RFCs, planning ahead of a version
```

## pipeline/ — stage reference docs

One document per pipeline stage, describing its contract, configuration, and
outputs. The data flow is `cleaning → time_series → feature_engineering →
datasets → modeling → serving`.

| Stage | Doc |
|---|---|
| Data cleaning | [pipeline/data_cleaning.md](pipeline/data_cleaning.md) |
| Time-series engineering | [pipeline/time_series_engineering.md](pipeline/time_series_engineering.md) |
| Feature engineering | [pipeline/feature_engineering.md](pipeline/feature_engineering.md) |
| Specialized datasets | [pipeline/specialized_datasets.md](pipeline/specialized_datasets.md) |

> Future stages (anomaly modeling, forecasting, energy, API serving,
> visualization) get a sibling doc here as they are built.

## intelligence/ — Intelligence Layer reference docs

The layer past preprocessing: it characterises normal machine behaviour and
(later) scores deviation from it. One document per component.

| Component | Doc |
|---|---|
| Behaviour Intelligence (profiles + baselines) | [intelligence/behaviour_intelligence.md](intelligence/behaviour_intelligence.md) |
| Correlation Intelligence (per-profile relationships + shift diagnostics) | [intelligence/correlation_intelligence.md](intelligence/correlation_intelligence.md) |
| PCA Intelligence (per-profile multivariate structure, T²/Q scoring) | [intelligence/pca_intelligence.md](intelligence/pca_intelligence.md) |
| Anomaly Intelligence v1 (four explainable detectors + severity) | [intelligence/anomaly_intelligence.md](intelligence/anomaly_intelligence.md) |

## project-state/ — versioned snapshots

Authoritative, point-in-time consolidations produced by the
`master-version-agent`. Each `MASTER_VERSION_vN` diffs against the prior one and
never rewrites the source-of-truth reference docs.

| Version | Doc |
|---|---|
| v1 (preprocessing layer baseline) | [project-state/MASTER_VERSION_v1.md](project-state/MASTER_VERSION_v1.md) |

## proposals/ — planning & RFCs

Forward-looking, severity-ranked improvement proposals reviewed ahead of a
version transition. Not authoritative state; they record what *should* change.

| Scope | Doc |
|---|---|
| v1 → v2 transition | [proposals/IMPROVEMENT_PROPOSALS_v1.md](proposals/IMPROVEMENT_PROPOSALS_v1.md) |

## Where new docs go

| If the document is… | Put it in… | Naming |
|---|---|---|
| A reference for how a pipeline stage / component works | `pipeline/` | `lower_snake_case.md` |
| A reference for an Intelligence Layer component | `intelligence/` | `lower_snake_case.md` |
| A point-in-time project-state snapshot | `project-state/` | `MASTER_VERSION_vN.md` |
| A proposal, RFC, or pre-version plan | `proposals/` | `IMPROVEMENT_PROPOSALS_vN.md` / `RFC_<topic>.md` |

Candidate folders to add when the need is real (avoid empty placeholders):
`architecture/` for system-design docs and ADRs, `operations/` for
deployment/runbook docs, `api/` for the serving contract.
