"use client";

import { distanceInUnits, unitLabel, type Units } from "@/lib/units";
import { useState } from "react";
import { PlanDay } from "@/components/plan-day";
import { localDateStr } from "@/lib/format";
import type { PlanWeek as PlanWeekType } from "@/lib/types";

interface PlanWeekProps {
  week: PlanWeekType;
  units?: Units;
  isCurrent: boolean;
  onPlanChanged?: () => void;
  readOnly?: boolean;
}

export function PlanWeek({ week, isCurrent, onPlanChanged, readOnly, units = "miles" }: PlanWeekProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const today = localDateStr();

  const hasActuals = week.actual_miles !== undefined && week.actual_miles > 0;

  return (
    <div className="space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium">
            Week {week.week_number}
            {isCurrent && (
              <span className="ml-2 text-xs text-muted-foreground">(current)</span>
            )}
          </h3>
          {week.phase && week.phase.phase !== "general" && (
            <p className="text-xs text-muted-foreground">
              {week.phase.label}
              {week.phase.back_to_back && " · back-to-back weekend"}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end font-mono text-xs text-muted-foreground sm:flex-row sm:gap-1 sm:text-sm">
          <span>{distanceInUnits(week.total_miles, units)} {unitLabel(units)} planned</span>
          {hasActuals && (
            <span>
              <span className="hidden sm:inline">/ </span>
              {distanceInUnits(week.actual_miles!, units)} {unitLabel(units)} actual
            </span>
          )}
        </div>
      </div>
      <div className="space-y-1.5">
        {week.workouts.map((w) => (
          <PlanDay
            key={w.id}
            workout={w}
            units={units}
            readOnly={readOnly}
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
