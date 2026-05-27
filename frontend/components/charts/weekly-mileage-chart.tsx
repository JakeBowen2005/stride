"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { WeeklyMileage } from "@/lib/types";

export function WeeklyMileageChart({ data }: { data: WeeklyMileage[] }) {
  const formatted = data.map((d) => ({
    ...d,
    label: new Date(d.week_start).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
  }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={formatted} barGap={2}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11 }}
          className="fill-muted-foreground"
        />
        <YAxis tick={{ fontSize: 11 }} className="fill-muted-foreground" />
        <Tooltip
          contentStyle={{
            backgroundColor: "var(--color-card)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            fontSize: 12,
          }}
        />
        <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
        <Bar
          dataKey="planned"
          fill="var(--color-muted-foreground)"
          radius={[3, 3, 0, 0]}
          opacity={0.3}
          name="Planned"
        />
        <Bar
          dataKey="actual"
          fill="var(--color-foreground)"
          radius={[3, 3, 0, 0]}
          name="Actual"
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
