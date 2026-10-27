"use client";

import { useEffect, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useUnits } from "@/components/unit-preferences";
import { getJson, USER_ID } from "@/lib/api";
import type { MileageBucket, MileagePeriod } from "@/lib/types";
import { distanceValueInUnits, unitLabel } from "@/lib/units";
import { hoursLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

const VIEWS: { bucket: MileageBucket; label: string; noun: string }[] = [
  { bucket: "week", label: "Weekly", noun: "week" },
  { bucket: "month", label: "Monthly", noun: "month" },
  { bucket: "year", label: "Yearly", noun: "year" },
];

type Metric = "distance" | "time";

function periodLabel(start: string, bucket: MileageBucket, long = false) {
  // Noon local time so a YYYY-MM-DD start doesn't shift a day west of UTC
  const d = new Date(`${start}T12:00:00`);
  if (bucket === "year") return String(d.getFullYear());
  if (bucket === "month") {
    if (long) return d.toLocaleDateString("en-US", { month: "long", year: "numeric" });
    const month = d.toLocaleDateString("en-US", { month: "short" });
    return d.getMonth() === 0 ? `${month} ’${String(d.getFullYear()).slice(2)}` : month;
  }
  return long ? `Week of ${d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}` : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function MileageOverTimeChart({ revision = 0 }: { revision?: number }) {
  const units = useUnits();
  const unit = unitLabel(units);
  const [bucket, setBucket] = useState<MileageBucket>("week");
  const [rows, setRows] = useState<MileagePeriod[] | null>(null);
  const [error, setError] = useState("");
  const [showData, setShowData] = useState(false);
  const [metric, setMetric] = useState<Metric>("distance");
  const timeMode = metric === "time";

  useEffect(() => {
    let active = true;
    getJson<MileagePeriod[]>(`/analysis/${USER_ID}/mileage?bucket=${bucket}`)
      .then((data) => { if (active) { setRows(data ?? []); setError(""); } })
      .catch(() => { if (active) setError("Mileage history could not load. Reload to retry."); });
    return () => { active = false; };
  }, [bucket, revision]);

  const noun = VIEWS.find((v) => v.bucket === bucket)!.noun;
  // Time is running (moving) time in hours; distance keeps the athlete's unit. Same buckets either way.
  const formatted = (rows ?? []).map((r) => ({
    ...r,
    distance: Number(distanceValueInUnits(r.actual, units).toFixed(1)),
    actual: timeMode ? Number(((r.actual_seconds ?? 0) / 3600).toFixed(1)) : Number(distanceValueInUnits(r.actual, units).toFixed(1)),
    planned: timeMode
      ? (r.planned_seconds == null ? null : Number((r.planned_seconds / 3600).toFixed(1)))
      : (r.planned == null ? null : Number(distanceValueInUnits(r.planned, units).toFixed(1))),
    label: periodLabel(r.period_start, bucket),
    longLabel: periodLabel(r.period_start, bucket, true),
  }));
  const shownUnit = timeMode ? "h" : unit;
  const untimed = formatted.reduce((sum, r) => sum + (r.runs_without_time ?? 0), 0);
  const complete = formatted.filter((r) => !r.partial);
  const total = formatted.reduce((sum, r) => sum + r.actual, 0);
  const average = complete.length ? complete.reduce((sum, r) => sum + r.actual, 0) / complete.length : 0;
  const peak = formatted.reduce<(typeof formatted)[number] | null>((best, r) => (!best || r.actual > best.actual ? r : best), null);
  // Blocks cover two weeks, so only a week is fully planned; months and years would understate it.
  const hasPlanned = bucket === "week" && formatted.some((r) => r.planned != null);

  return (
    <div className="space-y-3 px-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
        <div className="flex gap-1 rounded-lg bg-muted p-1" role="group" aria-label="Show volume as">
          {(["distance", "time"] as const).map((m) => (
            <button key={m} type="button" aria-pressed={metric === m} onClick={() => setMetric(m)}
              className={cn("min-h-9 rounded-md px-3 text-xs font-medium transition-colors",
                metric === m ? "bg-card text-primary" : "text-muted-foreground hover:text-foreground")}>
              {m === "distance" ? "Distance" : "Time"}
            </button>
          ))}
        </div>
        <div className="flex gap-1 rounded-lg bg-muted p-1" role="group" aria-label="Group mileage by">
          {VIEWS.map((v) => (
            <button key={v.bucket} type="button" aria-pressed={bucket === v.bucket} onClick={() => setBucket(v.bucket)}
              className={cn("min-h-9 rounded-md px-3 text-xs font-medium transition-colors",
                bucket === v.bucket ? "bg-card text-primary" : "text-muted-foreground hover:text-foreground")}>
              {v.label}
            </button>
          ))}
        </div>
        </div>
        {hasPlanned && (
          <p className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1"><span className="inline-block size-2.5 rounded-sm bg-[var(--viz-series-1)]" />Recorded</span>
            <span className="flex items-center gap-1"><span className="inline-block w-4 border-t-2 border-dashed border-muted-foreground" />Planned</span>
          </p>
        )}
      </div>

      {error ? <p role="alert" className="py-8 text-center text-sm text-destructive">{error}</p>
        : !rows ? <p role="status" className="py-8 text-center text-sm text-muted-foreground">Loading mileage…</p>
        : !formatted.some((r) => r.actual > 0) ? <p className="py-8 text-center text-sm text-muted-foreground">Your mileage history will appear after runs are logged.</p>
        : (
          <>
            <dl className="grid grid-cols-3 gap-2">
              <div><dt className="text-xs text-muted-foreground">Total shown</dt><dd className="font-mono text-base font-semibold">{total.toFixed(0)} {shownUnit}</dd></div>
              <div><dt className="text-xs text-muted-foreground">Avg per {noun}</dt><dd className="font-mono text-base font-semibold">{average.toFixed(1)} {shownUnit}</dd></div>
              <div><dt className="text-xs text-muted-foreground">Biggest {noun}</dt><dd className="font-mono text-base font-semibold">{peak ? `${peak.actual.toFixed(1)} ${shownUnit}` : "—"}</dd>
                {peak && <dd className="text-xs text-muted-foreground">{peak.label}</dd>}</div>
            </dl>
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={formatted} margin={{ top: 8, right: 8, bottom: 0, left: -8 }} accessibilityLayer>
                <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={16} />
                <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={timeMode} width={44}
                  tickFormatter={(v) => (timeMode ? `${v} h` : String(v))} />
                <Tooltip
                  cursor={{ fill: "var(--muted)" }}
                  contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                  labelFormatter={(_label, payload) => {
                    const row = payload?.[0]?.payload as (typeof formatted)[number] | undefined;
                    if (!row) return "";
                    const head = `${row.longLabel}${row.partial ? " (so far)" : ""} · ${row.runs} run${row.runs === 1 ? "" : "s"}`;
                    if (!timeMode) return `${head} · ${hoursLabel(row.actual_seconds ?? 0)}`;
                    const stops = (row.elapsed_seconds ?? 0) - (row.actual_seconds ?? 0) >= 60 ? ` (${hoursLabel(row.elapsed_seconds ?? 0)} elapsed)` : "";
                    return `${head} · ${row.distance.toFixed(1)} ${unit}${stops}`;
                  }}
                  formatter={(value, name, item) => {
                    const row = item?.payload as (typeof formatted)[number] | undefined;
                    if (!timeMode || !row) return [`${Number(value).toFixed(1)} ${unit}`, name];
                    return [hoursLabel(name === "Planned" ? row.planned_seconds ?? 0 : row.actual_seconds ?? 0), name];
                  }}
                />
                <Bar dataKey="actual" name="Recorded" fill="var(--viz-series-1)" radius={[4, 4, 0, 0]} maxBarSize={38} isAnimationActive={false} />
                {hasPlanned && <Line dataKey="planned" name="Planned" stroke="var(--muted-foreground)" strokeWidth={2} strokeDasharray="4 3"
                  dot={{ r: 2.5, fill: "var(--muted-foreground)", strokeWidth: 0 }} connectNulls={false} isAnimationActive={false} />}
              </ComposedChart>
            </ResponsiveContainer>
            <p className="text-xs text-muted-foreground">
              Garmin data. The latest {noun} is still in progress. Periods with no recorded runs show as zero; missing uploads are not proven rest.
              {timeMode && " Time is moving time from your watch; walks never count, and planned time is estimated from each block's easy pace."}
              {timeMode && untimed > 0 && ` ${untimed} run${untimed === 1 ? " has" : "s have"} no recorded time and ${untimed === 1 ? "is" : "are"} missing from these hours.`}
            </p>
            <button type="button" aria-expanded={showData} onClick={() => setShowData(!showData)} className="min-h-10 text-xs font-medium text-primary">
              {showData ? `Hide ${noun}ly totals` : `See ${noun}ly totals`}
            </button>
            {showData && (
              <dl className="grid grid-cols-2 gap-2 rounded-lg bg-muted/50 p-3 sm:grid-cols-4">
                {formatted.map((r) => (
                  <div key={r.period_start}>
                    <dt className="text-xs text-muted-foreground">{r.longLabel}</dt>
                    <dd className="font-mono text-sm">{timeMode ? hoursLabel(r.actual_seconds ?? 0) : `${r.actual.toFixed(1)} ${unit}`}{hasPlanned && r.planned != null && <span className="text-muted-foreground"> / {timeMode ? hoursLabel(r.planned_seconds ?? 0) : r.planned.toFixed(1)} planned</span>}</dd>
                  </div>
                ))}
              </dl>
            )}
          </>
        )}
    </div>
  );
}
