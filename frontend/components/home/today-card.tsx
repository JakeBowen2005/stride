"use client";

import { useState } from "react";
import { FeedbackForm } from "@/components/feedback-form";
import Link from "next/link";
import { CircleCheck, ChevronDown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cleanPurpose, formatDistance, secondsToPace, secondsToTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ActivityLine, ExecutedWorkout } from "@/lib/types";

export interface PlanDayLite {
  date: string;
  type: string;
  title: string;
  description: string | null;
  purpose?: string | null;
  distance_miles: number;
  warmup?: string | null;
  cooldown?: string | null;
  actual?: {
    distance_miles: number;
    avg_pace: string | null;
    duration_seconds?: number;
    average_heartrate?: number | null;
    workout?: ExecutedWorkout | null;
    total_distance_miles?: number;
    other_runs?: ActivityLine[];
    walks?: ActivityLine[];
  } | null;
  feedback?: {
    feel_rating: number | null;
    coach_response: string | null;
    evaluation?: { decision: string; reason: string } | null;
    changes?: { date: string | null; change: string; reason: string }[];
  } | null;
}

const RUN_TITLE: Record<string, string> = { easy: "Easy run", long_run: "Long run", recovery: "Recovery run", race: "Race", workout: "Run" };

/** What was actually run: the headline once today's run is recorded. */
function ActualRun({ day }: { day: PlanDayLite }) {
  const actual = day.actual!;
  const workout = actual.workout;
  const hr = workout?.reps.map((r) => r.average_hr).filter((h): h is number => h != null) ?? [];
  const stats = [
    `${formatDistance(actual.distance_miles)} mi`,
    actual.avg_pace && `${actual.avg_pace}/mi`,
    actual.duration_seconds && secondsToTime(actual.duration_seconds),
    actual.average_heartrate && `${Math.round(actual.average_heartrate)} bpm`,
  ].filter(Boolean);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <CircleCheck className="size-4 shrink-0" style={{ color: "var(--type-easy)" }} aria-hidden />
        <span className="stat-label">Ran today</span>
        {workout?.off_plan && <Badge variant="secondary" className="text-[11px]">Off plan</Badge>}
      </div>
      <div className="text-xl font-semibold leading-tight sm:text-2xl">{workout?.title ?? RUN_TITLE[day.type] ?? "Run"}</div>
      <div className="num text-sm font-medium sm:text-base">{stats.join(" · ")}</div>
      {workout && workout.reps.length > 1 && (
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
          <span className="text-muted-foreground">Reps</span>
          <span className="num font-medium">{workout.reps.map((r) => secondsToPace(r.pace_sec_per_mile)).join(" · ")}<span className="text-muted-foreground">/mi</span></span>
          {hr.length > 1 && <span className="num text-muted-foreground">HR {hr[0]}→{hr[hr.length - 1]}</span>}
        </div>
      )}
      <AlsoToday runs={actual.other_runs} walks={actual.walks} />
    </div>
  );
}

/** Other activities that day, each with its own numbers: never blended into the run above. */
export function AlsoToday({ runs = [], walks = [] }: { runs?: ActivityLine[]; walks?: ActivityLine[] }) {
  if (!runs.length && !walks.length) return null;
  const line = (a: ActivityLine) => [`${formatDistance(a.distance_miles)} mi`, a.avg_pace && `${a.avg_pace}/mi`, a.duration_seconds && secondsToTime(a.duration_seconds)].filter(Boolean).join(" · ");
  return (
    <ul className="space-y-0.5 text-xs text-muted-foreground">
      {runs.map((a) => <li key={a.id}><span className="font-medium text-foreground">+ Run</span> {a.name ? `${a.name} · ` : ""}<span className="num">{line(a)}</span></li>)}
      {walks.map((a) => <li key={a.id}><span className="font-medium text-foreground">+ Walk</span> <span className="num">{line(a)}</span> · not counted in your running</li>)}
    </ul>
  );
}

export function TodayCard({
  today,
  planStale,
  onFeedbackSaved,
  coach,
  recoveryCaution,
}: {
  today: PlanDayLite | null;
  planStale: boolean;
  /** Feedback can change upcoming days and the plan — let the page reload its data */
  onFeedbackSaved?: () => void;
  /** The coach's read on today's run, shown inline under it */
  coach?: React.ReactNode;
  /** Recovery signals are down: suggest easing a hard day before it's run */
  recoveryCaution?: boolean;
}) {
  const hardToday = !!today && (today.type === "workout" || today.type === "long_run" || today.type === "race");
  const done = !!today?.actual;
  // Before the run, hard days open by default so the "why" is visible without a tap
  const [open, setOpen] = useState(hardToday && !done);
  const [feedback, setFeedback] = useState(today?.feedback ?? null);
  const offPlan = !!today?.actual?.workout?.off_plan;

  const details = today && open && (
    <div className="mt-2 space-y-1.5 text-sm">
      {today.warmup && <p><span className="font-medium">Warmup:</span> {today.warmup}</p>}
      {today.description && <p className="leading-relaxed">{today.description}</p>}
      {today.cooldown && <p><span className="font-medium">Cooldown:</span> {today.cooldown}</p>}
    </div>
  );

  return (
    <Card>
      <CardContent className="space-y-3 pt-4">
        {planStale ? (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Your last training block has ended.</p>
            <Link href="/plan" className={buttonVariants({ size: "sm" })}>Generate this week&apos;s plan</Link>
          </div>
        ) : !today ? (
          <p className="text-sm text-muted-foreground">No plan for today yet.</p>
        ) : done ? (
          <>
            <ActualRun day={today} />
            {today.type !== "rest" && (
              <div>
                <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
                  className="flex w-full items-center gap-1.5 text-left text-xs text-muted-foreground hover:text-foreground">
                  <span className={cn(offPlan && "line-through decoration-muted-foreground/60")}>
                    Planned: {today.title} · {formatDistance(today.distance_miles)} mi
                  </span>
                  <ChevronDown className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-180")} aria-hidden />
                </button>
                {details}
              </div>
            )}
          </>
        ) : (
          <button type="button" className="w-full text-left" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <div className="text-xl font-semibold leading-tight sm:text-2xl">{today.title}</div>
                <div className="num text-base font-medium sm:text-lg">
                  {today.type === "rest" ? "Rest day" : `${formatDistance(today.distance_miles)} mi planned`}
                </div>
                {cleanPurpose(today.purpose) && <p className="text-sm text-muted-foreground">{cleanPurpose(today.purpose)}</p>}
              </div>
              <div className="flex items-center gap-2">
                {hardToday && <Badge variant="secondary" className="text-xs">Quality</Badge>}
                <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-180")} />
              </div>
            </div>
            {details}
          </button>
        )}

        {done && today && today.type !== "rest" && !feedback?.feel_rating && (
          <div className="rounded-lg border p-3">
            <p className="mb-2 text-sm font-medium">How did it feel?</p>
            <FeedbackForm compact date={today.date} onSubmitted={(fb) => { setFeedback(fb); onFeedbackSaved?.(); }} />
          </div>
        )}
        {feedback?.evaluation && (
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{feedback.evaluation.decision === "off_plan" ? "Logged: " : "Progression: "}</span>
            {feedback.evaluation.reason}
          </p>
        )}
        {feedback?.changes?.map((c) => (
          <p key={`${c.change}-${c.date}`} className="text-xs text-muted-foreground">{c.reason}</p>
        ))}
        {hardToday && !done && recoveryCaution && (
          <p className="rounded-md bg-muted p-2 text-sm">
            Recovery numbers are down and today is a hard day. Consider running easy and doing the session tomorrow.{" "}
            <Link href="/plan" className="font-medium underline underline-offset-2">Adjust in Plan →</Link>
          </p>
        )}
        {coach && <div className="border-t pt-3">{coach}</div>}
      </CardContent>
    </Card>
  );
}
