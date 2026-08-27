"use client";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  workoutTypeLabel,
  isHardWorkout,
  formatDistance,
  formatDate,
} from "@/lib/format";
import type { Activity } from "@/lib/types";

interface RunListProps {
  activities: Activity[];
  onSelect: (activity: Activity) => void;
}

export function RunList({ activities, onSelect }: RunListProps) {
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
    <div className="space-y-6">
      {Object.entries(grouped).map(([month, runs]) => (
        <div key={month}>
          <h3 className="mb-2 text-sm font-medium text-muted-foreground">
            {month}
          </h3>
          <div className="space-y-2.5">
            {runs.map((run) => (
              <div
                key={run.id}
                className="cursor-pointer rounded-md border p-3.5 transition-colors hover:bg-secondary/50"
                onClick={() => onSelect(run)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && onSelect(run)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-16 text-sm">
                      <div className="text-xs text-muted-foreground">
                        {formatDate(run.date)}
                      </div>
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{run.title}</span>
                        {isHardWorkout(run.type) && (
                          <Badge
                            variant="default"
                            className="text-[10px] px-1.5 py-0"
                          >
                            {workoutTypeLabel(run.type)}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-sm">
                    <span className="font-mono">
                      {formatDistance(run.distance_miles)} mi
                    </span>
                    <span className="font-mono text-muted-foreground">
                      {run.avg_pace}
                    </span>
                    {run.feel_rating && (
                      <span
                        className={cn(
                          "text-xs",
                          run.feel_rating >= 7
                            ? "text-foreground"
                            : "text-muted-foreground"
                        )}
                      >
                        {run.feel_rating}/10
                      </span>
                    )}
                  </div>
                </div>
                {run.description && (
                  <p className="mt-1.5 ml-[76px] text-xs text-muted-foreground line-clamp-2">
                    {run.description}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
