"use client";

import { apiUrl, USER_ID } from "@/lib/api";
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
      skipped: false,
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

function BlockSummary({ load, assessment }: { load: NonNullable<ApiPlan["load"]>; assessment: ApiPlan["assessment"] }) {
  const budgets = load.weekly_budgets.map((b) => Math.round(b)).join(" → ");
  return (
    <Card>
      <CardContent className="space-y-2 pt-4 text-sm">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="font-medium">This block: {MODE_LABEL[load.mode] ?? load.mode}</h3>
          <span className="shrink-0 font-mono text-muted-foreground">{budgets} mi/wk</span>
        </div>
        <p className="text-muted-foreground">
          Baseline {Math.round(load.baseline)} mi/week from your recent runs
          {load.destination ? ` · goal ${Math.round(load.destination)} mi/week` : ""}
        </p>
        {load.destination && load.destination > load.baseline && (
          <div className="h-1.5 overflow-hidden rounded-full bg-muted" aria-label="Progress toward mileage goal">
            <div
              className="h-full rounded-full"
              style={{ width: `${Math.min(100, (load.baseline / load.destination) * 100)}%`, background: "var(--viz-series-1)" }}
            />
          </div>
        )}
        {assessment?.reasons?.length ? (
          <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
            {assessment.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
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
  const [plan, setPlan] = useState<ApiPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noPlan, setNoPlan] = useState(false);
  const [showPast, setShowPast] = useState(false);

  const fetchPlan = useCallback(async () => {
    try {
      const res = await fetch(apiUrl(`/plans/${USER_ID}/current`));
      if (res.status === 404) {
        setNoPlan(true);
        return;
      }
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || "Failed to load plan");
        return;
      }
      setNoPlan(false);
      setPlan(await res.json());
    } catch {
      setError("Failed to connect to server");
    } finally {
      setLoading(false);
    }
  }, []);

  const generatePlan = useCallback(async () => {
    setGenerating(true);
    setError(null);
    try {
      const res = await fetch(apiUrl(`/plans/${USER_ID}/generate`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || "Failed to generate plan");
        return;
      }
      // Re-fetch via GET to get matched actuals
      setLoading(true);
      await fetchPlan();
    } catch {
      setError("Failed to connect to server");
    } finally {
      setGenerating(false);
    }
  }, [fetchPlan]);

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
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground mb-4">No plan yet. Generate your first training plan.</p>
            <Button onClick={generatePlan} disabled={generating}>
              {generating ? "Generating..." : "Generate Your First Plan"}
            </Button>
            {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error || !plan) {
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
        <Card>
          <CardContent className="space-y-3 py-8 text-center">
            <p className="font-medium">Your last training block ended {formatDateShort(plan.end_date)}.</p>
            <p className="mx-auto max-w-sm text-sm text-muted-foreground">
              Generate a fresh 2-week block. It&apos;s built from your latest Garmin runs, current fitness and{" "}
              {plan.goal.race_date ? "where you are relative to race day" : "your goal"}.
            </p>
            <Button onClick={generatePlan} disabled={generating}>
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
          weeks.map((week) => <PlanWeek key={week.week_number} week={week} isCurrent={false} />)}
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

      {plan.load && <BlockSummary load={plan.load} assessment={plan.assessment ?? null} />}

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
                <span className="shrink-0 font-mono">{value}/mi</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

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
          <PlanWeek key={week.week_number} week={week} isCurrent={false} onPlanChanged={() => fetchPlan()} />
        ))}

      {visibleWeeks.map((week, i) => (
        <PlanWeek
          key={week.week_number}
          week={week}
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
    </div>
  );
}
