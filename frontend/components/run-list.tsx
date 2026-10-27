"use client";

import { useUnits } from "@/components/unit-preferences";
import { distanceInUnits, paceInUnits, unitLabel } from "@/lib/units";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  workoutTypeLabel,
  isHardWorkout,
  formatDate,
} from "@/lib/format";
import type { Activity } from "@/lib/types";
import { activityKind } from "@/lib/workout-style";

interface RunListProps {
  activities: Activity[];
  onSelect: (activity: Activity) => void;
}

export function RunList({ activities, onSelect }: RunListProps) {
  const units = useUnits();
  const unit = unitLabel(units);
  // Group by month
  const grouped: Record<string, Activity[]> = {};
  for (const a of activities) {
    const month = new Date(a.date).toLocaleDateString("en-US", {
      month: "long",
      year: "numeric",
    });
    if (!grouped[month]) grouped[month] = [];
    grouped[month].push(a);
  }

  return (
    <div className="space-y-5">
      {Object.entries(grouped).map(([month, runs]) => (
        <section key={month} className="glass space-y-1.5 p-3 sm:p-4" aria-label={month}>
          <h3 className="px-1 pb-1 text-[13px] font-bold">{month}</h3>
          {/* Column labels, as in the wireframe table (wide screens only) */}
          <div aria-hidden="true" className="hidden grid-cols-[6.5rem_minmax(0,1fr)_5.5rem_6.5rem_3.5rem] gap-3 px-3 text-[11px] text-muted-foreground md:grid">
            <span>Date</span><span>Run</span><span className="text-right">Distance</span><span className="text-right">Pace</span><span className="text-right">Feel</span>
          </div>
          <div className="space-y-1.5">
            {runs.map((run) => {
              const kind = activityKind(run.type, run.session?.title ?? run.title);
              return (
              <div
                key={run.id}
                className="glass-tile lift cursor-pointer px-3 py-2.5 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary"
                onClick={() => onSelect(run)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && onSelect(run)}
              >
                <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5 md:grid-cols-[6.5rem_minmax(0,1fr)_5.5rem_6.5rem_3.5rem]">
                  <div className="text-xs text-muted-foreground">
                    {formatDate(run.date)}
                  </div>
                  <div className="order-3 col-span-2 flex min-w-0 items-center gap-2 md:order-none md:col-span-1">
                    <span aria-hidden="true" className="dot" style={{ background: `var(--type-${kind})` }} />
                    <span className="truncate text-sm font-semibold">{run.session?.title ?? run.title}</span>
                    {run.type === "walk" && <span className="text-xs text-muted-foreground">walk</span>}
                    {isHardWorkout(run.type) && (
                      <Badge
                        variant="default"
                        className="px-1.5 py-0 text-[10px]"
                      >
                        {workoutTypeLabel(run.type)}
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-baseline justify-end gap-3 text-sm md:contents">
                    <span className="num font-bold md:text-right">
                      {distanceInUnits(run.distance_miles, units)} {unit}
                    </span>
                    <span className="num text-muted-foreground md:text-right md:text-foreground">
                      {paceInUnits(run.avg_pace.replace(/\/mi$/, ""), units)}/{unit}
                    </span>
                    <span
                      className={cn(
                        "text-xs md:text-right",
                        run.feel_rating && run.feel_rating >= 7
                          ? "text-foreground"
                          : "text-muted-foreground"
                      )}
                    >
                      {run.feel_rating ? `${run.feel_rating}/10` : <span className="max-md:hidden">—</span>}
                    </span>
                  </div>
                </div>
                {run.description && (
                  <p className="mt-1.5 line-clamp-2 text-xs text-muted-foreground md:ml-[7.25rem]">
                    {run.description}
                  </p>
                )}
              </div>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
