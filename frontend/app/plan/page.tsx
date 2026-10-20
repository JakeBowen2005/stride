"use client";

import { distanceInUnits, paceInUnits, unitLabel, type Units } from "@/lib/units";
import { apiUrl, getJson, USER_ID } from "@/lib/api";
import { loadPlanState, nextBlockAvailable } from "@/lib/plan-state";
import { useState, useEffect, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PlanWeek } from "@/components/plan-week";
import { formatDateShort, localDateStr } from "@/lib/format";
import type { PlanWeek as PlanWeekType, Workout, WeekPhaseInfo } from "@/lib/types";


interface ApiPlanDay {
  date: string;
  day: string;
  type: string;
  title: string;
  description: string | null;
  purpose: string | null;
  distance_miles: number;
  warmup: string | null;
  cooldown: string | null;
  prescribed?: boolean;
  session_status?: Workout["session_status"];
  moved_to?: string | null;
  adjustment_note?: string | null;
  actual?: {
    distance_miles: number;
    avg_pace: string | null;
    duration_seconds: number;
    average_heartrate: number | null;
    description: string | null;
    feel_rating: number | null;
    name: string | null;
    activity_count?: number;
    activities?: { name: string; distance_miles: number; avg_pace: string | null; duration_seconds: number }[];
  } | null;
  comparison?: {
    distance_diff_miles: number;
    summary: string;
  } | null;
  feedback?: {
    feel_rating: number | null;
    feel_notes: string | null;
    pace_assessment: string | null;
    swapped: boolean;
    swap_reason: string | null;
    actual_workout_type: string | null;
    coach_response: string | null;
    evaluation?: { decision: string; reason: string; evidence: string } | null;
  } | null;
}

interface ApiWeek {
  week_number: number;
  target_mileage: number;
  actual_mileage?: number;
  phase?: WeekPhaseInfo | null;
  days: ApiPlanDay[];
}

interface ApiPlan {
  id: number;
  preview?: boolean;
  start_date: string;
  end_date: string;
  block_number: number;
  is_deload: boolean;
  is_stale?: boolean;
  phase?: WeekPhaseInfo | null;
  load?: {
    baseline: number;
    destination: number | null;
    mode: string;
    weekly_budgets: number[];
    reasons: string[];
    recent_week_miles?: number | null;
    planning_anchor?: number | null;
  } | null;
  assessment?: { decision: string | null; reasons: string[] } | null;
  weeks: ApiWeek[];
  pacing_guide: Record<string, string>;
  notes: string[];
  goal: {
    type: string;
    distance: string;
    target_time: number | null;
    race_date: string | null;
    description: string;
  };
  athlete: {
    name: string;
    current_weekly_mileage: number;
    peak_weekly_mileage: number;
    experience_level: string;
    injury_risk: string;
  };
}

function mapApiToWeek(apiWeek: ApiWeek): PlanWeekType {
  return {
    week_number: apiWeek.week_number,
    total_miles: apiWeek.target_mileage,
    actual_miles: apiWeek.actual_mileage,
    phase: apiWeek.phase ?? null,
    workouts: apiWeek.days.map((d, i) => ({
      id: apiWeek.week_number * 100 + i,
      date: d.date,
      type: d.type as Workout["type"],
      title: d.title,
      description: d.description,
      purpose: d.purpose,
      distance_miles: d.distance_miles,
      warmup: d.warmup || undefined,
      cooldown: d.cooldown || undefined,
      completed: !!d.actual,
      skipped: d.session_status === "skipped",
      session_status: d.session_status,
      moved_to: d.moved_to,
      prescribed: d.prescribed !== false,
      actual: d.actual || null,
      comparison: d.comparison || null,
      feedback: d.feedback || null,
      adjustment_note: d.adjustment_note ?? null,
    })),
  };
}

const MODE_LABEL: Record<string, string> = {
  build: "Building", hold: "Holding steady", reduce: "Easing back", recovery: "Recovery block",
  deload: "Deload included", start: "Getting started",
};

function BlockSummary({ plan, units }: { plan: ApiPlan; units: Units }) {
  const distance = (miles: number) => distanceInUnits(miles, units);
  const unit = unitLabel(units);
  const load = plan.load!;
  return (
    <Card><CardContent className="space-y-3 pt-4 text-sm">
      <h3 className="font-medium">This block: {MODE_LABEL[load.mode] ?? load.mode}</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {plan.weeks.map((week) => {
          const logged = week.days.reduce((sum, d) => sum + (d.actual?.distance_miles ?? (d.prescribed === false ? d.distance_miles : 0)), 0);
          const remaining = week.days.filter((d) => d.prescribed !== false && !d.actual).reduce((sum, d) => sum + d.distance_miles, 0);
          return <div key={week.week_number} className="rounded-md bg-muted/50 p-3">
            <p className="text-xs text-muted-foreground">Week {week.week_number} · {formatDateShort(week.days[0].date)}–{formatDateShort(week.days[week.days.length - 1].date)}</p>
            <p className="font-mono">{distance(logged + remaining)} {unit} {logged > 0 ? "total" : "planned"}</p>
            {logged > 0 && <p className="text-xs text-muted-foreground">{distance(logged)} logged · {distance(remaining)} remaining</p>}
          </div>;
        })}
      </div>
      <p className="text-muted-foreground">
        {load.recent_week_miles != null && `Last full week ${distance(load.recent_week_miles)} ${unit} · `}
        Four-week average {distance(load.baseline)} {unit}/week
        {load.destination ? ` · goal ${distance(load.destination)} ${unit}/week` : ""}
      </p>
      {plan.assessment?.reasons?.map((reason) => <p key={reason} className="text-muted-foreground">{reason}</p>)}
    </CardContent></Card>
  );
}

/** Rows for the pacing guide; falls back to the old keys on plans generated before Oct 2026. */
function pacingRows(g: Record<string, string>): [string, string, string][] {
  const rows: [string, string, string | undefined][] = [
    ["Easy", "conversational", g.easy],
    ["Steady", "long-run finishes", g.steady],
    ["Tempo", "continuous", g.tempo ?? g.current_tempo],
    ["Threshold reps", "e.g. 2x10min", g.threshold_reps ?? g.current_threshold],
    ["Intervals", "800m-mile reps", g.intervals ?? g.current_interval],
    ["Goal race", "target", g.goal_race_pace],
  ];
  return rows.filter((r): r is [string, string, string] => !!r[2]);
}

export default function PlanPage() {
  const [units, setUnits] = useState<Units>("miles");
  const [plan, setPlan] = useState<ApiPlan | null>(null);
  const [activePlan, setActivePlan] = useState<ApiPlan | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noPlan, setNoPlan] = useState(false);
  const [showPast, setShowPast] = useState(false);

  useEffect(() => {
    getJson<{ units: Units }>(`/users/${USER_ID}`).then((u) => { if (u) setUnits(u.units); }).catch((e) => setError(e instanceof Error ? e.message : "Could not load display preferences."));
  }, []);

  const fetchPlan = useCallback(async () => {
    try {
      setError(null);
      const state = await loadPlanState<ApiPlan>();
      setActivePlan(state.active);
      setPlan(state.visible);
      setNoPlan(!state.visible);
    } catch {
      setError("Failed to connect to server");
    } finally {
      setLoading(false);
    }
  }, []);

  const generatePlan = useCallback(async (lighter = false, scope: "current" | "next" = "current") => {
    setGenerating(true);
    setError(null);
    try {
      const res = await fetch(apiUrl(`/plans/${USER_ID}/preview`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lighter, scope }),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || "Failed to generate plan");
        return;
      }
      setNotice(null);
      await fetchPlan();
    } catch {
      setError("Failed to connect to server");
    } finally {
      setGenerating(false);
    }
  }, [fetchPlan]);

  async function finishPreview(action: "approve" | "discard") {
    if (!plan) return;
    setGenerating(true);
    try {
      const res = await fetch(apiUrl(`/plans/${USER_ID}/drafts/${plan.id}/${action}`), { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not save your choice");
      await fetchPlan();
      setNotice(action === "approve" ? "Plan approved. Your training block is active." : "Preview discarded. Your current plan is unchanged.");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not reach Stride"); }
    finally { setGenerating(false); }
  }

  useEffect(() => {
    const id = setTimeout(fetchPlan, 0);
    return () => clearTimeout(id);
  }, [fetchPlan]);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold">Current Plan</h1>
        <div className="py-20 text-center text-muted-foreground">
          Loading your plan...
        </div>
      </div>
    );
  }

  if (noPlan) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold">Current Plan</h1>
        {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground mb-4">No plan yet. Generate your first training plan.</p>
            <Button onClick={() => generatePlan()} disabled={generating}>
              {generating ? "Generating..." : "Generate Your First Plan"}
            </Button>
            {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!plan) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold">Current Plan</h1>
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {error || "No plan available"}
          </CardContent>
        </Card>
      </div>
    );
  }

  const weeks: PlanWeekType[] = plan.weeks.map(mapApiToWeek);

  const today = localDateStr();
  const currentWeekIndex = weeks.findIndex((w) =>
    w.workouts.some((wo) => wo.date >= today)
  );
  // Weeks fully in the past are tucked away so the plan opens on this week
  const pastWeeks = currentWeekIndex > 0 ? weeks.slice(0, currentWeekIndex) : [];
  const visibleWeeks = currentWeekIndex > 0 ? weeks.slice(currentWeekIndex) : weeks;

  if (plan.is_stale) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold">Current Plan</h1>
        {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
        <Card>
          <CardContent className="space-y-3 py-8 text-center">
            <p className="font-medium">Your last training block ended {formatDateShort(plan.end_date)}.</p>
            <p className="mx-auto max-w-sm text-sm text-muted-foreground">
              Generate a fresh 2-week block. It&apos;s built from your latest Garmin runs, current fitness and{" "}
              {plan.goal.race_date ? "where you are relative to race day" : "your goal"}.
            </p>
            <Button onClick={() => generatePlan(false, "next")} disabled={generating}>
              {generating ? "Building your plan…" : "Generate this week's plan"}
            </Button>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <button
              className="block w-full text-xs text-muted-foreground underline underline-offset-2"
              onClick={() => setShowPast((v) => !v)}
            >
              {showPast ? "Hide" : "Show"} last block
            </button>
          </CardContent>
        </Card>
        {showPast &&
          weeks.map((week) => <PlanWeek units={units} key={week.week_number} week={week} isCurrent={false} />)}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Current Plan</h1>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">
            {plan.goal.description}
          </span>
          <span>&middot;</span>
          <span>
            {formatDateShort(plan.start_date)} &ndash;{" "}
            {formatDateShort(plan.end_date)}
          </span>
          {plan.phase && plan.phase.phase !== "general" && (
            <>
              <span>&middot;</span>
              <Badge variant={plan.phase.phase === "race_week" ? "default" : "secondary"} className="text-xs">
                {plan.phase.label}
              </Badge>
            </>
          )}
          {plan.goal.race_date && (
            <>
              <span>&middot;</span>
              <span>Race {formatDateShort(plan.goal.race_date)}</span>
            </>
          )}
          {plan.is_deload && (
            <>
              <span>&middot;</span>
              <Badge variant="secondary" className="text-xs">
                Deload
              </Badge>
            </>
          )}
        </div>
      </div>

      {error && <p role="alert" className="text-destructive">{error}</p>}
      {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
      {plan.preview && <Card><CardContent className="space-y-3 pt-4">
        <h2 className="font-semibold">Review this block before starting</h2>
        <p className="text-sm text-muted-foreground">Your current plan stays active until you approve. Make it lighter reduces volume, keeping workout paces unchanged.</p>
        <div className="flex flex-wrap gap-2">
          <Button disabled={generating} onClick={() => finishPreview("approve")}>Approve</Button>
          <Button variant="outline" disabled={generating} onClick={() => generatePlan(true)}>Make it lighter</Button>
          {activePlan && !activePlan.is_stale && <Button variant="ghost" disabled={generating} onClick={() => finishPreview("discard")}>Keep current plan</Button>}
        </div>
      </CardContent></Card>}
      {!plan.preview && <p className="text-sm text-muted-foreground">Approved block · log your runs and feel ratings to adjust it as you go.</p>}
      {plan.load && <BlockSummary plan={plan} units={units} />}

      {pastWeeks.length > 0 && (
        <button
          className="text-xs text-muted-foreground underline underline-offset-2"
          onClick={() => setShowPast((v) => !v)}
        >
          {showPast ? "Hide" : "Show"} {pastWeeks.length} completed week{pastWeeks.length > 1 ? "s" : ""}
        </button>
      )}
      {showPast &&
        pastWeeks.map((week) => (
          <PlanWeek units={units} key={week.week_number} week={week} isCurrent={false} onPlanChanged={() => fetchPlan()} />
        ))}

      {visibleWeeks.map((week, i) => (
        <PlanWeek
          units={units}
          key={week.week_number}
          week={week}
          readOnly={!!plan.preview}
          isCurrent={i === 0 && currentWeekIndex >= 0}
          onPlanChanged={() => {
            setLoading(true);
            fetchPlan();
          }}
        />
      ))}

      {plan.notes.length > 0 && (
        <Card>
          <CardContent className="pt-4">
            <h3 className="text-sm font-medium">Plan Notes</h3>
            <div className="mt-1 space-y-1">
              {plan.notes.map((note, i) => (
                <p key={i} className="text-sm leading-relaxed text-muted-foreground">
                  {note}
                </p>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
      {!plan.preview && <details className="rounded-md border p-4 text-sm">
        <summary className="cursor-pointer font-medium">Plan options</summary>
        <div className="mt-3 space-y-3">
          <p className="text-muted-foreground">Need to revise this block? Review a replacement using your latest training. Your approved sessions stay active until you approve the revision.</p>
          <Button variant="outline" disabled={generating} onClick={() => generatePlan()}>Review revised current block</Button>
          {nextBlockAvailable(plan.end_date, today) ? <div>
            <p className="mb-2 text-muted-foreground">Your next block starts after {formatDateShort(plan.end_date)}.</p>
            <Button disabled={generating} onClick={() => generatePlan(false, "next")}>Preview next block</Button>
          </div> : <p className="text-muted-foreground">When this block ends, review the next one using your latest runs and feedback.</p>}
        </div>
      </details>}
      {/* Pacing Guide — the same numbers the workouts below use */}
      <Card>
        <CardContent className="pt-4">
          <h3 className="mb-2 text-sm font-medium">Pacing Guide</h3>
          <div className="space-y-1 text-sm">
            {pacingRows(plan.pacing_guide).map(([label, hint, value]) => (
              <div key={label} className="flex items-baseline justify-between gap-3">
                <span className="text-muted-foreground">
                  {label} <span className="text-xs">· {hint}</span>
                </span>
                <span className="shrink-0 font-mono">{paceInUnits(value, units)}/{unitLabel(units)}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

    </div>
  );
}
