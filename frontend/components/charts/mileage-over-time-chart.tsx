"use client";

import { useUnits } from "@/components/unit-preferences";
import { distanceValueInUnits, unitLabel } from "@/lib/units";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { WeeklyMileage } from "@/lib/types";

export function MileageOverTimeChart({ data }: { data: WeeklyMileage[] }) {
  const units = useUnits();
  const unit = unitLabel(units);
  const formatted = data.map((d) => ({
    ...d,
    actual: distanceValueInUnits(d.actual ?? 0, units),
    // Noon local time so a YYYY-MM-DD week start doesn't shift a day west of UTC
    label: new Date(`${d.week_start.slice(0, 10)}T12:00:00`).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
  }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={formatted} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-border" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11 }}
          className="fill-muted-foreground"
          interval="preserveStartEnd"
          minTickGap={24}
        />
        <YAxis
          tick={{ fontSize: 11 }}
          className="fill-muted-foreground"
          domain={[0, "auto"]}
          allowDecimals={false}
          width={40}
        />
        <Tooltip
          cursor={{ stroke: "var(--color-border)" }}
          contentStyle={{
            backgroundColor: "var(--color-card)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            fontSize: 12,
          }}
          separator=""
          labelFormatter={() => ""}
          labelStyle={{ display: "none" }}
          formatter={(v, _name, item) => [
            `${item.payload.label} · ${typeof v === "number" ? v.toFixed(1) : v} ${unit}`,
            "",
          ]}
        />
        <Line
          type="linear"
          dataKey="actual"
          stroke="var(--viz-series-1)"
          strokeWidth={2}
          fill="none"
          dot={{ r: 3, fill: "var(--viz-series-1)", strokeWidth: 0 }}
          activeDot={{ r: 5 }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
