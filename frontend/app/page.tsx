"use client";

import { useUnits, useAthleteToday } from "@/components/unit-preferences";
import { distanceInUnits, paceInUnits, unitLabel } from "@/lib/units";
import { primaryRunId } from "@/lib/activity-selection";
import { CoachingReview } from "@/components/coaching-review";

import { getJson, USER_ID } from "@/lib/api";
import { useCallback, useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
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
import { MileageStrip } from "@/components/home/mileage-strip";
import { RecentFeedback, runsAwaitingFeedback } from "@/components/home/recent-feedback";
import { ReadinessStrip } from "@/components/home/readiness-strip";
import { RunDetailSheet } from "@/components/run-detail-sheet";
import { formatDate } from "@/lib/format";
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
  const units = useUnits();
  const today = useAthleteToday();
  const formatDistance = (miles: number) => distanceInUnits(miles, units);
  const unit = unitLabel(units);
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
  // Each saved comment queues a run review: remount the coach panel so it sees the job and polls
  const [commentSaves, setCommentSaves] = useState(0);

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
    setSelectedRun(previous=>previous ? (acts??[]).find(a=>a.id===previous.id) || previous : null);
    setRecentRuns((acts ?? []).map((a) => ({ ...a, splits: a.splits || [] })));
    setWeeklyMileage((mileage ?? []).map((d) => ({ ...d, planned: 0 })));
    setGoal(goalData);
    setPlan(planData);
    setWellness(wellnessData);
    setPrs(Object.fromEntries((prList ?? []).map((p) => [p.distance, p.time_seconds])));
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load your dashboard"); }
    finally { setLoading(false); }
  }, []);

  const [activityError, setActivityError] = useState<string | null>(null);
  const openTodayActivity = async (id: number) => {
    setActivityError(null);
    const existing = recentRuns.find((activity) => activity.id === id);
    if (existing) { setSelectedRun(existing); return; }
    try {
      const activity = await getJson<Activity>(`/analysis/${USER_ID}/activities/${id}`);
      if (!activity) throw new Error("Could not load activity details.");
      setSelectedRun({ ...activity, splits: activity.splits || [] });
    } catch (error) { setActivityError(error instanceof Error ? error.message : "Could not load activity details."); }
  };

  useEffect(() => {
    const id = setTimeout(load, 0);
    window.addEventListener(SYNC_EVENT, load);
    return () => { clearTimeout(id); window.removeEventListener(SYNC_EVENT, load); };
  }, [load]);

  if (error) return <div role="alert" className="glass space-y-3 p-5"><p>{error}</p><Button variant="outline" size="sm" onClick={load}>Retry</Button></div>;

  const now = new Date();
  const greeting = now.getHours() < 12 ? "Good morning" : now.getHours() < 17 ? "Good afternoon" : "Good evening";
  const planStale = !!plan?.is_stale;
  const thisWeek = planStale ? null : plan?.weeks.find((w) => w.days.some((d) => d.date === today)) ?? null;
  const todayPlan = thisWeek?.days.find((d) => d.date === today) ?? null;
  const awaitingFeedback = runsAwaitingFeedback(recentRuns, today);
  const todayRunId = primaryRunId(recentRuns, today, todayPlan?.actual?.activity_id);

  const weekDone = thisWeek ? thisWeek.days.reduce((sum, d) => sum + (d.actual?.total_distance_miles ?? d.actual?.distance_miles ?? 0), 0) : null;
  const weekPct = thisWeek && thisWeek.target_mileage > 0 && weekDone != null ? Math.round((weekDone / thisWeek.target_mileage) * 100) : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 pt-1">
        <div className="min-w-0">
          <h1 className="display">
            {now.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {firstName ? `${greeting}, ${firstName}` : greeting}
            {goal?.description && ` · ${goal.description}`}
            {plan?.phase && !planStale && plan.phase.phase !== "general" && ` · ${plan.phase.label}`}
          </p>
        </div>
        <div className="flex items-end gap-5">
          {thisWeek && weekDone != null && (
            <div className="sm:text-right">
              <div className="stat-label">This week</div>
              <div className="num mt-1 text-[30px] font-semibold leading-none tracking-tight">
                {formatDistance(weekDone)}<span className="text-[15px] font-normal tracking-normal text-muted-foreground"> / {formatDistance(thisWeek.target_mileage)} {unit}</span>
                {weekPct != null && <span className="ml-2 text-[15px] font-semibold tracking-normal" style={{ color: "var(--accent-warm)" }}>{weekPct}%</span>}
              </div>
            </div>
          )}
          <GarminSync autoSync={false} />
        </div>
      </div>

      {loading ? (
        <div className="grid gap-4 lg:grid-cols-3" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="glass h-40 animate-pulse" />
          ))}
        </div>
      ) : (
        <>
          {wellness?.freshness === "stale" && wellness.as_of && (
            <p className="rounded-2xl border px-4 py-2.5 text-xs" style={{ borderColor: "color-mix(in srgb, var(--warn) 45%, transparent)", background: "var(--warn-tint)" }}>
              Today&apos;s Garmin data hasn&apos;t synced yet. Showing {wellness.as_of}; readiness is hidden until it does.
            </p>
          )}
          <MileageStrip data={weeklyMileage} />
          {/* Phone: one column in priority order. Desktop: the wireframe's wide run column + a side column. */}
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.75fr)_minmax(0,1fr)] lg:items-start">
            <div className="contents lg:block lg:min-w-0 lg:space-y-4">
              <Section label="Today" accent="var(--type-easy)" className="order-1"
                meta={todayPlan?.actual ? "done" : todayPlan && todayPlan.type !== "rest" ? `${formatDistance(todayPlan.distance_miles)} ${unit} planned` : undefined}>
                <TodayCard
                  // Remount when the day or its saved feedback changes, so local state follows the data
                  key={`${todayPlan?.date ?? "none"}-${todayPlan?.feedback?.feel_notes ?? "x"}`}
                  onFeedbackSaved={() => { setCommentSaves((n) => n + 1); load(); }}
                  onOpenActivity={openTodayActivity}
                  today={todayPlan}
                  planStale={planStale || !plan}
                  recoveryCaution={(wellness?.signals ?? []).some((s) => s.level !== "good")}
                  coach={todayRunId ? (
                    <CoachingReview
                      key={`coach-${todayRunId}-${todayPlan?.feedback?.feel_notes ?? ""}-${commentSaves}`}
                      activityId={todayRunId} onPlanChanged={load} presentation="today" showLabel={false} />
                  ) : undefined}
                />
                {activityError && <p role="alert" className="mx-4 mb-3 text-xs text-destructive">{activityError}</p>}
                {awaitingFeedback.length > 0 && (
                  <div className="mx-4 mb-4"><RecentFeedback days={awaitingFeedback} onSaved={() => { setCommentSaves((n) => n + 1); load(); }} /></div>
                )}
              </Section>
              {thisWeek && (
                <Section label="This week" accent="var(--type-threshold)" className="order-2" meta="tap a day">
                  <Card className="py-0">
                    <CardContent className="pb-4">
                      <WeekProgress days={thisWeek.days} />
                    </CardContent>
                  </Card>
                </Section>
              )}
              <Panel label="Recent runs" className="order-6" meta={recentRuns.length ? `${Math.min(recentRuns.length, 5)} latest` : undefined} bodyClassName="px-3 pb-3 pt-2 sm:px-3">
                {recentRuns.length > 0 ? (
                  <ul className="space-y-1.5">
                    {recentRuns.slice(0, 5).map((run) => {
                      const kind = activityKind(run.session?.category === "fartlek" || run.session?.category === "speed" ? "intervals" : run.session?.category ?? run.type, run.title);
                      const pace = run.avg_pace ? paceInUnits(run.avg_pace.replace(/\/mi$/, ""), units) : null;
                      return (
                        <li key={run.id}>
                          <button type="button" onClick={() => setSelectedRun(run)}
                            className="glass-tile lift block w-full px-3.5 py-2.5 text-left focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary">
                            <span className="flex min-w-0 items-center gap-2 text-sm font-semibold">
                              <span aria-hidden="true" className="dot" style={{ background: `var(--type-${kind})` }} />
                              <span className="truncate">{run.session?.title ?? run.title}</span>
                              {run.type === "walk" ? <span className="text-xs font-normal text-muted-foreground">walk</span> : kind !== "easy" && <KindPill kind={kind} />}
                            </span>
                            <span className="num mt-0.5 block pl-4 text-xs text-muted-foreground">
                              {formatDate(run.date).replace(/^\w+, /, "")} · {formatDistance(run.distance_miles)} {unit}{pace ? ` · ${pace} pace` : ""}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="py-6 text-center text-sm text-muted-foreground">No runs yet — sync Garmin.</p>
                )}
              </Panel>
            </div>

            <div className="contents lg:block lg:min-w-0 lg:space-y-4">
              <Section label="Recovery" accent="var(--type-support)" className="order-3" meta="Garmin · tap a tile for its trend">
                <div className="space-y-2">
                  <ReadinessStrip wellness={wellness?.today ?? null} signals={wellness?.signals ?? []}
                    mileageRisk={planStale ? null : plan?.athlete?.injury_risk} />
                  <MetricTiles today={wellness?.latest ?? null} history={wellness?.history ?? []} />
                </div>
              </Section>
              <Section label="Weekly mileage" accent="var(--type-long)" className="order-4" meta="12 weeks">
                <WeeklyMileageChartWrapper data={weeklyMileage} showTitle={false} />
              </Section>
              <Section label="Race predictions" accent="var(--type-race)" className="order-5" meta="Garmin · current fitness">
                <RacePredictions wellness={wellness?.latest ?? null} prs={prs} goal={goal} />
              </Section>
            </div>
          </div>
        </>
      )}

      <RunDetailSheet activity={selectedRun} open={!!selectedRun} onClose={() => setSelectedRun(null)} onClassificationChanged={load} />
    </div>
  );
}
