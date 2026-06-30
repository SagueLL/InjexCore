"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TimelinePoint } from "@/types/timeline";

interface OperationalTimelineChartProps {
  data: TimelinePoint[];
}

export function OperationalTimelineChart({
  data,
}: OperationalTimelineChartProps) {
  return (
    <div className="h-[320px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="date" stroke="var(--muted-foreground)" tick={{ fontSize: 12 }} />
          <YAxis
            yAxisId="deviation"
            domain={[0, 1]}
            tickFormatter={(value) => Number(value).toFixed(1)}
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
          />
          <YAxis
            yAxisId="incidents"
            orientation="right"
            allowDecimals={false}
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
          />
          <Tooltip />
          <Legend />
          <Bar
            yAxisId="incidents"
            dataKey="incidentCount"
            name="Incident windows"
            fill="var(--muted-foreground)"
            fillOpacity={0.25}
            radius={[2, 2, 0, 0]}
          />
          <Line
            yAxisId="deviation"
            type="monotone"
            dataKey="deviationScore"
            name="Deviation score"
            stroke="var(--primary)"
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
