"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { IncidentSeverityDistributionItem } from "@/types/incidents";

interface IncidentsSeverityChartProps {
  data: IncidentSeverityDistributionItem[];
}

export function IncidentsSeverityChart({ data }: IncidentsSeverityChartProps) {
  if (data.length === 0) {
    return (
      <div className="flex h-[320px] min-h-[320px] w-full min-w-0 items-center justify-center">
        <p className="text-sm text-muted-foreground">
          No incident severity data available.
        </p>
      </div>
    );
  }

  return (
    <div className="h-[320px] min-h-[320px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="label" stroke="var(--muted-foreground)" tick={{ fontSize: 12 }} />
          <YAxis
            allowDecimals={false}
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
          />
          <Tooltip />
          <Bar
            dataKey="count"
            name="Incidents"
            fill="var(--primary)"
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
