"use client";

import { useEffect, useState } from "react";
import { getJson, USER_ID } from "@/lib/api";
import { PlanDay } from "@/components/plan-day";
import { RunDetailBody } from "@/components/run-detail-sheet";
import type { Units } from "@/lib/units";
import type { Activity, Workout } from "@/lib/types";

/**
 * A Plan day. Once run, it reads like the run sheet on Today (hero distance, Garmin tiles, laps,
 * notes, run review) with the plan comparison and the day's feedback in the right-hand column.
 * Days not run yet keep the plain planned-session view.
 */
export function PlanDayDetail({ workout, units, readOnly, isToday, sessionAction, onPlanChanged, revision }: {
  workout: Workout;
  units: Units;
  readOnly?: boolean;
  isToday: boolean;
  sessionAction?: "move";
  onPlanChanged?: () => void;
  /** Changes whenever the plan is re-fetched, so the run (comment, laps, review) re-loads too */
  revision?: number;
}) {
  const activityId = workout.actual?.activity_id;
  const [loaded, setLoaded] = useState<Activity | null>(null);
  useEffect(() => {
    if (!activityId) return;
    let live = true;
    getJson<Activity>(`/analysis/${USER_ID}/activities/${activityId}`)
      .then((a) => { if (live) setLoaded(a); })
      .catch(() => { if (live) setLoaded(null); });  // the plan view below still shows the day
    return () => { live = false; };
  }, [activityId, revision]);
  const activity = loaded && loaded.id === activityId ? loaded : null;

  const day = <PlanDay workout={workout} units={units} sessionAction={sessionAction} readOnly={readOnly}
    isToday={isToday} expanded pinned hideRunStats={!!activity} onPlanChanged={onPlanChanged} />;
  if (!activity) return day;
  return <RunDetailBody activity={activity} aside={<section aria-label="Planned and ran">{day}</section>}
    showFeedback={false} onChanged={onPlanChanged} className="px-0 sm:px-0" />;
}
