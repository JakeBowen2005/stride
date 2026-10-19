"use client";

import { useState } from "react";
import { formatDistance, localDateStr } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { PlanDayLite } from "@/components/home/today-card";

const HARD = new Set(["workout", "long_run", "race"]);

export function WeekProgress({ days, plannedMiles }: { days: PlanDayLite[]; plannedMiles: number }) {
  const today = localDateStr();
  const [selected, setSelected] = useState<string | null>(null);
  const done = days.reduce((sum, d) => sum + (d.actual?.distance_miles ?? 0), 0);
  const pct = plannedMiles > 0 ? Math.min(done / plannedMiles, 1) : 0;
  const sel = days.find((d) => d.date === selected);

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">This week</div>
          <div className="font-mono text-4xl font-semibold leading-none">
            {formatDistance(done)}
            <span className="ml-1 text-base font-normal text-muted-foreground">/ {formatDistance(plannedMiles)} mi</span>
          </div>
        </div>
        <span className="text-sm text-muted-foreground">{Math.round(pct * 100)}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={Math.round(pct * 100)} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full rounded-full transition-all" style={{ width: `${pct * 100}%`, background: "var(--viz-series-1)" }} />
      </div>
      <div className="grid grid-cols-7 gap-1">
        {days.map((d) => {
          const isToday = d.date === today;
          const dayName = new Date(`${d.date}T12:00:00`).toLocaleDateString("en-US", { weekday: "narrow" });
          return (
            <button
              key={d.date}
              type="button"
              onClick={() => setSelected(selected === d.date ? null : d.date)}
              aria-label={`${d.date}: ${d.title}`}
              aria-pressed={selected === d.date}
              className={cn(
                "flex flex-col items-center gap-1 rounded-lg py-1.5 text-xs transition-colors hover:bg-muted",
                selected === d.date && "bg-muted",
              )}
            >
              <span className={cn("text-muted-foreground", isToday && "font-semibold text-foreground")}>{dayName}</span>
              <span
                className={cn(
                  "flex size-7 items-center justify-center rounded-full border font-mono text-xs",
                  d.actual && "border-transparent text-white",
                  !d.actual && HARD.has(d.type) && "border-foreground/50 font-semibold",
                  !d.actual && d.type === "rest" && "border-dashed",
                  isToday && !d.actual && "ring-2 ring-foreground/30",
                )}
                style={d.actual ? { background: "var(--viz-series-1)" } : undefined}
              >
                {d.type === "rest" ? "–" : Math.round(d.actual?.distance_miles ?? d.distance_miles)}
              </span>
            </button>
          );
        })}
      </div>
      {sel && (
        <div className="rounded-lg border p-3 text-sm">
          <div className="font-medium">{sel.title}</div>
          <div className="text-muted-foreground">
            {sel.type === "rest" ? "Rest" : `${formatDistance(sel.distance_miles)} mi planned`}
            {sel.actual && ` · ran ${formatDistance(sel.actual.distance_miles)} mi`}
          </div>
          {sel.description && <p className="mt-1 text-muted-foreground">{sel.description}</p>}
        </div>
      )}
      <p className="text-xs text-muted-foreground">Filled = run done · bold ring = quality day · dashed = rest. Tap a day for details.</p>
    </div>
  );
}
