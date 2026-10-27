"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useUnits } from "@/components/unit-preferences";
import { getJson, USER_ID } from "@/lib/api";
import { secondsToPace } from "@/lib/format";
import type { AerobicEfficiency } from "@/lib/types";
import { paceValueInUnits, unitLabel } from "@/lib/units";

const pace = (seconds: number) => secondsToPace(Math.round(seconds));

export function AerobicEfficiencyChart({ revision = 0 }: { revision?: number }) {
  const units = useUnits();
  const unit = unitLabel(units);
  const [data, setData] = useState<AerobicEfficiency | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getJson<AerobicEfficiency>(`/analysis/${USER_ID}/aerobic-efficiency?weeks=26`)
      .then((d) => { if (active) { setData(d); setError(""); } })
      .catch(() => { if (active) setError("Aerobic efficiency could not load. Reload to retry."); });
    return () => { active = false; };
  }, [revision]);

  if (error) return <p role="alert" className="px-3 py-8 text-center text-sm text-destructive">{error}</p>;
  if (!data) return <p role="status" className="px-3 py-8 text-center text-sm text-muted-foreground">Loading aerobic efficiency…</p>;
  if (data.weeks.length < 2 || data.reference_heartrate == null)
    return <p className="px-3 py-8 text-center text-sm text-muted-foreground">{data.note}</p>;

  const points = data.weeks.map((w, i) => {
    // Rolling 4-week mean smooths weather and sensor noise out of single weeks.
    const window = data.weeks.slice(Math.max(0, i - 3), i + 1);
    return {
      ...w,
      pace: Math.round(paceValueInUnits(w.pace_sec_per_mile, units)),
      trend: Math.round(paceValueInUnits(window.reduce((sum, x) => sum + x.pace_sec_per_mile, 0) / window.length, units)),
      label: new Date(`${w.week_start}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    };
  });
  const latest = points.at(-1)!;
  const change = data.change_sec_per_mile == null ? null : Math.round(paceValueInUnits(data.change_sec_per_mile, units));
  const trend = change == null ? "Not enough weeks yet to call a trend."
    : Math.abs(change) < 5 ? "Holding steady over this period."
    : change < 0 ? `${Math.abs(change)}s/${unit} faster at the same heart rate than at the start of this period.`
    : `${change}s/${unit} slower at the same heart rate than at the start of this period.`;

  return (
    <div className="space-y-3 px-3">
      <div>
        <p className="text-xs text-muted-foreground">Easy pace at {data.reference_heartrate} bpm, 4-week average</p>
        <p className="font-mono text-base font-semibold">{pace(latest.trend)}/{unit}</p>
        <p className={change != null && change <= -5 ? "text-sm text-primary" : "text-sm"}>{trend}</p>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: -4 }} accessibilityLayer>
          <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-border" />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
          {/* Reversed so faster (fitter) plots higher */}
          <YAxis reversed domain={([min, max]: readonly number[]) => [Math.floor((min - 5) / 15) * 15, Math.ceil((max + 5) / 15) * 15]} tickCount={5} allowDecimals={false} tickFormatter={(v: number) => pace(v)}
            tick={{ fontSize: 11 }} axisLine={false} tickLine={false} width={44} />
          <Tooltip
            cursor={{ stroke: "var(--border)" }}
            contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
            labelFormatter={(_label, payload) => {
              const row = payload?.[0]?.payload as (typeof points)[number] | undefined;
              return row ? `Week of ${row.label} · ${row.runs} easy run${row.runs === 1 ? "" : "s"} at ${data.reference_heartrate} bpm` : "";
            }}
            formatter={(value, name) => [`${pace(Number(value))}/${unit}`, name]}
          />
          <Line type="monotone" dataKey="pace" name="That week" stroke="none" dot={{ r: 2.5, fill: "var(--muted-foreground)", fillOpacity: 0.5, strokeWidth: 0 }}
            activeDot={{ r: 4 }} isAnimationActive={false} />
          <Line type="monotone" dataKey="trend" name="4-week average" stroke="var(--viz-series-1)" strokeWidth={2.5}
            dot={false} activeDot={{ r: 5 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <p className="text-xs text-muted-foreground">Line: 4-week average. Dots: single weeks. Higher is fitter: more speed for the same heart rate. {data.note}</p>
    </div>
  );
}
