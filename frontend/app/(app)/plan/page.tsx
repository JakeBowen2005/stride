"use client";
import { TrainingExpectations, type WeekExpectation } from "@/components/training-expectations";
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
import { PlanDayDetail } from "@/components/plan-day-detail";
import { Panel, StatCell } from "@/components/cockpit/panel";
import { PlanCalendar } from "@/components/cockpit/plan-calendar";
import { PlanSpotlight } from "@/components/plan-spotlight";
import { raceDistanceLabel } from "@/components/goal-editor";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { SYNC_EVENT } from "@/components/garmin-sync";
import { formatDateLong, formatDateShort, hoursLabel } from "@/lib/format";
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
    session?: import("@/lib/types").RanSession | null;
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
  expectations?: WeekExpectation[];
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
    /** docs/aerobic-hours.md phase 2: recorded for review, never applied to the plan */
    shadow_hours?: {
      hours_baseline: number;
      sustainable_hours: number;
      weeks: { week_number: number; planned_minutes: number; hours_budget: number | null }[];
      notes: string[];
    } | null;
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

/** Rows for the pacing guide; falls back to the old keys on plans generated before Oct 2026.
 * Only the zones this block actually uses (every zone on legacy plans with no prescriptions). */
function pacingRows(g: Record<string, string>, weeks: ApiWeek[]): [string, string, string][] {
  const days = weeks.flatMap((w) => w.days);
  const categories = new Set(days.map((d) => d.prescription?.category).filter(Boolean));
  const legacy = categories.size === 0;
  const steady = legacy || categories.has("long_run") || days.some((d) => /steady|progress/i.test(d.title));
  const rows: [string, string, string | undefined, boolean][] = [
    ["Easy", "conversational", g.easy, true],
    ["Steady", "long-run finishes", g.steady, steady],
    ["Tempo", "continuous", g.tempo ?? g.current_tempo, legacy || categories.has("threshold")],
    ["Threshold reps", "e.g. 2x10min", g.threshold_reps ?? g.current_threshold, legacy || categories.has("threshold")],
    ["Intervals", "800m-mile reps", g.intervals ?? g.current_interval, legacy || categories.has("intervals")],
    ["Goal race", "target", g.goal_race_pace, true],
  ];
  return rows.filter((r) => !!r[2] && r[3]).map(([label, hint, value]) => [label, hint, value as string]);
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
  const [switchRequest, setSwitchRequest] = useState<{ date: string; nonce: number } | null>(null);
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
  // Bumped on every plan fetch: the open day's run and the coach perspective re-load with it
  const [planRevision, setPlanRevision] = useState(0);
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
      setPlanRevision((n) => n + 1);
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
        <div className="kicker">Two-week block</div>
        <h1 className="display mt-3">Current <em>plan</em></h1>
        <div className="glass py-20 text-center text-muted-foreground">
          Loading your plan...
        </div>
      </div>
    );
  }

  if (noPlan) {
    return (
      <div className="space-y-6">
        <div className="kicker">Two-week block</div>
        <h1 className="display mt-3">Current <em>plan</em></h1>
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
        <div className="kicker">Two-week block</div>
        <h1 className="display mt-3">Current <em>plan</em></h1>
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
        <div className="kicker">Two-week block</div>
        <h1 className="display mt-3">Current <em>plan</em></h1>
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
  const refresh = () => { setSwitchRequest(null); setLoading(true); fetchPlan(); };
  // A changed session returns to the plan: the sheet closes so the updated week is what you see.
  const sessionChanged = () => { setInspectorOpen(false); refresh(); };
  const switchable = (w: Workout) => w.date >= today && !w.actual && w.prescribed !== false && !w.skipped && !w.moved_to && w.type !== "race";
  const switchSource = selected && switchable(selected) ? selected : allDays.find(switchable);
  const openDay = (date: string) => {
    setSelectedDate(date);
    if (isDesktop) setInspectorOpen(true);
    else requestAnimationFrame(() => document.getElementById("plan-inspector")?.scrollIntoView({ block: "start" }));
  };
  const inspector = selected && (
    <PlanDayDetail
      key={`${selected.date}-${selected.title}-${selected.session_status ?? ""}-${switchRequest?.nonce ?? ""}`}
      workout={selected}
      units={units}
      sessionAction={switchRequest?.date === selected.date ? "switch" : undefined}
      readOnly={!!plan.preview}
      isToday={selected.date === today}
      revision={planRevision}
      onPlanChanged={refresh}
      onSessionChanged={sessionChanged}
    />
  );
  // Compare with the block on screen: a draft built from the new settings already resolves it.
  const builtFor = plan.athlete.schedule_preferences;
  const preferenceMismatch = !!currentPreferences && !!builtFor && scheduleChanged(builtFor, currentPreferences);

  // A week that began before the plan only prescribes its remaining days: no % comparison.
  const firstWeekPartial = !!plan.weeks[0]?.days.some((d) => d.prescribed === false);
  const stats = (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {weekTotals.slice(0, 2).map((t, i) => (
          <div key={i} className="glass rounded-[22px]"><StatCell size="sm" key={i} label={`W${i + 1} plan / act`} value={<>{distance(t.planned)}<span className="text-muted-foreground"> / {t.actual > 0 ? distance(t.actual) : "—"}</span></>}
            sub={i === 1 && weekTotals[0].planned > 0 && !firstWeekPartial ? `${t.planned >= weekTotals[0].planned ? "+" : ""}${Math.round((t.planned / weekTotals[0].planned - 1) * 100)}% vs W1` : unit} /></div>
        ))}
        <div className="glass rounded-[22px]"><StatCell size="sm" label="Block baseline" value={distance(plan.load?.baseline)} sub={`${unit}/week · four completed weeks${plan.athlete.baseline_as_of ? ` · as of ${formatDateShort(plan.athlete.baseline_as_of)}` : " · saved when approved"}`} /></div>
        {/* The goal tile is the one solid accent, as in the wireframes */}
        <div className="btn-gloss rounded-[22px] [&_.stat-label]:text-primary-foreground/80 [&_.text-muted-foreground]:text-primary-foreground/80">
          <StatCell size="sm" label="Goal" value={plan.load?.destination ? distance(plan.load.destination) : plan.goal.distance?.toUpperCase() || undefined}
            sub={plan.load?.destination ? `${unit}/week` : plan.goal.race_date ? `race ${formatDateShort(plan.goal.race_date)}` : undefined} />
        </div>
      </div>

      {plan.load?.shadow_hours && (
        <details className="glass rounded-[22px] px-4 py-3 text-sm">
          <summary className="cursor-pointer">
            <span className="stat-label">Running time</span>{" "}
            <span className="text-muted-foreground">
              {plan.load.shadow_hours.weeks.map((w) => `W${w.week_number} ≈ ${hoursLabel(w.planned_minutes * 60)}`).join(" · ")}
              {" · "}recent {hoursLabel(plan.load.shadow_hours.hours_baseline * 3600)}/week
            </span>
          </summary>
          <div className="mt-2 space-y-1 text-xs text-muted-foreground">
            <p>Only you (the owner) see this. Time check in shadow mode: Stride records where a weekly hours budget or the longest-run guard would limit this block, but doesn&apos;t apply them yet.</p>
            {plan.load.shadow_hours.notes.length ? <ul className="list-disc pl-4">{plan.load.shadow_hours.notes.map((n) => <li key={n}>{n}</li>)}</ul>
              : <p>Nothing in this block would be limited.</p>}
            {plan.load.shadow_hours.sustainable_hours > 0 && <p>Highest weekly time you&apos;ve held for 6 straight weeks (last 2 years): {hoursLabel(plan.load.shadow_hours.sustainable_hours * 3600)}.</p>}
          </div>
        </details>
      )}
    </>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3 pt-1">
        <div className="min-w-0">
          <div className="kicker">{plan.block_number ? `Block ${plan.block_number} · ` : ""}two weeks</div>
          <h1 className="display mt-3">
            {plan.load ? <><span className="sr-only">Current Plan · </span>{MODE_LABEL[plan.load.mode] ?? plan.load.mode}</> : "Current Plan"}
            {plan.goal.distance && <> <em>for the {raceDistanceLabel(plan.goal.distance)}</em></>}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
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
            onSwitchSession={switchSource ? () => { setSwitchRequest({ date: switchSource.date, nonce: Date.now() }); openDay(switchSource.date); } : undefined}
            onLighter={() => generatePlan(true)}
            onRevise={() => generatePlan()}
            onNextBlock={() => generatePlan(false, "next")}
          />
        )}
      </div>

      {error && <p role="alert" className="text-destructive">{error}</p>}
      {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
      {preferenceMismatch && builtFor && currentPreferences && <div role="status" className="glass flex flex-wrap items-center justify-between gap-3 rounded-[22px] px-4 py-3 text-sm">
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

      <PlanSpotlight days={allDays} today={today} units={units} onOpen={openDay} />

      <Panel label="Your two weeks" meta="hatched = quality / long · tap a day" bodyClassName="p-2.5 sm:p-3">
        <PlanCalendar weeks={weeks} units={units} selectedDate={selected?.date ?? null} onSelect={(w) => openDay(w.date)} />
      </Panel>

      {!isDesktop && selected && (
        <div id="plan-inspector" className="scroll-mt-20">
          <Panel label={`Selected · ${formatDateShort(selected.date)}`} accent="var(--type-easy)" bodyClassName="p-2">{inspector}</Panel>
        </div>
      )}

      {/* Block numbers follow the weeks they describe. */}
      {stats}

      <div id="plan-coach" className="panel min-w-0 scroll-mt-24">
        <button type="button" aria-expanded={coachOpen} aria-controls="plan-coach-body" onClick={() => setCoachOpen((v) => !v)}
          className="panel-head w-full pb-3 text-left transition-colors hover:bg-[var(--row-hover)] focus-visible:outline-2 focus-visible:outline-offset-[-3px] focus-visible:outline-primary">
          <span className="inline-flex items-center gap-2"><span aria-hidden="true" className="dot" style={{ background: "var(--accent-warm)" }} />Coach perspective · this week &amp; next</span>
          <span aria-hidden="true" className="meta inline-flex items-center gap-1">
            {coachOpen ? "Hide" : "Show"}<span className={cn("inline-block transition-transform", coachOpen && "rotate-180")}>▾</span>
          </span>
        </button>
        {/* Stays mounted while collapsed so an in-flight review or a coach request isn't lost. */}
        <div id="plan-coach-body" hidden={!coachOpen} className="px-4 pb-4 sm:px-5">
          <CoachingReview key={`coach-${plan.id}`} planId={plan.id} onPlanChanged={() => fetchPlan()} request={plan.preview ? null : coachRequest} showLabel={false} refreshKey={planRevision} />
        </div>
      </div>
      <TrainingExpectations weeks={plan.expectations || []} />
      {(plan.review || plan.outlook) && (
        <div className="grid min-w-0 items-stretch gap-3 sm:grid-cols-2 [&>section]:h-full">
          {plan.review && <BlockReviewPanel review={plan.review} />}
          {plan.outlook && <GoalRoute key={plan.outlook.decision?.key ?? "none"} outlook={plan.outlook} />}
        </div>
      )}
      {/* Reference panels under the coach. */}
      <div className="grid min-w-0 items-stretch gap-3 sm:grid-cols-2 [&>section]:h-full">
        {changes.length === 0 && (plan.review || !plan.assessment?.reasons?.length) ? (
          <Panel label="Change log" meta="No changes yet" bodyClassName="hidden">{null}</Panel>
        ) : <Panel label="Change log" meta={changes.length ? `${changes.length}` : undefined} bodyClassName="px-3 py-2">
          <ul className="space-y-1.5 text-sm">
            {changes.map((w) => (
              <li key={w.date}>
                <button type="button" className="rounded-lg text-left transition-colors hover:underline" onClick={() => openDay(w.date)}>
                  <span className="num text-xs font-bold">{formatDateShort(w.date)}</span>{" "}
                  <span className="text-muted-foreground">{w.adjustment_note}</span>
                </button>
              </li>
            ))}
          </ul>
          {/* The block review panel already lists these reasons; repeat them only without it. */}
          {!plan.review && plan.assessment?.reasons?.map((reason, i) => <p key={reason} className={cn("text-xs text-muted-foreground", (changes.length > 0 || i > 0) && "mt-2 border-t pt-2")}>{reason}</p>)}
        </Panel>}
        <Panel label="Pacing guide" meta={`per ${unit}`} bodyClassName="px-3 py-2">
          <div className="space-y-1 text-[13px]">
            {pacingRows(plan.pacing_guide, plan.weeks).map(([label, hint, value]) => (
              <div key={label} className="glass-tile flex items-baseline justify-between gap-3 rounded-xl px-3 py-2">
                <span className="text-muted-foreground">{label} <span className="text-xs">· {hint}</span></span>
                <span className="num shrink-0 font-bold">{paceInUnits(value, units)}/{unit}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Sheet open={isDesktop && inspectorOpen && !!selected} onOpenChange={setInspectorOpen}>
        <SheetContent className={cn("overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:w-3/4 data-[side=right]:sm:max-w-2xl",
          selected?.actual ? "data-[side=right]:lg:max-w-4xl" : "data-[side=right]:lg:max-w-3xl")}>
          {selected && (
            <>
              <SheetHeader className="pb-0 sm:px-6 sm:pt-6">
                <SheetTitle className="pr-10 text-2xl font-light tracking-tight">{formatDateLong(selected.date)}</SheetTitle>
              </SheetHeader>
              <div className="px-4 pb-6 sm:px-6">{inspector}</div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
