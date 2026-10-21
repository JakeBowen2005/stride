"use client";

import { useUnits } from "@/components/unit-preferences";
import { paceValueInUnits, unitLabel } from "@/lib/units";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { secondsToPace } from "@/lib/format";
import type { PaceVsTarget } from "@/lib/types";

export function PaceVsTargetChart({ data }: { data: PaceVsTarget[] }) {
  const units = useUnits();
  const unit = unitLabel(units);
  const formatted = data.map((d) => ({
    ...d,
    target_pace_seconds: paceValueInUnits(d.target_pace_seconds, units),
    actual_pace_seconds: paceValueInUnits(d.actual_pace_seconds, units),
    label: new Date(d.date).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
    target_display: secondsToPace(d.target_pace_seconds),
    actual_display: secondsToPace(d.actual_pace_seconds),
  }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={formatted}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11 }}
          className="fill-muted-foreground"
        />
        <YAxis
          tick={{ fontSize: 11 }}
          className="fill-muted-foreground"
          tickFormatter={(v: number) => secondsToPace(v)}
          reversed
          domain={["dataMin - 10", "dataMax + 10"]}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "var(--color-card)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            fontSize: 12,
          }}
          formatter={(value) => `${secondsToPace(Number(value))}/${unit}`}
        />
        <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
        <Line
          type="monotone"
          dataKey="target_pace_seconds"
          stroke="var(--color-muted-foreground)"
          strokeDasharray="5 5"
          dot={false}
          name="Target"
        />
        <Line
          type="monotone"
          dataKey="actual_pace_seconds"
          stroke="var(--color-foreground)"
          strokeWidth={2}
          dot={{ r: 3 }}
          name="Actual"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
