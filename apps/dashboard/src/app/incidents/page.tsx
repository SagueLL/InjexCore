import { PageHeader } from "@/components/app/page-header";

export default function IncidentsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Incidents"
        description="Aggregated incident evidence grouped for operational review."
      />
      <div className="rounded-lg border border-dashed bg-muted/30 p-8 text-center">
        <p className="text-sm text-muted-foreground">
          This view is part of the Dashboard v0 foundation. Operational content
          will be added in the next step.
        </p>
      </div>
    </div>
  );
}
