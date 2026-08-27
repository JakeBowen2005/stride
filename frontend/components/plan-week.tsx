"use client";

import { useState } from "react";
import { PlanDay } from "@/components/plan-day";
import { formatDistance, localDateStr } from "@/lib/format";
import type { PlanWeek as PlanWeekType } from "@/lib/types";

interface PlanWeekProps {
  week: PlanWeekType;
  isCurrent: boolean;
  onPlanChanged?: () => void;
}

export function PlanWeek({ week, isCurrent, onPlanChanged }: PlanWeekProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const today = localDateStr();

  const hasActuals = week.actual_miles !== undefined && week.actual_miles > 0;

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium">
          Week {week.week_number}
          {isCurrent && (
            <span className="ml-2 text-xs text-muted-foreground">(current)</span>
          )}
        </h3>
        <span className="font-mono text-sm text-muted-foreground">
          {formatDistance(week.total_miles)} mi planned
          {hasActuals && (
            <> / {formatDistance(week.actual_miles!)} mi actual</>
          )}
        </span>
      </div>
      <div className="space-y-1.5">
        {week.workouts.map((w) => (
          <PlanDay
            key={w.id}
            workout={w}
            isToday={w.date === today}
            expanded={expandedId === w.id}
            onToggle={() =>
              setExpandedId(expandedId === w.id ? null : w.id)
            }
            onPlanChanged={onPlanChanged}
          />
        ))}
      </div>
    </div>
  );
}
