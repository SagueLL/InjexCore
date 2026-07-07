// Dashboard API wire types shared by every backend endpoint (see
// docs/dashboard/dashboard_api_contract.md §2). View endpoints wrap the
// existing view summary types in a { meta, data } envelope; /dashboard/meta
// is deliberately flat. Produced by the read-only FastAPI service, consumed
// by the data access layer in @/lib/dashboard/data-access.

export interface DashboardNotice {
  key: string;
  text: string;
}

export interface DashboardViewMeta {
  contractVersion: string;
  runId: string;
  bomRunId: string;
  dataGeneratedAt: string;
  notices: DashboardNotice[];
}

export interface DashboardViewPayload<TData> {
  meta: DashboardViewMeta;
  data: TData;
}

export type DashboardLineageSeverity = "ok" | "warning" | "invalid";

export interface DashboardLineage {
  isValid: boolean;
  canonicalMatch: boolean;
  severity: DashboardLineageSeverity;
  warnings: string[];
}

export interface DashboardMetaResponse {
  contractVersion: string;
  runId: string;
  bomRunId: string;
  dataGeneratedAt: string;
  trainWindowEnd: string;
  lineage: DashboardLineage;
  requiredWarnings: string[];
}

export interface DashboardApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}
