"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { FeedbackForm } from "@/components/feedback-form";
import type { PlanDayLite } from "@/components/home/today-card";
import { useUnits } from "@/components/unit-preferences";
import { distanceInUnits, unitLabel } from "@/lib/units";
import { cn } from "@/lib/utils";

const DAYS_BACK = 7;

/** Completed runs from the last week that still have no app feedback, newest first.
 * The athlete may not open the app every day; a missed day must not mean a lost rating. */
export function runsAwaitingFeedback(days: PlanDayLite[], today: string): PlanDayLite[] {
  const cutoff = new Date(`${today}T12:00:00`);
  cutoff.setDate(cutoff.getDate() - DAYS_BACK);
  const since = cutoff.toLocaleDateString("en-CA");
  return days
    .filter((d) => d.date < today && d.date >= since && d.type !== "rest" && d.actual
      && !d.feedback?.feel_rating && d.actual.feel_rating == null)
    .sort((a, b) => b.date.localeCompare(a.date));
}

export function RecentFeedback({ days, onSaved }: { days: PlanDayLite[]; onSaved?: () => void }) {
  const units = useUnits();
  const [open, setOpen] = useState<string | null>(null);
  if (!days.length) return null;
  return (
    <section className="space-y-2 rounded-lg border p-3" aria-label="Recent runs to review">
      <h2 className="stat-label">Recent runs to review</h2>
      <ul className="divide-y">
        {days.map((d) => {
          const fromWatch = d.actual?.watch_feel != null || d.actual?.watch_effort != null;
          const label = new Date(`${d.date}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
          return (
            <li key={d.date} className="py-2">
              <button type="button" className="flex min-h-11 w-full items-center justify-between gap-3 text-left"
                aria-expanded={open === d.date} onClick={() => setOpen(open === d.date ? null : d.date)}>
                <span className="min-w-0">
                  <span className="block text-sm font-medium">{label} · {d.title}</span>
                  <span className="block text-xs text-muted-foreground">
                    {distanceInUnits(d.actual?.total_distance_miles ?? d.actual?.distance_miles ?? 0, units)} {unitLabel(units)}
                    {fromWatch ? " · watch rating ready to confirm" : " · not rated yet"}
                  </span>
                </span>
                <ChevronDown className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open === d.date && "rotate-180")} aria-hidden />
              </button>
              {open === d.date && (
                <div className="pt-2">
                  <FeedbackForm compact date={d.date} isWorkout={d.type === "workout"}
                    hasPaceTarget={!!d.prescription?.segments?.some((seg) => seg.pace_range_sec_per_mile)}
                    initial={{ feel: d.actual?.watch_feel, effort: d.actual?.watch_effort }} fromWatch={fromWatch}
                    onSubmitted={() => { setOpen(null); onSaved?.(); }} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
