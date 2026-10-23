"use client";

import { useUnits } from "@/components/unit-preferences";
import { distanceInUnits, paceInUnits, unitLabel } from "@/lib/units";
import { useState } from "react";
import { FeedbackForm } from "@/components/feedback-form";
import Link from "next/link";
import { CircleCheck, ChevronDown, ArrowUpRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cleanPurpose, secondsToPace, secondsToTime } from "@/lib/format";
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
  prescription?: { segments?: { pace_range_sec_per_mile?: { fast: number; slow: number } | null }[] } | null;
  actual?: {
    activity_id?: number;
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

/** Separate recordings stay separate; the total never becomes a workout or coach target. */
function ActualRun({ day, onOpenActivity }: { day: PlanDayLite; onOpenActivity?: (id: number) => void }) {
  const units = useUnits();
  const unit = unitLabel(units);
  const distance = (miles: number) => distanceInUnits(miles, units);
  const actual = day.actual!;
  const workout = actual.workout;
  const [selected, setSelected] = useState("primary");
  const activities = [
    { key: "primary", id: actual.activity_id, kind: "Run", title: workout?.title ?? RUN_TITLE[day.type] ?? "Run", ...actual },
    ...(actual.other_runs ?? []).map((a) => ({ ...a, key: `run-${a.id}`, kind: "Run", title: a.name ?? "Additional run" })),
    ...(actual.walks ?? []).map((a) => ({ ...a, key: `walk-${a.id}`, kind: "Walk", title: a.name ?? "Walk" })),
  ];
  const activity = activities.find((a) => a.key === selected) ?? activities[0];
  const total = selected === "total";
  const runningMiles = actual.total_distance_miles ?? actual.distance_miles + (actual.other_runs ?? []).reduce((sum, a) => sum + a.distance_miles, 0);
  const walkingMiles = (actual.walks ?? []).reduce((sum, a) => sum + a.distance_miles, 0);
  const totalSeconds = activities.reduce((sum, a) => sum + (a.duration_seconds ?? 0), 0);
  const primary = !total && activity.key === "primary";

  return <div className="space-y-4">
    {activities.length > 1 && <div className="-mx-4 -mt-4 flex overflow-x-auto border-b bg-muted/30" role="group" aria-label="Today's activities">
      {activities.map((a, index) => <button key={a.key} type="button" aria-pressed={!total && activity.key === a.key}
        onClick={() => setSelected(a.key)} className={cn("min-h-14 min-w-24 flex-1 border-r px-3 py-2 text-left text-xs transition-colors last:border-r-0 hover:bg-muted focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary", !total && activity.key === a.key && "bg-card shadow-[inset_0_-3px_0_var(--type-easy)]")}>
        <span className="block font-medium">{a.kind}{activities.filter((other) => other.kind === a.kind).length > 1 ? ` ${activities.slice(0, index + 1).filter((other) => other.kind === a.kind).length}` : ""}</span>
        <span className="num mt-0.5 block text-muted-foreground">{distance(a.distance_miles)} {unit}</span>
      </button>)}
      <button type="button" aria-pressed={total} onClick={() => setSelected("total")}
        className={cn("min-h-14 min-w-24 flex-1 px-3 py-2 text-left text-xs transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary", total && "bg-card shadow-[inset_0_-3px_0_var(--type-easy)]")}>
        <span className="block font-medium">Day total</span><span className="num mt-0.5 block text-muted-foreground">{distance(runningMiles + walkingMiles)} {unit}</span>
      </button>
    </div>}

    <div className="space-y-3" aria-live="polite">
      <div className="flex items-center justify-between gap-2">
        <span className="stat-label flex items-center gap-1.5"><CircleCheck className="size-4" style={{ color: "var(--type-easy)" }} aria-hidden />{total ? "All activities" : activity.kind === "Walk" ? "Walk recorded" : "Ran today"}</span>
        {primary && workout?.off_plan && <Badge variant="secondary" className="text-[11px]">Off plan</Badge>}
      </div>
      {total ? <h3 className="text-xl font-semibold leading-tight">Today&apos;s total</h3> : <button type="button" disabled={activity.id == null || !onOpenActivity} onClick={() => activity.id != null && onOpenActivity?.(activity.id)}
        className="group flex w-full items-start justify-between gap-3 text-left disabled:cursor-default">
        <h3 className="text-xl font-semibold leading-tight group-enabled:group-hover:underline group-enabled:group-hover:underline-offset-4 sm:text-2xl">{activity.title}</h3>
        {activity.id != null && onOpenActivity && <ArrowUpRight className="mt-1 size-4 shrink-0 text-muted-foreground" aria-hidden />}
      </button>}

      <dl className="grid grid-cols-2 overflow-hidden rounded-md border min-[380px]:grid-cols-4">
        {(total ? [
          { label: `${unit} total`, value: distance(runningMiles + walkingMiles) },
          { label: `${unit} running`, value: distance(runningMiles) },
          { label: `${unit} walking`, value: distance(walkingMiles) },
          { label: "Total time", value: totalSeconds > 0 ? secondsToTime(totalSeconds) : "—" },
        ] : [
          { label: unit === "mi" ? "Miles" : "Kilometers", value: distance(activity.distance_miles) },
          { label: `Pace /${unit}`, value: activity.avg_pace ? paceInUnits(activity.avg_pace, units) : "—" },
          { label: "Time", value: activity.duration_seconds ? secondsToTime(activity.duration_seconds) : "—" },
          { label: "Avg BPM", value: activity.average_heartrate != null ? Math.round(activity.average_heartrate) : "—" },
        ]).map((stat) => <div key={stat.label} className="min-w-0 border-r px-2.5 py-3 last:border-r-0 odd:bg-muted/20">
          <dt className="stat-label text-[10px]">{stat.label}</dt><dd className="num mt-1 text-lg font-semibold leading-none">{stat.value}</dd>
        </div>)}
      </dl>

      {primary && workout && workout.reps.length > 0 && <section aria-label="Work repetitions" className="overflow-hidden rounded-md border">
        <div className="border-b bg-muted/30 px-3 py-2"><h4 className="stat-label">{workout.reps.length > 1 ? "Work reps" : "Work segment"}</h4></div>
        <table className="w-full text-left text-xs">
          <thead className="text-[10px] uppercase tracking-wide text-muted-foreground"><tr><th scope="col" className="px-3 py-2 font-normal">Rep</th><th scope="col" className="py-2 font-normal">Time</th><th scope="col" className="py-2 font-normal">Pace /{unit}</th><th scope="col" className="px-3 py-2 text-right font-normal">Avg BPM</th></tr></thead>
          <tbody>{workout.reps.map((rep, index) => <tr key={index} className="border-t odd:bg-muted/20">
            <th scope="row" className="px-3 py-2.5 font-normal text-muted-foreground">{index + 1}</th>
            <td className="num py-2.5">{secondsToTime(Math.round(rep.duration_s))}</td><td className="num py-2.5 font-medium">{paceInUnits(secondsToPace(Math.round(rep.pace_sec_per_mile)), units)}</td>
            <td className="num px-3 py-2.5 text-right">{rep.average_hr != null ? Math.round(rep.average_hr) : "—"}</td>
          </tr>)}</tbody>
        </table>
        {workout.recovery_seconds != null && <p className="border-t px-3 py-2 text-xs text-muted-foreground">Recovery between reps <span className="num ml-1 text-foreground">{secondsToTime(workout.recovery_seconds)}</span></p>}
      </section>}
      {total && <p className="text-xs leading-relaxed text-muted-foreground">Running and walking are shown separately. Only running mileage counts toward your training plan; no combined pace or heart rate is calculated.</p>}
      {!total && activity.kind === "Walk" && <p className="text-xs leading-relaxed text-muted-foreground">Recorded separately. This walk is not counted in your running mileage.</p>}
      {!total && activity.id != null && onOpenActivity && <button type="button" onClick={() => onOpenActivity(activity.id!)} className="flex min-h-9 items-center gap-1 text-xs font-medium underline underline-offset-4">View {activity.kind.toLowerCase()} details &amp; Garmin laps <ArrowUpRight className="size-3" aria-hidden /></button>}
    </div>
  </div>;
}

/** Other activities that day, each with its own numbers: never blended into the run above. */
export function AlsoToday({ runs = [], walks = [] }: { runs?: ActivityLine[]; walks?: ActivityLine[] }) {
  const units = useUnits();
  const unit = unitLabel(units);
  const formatDistance = (miles: number) => distanceInUnits(miles, units);
  if (!runs.length && !walks.length) return null;
  const line = (a: ActivityLine) => [`${formatDistance(a.distance_miles)} ${unit}`, a.avg_pace && `${paceInUnits(a.avg_pace, units)}/${unit}`, a.duration_seconds && secondsToTime(a.duration_seconds)].filter(Boolean).join(" · ");
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
  onOpenActivity,
}: {
  today: PlanDayLite | null;
  planStale: boolean;
  /** Feedback can change upcoming days and the plan — let the page reload its data */
  onFeedbackSaved?: () => void;
  /** The coach's read on today's run, shown inline under it */
  coach?: React.ReactNode;
  /** Recovery signals are down: suggest easing a hard day before it's run */
  recoveryCaution?: boolean;
  onOpenActivity?: (id: number) => void;
}) {
  const units = useUnits();
  const unit = unitLabel(units);
  const formatDistance = (miles: number) => distanceInUnits(miles, units);
  const hardToday = !!today && (today.type === "workout" || today.type === "long_run" || today.type === "race");
  const done = !!today?.actual;
  // Before the run, hard days open by default so the "why" is visible without a tap
  const [open, setOpen] = useState(hardToday && !done);
  const [feedback, setFeedback] = useState(today?.feedback ?? null);
  const offPlan = !!today?.actual?.workout?.off_plan;

  const details = today && open && (
    <div className="mt-3 space-y-3 rounded-md bg-muted/20 p-3 text-sm">
      {done && cleanPurpose(today.purpose) && <div className="space-y-1"><h4 className="stat-label">Coach preview</h4><p className="leading-relaxed text-muted-foreground">{cleanPurpose(today.purpose)}</p></div>}
      {today.warmup && <p><span className="font-medium">Warmup:</span> {today.warmup}</p>}
      {today.description && <p className="leading-relaxed">{today.description}</p>}
      {today.cooldown && <p><span className="font-medium">Cooldown:</span> {today.cooldown}</p>}
    </div>
  );

  return (
    <Card className={done ? "py-0" : undefined}>
      <CardContent className={cn("space-y-4 pt-4", done && "pb-4")}>
        {planStale ? (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Your last training block has ended.</p>
            <Link href="/plan" className={buttonVariants({ size: "sm" })}>Generate this week&apos;s plan</Link>
          </div>
        ) : !today ? (
          <p className="text-sm text-muted-foreground">No plan for today yet.</p>
        ) : done ? (
          <>
            <ActualRun day={today} onOpenActivity={onOpenActivity} />
            {today.type !== "rest" && (
              <div className="space-y-2 border-t pt-3">
                <h3 className="stat-label">Training context · main run</h3>
                <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
                  className="flex w-full items-center gap-1.5 text-left text-xs text-muted-foreground hover:text-foreground">
                  <span className={cn(offPlan && "line-through decoration-muted-foreground/60")}>
                    Planned: {today.title} · {formatDistance(today.distance_miles)} {unit}
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
                  {today.type === "rest" ? "Rest day" : `${formatDistance(today.distance_miles)} ${unit} planned`}
                </div>

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
            <p className="mb-2 text-sm font-medium">How did it go?</p>
            <FeedbackForm compact date={today.date} isWorkout={today.type === "workout"} hasPaceTarget={!!today.prescription?.segments?.some((seg) => seg.pace_range_sec_per_mile)} onSubmitted={(fb) => { setFeedback(fb); onFeedbackSaved?.(); }} />
          </div>
        )}
        {!done && today && today.type !== "rest" && !feedback?.feel_rating && (
          <details className="rounded-lg border p-3">
            <summary className="cursor-pointer text-sm text-muted-foreground">Ran without your watch? Log it</summary>
            <div className="mt-3">
              <FeedbackForm compact hasRecording={false} date={today.date} isWorkout={today.type === "workout"} hasPaceTarget={!!today.prescription?.segments?.some((seg) => seg.pace_range_sec_per_mile)}
                onSubmitted={(fb) => { setFeedback(fb); onFeedbackSaved?.(); }} />
            </div>
          </details>
        )}
        {feedback?.evaluation && (
          <p className="rounded-md border bg-muted/20 p-3 text-xs leading-relaxed text-muted-foreground">
            <span className="mb-1 block stat-label text-foreground">{feedback.evaluation.decision === "off_plan" ? "Logged: " : "Progression: "}</span>
            {feedback.evaluation.reason}
          </p>
        )}
        {feedback?.changes?.map((c) => (
          <p key={`${c.change}-${c.date}`} className="text-xs text-muted-foreground">{c.reason}</p>
        ))}
        {!done && today && cleanPurpose(today.purpose) && <section className="space-y-2 border-t pt-3" aria-label="Coach preview"><h3 className="stat-label">Coach preview</h3><p className="text-sm leading-relaxed text-muted-foreground">{cleanPurpose(today.purpose)}</p></section>}
        {hardToday && !done && recoveryCaution && (
          <p className="rounded-md bg-muted p-2 text-sm">
            Recovery signals are down and today is a hard day. Consider easy running or rest, and review a safe replacement or move in your plan.{" "}
            <Link href="/plan" className="font-medium underline underline-offset-2">Adjust in Plan →</Link>
          </p>
        )}
        {coach && <section className="space-y-3 border-t pt-4" aria-label="Coach analysis"><h3 className="stat-label">Coach analysis · main run</h3>{coach}</section>}
      </CardContent>
    </Card>
  );
}
