"use client";

import { useState, useSyncExternalStore } from "react";
import { X } from "lucide-react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
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
];

function Sparkline({ data }: { data: { v: number }[] }) {
  if (data.length < 2) return <div className="h-8" />;
  return (
    <ResponsiveContainer width="100%" height={32}>
      <LineChart data={data} margin={{ top: 4, bottom: 4, left: 0, right: 0 }}>
        <YAxis hide domain={["dataMin", "dataMax"]} />
        <Line type="linear" dataKey="v" stroke="var(--viz-series-1)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function shortDate(iso: string) {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// Shown before "Show all": the four that most often change what you should run today
const PRIMARY: MetricKey[] = ["sleep", "hrv", "rhr", "load"];

const STORAGE_KEY = "stride.home.trendMetric";
const HIDDEN = "none";
const DEFAULT_METRIC: MetricKey = "hrv";

// Persisted trend-chart choice. localStorage can be missing or throw (private mode,
// blocked storage); in that case the choice simply lives for this page view.
const listeners = new Set<() => void>();
let memoryChoice: string | null = null;

function readChoice(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? memoryChoice;
  } catch {
    return memoryChoice;
  }
}

function writeChoice(v: MetricKey | null) {
  memoryChoice = v ?? HIDDEN;
  try {
    window.localStorage.setItem(STORAGE_KEY, memoryChoice);
  } catch {
    // storage unavailable — keep the in-memory value only
  }
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

function toMetric(raw: string | null): MetricKey | null {
  if (raw === HIDDEN) return null;
  return METRICS.some((m) => m.key === raw) ? (raw as MetricKey) : DEFAULT_METRIC;
}

export function MetricTiles({ today, history }: { today: Wellness | null; history: Wellness[] }) {
  // null = trend chart hidden
  const selected = toMetric(useSyncExternalStore(subscribe, readChoice, () => null));
  const setSelected = writeChoice;
  const [showAll, setShowAll] = useState(false);
  if (!today) return null;

  const available = METRICS.filter((m) => m.value(today) != null || history.some((h) => m.value(h) != null));
  const tiles = showAll ? available : available.filter((m) => PRIMARY.includes(m.key) || m.key === selected);
  const active = selected == null ? null : (available.find((m) => m.key === selected) ?? available[0]);
  if (available.length === 0) return null;

  const series = (m: MetricDef) =>
    history.map((h) => ({ date: h.date, label: shortDate(h.date), v: m.value(h) ?? null })).filter((p) => p.v != null) as {
      date: string; label: string; v: number;
    }[];
  const activeSeries = active ? series(active) : [];
  const band = active?.band?.(today) ?? null;
  const first = activeSeries[0]?.v;
  const last = activeSeries[activeSeries.length - 1]?.v;
  const change = first != null && last != null && activeSeries.length > 6 ? last - first : null;

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-2">
        {tiles.map((m) => (
          <button
            key={m.key}
            type="button"
            onClick={() => setSelected(active?.key === m.key ? null : m.key)}
            aria-pressed={active?.key === m.key}
            className={cn(
              "glass-tile lift border border-transparent px-3.5 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active?.key === m.key && "border-[var(--glass-border)] ring-1 ring-[var(--ring)]",
            )}
          >
            <div className="text-xs font-medium text-muted-foreground">{m.label}</div>
            <div className="mt-0.5 flex items-baseline gap-1">
              <span className="num text-[22px] font-semibold leading-tight">{m.display(today)}</span>
              {m.unit && <span className="text-xs text-muted-foreground">{m.unit}</span>}
            </div>
            <div className="truncate text-xs text-muted-foreground">{m.sub(today) || " "}</div>
            <Sparkline data={series(m)} />
          </button>
        ))}
      </div>
      {available.length > tiles.length || showAll ? (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="min-h-8 rounded-full px-1 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
        >
          {showAll ? "Show fewer" : `+${available.length - tiles.length} more metrics`}
        </button>
      ) : null}

      {active && (
        <Card className="rounded-2xl border-0 bg-[var(--glass-inner)] py-0 shadow-none backdrop-blur-none">
          <CardContent className="space-y-1 px-3.5 py-3">
            <div className="flex items-center justify-between gap-2">
              <h4 className="text-sm font-medium" title={active.help}>{active.label} · last {activeSeries.length} days</h4>
              <div className="flex items-center gap-2">
                {change != null && (
                  <span className="text-xs text-muted-foreground">
                    {change === 0 ? "flat" : `${change > 0 ? "▲" : "▼"} ${Math.abs(change) < 10 ? Math.abs(change).toFixed(1) : Math.round(Math.abs(change))}`}
                    {change !== 0 && !active.neutralTrend && ` ${(change < 0) === !!active.lowerIsBetter ? "(better)" : "(watch)"}`}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  aria-label="Hide chart"
                  title="Hide chart"
                  className="-mr-1 rounded-full p-1.5 text-muted-foreground hover:bg-[var(--row-hover)] hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="size-4" />
                </button>
              </div>
            </div>
            {activeSeries.length > 1 ? (
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={activeSeries} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
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
                  <Line type="linear" dataKey="v" stroke="var(--viz-series-1)" strokeWidth={2}
                    dot={{ r: 2.5, fill: "var(--viz-series-1)", strokeWidth: 0 }} activeDot={{ r: 4 }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="py-6 text-center text-sm text-muted-foreground">Not enough history yet.</p>
            )}
            <p className="text-xs text-muted-foreground">{band ? `Shaded = ${active.key === "hrv" ? "your normal HRV range" : "the 0.8-1.3 sweet spot"}. ` : ""}{active.help}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
