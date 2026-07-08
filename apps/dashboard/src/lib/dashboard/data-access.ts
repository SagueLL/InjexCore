// Centralized data access for the read-only dashboard API. Server-side only:
// DASHBOARD_API_URL has no NEXT_PUBLIC_ prefix, so it never reaches the
// client bundle — call these functions from Server Components, not client
// code. Errors are never masked with demo data: backend error envelopes and
// unreachable-API failures alike become DashboardApiError and propagate.
//
// Only enveloped getters are exported. A `.data`-only convenience getter would
// silently discard `meta.notices`, and rendering those notices is part of the
// API contract, not a frontend courtesy (data contract §5.4).

import { unstable_rethrow } from "next/navigation";

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

  constructor(
    status: number,
    code: string,
    message: string,
    options?: ErrorOptions,
  ) {
    super(message, options);
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
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  } catch (cause) {
    // Next signals control flow (dynamic-rendering bailout, redirect, notFound)
    // by throwing internal errors from fetch. Swallowing them breaks the build:
    // a `no-store` fetch throws DYNAMIC_SERVER_USAGE during prerender so the
    // route opts into dynamic rendering. Hand those straight back to Next.
    unstable_rethrow(cause);
    // A stopped backend is the most likely demo failure. Surface it as a typed
    // error with a code, not a bare `TypeError: fetch failed`. Still no fallback
    // data: the caller fails, it does not degrade to fixtures.
    throw new DashboardApiError(
      0,
      "API_UNREACHABLE",
      `The dashboard API did not answer at ${API_BASE_URL}. Is it running?`,
      { cause },
    );
  }
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

// /meta is the gate banner source and answers 200 even when lineage is invalid,
// so the only reason it fails is an unreachable API. The trust banner degrades to
// "run identity unavailable" rather than taking a page down with it — the page's
// own data fetch will surface the real failure.
export async function getDashboardMetaSafe(): Promise<DashboardMetaResponse | null> {
  try {
    return await getDashboardMeta();
  } catch (error) {
    if (error instanceof DashboardApiError) {
      console.error(`[dashboard] /meta unavailable: ${error.code}`, error.message);
      return null;
    }
    throw error;
  }
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

