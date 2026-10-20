"use client";

import { CoachingReview } from "@/components/coaching-review";

import { getJson, USER_ID } from "@/lib/api";
import { useCallback, useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Panel, Section } from "@/components/cockpit/panel";
import { KindPill } from "@/components/cockpit/pill";
import { activityKind } from "@/lib/workout-style";
import { WeeklyMileageChartWrapper } from "@/components/charts-wrapper";
import { GarminSync, SYNC_EVENT } from "@/components/garmin-sync";
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
    window.addEventListener(SYNC_EVENT, load);
    return () => { clearTimeout(id); window.removeEventListener(SYNC_EVENT, load); };
  }, [load]);

  if (error) return <div role="alert" className="space-y-3"><p>{error}</p><button className="underline" onClick={load}>Retry</button></div>;

  const now = new Date();
  const greeting = now.getHours() < 12 ? "Good morning" : now.getHours() < 17 ? "Good afternoon" : "Good evening";
  const today = localDateStr();
  const planStale = !!plan?.is_stale;
  const todayRun = recentRuns.find(run => run.date.startsWith(today));
  const thisWeek = planStale ? null : plan?.weeks.find((w) => w.days.some((d) => d.date === today)) ?? null;
  const todayPlan = thisWeek?.days.find((d) => d.date === today) ?? null;

  const weekDone = thisWeek ? thisWeek.days.reduce((sum, d) => sum + (d.actual?.distance_miles ?? 0), 0) : null;
  const weekPct = thisWeek && thisWeek.target_mileage > 0 && weekDone != null ? Math.round((weekDone / thisWeek.target_mileage) * 100) : null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="font-heading text-2xl font-black italic tracking-tight">
            {now.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}
          </h1>
          <p className="text-sm text-muted-foreground">
            {firstName ? `${greeting}, ${firstName}` : greeting}
            {goal?.description && ` · ${goal.description}`}
            {plan?.phase && !planStale && plan.phase.phase !== "general" && ` · ${plan.phase.label}`}
          </p>
        </div>
        <div className="flex items-end gap-5">
          {thisWeek && weekDone != null && (
            <div className="text-right">
              <div className="stat-label">This week</div>
              <div className="num text-2xl font-semibold leading-none">
                {formatDistance(weekDone)}<span className="text-base font-normal text-muted-foreground"> / {formatDistance(thisWeek.target_mileage)} mi</span>
                {weekPct != null && <span className="ml-2 text-sm font-medium" style={{ color: "var(--type-easy)" }}>{weekPct}%</span>}
              </div>
            </div>
          )}
          <GarminSync onNewActivities={load} />
        </div>
      </div>

      {loading ? (
        <div className="grid gap-3 lg:grid-cols-3" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-md bg-muted" />
          ))}
        </div>
      ) : (
        <>
          {wellness?.freshness === "stale" && wellness.as_of && (
            <p className="rounded-md border px-3 py-2 text-xs" style={{ borderColor: "var(--warn)", background: "var(--warn-tint)", color: "var(--warn)" }}>
              Today&apos;s Garmin data hasn&apos;t synced yet. Showing {wellness.as_of}; readiness is hidden until it does.
            </p>
          )}
          <div className="grid gap-3 xl:grid-cols-[minmax(0,340px)_minmax(0,1fr)_minmax(0,300px)] lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
            <div className="space-y-3">
              <Section label="Today's run" accent="var(--type-easy)" meta={todayPlan ? `${formatDistance(todayPlan.distance_miles)} mi planned` : undefined}>
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
              </Section>
              {todayRun && <Section label="Coach review" accent="var(--type-intervals)">
                <CoachingReview
                  key={`coach-${todayRun.id}-${todayRun.feel_rating}-${todayRun.notes}`}
                  activityId={todayRun.id} onPlanChanged={load} />
              </Section>}
            </div>

            <div className="min-w-0 space-y-3">
              <Section label="Recovery" accent="var(--type-support)" meta="Garmin · 28 days">
                <MetricTiles today={wellness?.latest ?? null} history={wellness?.history ?? []} />
              </Section>
              <Section label="Weekly mileage" accent="var(--type-long)" meta="12 weeks">
                <WeeklyMileageChartWrapper data={weeklyMileage} />
              </Section>
            </div>

            <div className="min-w-0 space-y-3 lg:col-span-2 xl:col-span-1">
              <Section label="Race predictions" accent="var(--type-race)" meta="Garmin">
                <RacePredictions wellness={wellness?.latest ?? null} prs={prs} goal={goal} />
              </Section>
              {thisWeek && (
                <Section label="This week" accent="var(--type-threshold)">
                  <Card>
                    <CardContent className="pt-1">
                      <WeekProgress days={thisWeek.days} plannedMiles={thisWeek.target_mileage} />
                    </CardContent>
                  </Card>
                </Section>
              )}
            </div>
          </div>

          <Panel label="Recent runs" meta={recentRuns.length ? `${Math.min(recentRuns.length, 7)} latest` : undefined} bodyClassName="p-0">
            {recentRuns.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th scope="col">Date</th><th scope="col">Run</th><th scope="col" className="r">Dist</th><th scope="col" className="r">Pace</th><th scope="col" className="r">Time</th><th scope="col">Type</th></tr></thead>
                  <tbody>
                    {recentRuns.slice(0, 7).map((run) => (
                      <tr key={run.id} className="cursor-pointer" onClick={() => setSelectedRun(run)}>
                        <td className="whitespace-nowrap text-muted-foreground">{formatDate(run.date)}</td>
                        <td className="max-w-[16rem] truncate font-medium">
                          <button type="button" className="max-w-full truncate text-left hover:underline focus-visible:outline-2 focus-visible:outline-primary"
                            onClick={(e) => { e.stopPropagation(); setSelectedRun(run); }}>{run.title}</button>
                        </td>
                        <td className="r">{formatDistance(run.distance_miles)}</td>
                        <td className="r">{run.avg_pace || "—"}</td>
                        <td className="r">{secondsToTime(run.duration_seconds)}</td>
                        <td><KindPill kind={activityKind(run.type, run.title)} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="py-6 text-center text-muted-foreground">No runs yet — sync Garmin.</p>
            )}
          </Panel>
        </>
      )}

      <RunDetailSheet activity={selectedRun} open={!!selectedRun} onClose={() => setSelectedRun(null)} />
    </div>
  );
}
