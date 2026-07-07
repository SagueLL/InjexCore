import { PageHeader } from "@/components/app/page-header";
import { InsightCard } from "@/components/dashboard/insight-card";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { SectionCard } from "@/components/dashboard/section-card";
import { StatusBadge } from "@/components/dashboard/status-badge";
import { getOverviewData } from "@/lib/dashboard/data-access";

export default async function OverviewPage() {
  const summary = await getOverviewData();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Executive Overview"
        description="High-level operational summary of the analysed industrial period."
      />

      <div className="flex flex-col gap-4 rounded-lg border bg-muted/30 p-4 sm:flex-row sm:items-center sm:justify-between">
        <dl className="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-3">
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Asset</dt>
            <dd className="text-sm font-medium text-foreground">{summary.assetName}</dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Dataset</dt>
            <dd className="text-sm font-medium text-foreground">{summary.datasetName}</dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Analysed period</dt>
            <dd className="text-sm font-medium text-foreground">
              {summary.periodStart} to {summary.periodEnd}
            </dd>
          </div>
        </dl>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Operational status</span>
          <StatusBadge className="text-xs" status={summary.operationalStatus} />
        </div>
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Key indicators</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          {summary.kpis.map((kpi) => (
            <KpiCard
              key={kpi.label}
              title={kpi.label}
              value={kpi.value}
              description={kpi.description}
              helperText={kpi.helperText}
            />
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Operational insights</h2>
        <div className="grid gap-4 lg:grid-cols-3">
          {summary.executiveInsights.map((insight) => (
            <InsightCard key={insight.title} {...insight} />
          ))}
        </div>
      </section>

      <SectionCard title="Limitations" description="Scope and honest caveats for this analysis.">
        <ul className="list-disc space-y-2 pl-5 text-sm text-muted-foreground">
          {summary.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </SectionCard>
    </div>
  );
}
