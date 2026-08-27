"use client";

import { cn } from "@/lib/utils";
import { workoutTypeShort, formatDistance, isHardWorkout, localDateStr } from "@/lib/format";
import type { Workout } from "@/lib/types";

interface WeekStripProps {
  workouts: Workout[];
  totalPlanned: number;
}

export function WeekStrip({ workouts, totalPlanned }: WeekStripProps) {
  const today = localDateStr();
  const completedMiles = workouts
    .filter((w) => w.completed)
    .reduce((sum, w) => sum + w.distance_miles, 0);

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium">This Week</h3>
        <span className="text-sm text-muted-foreground">
          <span className="font-mono font-semibold text-foreground">
            {formatDistance(completedMiles)}
          </span>
          {" / "}
          <span className="font-mono">{totalPlanned}</span>
          {" mi"}
        </span>
      </div>
      <div className="grid grid-cols-7 gap-1.5">
        {workouts.map((w) => {
          const isToday = w.date === today;
          const hard = isHardWorkout(w.type);
          return (
            <div
              key={w.id}
              className={cn(
                "flex flex-col items-center rounded-md border p-1.5 text-center",
                isToday && "border-foreground bg-secondary",
                !isToday && "border-border",
                w.completed && !isToday && "bg-secondary/50"
              )}
            >
              <span className="text-[10px] text-muted-foreground">
                {new Date(w.date).toLocaleDateString("en-US", { weekday: "short" }).slice(0, 3)}
              </span>
              <span
                className={cn(
                  "font-mono text-xs font-medium",
                  hard && "text-foreground",
                  !hard && "text-muted-foreground",
                  w.type === "rest" && "text-muted-foreground/50"
                )}
              >
                {w.type === "rest" ? "—" : workoutTypeShort(w.type)}
              </span>
              {w.type !== "rest" && (
                <span className="font-mono text-[10px] text-muted-foreground">
                  {formatDistance(w.distance_miles)}
                </span>
              )}
              {w.completed && (
                <div className="mt-0.5 h-1 w-1 rounded-full bg-foreground" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
