"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";

// Error boundaries must be Client Components. Next 16 passes `unstable_retry`
// (preferred over `reset`: it re-fetches the segment inside a Transition).
//
// IMPORTANT: in a production build Next redacts errors thrown in Server
// Components before they reach the client — `error.message` becomes a generic
// string and only `error.digest` correlates to the server log. So the API's
// error code (LINEAGE_INVALID / ARTIFACT_UNREADABLE / API_UNREACHABLE) is
// visible below only under `npm run dev`. That is expected, not a bug: read the
// uvicorn log, or curl the endpoint, for the real code in production.
export default function DashboardError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error("[dashboard] view failed to render", error);
  }, [error]);

  return (
    <div className="space-y-6">
      <header className="border-b border-border/70 pb-6">
        <div className="mb-4 h-1 w-16 rounded-full bg-red-500" />
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">
          Dashboard data unavailable
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
          The dashboard could not load data from the API. Nothing is shown rather
          than something unverified: this dashboard never falls back to demo values.
        </p>
      </header>

      <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
        <div className="space-y-2 text-sm text-muted-foreground">
          <p className="font-medium text-foreground">Most likely causes</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>
              The API is not running. Start it with{" "}
              <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                python -m uvicorn src.api.main:app --port 8000
              </code>
              .
            </li>
            <li>
              The pinned canonical run failed lineage validation, so the API is
              refusing to serve data (fail-closed, <code>LINEAGE_INVALID</code>).
            </li>
            <li>
              A required artifact of the pinned run could not be read (
              <code>ARTIFACT_UNREADABLE</code>).
            </li>
          </ul>
        </div>

        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer select-none">
            Diagnostic detail
          </summary>
          <div className="mt-2 space-y-1">
            <p className="font-mono break-words">{error.message}</p>
            {error.digest ? (
              <p className="font-mono">digest: {error.digest}</p>
            ) : null}
            <p className="italic">
              Production builds redact server-side error messages; use the digest
              to find the matching entry in the API log.
            </p>
          </div>
        </details>

        <Button onClick={() => unstable_retry()} variant="outline" size="sm">
          Try again
        </Button>
      </div>
    </div>
  );
}
