"use client";

import { useState } from "react";
import { localDateStr } from "@/lib/format";
import { useUnits } from "@/components/unit-preferences";
import { distanceInUnits, unitLabel } from "@/lib/units";
import { cn } from "@/lib/utils";
import type { PlanDayLite } from "@/components/home/today-card";
import { ranDay, sessionKind } from "@/lib/workout-style";

const HARD = new Set(["workout", "long_run", "race"]);

export function WeekProgress({ days }: { days: PlanDayLite[] }) {
  const units = useUnits();
  const unit = unitLabel(units);
  const formatDistance = (miles: number) => distanceInUnits(miles, units);
  const today = localDateStr();
  const [selected, setSelected] = useState<string | null>(null);
  const sel = days.find((d) => d.date === selected);

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-7 gap-1 sm:gap-1.5">
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
                "flex min-h-12 flex-col items-center gap-1.5 rounded-2xl py-2 text-xs transition-colors hover:bg-[var(--row-hover)]",
                selected === d.date && "bg-[var(--glass-inner)] ring-1 ring-[var(--glass-border)]",
              )}
            >
              <span className={cn("text-muted-foreground", isToday && "font-semibold text-foreground")}>{dayName}</span>
              <span
                className={cn(
                  "flex size-9 items-center justify-center rounded-full border border-[var(--glass-border)] font-mono text-xs",
                  d.actual && "border-transparent font-semibold",
                  !d.actual && HARD.has(d.type) && "border-foreground/50 font-semibold",
                  !d.actual && d.type === "rest" && "border-dashed",
                  isToday && !d.actual && "ring-2 ring-foreground/30",
                )}
                style={d.actual ? { background: "var(--accent-warm)", color: "var(--type-on)" } : undefined}
              >
                {d.type === "rest" ? "–" : formatDistance(d.actual?.total_distance_miles ?? d.actual?.distance_miles ?? d.distance_miles)}
              </span>
              <span aria-hidden="true" className="dot size-1.5" style={{ background: `var(--type-${d.actual ? ranDay(d).kind : sessionKind(d.type, d.title)})`, opacity: d.type === "rest" ? 0.4 : 1 }} />
            </button>
          );
        })}
      </div>
      {sel && (
        <div className="glass-tile p-3.5 text-sm">
          <div className="font-semibold">{ranDay(sel).title}</div>
          <div className="text-muted-foreground">
            {sel.type === "rest" ? "Rest" : `${formatDistance(sel.distance_miles)} ${unit} planned`}
            {sel.actual && ` · ran ${formatDistance(sel.actual.distance_miles)} ${unit}`}
          </div>
          {sel.description && <p className="mt-1 text-muted-foreground">{sel.description}</p>}
        </div>
      )}
    </div>
  );
}
