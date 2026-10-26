"use client";

import { useState } from "react";
import { useUnits } from "@/components/unit-preferences";
import { distanceValueInUnits, unitLabel } from "@/lib/units";
import { calendarMileage } from "@/lib/mileage-calendar";
import type { WeeklyMileage } from "@/lib/types";
import { cn } from "@/lib/utils";

const WEEKS = 12;

/** The hero metric at a glance: the last 12 calendar weeks as a slim bar strip.
 * Hover or focus a bar for its week; the current week (in progress) is the accent bar. */
export function MileageStrip({ data }: { data: WeeklyMileage[] }) {
  const units = useUnits();
  const unit = unitLabel(units);
  const [active, setActive] = useState<number | null>(null);
  if (!data.length) return null;
  const weeks = calendarMileage(data, WEEKS).map((d) => ({
    start: d.week_start,
    miles: distanceValueInUnits(d.actual, units),
    label: new Date(`${d.week_start}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
  }));
  const total = weeks.reduce((sum, w) => sum + w.miles, 0);
  const max = Math.max(1, ...weeks.map((w) => w.miles));
  const shown = active != null ? weeks[active] : null;
  const last = weeks.length - 1;

  return (
    <section aria-label={`Weekly mileage, last ${weeks.length} weeks`} className="glass flex items-center gap-4 rounded-[26px] px-4 py-3 sm:gap-6 sm:px-6">
      <div className="w-[8.5rem] flex-none sm:w-[10rem]" aria-live="polite">
        <div className="text-xs text-muted-foreground">{shown ? `Week of ${shown.label}${active === last ? " · now" : ""}` : `Weekly mileage · ${weeks.length} wks`}</div>
        <div className="num text-[22px] font-bold leading-tight">
          {(shown ? shown.miles : total).toFixed(1)} <span className="text-xs font-normal text-muted-foreground">{unit}</span>
        </div>
      </div>
      <ol className="flex h-14 flex-1 items-end gap-[5px] sm:gap-[7px]" onMouseLeave={() => setActive(null)}>
        {weeks.map((w, i) => (
          <li key={w.start} className="flex h-full flex-1 items-end">
            <button type="button" aria-label={`Week of ${w.label}: ${w.miles.toFixed(1)} ${unit}${i === last ? ", in progress" : ""}`}
              onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)} onBlur={() => setActive(null)}
              className={cn("w-full rounded-t-[7px] rounded-b-[3px] transition-[opacity,transform] duration-150 hover:scale-y-[1.04] focus-visible:outline-offset-2",
                i === last ? "bg-[var(--accent-warm)] opacity-100" : cn("bg-primary dark:bg-white", active === i ? "opacity-90" : "opacity-55"))}
              style={{ height: `${Math.max(6, (w.miles / max) * 100)}%`, transformOrigin: "bottom" }} />
          </li>
        ))}
      </ol>
    </section>
  );
}
