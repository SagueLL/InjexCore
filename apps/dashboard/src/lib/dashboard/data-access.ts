// Centralized data access for the read-only dashboard API. Server-side only:
// DASHBOARD_API_URL has no NEXT_PUBLIC_ prefix, so it never reaches the
// client bundle — call these functions from Server Components, not client
// code. Errors are never masked with demo data: backend error envelopes
// become DashboardApiError, and network failures propagate as-is.

import type {
  DashboardApiErrorBody,
  DashboardMetaResponse,
  DashboardViewPayload,
} from "@/types/dashboard-api";
import type { DashboardSummary } from "@/types/dashboard";
import type { OperationalTimeline } from "@/types/timeline";
import type { SensorHealthSummary } from "@/types/sensor-health";
import type { DriftAnomalySummary } from "@/types/drift-anomaly";
import type { IncidentsSummary } from "@/types/incidents";

const API_BASE_URL = process.env.DASHBOARD_API_URL ?? "http://127.0.0.1:8000";

export class DashboardApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "DashboardApiError";
    this.status = status;
    this.code = code;
  }
}

function isDashboardApiErrorBody(body: unknown): body is DashboardApiErrorBody {
  if (typeof body !== "object" || body === null || !("error" in body)) {
    return false;
  }
  const error = (body as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
}

export async function fetchDashboardApi<T>(path: string): Promise<T> {
  // no-store: always fetch per request — the Next 16 default would freeze
  // the response into the static prerender at build time.
  const response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // Non-JSON error body (e.g. a proxy error page) — fall through.
    }
    if (isDashboardApiErrorBody(body)) {
      throw new DashboardApiError(
        response.status,
        body.error.code,
        body.error.message,
      );
    }
    throw new DashboardApiError(
      response.status,
      "UNKNOWN",
      response.statusText || `Dashboard API request failed (${response.status})`,
    );
  }
  return (await response.json()) as T;
}

export async function getDashboardMeta(): Promise<DashboardMetaResponse> {
  return fetchDashboardApi<DashboardMetaResponse>("/api/v1/dashboard/meta");
}

export async function getOverviewPayload(): Promise<
  DashboardViewPayload<DashboardSummary>
> {
  return fetchDashboardApi<DashboardViewPayload<DashboardSummary>>(
    "/api/v1/dashboard/overview",
  );
}

export async function getTimelinePayload(): Promise<
  DashboardViewPayload<OperationalTimeline>
> {
  return fetchDashboardApi<DashboardViewPayload<OperationalTimeline>>(
    "/api/v1/dashboard/timeline",
  );
}

export async function getSensorHealthPayload(): Promise<
  DashboardViewPayload<SensorHealthSummary>
> {
  return fetchDashboardApi<DashboardViewPayload<SensorHealthSummary>>(
    "/api/v1/dashboard/sensor-health",
  );
}

export async function getDriftAnomalyPayload(): Promise<
  DashboardViewPayload<DriftAnomalySummary>
> {
  return fetchDashboardApi<DashboardViewPayload<DriftAnomalySummary>>(
    "/api/v1/dashboard/drift-anomaly",
  );
}

export async function getIncidentsPayload(): Promise<
  DashboardViewPayload<IncidentsSummary>
> {
  return fetchDashboardApi<DashboardViewPayload<IncidentsSummary>>(
    "/api/v1/dashboard/incidents",
  );
}

export async function getOverviewData(): Promise<DashboardSummary> {
  return (await getOverviewPayload()).data;
}

export async function getTimelineData(): Promise<OperationalTimeline> {
  return (await getTimelinePayload()).data;
}

export async function getSensorHealthData(): Promise<SensorHealthSummary> {
  return (await getSensorHealthPayload()).data;
}

export async function getDriftAnomalyData(): Promise<DriftAnomalySummary> {
  return (await getDriftAnomalyPayload()).data;
}

export async function getIncidentsData(): Promise<IncidentsSummary> {
  return (await getIncidentsPayload()).data;
}
