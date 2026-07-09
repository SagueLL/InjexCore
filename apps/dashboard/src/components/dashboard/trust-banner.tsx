import { getDashboardMetaSafe } from "@/lib/dashboard/data-access";

import type { DashboardLineageSeverity } from "@/types/dashboard-api";

// Must never be rendered from the root layout. A layout that fetches would throw
// when the API is down, and app/error.tsx is a *child* of the layout — the whole
// page, navigation included, would go blank. Render it inside a page instead.

const SEVERITY_LABEL: Record<DashboardLineageSeverity, string> = {
  ok: "Lineage verified",
  warning: "Lineage verified with warnings",
  invalid: "Lineage validation failed",
};

const SEVERITY_STYLE: Record<DashboardLineageSeverity, string> = {
  ok: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  warning: "bg-amber-50 text-amber-800 ring-amber-600/20",
  invalid: "bg-red-50 text-red-700 ring-red-600/20",
};

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-mono text-xs text-foreground">{value}</dd>
    </div>
  );
}

export async function TrustBanner() {
  const meta = await getDashboardMetaSafe();

  if (!meta) {
    return (
      <div className="rounded-lg border border-dashed bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
        Run identity unavailable — the dashboard API did not answer.
      </div>
    );
  }

  const { lineage } = meta;

  return (
    <section className="space-y-3 rounded-lg border bg-muted/30 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs font-medium text-muted-foreground">
          Read-only technical validation &middot; one pinned canonical run
        </p>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${SEVERITY_STYLE[lineage.severity]}`}
        >
          {SEVERITY_LABEL[lineage.severity]}
        </span>
      </div>

      <dl className="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-3">
        <Field label="Run" value={meta.runId} />
        <Field label="BOM run" value={meta.bomRunId} />
        <Field label="Data generated" value={meta.dataGeneratedAt} />
      </dl>

      {lineage.warnings.length > 0 ? (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer select-none">
            {lineage.warnings.length} lineage warning
            {lineage.warnings.length === 1 ? "" : "s"}
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {lineage.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer select-none">
          How to read this dashboard ({meta.requiredWarnings.length} notices)
        </summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {meta.requiredWarnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}
