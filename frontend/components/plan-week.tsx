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
      <div className="glass grid grid-cols-7 gap-1 rounded-[22px] p-2" aria-label={`Week ${week.week_number} session overview`}>
        {week.workouts.map((w) => <button key={w.id} type="button" onClick={() => {
          setExpandedId(w.id);
          requestAnimationFrame(() => {
            const row=document.getElementById(`session-${w.id}`);
            row?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'center'});
            row?.focus({preventScroll:true});
          });
        }} aria-expanded={expandedId===w.id} aria-label={`${w.date}: ${w.title}, ${distanceInUnits(w.distance_miles, units)} ${unitLabel(units)}. Show session.`} className="group flex min-h-20 flex-col items-center justify-end gap-1 rounded-xl p-1 hover:bg-[var(--row-hover)] focus-visible:outline-2 focus-visible:outline-primary">
          <span className="font-mono text-[10px] tabular-nums text-muted-foreground">{w.distance_miles>0?distanceInUnits(w.distance_miles, units):"—"}</span>
          <span aria-hidden="true" className={`w-full max-w-6 rounded-sm ${w.type==='workout'?'bg-[var(--accent-warm)]':w.type==='long_run'?'bg-[var(--accent-warm)]/60':w.type==='rest'?'bg-border':'bg-foreground/30'}`} style={{height:Math.max(4,Math.min(36,w.distance_miles*3))}} />
          <span className="text-[10px] font-medium text-muted-foreground">{new Date(w.date+"T12:00:00").toLocaleDateString("en-US",{weekday:"short"})}</span>
        </button>)}
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
