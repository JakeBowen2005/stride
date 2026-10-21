"use client";

import { useUnits } from "@/components/unit-preferences";
import { distanceValueInUnits, unitLabel } from "@/lib/units";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { localDateStr } from "@/lib/format";
import type { Activity } from "@/lib/types";

interface DailyMileageData {
  label: string;
  miles: number;
}

export function DailyMileageChart({ activities }: { activities: Activity[] }) {
  const units = useUnits();
  const unit = unitLabel(units);
  // Build last 7 days
  const days: DailyMileageData[] = [];
  const now = new Date();

  for (let i = 6; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const dateStr = localDateStr(d);
    const label = d.toLocaleDateString("en-US", { weekday: "short" });
    const miles = activities
      .filter((a) => a.date.startsWith(dateStr) && a.type !== "walk")
      .reduce((sum, a) => sum + a.distance_miles, 0);
    days.push({ label, miles: Math.round(distanceValueInUnits(miles, units) * 10) / 10 });
  }

  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={days} barGap={2}>
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
          formatter={(value) => [`${value} ${unit}`, "Completed"]}
        />
        <Bar
          dataKey="miles"
          fill="var(--color-foreground)"
          radius={[3, 3, 0, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
