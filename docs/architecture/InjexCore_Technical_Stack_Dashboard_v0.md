# InjexCore Technical Stack - Dashboard v0

**Version:** v0.1  
**Date:** 23 June 2026  
**Scope:** Backend current stack + Dashboard v0 frontend stack

## 1. Purpose

This document records the technical stack currently used or planned for InjexCore. It is intended to keep backend, frontend, dashboard data contracts, UI tooling, and MCP integrations aligned during the Dashboard v0 phase.

Dashboard v0 should remain simple, stable, demo-ready, and aligned with the project roadmap: translating technical intelligence outputs into an understandable industrial dashboard experience.

## 2. Current backend stack

| Layer | Technology / Practice | Purpose in InjexCore | Status |
|---|---|---|---|
| Language | Python | Core backend, data processing, Intelligence Layer, pipeline execution, reports. | Active |
| Data processing | pandas, NumPy | Tabular processing, transformations, feature engineering, time-window logic, summaries. | Active |
| Storage / artifacts | Parquet, JSON, Markdown reports | Run-versioned outputs, manifests, review reports, dashboard-consumable artifacts. | Active |
| Machine learning | scikit-learn family: PCA, Isolation Forest, LOF, One-Class SVM, correlation analysis | Anomaly v1, PCA residuals, correlation, drift, sensor health, operational intelligence. | Active |
| Project structure | src/ modular packages | Separation between preprocessing, intelligence, context/BOM, human decisions, reporting, and validation logic. | Active |
| Quality gates | pytest, ruff, mypy | Regression safety, linting, type checking, maintainability, CI-ready validation. | Active |
| Execution model | Python module entrypoints / CLI-style runs | Repeatable, lineage-aware generation of intelligence artifacts. | Active |
| Documentation | Markdown reports, manifests, decision summaries, master versions | Traceability, project continuity, technical/commercial documentation. | Active |

## 3. Dashboard backend/data boundary

The dashboard must not consume raw pipeline artifacts directly. A dashboard data-contract layer should sit between Intelligence Layer outputs and frontend views.

| Area | Decision | Rationale |
|---|---|---|
| Contract format | JSON payloads + JSON Schema | Stable, versioned, frontend-friendly structure for dashboard consumption. |
| Fixtures | Static fixtures first | Allows UI development before API integration and supports repeatable demos. |
| Future API | API integration later | Prevents premature backend/API complexity during Dashboard v0. |
| Agent ownership | dashboard-data-contract-agent | Defines payload contracts, validates schemas, maps intelligence outputs to UI concepts, and generates fixtures. |

## 4. Frontend stack for Dashboard v0

| Technology | Role | Why we chose it | Status |
|---|---|---|---|
| Next.js + React | Frontend application framework | Scalable product-style dashboard foundation with routing, layouts, future APIs, and deployment flexibility. | Selected |
| TypeScript | Type-safe frontend development | Keeps dashboard contracts, fixtures, and UI components aligned with fewer runtime errors. | Selected |
| Tailwind CSS | Styling system | Fast, consistent, responsive styling aligned with shadcn/ui and future InjexCore visual identity. | Selected |
| shadcn/ui | UI component foundation | Reusable, professional components without locking the project into a heavy template or closed design system. | Selected |
| Recharts | Charting library | Composable React charts suitable for time-series, anomaly scores, drift trends, sensor evolution, and overview charts. | Selected |
| JSON Schema | Contract validation layer | Defines and validates expected JSON structures between backend intelligence and dashboard UI. | Selected |

## 5. Recommended frontend repository structure

```txt
frontend/
  app/
    dashboard/
      page.tsx
    dashboard/sensors/
      page.tsx
    dashboard/incidents/
      page.tsx
    dashboard/drift/
      page.tsx

  components/
    dashboard/
      overview-card.tsx
      sensor-health-card.tsx
      incident-timeline.tsx
      drift-chart.tsx
      anomaly-table.tsx
      severity-badge.tsx

    ui/
      ...shadcn components

  contracts/
    dashboard/
      overview.schema.json
      sensor-health.schema.json
      incident-timeline.schema.json
      drift-events.schema.json

  fixtures/
    dashboard/
      overview.fixture.json
      sensor-health.fixture.json
      incident-timeline.fixture.json
      drift-events.fixture.json

  lib/
    dashboard/
      mappers.ts
      validators.ts
      types.ts
```

## 6. MCP stack for Dashboard v0

| MCP | Priority | Purpose | Expected use |
|---|---|---|---|
| shadcn/ui MCP | Install first | Browse, search, and install UI components from shadcn-compatible registries. | Component selection, cards, tables, tabs, badges, alerts, skeletons, layout blocks. |
| Chrome DevTools MCP | Install first | Inspect and debug the dashboard in a real Chrome browser context. | Console errors, layout inspection, responsive checks, performance/Lighthouse, chart rendering validation. |
| Playwright MCP | Install first / shortly after | Browser automation through structured accessibility snapshots. | Navigation, filters, smoke tests, incident detail flow, empty/loading/error states, QA agent workflows. |

## 7. Agent alignment

| Agent | Stack responsibility |
|---|---|
| dashboard-data-contract-agent | Defines dashboard contracts, schemas, fixtures, validation, and Intelligence Layer to UI mapping. |
| dashboard-ui-agent | Designs views, layouts, component composition, UI states, and demo-readiness. |
| qa-agent | Uses Playwright/browser checks to validate flows and prevent regressions. |
| code-reviewer-agent | Reviews frontend implementation quality, maintainability, and architecture. |
| security-reviewer-agent | Reviews exposed data, config risks, dependencies, and browser/MCP safety. |
| documentation-architect-agent | Documents the dashboard architecture and keeps project docs consistent. |

## 8. Explicit non-decisions for v0

- No Power BI as primary product UI. It can remain useful for quick reporting or comparison, but not as the core InjexCore dashboard.
- No Streamlit/Dash as primary product UI. They are useful for data-science prototypes, but less aligned with a product-grade SaaS dashboard direction.
- No Grafana/Metabase as main Dashboard v0 UI. They may be useful later for internal observability or BI, but not as the customer-facing InjexCore interface.
- No premature real-time architecture. Dashboard v0 should start with static fixtures or exported payloads, then evolve toward API integration.

## 9. Next implementation steps

1. Create or confirm `frontend/` workspace.
2. Initialize Next.js with TypeScript and Tailwind CSS.
3. Initialize shadcn/ui and add the first required components.
4. Create `contracts/dashboard/` and `fixtures/dashboard/`.
5. Generate first dashboard fixtures from current Intelligence Layer outputs.
6. Build Dashboard v0 skeleton: overview, sensor health, timeline, drift/anomalies, incident detail.
7. Install and validate shadcn/ui MCP, Chrome DevTools MCP, and Playwright MCP.

## 10. Source references

- Project roadmap: InjexCore Roadmap de Pivotaje — junio-agosto 2026.
- Next.js documentation: https://nextjs.org/docs
- Tailwind CSS / Next.js installation guide: https://tailwindcss.com/docs/guides/nextjs
- shadcn/ui MCP documentation: https://ui.shadcn.com/docs/mcp
- Recharts documentation: https://recharts.org/
- JSON Schema documentation: https://json-schema.org/docs
- Chrome DevTools for agents: https://developer.chrome.com/docs/devtools/agents
- Chrome DevTools MCP repository/security note: https://github.com/ChromeDevTools/chrome-devtools-mcp
- Playwright MCP documentation: https://playwright.dev/docs/getting-started-mcp
