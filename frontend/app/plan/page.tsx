"use client";
import { useAthleteToday } from "@/components/unit-preferences";

import { CoachingReview } from "@/components/coaching-review";
import { describeSchedule, scheduleChanged, type SchedulePreferences } from "@/lib/plan-preferences";
import type { AthletePreferences } from "@/components/profile-preferences";
import { PlanOptionsDialog } from "@/components/plan-options-dialog";

import { distanceInUnits, paceInUnits, unitLabel, type Units } from "@/lib/units";
import { apiUrl, getJson, USER_ID } from "@/lib/api";
import { loadPlanState, nextBlockAvailable } from "@/lib/plan-state";
import { useState, useEffect, useCallback, useSyncExternalStore } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PlanWeek } from "@/components/plan-week";
import { BlockReviewPanel, GoalRoute, type BlockReview, type Outlook } from "@/components/goal-route";
import { PlanDay } from "@/components/plan-day";
import { Panel, StatCell } from "@/components/cockpit/panel";
import { PlanCalendar } from "@/components/cockpit/plan-calendar";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { SYNC_EVENT } from "@/components/garmin-sync";
import { formatDateShort } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ExecutedWorkout, PlanWeek as PlanWeekType, Workout, WeekPhaseInfo } from "@/lib/types";


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
  prescription?: Workout["prescription"];
  walks?: import("@/lib/types").ActivityLine[];
  actual?: {
    workout?: ExecutedWorkout | null;
    distance_miles: number;
    avg_pace: string | null;
    duration_seconds: number;
    average_heartrate: number | null;
    description: string | null;
    feel_rating: number | null;
    name: string | null;
    activity_count?: number;
    total_distance_miles?: number;
    other_runs?: import("@/lib/types").ActivityLine[];
    walks?: import("@/lib/types").ActivityLine[];
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
  /** "schedule": only run days changed, so only the touched days moved. */
  revision?: "schedule";
  /** One plain line per week comparing this draft with the approved block. */
  change_summary?: string[];
  changes?: { date: string; before: string; after: string; reason: string }[];
  quality_policy?: { stage: string } | null;
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
  outlook?: Outlook | null;
  review?: BlockReview | null;
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
    baseline_as_of?: string;
    baseline_definition?: string;
    schedule_preferences?: SchedulePreferences;
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
      walks: d.walks ?? [],
      comparison: d.comparison || null,
      feedback: d.feedback || null,
      adjustment_note: d.adjustment_note ?? null,
      prescription: d.prescription ?? null,
    })),
  };
}

const MODE_LABEL: Record<string, string> = {
  build: "Building", hold: "Holding steady", reduce: "Easing back", recovery: "Recovery block",
  deload: "Deload included", start: "Getting started",
};

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

// Desktop shows the selected day in a side sheet; phones keep it inline under the calendar.
const DESKTOP_QUERY = "(min-width: 1024px)";
function subscribeDesktop(onChange: () => void) {
  const query = window.matchMedia(DESKTOP_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

export default function PlanPage() {
  const today=useAthleteToday();
  const [currentPreferences, setCurrentPreferences] = useState<AthletePreferences | null>(null);
  const [moveRequest, setMoveRequest] = useState<{ date: string; nonce: number } | null>(null);
  const [units, setUnits] = useState<Units>("miles");
  const [plan, setPlan] = useState<ApiPlan | null>(null);
  const [activePlan, setActivePlan] = useState<ApiPlan | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noPlan, setNoPlan] = useState(false);
  const [showPast, setShowPast] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [aiConfigured, setAiConfigured] = useState<boolean | null>(null);
  const [coachRequest, setCoachRequest] = useState<{ concern: string; nonce: number } | null>(null);
  const [coachOpen, setCoachOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const isDesktop = useSyncExternalStore(subscribeDesktop, () => window.matchMedia(DESKTOP_QUERY).matches, () => false);

  useEffect(() => {
    getJson<AthletePreferences>(`/users/${USER_ID}`).then((u) => { if (u) { setCurrentPreferences(u); setUnits(u.units === "km" ? "km" : "miles"); } }).catch((e) => setError(e instanceof Error ? e.message : "Could not load display preferences."));
    getJson<{ configured: boolean }>(`/coaching/${USER_ID}/status`).then((s) => setAiConfigured(s?.configured ?? false)).catch(() => setAiConfigured(false));
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

  const generatePlan = useCallback(async (lighter = false, scope: "current" | "next" = "current", mode: "full" | "schedule" = "full") => {
    setGenerating(true);
    setError(null);
    try {
      const res = await fetch(apiUrl(`/plans/${USER_ID}/preview`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lighter, scope, mode }),
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
    window.addEventListener(SYNC_EVENT, fetchPlan);
    return () => { clearTimeout(id); window.removeEventListener(SYNC_EVENT, fetchPlan); };
  }, [fetchPlan]);

  if (loading) {
    return (
      <div className="space-y-6">
        <p className="eyebrow">Your next training days</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Current Plan</h1>
        <div className="py-20 text-center text-muted-foreground">
          Loading your plan...
        </div>
      </div>
    );
  }

  if (noPlan) {
    return (
      <div className="space-y-6">
        <p className="eyebrow">Your next training days</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Current Plan</h1>
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
        <p className="eyebrow">Your next training days</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Current Plan</h1>
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {error || "No plan available"}
          </CardContent>
        </Card>
      </div>
    );
  }

  const weeks: PlanWeekType[] = plan.weeks.map(mapApiToWeek);


  if (plan.is_stale) {
    return (
      <div className="space-y-6">
        <p className="eyebrow">Your next training days</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Current Plan</h1>
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

  const allDays = weeks.flatMap((w) => w.workouts);
  const selected = allDays.find((w) => w.date === selectedDate)
    ?? allDays.find((w) => w.date === today) ?? allDays.find((w) => w.date > today) ?? allDays[0] ?? null;
  const distance = (miles: number | null | undefined) => (miles == null ? "—" : distanceInUnits(miles, units));
  const unit = unitLabel(units);
  const changes = allDays.filter((w) => w.adjustment_note);
  const weekTotals = plan.weeks.map((week) => ({
    planned: week.target_mileage,
    actual: week.days.reduce((sum, d) => sum + (d.actual?.total_distance_miles ?? d.actual?.distance_miles ?? 0), 0),
  }));
  const refresh = () => { setMoveRequest(null); setLoading(true); fetchPlan(); };
  const movable = (w: Workout) => w.date >= today && !w.actual && w.prescribed !== false && !w.skipped && !w.moved_to && !["race", "rest"].includes(w.type);
  const moveTarget = selected && movable(selected) ? selected : allDays.find(movable);
  const openDay = (date: string) => {
    setSelectedDate(date);
    if (isDesktop) setInspectorOpen(true);
    else requestAnimationFrame(() => document.getElementById("plan-inspector")?.scrollIntoView({ block: "start" }));
  };
  const inspector = selected && (
    <PlanDay
      key={`${selected.date}-${selected.title}-${selected.session_status ?? ""}-${moveRequest?.nonce ?? ""}`}
      workout={selected}
      units={units}
      sessionAction={moveRequest?.date === selected.date ? "move" : undefined}
      readOnly={!!plan.preview}
      isToday={selected.date === today}
      expanded
      pinned
      onPlanChanged={refresh}
    />
  );
  // Compare with the block on screen: a draft built from the new settings already resolves it.
  const builtFor = plan.athlete.schedule_preferences;
  const preferenceMismatch = !!currentPreferences && !!builtFor && scheduleChanged(builtFor, currentPreferences);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="font-heading text-2xl font-black italic tracking-tight">
            Current Plan{plan.load ? ` · ${MODE_LABEL[plan.load.mode] ?? plan.load.mode}` : ""}
          </h1>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{plan.goal.description}</span>
            <span className="num">{formatDateShort(plan.start_date)} &ndash; {formatDateShort(plan.end_date)}</span>
            {plan.phase && plan.phase.phase !== "general" && (
              <Badge variant={plan.phase.phase === "race_week" ? "default" : "secondary"} className="text-xs">{plan.phase.label}</Badge>
            )}
            {plan.goal.race_date && <span>Race {formatDateShort(plan.goal.race_date)}</span>}
            {plan.is_deload && <Badge variant="secondary" className="text-xs">Deload</Badge>}
            <span>{plan.preview ? "Draft for review" : "Approved block · log runs and feel ratings to adjust it as you go"}</span>
          </div>
        </div>
        {!plan.preview && (
          <PlanOptionsDialog
            aiConfigured={aiConfigured}
            busy={generating}
            nextBlockLabel={nextBlockAvailable(plan.end_date, today) ? `starts after ${formatDateShort(plan.end_date)}` : null}
            onAskCoach={(concern) => {
              setCoachRequest({ concern, nonce: Date.now() });
              setCoachOpen(true);
              requestAnimationFrame(() => document.getElementById("plan-coach")?.scrollIntoView({ behavior: "smooth", block: "start" }));
            }}
            onMoveSession={moveTarget ? () => { setMoveRequest({ date: moveTarget.date, nonce: Date.now() }); openDay(moveTarget.date); } : undefined}
            onLighter={() => generatePlan(true)}
            onRevise={() => generatePlan()}
            onNextBlock={() => generatePlan(false, "next")}
          />
        )}
      </div>

      {error && <p role="alert" className="text-destructive">{error}</p>}
      {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
      {preferenceMismatch && builtFor && currentPreferences && <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3 text-sm">
        <p>This block was built for {describeSchedule(builtFor.days_per_week, builtFor.rest_days)}. Your settings now say {describeSchedule(currentPreferences.days_per_week, (currentPreferences.rest_days || "").split(","))}.</p>
        <Button size="sm" disabled={generating} onClick={() => generatePlan(false, "current", "schedule")}>{generating ? "Building…" : "Update my plan"}</Button>
      </div>}
      {plan.preview && <Panel label="Review this block" accent="var(--type-threshold)">
        <p className="text-sm text-muted-foreground">{plan.revision === "schedule"
          ? "Only the days your new schedule touches changed: workouts and long runs are exactly as approved. Your current plan stays active until you approve."
          : "Your current plan stays active until you approve. Make it lighter reduces volume, keeping workout paces unchanged."}</p>
        {!!plan.change_summary?.length && <ul className="mt-2 space-y-0.5 text-sm">{plan.change_summary.map((line) => <li key={line}>{line}</li>)}</ul>}
        {!!plan.changes?.length && <ul className="mt-2 space-y-1 text-xs text-muted-foreground">{plan.changes.map((c) => (
          <li key={c.date}><span className="font-medium text-foreground">{formatDateShort(c.date)}</span>: {c.before} → {c.after}. {c.reason}</li>
        ))}</ul>}
        <div className="mt-3 flex flex-wrap gap-2">
          <Button disabled={generating} onClick={() => finishPreview("approve")}>Approve</Button>
          <Button variant="outline" disabled={generating} onClick={() => generatePlan(true)}>Make it lighter</Button>
          {activePlan && !activePlan.is_stale && <Button variant="ghost" disabled={generating} onClick={() => finishPreview("discard")}>Keep current plan</Button>}
        </div>
      </Panel>}

      <div className="panel grid grid-cols-2 divide-x divide-[#2a2a2a]/15 sm:grid-cols-4">
        {weekTotals.slice(0, 2).map((t, i) => (
          <StatCell size="sm" key={i} label={`W${i + 1} plan / act`} value={<>{distance(t.planned)}<span className="text-muted-foreground"> / {t.actual > 0 ? distance(t.actual) : "—"}</span></>}
            sub={i === 1 && weekTotals[0].planned > 0 ? `${t.planned >= weekTotals[0].planned ? "+" : ""}${Math.round((t.planned / weekTotals[0].planned - 1) * 100)}% vs W1` : unit} />
        ))}
        <StatCell size="sm" label="Block baseline" value={distance(plan.load?.baseline)} sub={`${unit}/week · four completed weeks${plan.athlete.baseline_as_of ? ` · as of ${formatDateShort(plan.athlete.baseline_as_of)}` : " · saved when approved"}`} />
        <StatCell size="sm" label="Goal" value={plan.load?.destination ? distance(plan.load.destination) : plan.goal.distance?.toUpperCase() || undefined}
          sub={plan.load?.destination ? `${unit}/week` : plan.goal.race_date ? `race ${formatDateShort(plan.goal.race_date)}` : undefined} tone="var(--type-easy)" />
      </div>

      <Panel label="Calendar" meta="hatched = quality / long · tap a day" bodyClassName="p-0">
        <PlanCalendar weeks={weeks} units={units} selectedDate={selected?.date ?? null} onSelect={(w) => openDay(w.date)} />
      </Panel>

      {!isDesktop && selected && (
        <div id="plan-inspector" className="scroll-mt-16">
          <Panel label={`Selected · ${formatDateShort(selected.date)}`} accent="var(--type-easy)" bodyClassName="p-2">{inspector}</Panel>
        </div>
      )}

      <div id="plan-coach" className="panel min-w-0 scroll-mt-16">
        <button type="button" aria-expanded={coachOpen} aria-controls="plan-coach-body" onClick={() => setCoachOpen((v) => !v)}
          className="panel-head w-full text-left hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-[-3px] focus-visible:outline-primary">
          <span>Coach perspective · this week &amp; next</span>
          <span aria-hidden="true" className="meta inline-flex items-center gap-1">
            {coachOpen ? "Hide" : "Show"}<span className={cn("inline-block transition-transform", coachOpen && "rotate-180")}>▾</span>
          </span>
        </button>
        {/* Stays mounted while collapsed so an in-flight review or a coach request isn't lost. */}
        <div id="plan-coach-body" hidden={!coachOpen} className="px-3 py-2.5">
          <CoachingReview key={`coach-${plan.id}`} planId={plan.id} onPlanChanged={() => fetchPlan()} request={plan.preview ? null : coachRequest} showLabel={false} />
        </div>
      </div>
      {(plan.review || plan.outlook) && (
        <div className="grid min-w-0 items-stretch gap-3 sm:grid-cols-2 [&>section]:h-full">
          {plan.review && <BlockReviewPanel review={plan.review} />}
          {plan.outlook && <GoalRoute outlook={plan.outlook} />}
        </div>
      )}
      {/* Reference panels under the coach. */}
      <div className="grid min-w-0 items-stretch gap-3 sm:grid-cols-2 [&>section]:h-full">
        {changes.length === 0 && !plan.assessment?.reasons?.length ? (
          <Panel label="Change log" meta="No changes yet" bodyClassName="hidden">{null}</Panel>
        ) : <Panel label="Change log" meta={changes.length ? `${changes.length}` : undefined} bodyClassName="px-3 py-2">
          <ul className="space-y-1.5 text-sm">
            {changes.map((w) => (
              <li key={w.date}>
                <button type="button" className="text-left hover:underline" onClick={() => openDay(w.date)}>
                  <span className="font-mono text-xs font-semibold">{formatDateShort(w.date)}</span>{" "}
                  <span className="text-muted-foreground">{w.adjustment_note}</span>
                </button>
              </li>
            ))}
          </ul>
          {plan.assessment?.reasons?.map((reason, i) => <p key={reason} className={cn("text-xs text-muted-foreground", (changes.length > 0 || i > 0) && "mt-2 border-t pt-2")}>{reason}</p>)}
        </Panel>}
        <Panel label="Pacing guide" meta={`per ${unit}`} bodyClassName="px-3 py-2">
          <div className="space-y-0.5 text-[13px]">
            {pacingRows(plan.pacing_guide).map(([label, hint, value]) => (
              <div key={label} className="flex items-baseline justify-between gap-3">
                <span className="text-muted-foreground">{label} <span className="text-xs">· {hint}</span></span>
                <span className="num shrink-0">{paceInUnits(value, units)}/{unit}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Sheet open={isDesktop && inspectorOpen && !!selected} onOpenChange={setInspectorOpen}>
        <SheetContent className="overflow-y-auto data-[side=right]:sm:max-w-lg">
          {selected && (
            <>
              <SheetHeader className="pb-0">
                <SheetTitle>Selected · {formatDateShort(selected.date)}</SheetTitle>
              </SheetHeader>
              <div className="px-4 pb-6">{inspector}</div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
