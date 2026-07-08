# InjexCore Documentation

Documentation is organized by **purpose**, so each new document has an obvious
home as the project grows from the preprocessing layer into modeling, serving,
and operations.

```
docs/
├── README.md          # this index
├── architecture/      # end-to-end dataflow + cross-component contracts
├── pipeline/          # technical reference for each pipeline stage (how it works)
├── intelligence/      # Intelligence Layer reference docs (behaviour, anomaly, …)
├── context/           # external operational-context layer docs (BOM, …)
├── dashboard/         # dashboard consumption contract (read-only, lineage-validated)
├── project-state/     # versioned MASTER_VERSION snapshots (point-in-time truth)
└── proposals/         # improvement proposals, RFCs, planning ahead of a version
```

## architecture/ — system-wide dataflow & contracts

| Doc | Covers |
|---|---|
| [architecture/intelligence_dataflow.md](architecture/intelligence_dataflow.md) | End-to-end dataflow, run-versioning + manifest-last + lineage contracts, original-vs-interpretive scores, no-auto-quarantine/refit policy, limitations. |

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
| Sensor Health Intelligence v1 (instrumentation-anomaly rules + quarantine recommendations) | [intelligence/sensor_health_intelligence.md](intelligence/sensor_health_intelligence.md) |
| Drift Intelligence v1 (windowed drift vs train reference; raw vs healthy-only views) | [intelligence/drift_intelligence.md](intelligence/drift_intelligence.md) |
| Incident Aggregation v1 (events → reviewable incidents + drift-aware forensic addendum) | [intelligence/incident_aggregation.md](intelligence/incident_aggregation.md) |
| Reference Governance v1 (current/candidate references + quarantine proposals, pending review) | [intelligence/reference_governance.md](intelligence/reference_governance.md) |
| Controlled Scoring Experiment v1 (interpretive scenarios + decision report) | [intelligence/controlled_scoring_experiment.md](intelligence/controlled_scoring_experiment.md) |

## context/ — external operational context

Contextual and analytical layers built from external data sources. They
enrich interpretation of the Intelligence-Layer outputs but never modify
model fitting or scoring.

| Component | Doc |
|---|---|
| BOM Operational Context (orders, recipes, signatures, master-aligned timeline) | [context/bom_context.md](context/bom_context.md) |
| Operational Context Overlay (profile + steam + sensor-health + BOM per timestamp) | [context/operational_context.md](context/operational_context.md) |

## dashboard/ — consumption contract

The read-only contract the Technical Validation Dashboard consumes. Pins the
canonical rematerialized chain, enumerates allowed artifacts and forbidden views,
and is enforced by the lineage validator in [`src/dashboard/`](../src/dashboard/).
The dashboard itself is the FastAPI service in [`src/api/`](../src/api/) plus the
Next.js app in [`apps/dashboard/`](../apps/dashboard/).

| Doc | Covers |
|---|---|
| [dashboard/dashboard_data_contract.md](dashboard/dashboard_data_contract.md) | Canonical run pins, allowed artifact groups (purpose/safe/unsafe/warning), forbidden MVP views, required warning copy, read-only / no-approval / no-refit boundaries. |
| [dashboard/dashboard_api_contract.md](dashboard/dashboard_api_contract.md) | The API boundary (contractVersion 1.1): endpoints, `{meta, data}` envelopes, per-view notice sets, backend→UI enum mappings, computed-field rules (`evidenceShare`, day-status ladder), error envelope, calibration pins. |
| [dashboard/running_the_dashboard.md](dashboard/running_the_dashboard.md) | Two-process dev flow: install, start the API, start Next, `DASHBOARD_API_URL`, what `LINEAGE_INVALID` / `ARTIFACT_UNREADABLE` mean, why `lineage.severity == "warning"` is expected, MVP security assumptions, verification commands. |

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
| A reference for an external-context component | `context/` | `lower_snake_case.md` |
| A dashboard / consumption contract | `dashboard/` | `lower_snake_case.md` |
| A point-in-time project-state snapshot | `project-state/` | `MASTER_VERSION_vN.md` |
| A proposal, RFC, or pre-version plan | `proposals/` | `IMPROVEMENT_PROPOSALS_vN.md` / `RFC_<topic>.md` |

Candidate folders to add when the need is real (avoid empty placeholders):
`architecture/` for system-design docs and ADRs, `operations/` for
deployment/runbook docs, `api/` for the serving contract.
