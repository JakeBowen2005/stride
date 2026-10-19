"use client";

import { useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { Wellness } from "@/components/home/types";

type MetricKey = "sleep" | "hrv" | "rhr" | "battery" | "stress" | "steps" | "vo2" | "load";

interface MetricDef {
  key: MetricKey;
  label: string;
  unit: string;
  value: (w: Wellness) => number | null | undefined;
  display: (w: Wellness) => string;
  sub: (w: Wellness) => string;
  /** lower is better (resting HR, stress) — flips the trend wording */
  lowerIsBetter?: boolean;
  /** no better/worse judgement on the trend (load ratio: both directions can be bad) */
  neutralTrend?: boolean;
  band?: (w: Wellness) => [number, number] | null;
  help: string;
}

const hrs = (s?: number | null) => (s ? `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m` : "—");
const titleCase = (s?: string | null) => (s ? s.charAt(0) + s.slice(1).toLowerCase() : "");

const METRICS: MetricDef[] = [
  {
    key: "sleep", label: "Sleep", unit: "score",
    value: (w) => w.sleep_score,
    display: (w) => (w.sleep_score != null ? String(w.sleep_score) : "—"),
    sub: (w) => `${hrs(w.sleep_seconds)}${w.sleep_quality ? ` · ${titleCase(w.sleep_quality)}` : ""}`,
    help: "Garmin sleep score (0-100). Sleep is when training adaptations actually happen.",
  },
  {
    key: "hrv", label: "HRV", unit: "ms",
    value: (w) => w.hrv_last_night,
    display: (w) => (w.hrv_last_night != null ? `${Math.round(w.hrv_last_night)}` : "—"),
    sub: (w) => (w.hrv_status ? titleCase(w.hrv_status) : "overnight avg"),
    band: (w) => (w.hrv_baseline_low && w.hrv_baseline_high ? [w.hrv_baseline_low, w.hrv_baseline_high] : null),
    help: "Overnight heart-rate variability. Inside your shaded normal range = recovered; below it = carrying fatigue.",
  },
  {
    key: "rhr", label: "Resting HR", unit: "bpm", lowerIsBetter: true,
    value: (w) => w.resting_hr,
    display: (w) => (w.resting_hr != null ? `${Math.round(w.resting_hr)}` : "—"),
    sub: (w) => (w.resting_hr_7d_avg ? `7-day avg ${Math.round(w.resting_hr_7d_avg)}` : "bpm"),
    help: "A resting HR 5+ bpm above your normal is an early sign of fatigue, illness or heat stress.",
  },
  {
    key: "battery", label: "Body Battery", unit: "",
    value: (w) => w.body_battery_wake,
    display: (w) => (w.body_battery_now != null ? `${w.body_battery_now}` : "—"),
    sub: (w) => (w.body_battery_wake != null ? `woke at ${w.body_battery_wake}` : "now"),
    help: "Garmin's energy estimate. The trend shows how charged you woke up each day.",
  },
  {
    key: "stress", label: "Stress", unit: "avg", lowerIsBetter: true,
    value: (w) => w.stress_avg,
    display: (w) => (w.stress_avg != null ? `${w.stress_avg}` : "—"),
    sub: (w) => (w.stress_avg == null ? "" : w.stress_avg < 26 ? "Rest" : w.stress_avg < 51 ? "Low" : w.stress_avg < 76 ? "Medium" : "High"),
    help: "All-day stress from HRV (0-100). Life stress and training stress draw from the same pool.",
  },
  {
    key: "steps", label: "Steps", unit: "",
    value: (w) => w.steps,
    display: (w) => (w.steps != null ? w.steps.toLocaleString() : "—"),
    sub: (w) => (w.step_goal ? `goal ${w.step_goal.toLocaleString()}` : ""),
    help: "Daily steps, runs included.",
  },
  {
    key: "vo2", label: "VO2max", unit: "",
    value: (w) => w.vo2max,
    display: (w) => (w.vo2max != null ? w.vo2max.toFixed(1) : "—"),
    sub: () => "Garmin estimate",
    help: "Garmin's aerobic-capacity estimate from your runs. Trend matters more than the number.",
  },
  {
    key: "load", label: "Load Ratio", unit: "", neutralTrend: true,
    value: (w) => w.acwr,
    display: (w) => (w.acwr != null ? w.acwr.toFixed(2) : "—"),
    sub: (w) => (w.acwr == null ? "acute:chronic" : w.acwr > 1.5 ? "High risk" : w.acwr < 0.8 ? "Detraining" : "Optimal"),
    band: () => [0.8, 1.3],
    help: "Acute (7-day) vs chronic (28-day) training load. 0.8-1.3 is the sweet spot; above 1.5 injury risk climbs fast.",
  },
];

function Sparkline({ data }: { data: { v: number }[] }) {
  if (data.length < 2) return <div className="h-8" />;
  return (
    <ResponsiveContainer width="100%" height={32}>
      <LineChart data={data} margin={{ top: 4, bottom: 4, left: 0, right: 0 }}>
        <YAxis hide domain={["dataMin", "dataMax"]} />
        <Line type="monotone" dataKey="v" stroke="var(--viz-series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function shortDate(iso: string) {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function MetricTiles({ today, history }: { today: Wellness | null; history: Wellness[] }) {
  const [selected, setSelected] = useState<MetricKey>("hrv");
  if (!today) return null;

  const available = METRICS.filter((m) => m.value(today) != null || history.some((h) => m.value(h) != null));
  const active = available.find((m) => m.key === selected) ?? available[0];
  if (!active) return null;

  const series = (m: MetricDef) =>
    history.map((h) => ({ date: h.date, label: shortDate(h.date), v: m.value(h) ?? null })).filter((p) => p.v != null) as {
      date: string; label: string; v: number;
    }[];
  const activeSeries = series(active);
  const band = active.band?.(today) ?? null;
  const first = activeSeries[0]?.v;
  const last = activeSeries[activeSeries.length - 1]?.v;
  const change = first != null && last != null && activeSeries.length > 6 ? last - first : null;

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium">Recovery & Body</h3>
        <span className="text-xs text-muted-foreground">from Garmin · tap a tile for its trend</span>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {available.map((m) => (
          <button
            key={m.key}
            type="button"
            onClick={() => setSelected(m.key)}
            aria-pressed={active.key === m.key}
            className={cn(
              "rounded-xl border bg-card p-3 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active.key === m.key && "border-foreground/40 ring-1 ring-foreground/20",
            )}
          >
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{m.label}</div>
            <div className="mt-0.5 flex items-baseline gap-1">
              <span className="font-mono text-xl font-semibold">{m.display(today)}</span>
              {m.unit && <span className="text-xs text-muted-foreground">{m.unit}</span>}
            </div>
            <div className="truncate text-xs text-muted-foreground">{m.sub(today) || " "}</div>
            <Sparkline data={series(m)} />
          </button>
        ))}
      </div>

      <Card>
        <CardContent className="space-y-2 pt-4">
          <div className="flex items-baseline justify-between gap-2">
            <h4 className="text-sm font-medium">{active.label} · last {activeSeries.length} days</h4>
            {change != null && (
              <span className="text-xs text-muted-foreground">
                {change === 0 ? "flat" : `${change > 0 ? "▲" : "▼"} ${Math.abs(change) < 10 ? Math.abs(change).toFixed(1) : Math.round(Math.abs(change))}`}
                {change !== 0 && !active.neutralTrend && ` ${(change < 0) === !!active.lowerIsBetter ? "(better)" : "(watch)"}`}
              </span>
            )}
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">{active.help}</p>
          {activeSeries.length > 1 ? (
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={activeSeries} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} className="fill-muted-foreground" interval="preserveStartEnd" minTickGap={24} />
                <YAxis tick={{ fontSize: 11 }} className="fill-muted-foreground" domain={["auto", "auto"]} width={40} />
                {band && (
                  <ReferenceArea y1={band[0]} y2={band[1]} fill="var(--viz-band)" stroke="none" ifOverflow="extendDomain" />
                )}
                <Tooltip
                  cursor={{ stroke: "var(--color-border)" }}
                  contentStyle={{
                    backgroundColor: "var(--color-card)",
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-md)",
                    fontSize: 12,
                  }}
                  formatter={(v) => [typeof v === "number" ? (v < 10 ? v.toFixed(2) : Math.round(v)) : v, active.label]}
                />
                <Area type="monotone" dataKey="v" stroke="var(--viz-series-1)" strokeWidth={2} fill={band ? "none" : "var(--viz-band)"} dot={false} activeDot={{ r: 4 }} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <p className="py-6 text-center text-sm text-muted-foreground">Not enough history yet.</p>
          )}
          {band && <p className="text-[11px] text-muted-foreground">Shaded band = {active.key === "hrv" ? "your normal HRV range" : "the 0.8-1.3 sweet spot"}.</p>}
        </CardContent>
      </Card>
    </div>
  );
}
