"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { WeeklyMileageChartWrapper } from "@/components/charts-wrapper";
import { GarminSync } from "@/components/garmin-sync";
import { MetricTiles } from "@/components/home/metric-tiles";
import { RacePredictions } from "@/components/home/race-predictions";
import { TodayCard, type PlanDayLite } from "@/components/home/today-card";
import type { WellnessResponse } from "@/components/home/types";
import { WeekProgress } from "@/components/home/week-progress";
import { RunDetailSheet } from "@/components/run-detail-sheet";
import { formatDate, formatDistance, localDateStr, secondsToTime } from "@/lib/format";
import type { Activity, WeeklyMileage } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "";

interface GoalData {
  description: string;
  distance: string | null;
  target_time: number | null;
  race_date: string | null;
}

interface PlanResponse {
  is_stale?: boolean;
  phase?: { label: string; phase: string } | null;
  weeks: { target_mileage: number; days: PlanDayLite[] }[];
}

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`);
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

export default function TodayPage() {
  const [loading, setLoading] = useState(true);
  const [recentRuns, setRecentRuns] = useState<Activity[]>([]);
  const [weeklyMileage, setWeeklyMileage] = useState<WeeklyMileage[]>([]);
  const [goal, setGoal] = useState<GoalData | null>(null);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [wellness, setWellness] = useState<WellnessResponse | null>(null);
  const [prs, setPrs] = useState<Record<string, number>>({});
  const [selectedRun, setSelectedRun] = useState<Activity | null>(null);

  const load = useCallback(async () => {
    const [acts, mileage, goalData, planData, wellnessData, prList] = await Promise.all([
      getJson<Activity[]>("/api/analysis/1/activities?limit=10"),
      getJson<WeeklyMileage[]>("/api/analysis/1/weekly-mileage?weeks=12"),
      getJson<GoalData>("/api/plans/1/goal"),
      getJson<PlanResponse>("/api/plans/1/current"),
      getJson<WellnessResponse>("/api/wellness/1?days=28"),
      getJson<{ distance: string; time_seconds: number }[]>("/api/analysis/1/prs"),
    ]);
    setRecentRuns((acts ?? []).map((a) => ({ ...a, splits: a.splits || [] })));
    setWeeklyMileage((mileage ?? []).map((d) => ({ ...d, planned: 0 })));
    setGoal(goalData);
    setPlan(planData);
    setWellness(wellnessData);
    setPrs(Object.fromEntries((prList ?? []).map((p) => [p.distance, p.time_seconds])));
    setLoading(false);
  }, []);

  useEffect(() => {
    const id = setTimeout(load, 0);
    return () => clearTimeout(id);
  }, [load]);

  const now = new Date();
  const greeting = now.getHours() < 12 ? "Good morning" : now.getHours() < 17 ? "Good afternoon" : "Good evening";
  const today = localDateStr();
  const planStale = !!plan?.is_stale;
  const thisWeek = planStale ? null : plan?.weeks.find((w) => w.days.some((d) => d.date === today)) ?? null;
  const todayPlan = thisWeek?.days.find((d) => d.date === today) ?? null;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{greeting}, Jake</h1>
          <p className="text-sm text-muted-foreground">
            {now.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })}
            {goal?.description && ` · ${goal.description}`}
            {plan?.phase && !planStale && plan.phase.phase !== "general" && ` · ${plan.phase.label}`}
          </p>
        </div>
        <GarminSync onNewActivities={load} />
      </div>

      {loading ? (
        <div className="space-y-3" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-28 animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
      ) : (
        <>
          <TodayCard
            today={todayPlan}
            wellness={wellness?.today ?? null}
            statusLabel={wellness?.training_status_label ?? null}
            signals={wellness?.signals ?? []}
            planStale={planStale || !plan}
          />

          {thisWeek && (
            <Card>
              <CardContent className="pt-4">
                <WeekProgress days={thisWeek.days} plannedMiles={thisWeek.target_mileage} />
              </CardContent>
            </Card>
          )}

          <MetricTiles today={wellness?.today ?? null} history={wellness?.history ?? []} />

          <RacePredictions wellness={wellness?.today ?? null} prs={prs} goal={goal} />

          <WeeklyMileageChartWrapper data={weeklyMileage} />

          <div>
            <h3 className="mb-2 text-sm font-medium">Recent Runs</h3>
            {recentRuns.length > 0 ? (
              <div className="space-y-1.5">
                {recentRuns.slice(0, 7).map((run) => (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() => setSelectedRun(run)}
                    className="flex w-full items-center justify-between gap-3 rounded-md border p-3 text-left transition-colors hover:bg-muted/50"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{run.title}</div>
                      <div className="text-xs text-muted-foreground">{formatDate(run.date)}</div>
                    </div>
                    <div className="flex shrink-0 items-center gap-3 text-sm">
                      <span className="font-mono">{formatDistance(run.distance_miles)} mi</span>
                      <span className="hidden font-mono text-muted-foreground sm:inline">{run.avg_pace}</span>
                      <span className="text-xs text-muted-foreground">{secondsToTime(run.duration_seconds)}</span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <Card>
                <CardContent className="py-6 text-center text-muted-foreground">No runs yet — sync Garmin.</CardContent>
              </Card>
            )}
          </div>
        </>
      )}

      <RunDetailSheet activity={selectedRun} open={!!selectedRun} onClose={() => setSelectedRun(null)} />
    </div>
  );
}
