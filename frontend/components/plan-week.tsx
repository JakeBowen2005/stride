"use client";

import { useState } from "react";
import { PlanDay } from "@/components/plan-day";
import { formatDistance } from "@/lib/format";
import type { PlanWeek as PlanWeekType } from "@/lib/types";

interface PlanWeekProps {
  week: PlanWeekType;
  isCurrent: boolean;
}

export function PlanWeek({ week, isCurrent }: PlanWeekProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const today = new Date().toISOString().split("T")[0];

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
          />
        ))}
      </div>
    </div>
  );
}
