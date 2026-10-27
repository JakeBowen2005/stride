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
    session?: import("@/lib/types").RanSession | null;
    total_distance_miles?: number;
    other_runs?: ActivityLine[];
    walks?: ActivityLine[];
    /** App feel already stored on the run itself */
    feel_rating?: number | null;
    /** The main run's own comment */
    notes?: string | null;
    /** The rating entered on the Garmin watch after the run (Stride's 1-10 scales) */
    watch_feel?: number | null;
    watch_effort?: number | null;
  } | null;
  feedback?: {
    feel_rating: number | null;
    effort_rating?: number | null;
    feel_notes?: string | null;
    reported_completion?: { status: string } | null;
    coach_response: string | null;
    evaluation?: { decision: string; reason: string } | null;
    changes?: { date: string | null; change: string; reason: string }[];
  } | null;
}

const RUN_TITLE: Record<string, string> = { easy: "Easy run", long_run: "Long run", recovery: "Recovery run", race: "Race", workout: "Run" };

/** Separate recordings stay separate; the total never becomes a workout or coach target. */
function ActualRun({ day, onOpenActivity, selected, setSelected }: {
  day: PlanDayLite; onOpenActivity?: (id: number) => void; selected: string; setSelected: (key: string) => void;
}) {
  const units = useUnits();
  const unit = unitLabel(units);
  const distance = (miles: number) => distanceInUnits(miles, units);
  const actual = day.actual!;
  const workout = actual.workout;
  const activities = [
    { key: "primary", id: actual.activity_id, kind: "Run", title: actual.session?.title ?? workout?.title ?? RUN_TITLE[day.type] ?? "Run", ...actual },
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
    {activities.length > 1 && <div className="glass-tile flex gap-1 overflow-x-auto rounded-[18px] p-1" role="group" aria-label="Today's activities">
      {activities.map((a, index) => <button key={a.key} type="button" aria-pressed={!total && activity.key === a.key}
        onClick={() => setSelected(a.key)} className={cn("min-h-14 min-w-24 flex-1 rounded-[14px] px-3 py-2 text-left text-xs transition-colors hover:bg-[var(--row-hover)] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary", !total && activity.key === a.key && "bg-primary text-primary-foreground hover:bg-primary [&_.text-muted-foreground]:text-primary-foreground/80")}>
        <span className="block font-medium">{a.kind}{activities.filter((other) => other.kind === a.kind).length > 1 ? ` ${activities.slice(0, index + 1).filter((other) => other.kind === a.kind).length}` : ""}</span>
        <span className="num mt-0.5 block text-muted-foreground">{distance(a.distance_miles)} {unit}</span>
      </button>)}
      <button type="button" aria-pressed={total} onClick={() => setSelected("total")}
        className={cn("min-h-14 min-w-24 flex-1 rounded-[14px] px-3 py-2 text-left text-xs transition-colors hover:bg-[var(--row-hover)] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary", total && "bg-primary text-primary-foreground hover:bg-primary [&_.text-muted-foreground]:text-primary-foreground/80")}>
        <span className="block font-medium">Day total</span><span className="num mt-0.5 block text-muted-foreground">{distance(runningMiles + walkingMiles)} {unit}</span>
      </button>
    </div>}

    <div className="space-y-3" aria-live="polite">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[13px] font-bold" style={{ color: "var(--accent-warm)" }}><CircleCheck className="size-4" aria-hidden />{total ? "All activities" : activity.kind === "Walk" ? "Walk recorded" : "Ran today"}</span>
        {primary && (actual.session?.off_plan ?? workout?.off_plan) && <Badge variant="secondary" className="text-[11px]">Off plan</Badge>}
      </div>
      {total ? <h3 className="text-xl font-semibold leading-tight">Today&apos;s total</h3> : <button type="button" disabled={activity.id == null || !onOpenActivity} onClick={() => activity.id != null && onOpenActivity?.(activity.id)}
        className="group flex w-full items-start justify-between gap-3 text-left disabled:cursor-default">
        <h3 className="text-xl font-bold leading-tight tracking-tight group-enabled:group-hover:underline group-enabled:group-hover:underline-offset-4 sm:text-2xl">{activity.title}</h3>
        {activity.id != null && onOpenActivity && <ArrowUpRight className="mt-1 size-4 shrink-0 text-muted-foreground" aria-hidden />}
      </button>}

      {total ? <dl className="grid grid-cols-2 gap-2 min-[420px]:grid-cols-4">
        {[
          { label: `${unit} total`, value: distance(runningMiles + walkingMiles) },
          { label: `${unit} running`, value: distance(runningMiles) },
          { label: `${unit} walking`, value: distance(walkingMiles) },
          { label: "Total time", value: totalSeconds > 0 ? secondsToTime(totalSeconds) : "—" },
        ].map((stat) => <div key={stat.label} className="glass-tile min-w-0 px-3 py-3">
          <dt className="stat-label">{stat.label}</dt><dd className="num mt-1 text-2xl font-medium leading-none">{stat.value}</dd>
        </div>)}
      </dl> : <dl className="space-y-4">
        {/* The run's distance is the hero number, as on a watch face */}
        <div className="flex items-end gap-2">
          <dt className="sr-only">{unit === "mi" ? "Miles" : "Kilometers"}</dt>
          <dd className="hero-num text-[clamp(4.5rem,15vw,9rem)]">{distance(activity.distance_miles)}<span className="ml-1 text-[clamp(1.25rem,3vw,1.9rem)] font-normal tracking-normal text-muted-foreground" aria-hidden> {unit}</span></dd>
        </div>
        <div className="grid grid-cols-3 border-t border-[var(--glass-border)] pt-4">
          {[
            { label: `Pace /${unit}`, value: activity.avg_pace ? paceInUnits(activity.avg_pace, units) : "—" },
            { label: "Time", value: activity.duration_seconds ? secondsToTime(activity.duration_seconds) : "—" },
            { label: "Avg BPM", value: activity.average_heartrate != null ? Math.round(activity.average_heartrate) : "—" },
          ].map((stat, i) => <div key={stat.label} className={cn("min-w-0", i > 0 && "border-l border-[var(--glass-border)] pl-3 sm:pl-5")}>
            <dt className="stat-label">{stat.label}</dt><dd className="num mt-1 text-[clamp(1.25rem,4vw,1.75rem)] font-medium leading-none">{stat.value}</dd>
          </div>)}
        </div>
      </dl>}

      {primary && workout && workout.reps.length > 0 && <section aria-label="Work repetitions" className="space-y-1.5">
        <h4 className="stat-label">{workout.reps.length > 1 ? "Work reps" : "Work segment"}</h4>
        <table className="data-table text-xs">
          <thead><tr><th scope="col">Rep</th><th scope="col">Time</th><th scope="col">Pace /{unit}</th><th scope="col" className="text-right">Avg BPM</th></tr></thead>
          <tbody>{workout.reps.map((rep, index) => <tr key={index}>
            <th scope="row" className="text-muted-foreground">Rep {index + 1}</th>
            <td className="num">{secondsToTime(Math.round(rep.duration_s))}</td><td className="num font-bold">{paceInUnits(secondsToPace(Math.round(rep.pace_sec_per_mile)), units)}</td>
            <td className="r text-muted-foreground">{rep.average_hr != null ? Math.round(rep.average_hr) : "—"}</td>
          </tr>)}</tbody>
        </table>
        {workout.recovery_seconds != null && <p className="px-1 text-xs text-muted-foreground">Recovery between reps <span className="num ml-1 font-semibold text-foreground">{secondsToTime(workout.recovery_seconds)}</span></p>}
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
  /** The coach's read on the selected run, shown inline under it */
  coach?: (activityId: number, hasComment: boolean) => React.ReactNode;
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
  // The run tab in view (Run 1 / Run 2 / walk / day total) decides which comment and review show.
  const [selected, setSelected] = useState("primary");
  const [savedNotes, setSavedNotes] = useState<Record<number, string>>({});
  const extra = today?.actual?.other_runs?.find((a) => `run-${a.id}` === selected) ?? null;
  const walkSelected = selected.startsWith("walk-");
  const primaryNotes = feedback?.feel_notes ?? today?.actual?.notes ?? null;

  const details = today && open && (
    <div className="mt-3 space-y-3 rounded-2xl bg-[var(--glass-inner)] p-3.5 text-sm">
      {done && cleanPurpose(today.purpose) && <div className="space-y-1"><h4 className="stat-label">Coach preview</h4><p className="leading-relaxed text-muted-foreground">{cleanPurpose(today.purpose)}</p></div>}
      {today.warmup && <p><span className="font-medium">Warmup:</span> {today.warmup}</p>}
      {today.description && <p className="leading-relaxed">{today.description}</p>}
      {today.cooldown && <p><span className="font-medium">Cooldown:</span> {today.cooldown}</p>}
    </div>
  );

  const extraNotes = extra ? savedNotes[extra.id] ?? extra.notes ?? null : null;
  // A second run of the day gets its own comment, saved to that recording (never the main run's).
  const extraBlock = extra && (
    <div className="glass-tile p-4">
      {extraNotes
        ? <details className="group"><summary className="min-h-8 text-sm text-muted-foreground transition-colors hover:text-foreground">Edit your comment on this run</summary>
            <div className="mt-3"><FeedbackForm key={`extra-${extra.id}-edit`} compact activityId={extra.id} date={today!.date} initial={{ notes: extraNotes }}
              watch={{ feel: extra.watch_feel, effort: extra.watch_effort }}
              onSubmitted={(fb) => { setSavedNotes((m) => ({ ...m, [extra.id]: fb.feel_notes ?? "" })); onFeedbackSaved?.(); }} /></div></details>
        : <><p className="mb-2 text-sm font-bold">How did this run go?</p>
            <FeedbackForm key={`extra-${extra.id}`} compact activityId={extra.id} date={today!.date}
              watch={{ feel: extra.watch_feel, effort: extra.watch_effort }}
              onSubmitted={(fb) => { setSavedNotes((m) => ({ ...m, [extra.id]: fb.feel_notes ?? "" })); onFeedbackSaved?.(); }} /></>}
    </div>
  );

  const feedbackBlocks = extra ? extraBlock : walkSelected ? null : <>
    {done && today && today.type !== "rest" && !feedback?.feel_notes && (
      <div className="glass-tile p-4">
        <p className="mb-2 text-sm font-bold">How did it go?</p>
        <FeedbackForm compact date={today.date}
          watch={{ feel: today.actual?.watch_feel, effort: today.actual?.watch_effort }}
          onSubmitted={(fb) => { setFeedback(fb); onFeedbackSaved?.(); }} />
      </div>
    )}
    {done && today && today.type !== "rest" && !!feedback?.feel_notes && (
      <details className="glass-tile group px-4 py-3">
        <summary className="min-h-8 text-sm text-muted-foreground transition-colors hover:text-foreground">Edit your comment</summary>
        <div className="mt-3">
          <FeedbackForm compact date={today.date} initial={{ notes: feedback.feel_notes }}
            watch={{ feel: today.actual?.watch_feel, effort: today.actual?.watch_effort }}
            onSubmitted={(fb) => { setFeedback(fb); onFeedbackSaved?.(); }} />
        </div>
      </details>
    )}
    {feedback?.evaluation && (
      <p className="glass-tile p-3.5 text-xs leading-relaxed text-muted-foreground">
        <span className="mb-1 block text-xs font-bold text-foreground">{feedback.evaluation.decision === "off_plan" ? "Logged: " : "Progression: "}</span>
        {feedback.evaluation.reason}
      </p>
    )}
    {feedback?.changes?.map((c) => (
      <p key={`${c.change}-${c.date}`} className="px-1 text-xs text-muted-foreground">{c.reason}</p>
    ))}
  </>;
  const coachRunId = extra ? extra.id : today?.actual?.activity_id;
  const coachBlock = coach && coachRunId != null && !walkSelected && (
    <section className="glass-tile space-y-3 p-4" aria-label="Coach analysis">
      <h3 className="text-[13px] font-bold">Coach analysis · {extra ? "this run" : (today?.actual?.other_runs?.length ? "main run" : "today's run")}</h3>
      {coach(coachRunId, !!(extra ? extraNotes : primaryNotes))}
    </section>);
  // A finished run gets the wireframe's two columns on wide screens: the run, then comment + coach.
  const split = done;

  return (
    <Card className="py-0">
      <CardContent className="pt-1 pb-4">
       <div className={cn("grid gap-4", split && "xl:grid-cols-[minmax(0,1fr)_minmax(0,20rem)] xl:gap-5")}>
        <div className="min-w-0 space-y-4">
        {planStale ? (
          <div className="space-y-3 py-2">
            <p className="text-sm text-muted-foreground">Your last training block has ended.</p>
            <Link href="/plan" className={buttonVariants({ size: "sm" })}>Generate this week&apos;s plan</Link>
          </div>
        ) : !today ? (
          <p className="py-2 text-sm text-muted-foreground">No plan for today yet.</p>
        ) : done ? (
          <>
            <ActualRun day={today} onOpenActivity={onOpenActivity} selected={selected} setSelected={setSelected} />
            {today.type !== "rest" && (
              <div className="glass-tile space-y-1.5 px-4 py-3">
                <h3 className="stat-label">Training context · main run</h3>
                <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
                  className="flex min-h-8 w-full items-center gap-1.5 text-left text-sm transition-colors hover:text-foreground">
                  <span className={cn(offPlan && "line-through decoration-muted-foreground/60")}>
                    Planned: {today.title} · {formatDistance(today.distance_miles)} {unit}
                  </span>
                  <ChevronDown className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} aria-hidden />
                </button>
                {details}
              </div>
            )}
          </>
        ) : (
          <button type="button" className="group w-full rounded-[20px] text-left" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 space-y-2">
                <div className="text-2xl font-bold leading-tight tracking-tight group-hover:underline group-hover:underline-offset-4 sm:text-3xl">{today.title}</div>
                <div className="hero-num text-[clamp(3.5rem,11vw,6.5rem)]">
                  {today.type === "rest" ? <span className="text-[clamp(2.5rem,8vw,4rem)]">Rest day</span> : <>{formatDistance(today.distance_miles)}<span className="ml-1 text-[clamp(1.1rem,3vw,1.6rem)] font-normal tracking-normal text-muted-foreground"> {unit} planned</span></>}
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                {hardToday && <Badge variant="secondary" className="text-xs">Quality</Badge>}
                <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-180")} />
              </div>
            </div>
            {details}
          </button>
        )}

        {!done && today && today.type !== "rest" && !feedback?.feel_notes && (
          <details className="glass-tile px-4 py-3">
            <summary className="min-h-8 text-sm text-muted-foreground transition-colors hover:text-foreground">Ran without your watch? Log it</summary>
            <div className="mt-3">
              <FeedbackForm compact hasRecording={false} date={today.date}
                onSubmitted={(fb) => { setFeedback(fb); onFeedbackSaved?.(); }} />
            </div>
          </details>
        )}
        {!split && feedbackBlocks}
        {!done && today && cleanPurpose(today.purpose) && <section className="glass-tile space-y-1.5 p-4" aria-label="Coach preview"><h3 className="text-[13px] font-bold">Coach preview</h3><p className="text-sm leading-relaxed text-muted-foreground">{cleanPurpose(today.purpose)}</p></section>}
        {hardToday && !done && recoveryCaution && (
          <p className="rounded-2xl border border-[color-mix(in_srgb,var(--warn)_45%,transparent)] bg-[var(--warn-tint)] p-3 text-sm">
            Recovery signals are down and today is a hard day. Consider easy running or rest, and review a safe replacement or move in your plan.{" "}
            <Link href="/plan" className="font-semibold underline underline-offset-2">Adjust in Plan →</Link>
          </p>
        )}
        {!split && coachBlock}
        </div>
        {split && <div className="min-w-0 space-y-3">{feedbackBlocks}{coachBlock}</div>}
       </div>
      </CardContent>
    </Card>
  );
}
