"use client";

import { getJson, USER_ID } from "@/lib/api";
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


interface GoalData {
  description: string;
  distance: string | null;
  target_time: number | null;
  race_date: string | null;
}

interface PlanResponse {
  is_stale?: boolean;
  athlete?: { injury_risk?: string | null };
  phase?: { label: string; phase: string } | null;
  weeks: { target_mileage: number; days: PlanDayLite[] }[];
}

export default function TodayPage() {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [recentRuns, setRecentRuns] = useState<Activity[]>([]);
  const [weeklyMileage, setWeeklyMileage] = useState<WeeklyMileage[]>([]);
  const [goal, setGoal] = useState<GoalData | null>(null);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [wellness, setWellness] = useState<WellnessResponse | null>(null);
  const [prs, setPrs] = useState<Record<string, number>>({});
  const [selectedRun, setSelectedRun] = useState<Activity | null>(null);
  const [firstName, setFirstName] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
    setError(null);
    const [acts, mileage, goalData, planData, wellnessData, prList, user] = await Promise.all([
      getJson<Activity[]>(`/analysis/${USER_ID}/activities?limit=10`),
      getJson<WeeklyMileage[]>(`/analysis/${USER_ID}/weekly-mileage?weeks=12`),
      getJson<GoalData>(`/plans/${USER_ID}/goal`),
      getJson<PlanResponse>(`/plans/${USER_ID}/current`, { allowNotFound: true }),
      getJson<WellnessResponse>(`/wellness/${USER_ID}?days=28`),
      getJson<{ distance: string; time_seconds: number }[]>(`/analysis/${USER_ID}/prs`),
      getJson<{ name: string | null }>(`/users/${USER_ID}`),
    ]);
    setFirstName(user?.name?.split(" ")[0] ?? null);
    setRecentRuns((acts ?? []).map((a) => ({ ...a, splits: a.splits || [] })));
    setWeeklyMileage((mileage ?? []).map((d) => ({ ...d, planned: 0 })));
    setGoal(goalData);
    setPlan(planData);
    setWellness(wellnessData);
    setPrs(Object.fromEntries((prList ?? []).map((p) => [p.distance, p.time_seconds])));
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load your dashboard"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const id = setTimeout(load, 0);
    return () => clearTimeout(id);
  }, [load]);

  if (error) return <div role="alert" className="space-y-3"><p>{error}</p><button className="underline" onClick={load}>Retry</button></div>;

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
          <h1 className="text-xl font-semibold">{firstName ? `${greeting}, ${firstName}` : greeting}</h1>
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
            // Remount when the day or its saved feedback changes, so local state follows the data
            key={`${todayPlan?.date ?? "none"}-${todayPlan?.feedback?.feel_rating ?? "x"}`}
            onFeedbackSaved={load}
            today={todayPlan}
            wellness={wellness?.today ?? null}
            statusLabel={wellness?.training_status_label ?? null}
            signals={wellness?.signals ?? []}
            planStale={planStale || !plan}
            mileageRisk={planStale ? null : plan?.athlete?.injury_risk}
          />

          {thisWeek && (
            <Card>
              <CardContent className="pt-4">
                <WeekProgress days={thisWeek.days} plannedMiles={thisWeek.target_mileage} />
              </CardContent>
            </Card>
          )}

          {wellness?.freshness === "stale" && wellness.as_of && (
            <p className="text-xs text-muted-foreground">
              Today&apos;s Garmin data hasn&apos;t synced yet. Showing {wellness.as_of}; readiness is hidden until it does.
            </p>
          )}
          <MetricTiles today={wellness?.latest ?? null} history={wellness?.history ?? []} />

          <RacePredictions wellness={wellness?.latest ?? null} prs={prs} goal={goal} />
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
