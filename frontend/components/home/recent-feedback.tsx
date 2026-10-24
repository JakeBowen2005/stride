"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { FeedbackForm } from "@/components/feedback-form";
import type { Activity } from "@/lib/types";
import { useUnits } from "@/components/unit-preferences";
import { distanceInUnits, unitLabel } from "@/lib/units";
import { cn } from "@/lib/utils";

const DAYS_BACK = 7;

/** Completed runs from the last week that still have no comment, newest first.
 * The athlete may not open the app every day; a missed day must not mean a lost review
 * (the AI review of a run starts when its comment is saved). */
export function runsAwaitingFeedback(days: Activity[], today: string): Activity[] {
  const cutoff = new Date(`${today}T12:00:00`);
  cutoff.setDate(cutoff.getDate() - DAYS_BACK);
  const since = cutoff.toLocaleDateString("en-CA");
  return days.filter(d => d.date.slice(0,10) <= today && d.date.slice(0,10) >= since && !(d.notes ?? "").trim())
    .sort((a,b) => b.date.localeCompare(a.date));
}

export function RecentFeedback({ days, onSaved }: { days: Activity[]; onSaved?: () => void }) {
  const units = useUnits();
  const [open, setOpen] = useState<string | null>(null);
  if (!days.length) return null;
  return (
    <section className="space-y-2 rounded-lg border p-3" aria-label="Runs waiting for your comment">
      <h2 className="stat-label">Runs waiting for your comment</h2>
      <ul className="divide-y">
        {days.map((d) => {
          const label = new Date(`${d.date.slice(0,10)}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
          return (
            <li key={d.id} className="py-2">
              <button type="button" className="flex min-h-11 w-full items-center justify-between gap-3 text-left"
                aria-expanded={open === d.date} onClick={() => setOpen(open === d.date ? null : d.date)}>
                <span className="min-w-0">
                  <span className="block text-sm font-medium">{label} · {d.title}</span>
                  <span className="block text-xs text-muted-foreground">
                    {distanceInUnits(d.distance_miles, units)} {unitLabel(units)}
                    {" · add a comment to get your coach review"}
                  </span>
                </span>
                <ChevronDown className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open === d.date && "rotate-180")} aria-hidden />
              </button>
              {open === d.date && (
                <div className="pt-2">
                  <FeedbackForm compact activityId={d.id} date={d.date.slice(0,10)}
                    watch={{ feel: d.watch_feel, effort: d.watch_effort }}
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
