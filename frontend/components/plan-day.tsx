"use client";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  workoutTypeLabel,
  isHardWorkout,
  formatDistance,
  formatDate,
} from "@/lib/format";
import type { Workout } from "@/lib/types";

interface PlanDayProps {
  workout: Workout;
  isToday: boolean;
  expanded: boolean;
  onToggle: () => void;
}

export function PlanDay({ workout, isToday, expanded, onToggle }: PlanDayProps) {
  const today = new Date().toISOString().split("T")[0];
  const isPast = workout.date < today;

  return (
    <div
      className={cn(
        "cursor-pointer rounded-md border p-3 transition-colors hover:bg-secondary/50",
        isToday && "border-foreground",
        workout.completed && "bg-secondary/30",
        workout.skipped && "opacity-50"
      )}
      onClick={onToggle}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onToggle()}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-20 text-sm">
            <div className="font-medium">{formatDate(workout.date).split(",")[0]}</div>
            <div className="text-xs text-muted-foreground">
              {formatDate(workout.date).split(", ")[1]}
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium">{workout.title}</span>
              {isHardWorkout(workout.type) && (
                <Badge variant="default" className="text-[10px] px-1.5 py-0">
                  Quality
                </Badge>
              )}
            </div>
            {workout.intervals && (
              <div className="font-mono text-xs text-muted-foreground">
                {workout.intervals}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 text-right">
          {workout.type !== "rest" && (
            <span className="font-mono text-sm font-medium">
              {formatDistance(workout.distance_miles)} mi
            </span>
          )}
          {workout.completed && (
            <span className="text-xs text-muted-foreground">Done</span>
          )}
          {isToday && !workout.completed && (
            <Badge variant="secondary" className="text-[10px]">Today</Badge>
          )}
          {isPast && !workout.completed && !workout.skipped && !isToday && (
            <span className="text-xs text-destructive">Missed</span>
          )}
          {workout.skipped && (
            <span className="text-xs text-muted-foreground">Skipped</span>
          )}
        </div>
      </div>

      {expanded && (
        <div className="mt-3 space-y-2 border-t pt-3 text-sm">
          <p className="text-muted-foreground">{workout.description}</p>
          {workout.target_pace && (
            <div>
              <span className="text-muted-foreground">Target: </span>
              <span className="font-mono">{workout.target_pace}</span>
            </div>
          )}
          {workout.warmup && (
            <div>
              <span className="text-muted-foreground">Warmup: </span>
              {workout.warmup}
            </div>
          )}
          {workout.cooldown && (
            <div>
              <span className="text-muted-foreground">Cooldown: </span>
              {workout.cooldown}
            </div>
          )}
          <div className="border-t pt-2">
            <span className="font-medium">Why: </span>
            <span className="text-muted-foreground">{workout.purpose}</span>
          </div>
        </div>
      )}
    </div>
  );
}
