import { PageHeader } from "@/components/app/page-header";
import { ChartContainer } from "@/components/charts/chart-container";
import { IncidentsSeverityChart } from "@/components/charts/incidents-severity-chart";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { NoticeStrip } from "@/components/dashboard/notice-strip";
import { SectionCard } from "@/components/dashboard/section-card";
import { StatusBadge } from "@/components/dashboard/status-badge";
import { getIncidentsPayload } from "@/lib/dashboard/data-access";

import type { IncidentStatus } from "@/types/incidents";

function formatIncidentStatus(status: IncidentStatus): string {
  const text = status.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatSignalList(signals: string[]): string {
  return signals.join(", ");
}

export default async function IncidentsPage() {
  // The API order IS the product feature: review-pack priority, then source
  // severity (4 tiers), then start date. Re-sorting by the 3-tier UI severity
  // collapsed that ordering and buried the pack priority.
  const { meta, data: incidentsSummary } = await getIncidentsPayload();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Incidents"
        description="Grouped operational events requiring technical review."
      />

      <NoticeStrip notices={meta.notices} />

      <SectionCard
        title="Analysed context"
        description="Current incident aggregation scope for the historical dataset."
      >
        <dl className="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Asset</dt>
            <dd className="text-sm font-medium text-foreground">
              {incidentsSummary.assetName}
            </dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Dataset</dt>
            <dd className="text-sm font-medium text-foreground">
              {incidentsSummary.datasetName}
            </dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Analysed period</dt>
            <dd className="text-sm font-medium text-foreground">
              {incidentsSummary.periodStart} to {incidentsSummary.periodEnd}
            </dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Mode</dt>
            <dd className="text-sm font-medium text-foreground">
              Historical analysis
            </dd>
          </div>
        </dl>
      </SectionCard>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Summary</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          {incidentsSummary.summaryKpis.map((kpi) => (
            <KpiCard
              key={kpi.label}
              title={kpi.label}
              value={kpi.value}
              description={kpi.description}
            />
          ))}
        </div>
      </section>

      <ChartContainer
        title="Incidents by severity"
        description="Grouped operational review candidates by severity level."
        footer="Severity prioritises technical review and does not represent confirmed failure impact."
      >
        <IncidentsSeverityChart data={incidentsSummary.severityDistribution} />
      </ChartContainer>

      <SectionCard
        title="Incident review candidates"
        description="Grouped evidence windows that should be reviewed with production and operator context."
      >
        <div className="space-y-4">
          {/* `incident.id` is not unique on the pinned run (87 unique of 88 —
              a known upstream defect in incident-id generation, pinned by
              tests/api/test_dashboard_incidents.py). The list index disambiguates
              the React key; it is never reordered or filtered on the client. */}
          {incidentsSummary.incidents.map((incident, index) => (
            <div
              key={`${incident.id}-${index}`}
              className="space-y-3 rounded-lg border p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-0.5">
                  <p className="text-sm font-medium text-foreground">
                    {incident.title}
                  </p>
                  <p className="text-xs text-muted-foreground">{incident.id}</p>
                </div>
                <StatusBadge
                  status={incident.severity}
                  size="md"
                  className="h-7 min-w-24 justify-center px-4 text-sm"
                />
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span>Status: {formatIncidentStatus(incident.status)}</span>
                <span>
                  Window: {incident.startDate} to {incident.endDate}
                </span>
                <span>
                  Affected signals: {formatSignalList(incident.affectedSignals)}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                {incident.evidenceSummary}
              </p>
              <p className="text-sm text-foreground">
                <span className="font-medium">Recommendation: </span>
                {incident.recommendation}
              </p>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Operational interpretation"
        description="How grouped incidents should be understood in the current v0."
      >
        <div className="space-y-3">
          {incidentsSummary.insights.map((insight) => (
            <div key={insight.title} className="space-y-1 rounded-lg border p-4">
              <p className="text-sm font-medium text-foreground">
                {insight.title}
              </p>
              <p className="text-sm text-muted-foreground">{insight.body}</p>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
