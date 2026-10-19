"use client";

import { useState } from "react";
import { FeedbackForm } from "@/components/feedback-form";
import Link from "next/link";
import { ChevronDown, CircleCheck, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { formatDistance } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { RecoverySignal, Wellness } from "@/components/home/types";

export interface PlanDayLite {
  date: string;
  type: string;
  title: string;
  description: string | null;
  purpose?: string | null;
  distance_miles: number;
  warmup?: string | null;
  cooldown?: string | null;
  actual?: { distance_miles: number; avg_pace: string | null } | null;
  feedback?: { feel_rating: number | null; coach_response: string | null } | null;
}

const LEVEL_COLOR: Record<string, string> = {
  PRIME: "var(--status-good)",
  HIGH: "var(--status-good)",
  MODERATE: "var(--status-warning)",
  LOW: "var(--status-serious)",
  POOR: "var(--status-critical)",
};

function ReadinessRing({ score, level }: { score: number; level: string | null | undefined }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const color = LEVEL_COLOR[(level || "").toUpperCase()] ?? "var(--viz-series-1)";
  return (
    <div className="relative h-20 w-20 shrink-0" role="img" aria-label={`Training readiness ${score} of 100${level ? `, ${level.toLowerCase()}` : ""}`}>
      <svg viewBox="0 0 80 80" className="h-20 w-20 -rotate-90">
        <circle cx="40" cy="40" r={r} fill="none" stroke="var(--color-muted)" strokeWidth="8" />
        <circle
          cx="40" cy="40" r={r} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - Math.min(score, 100) / 100)}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-mono text-xl font-semibold leading-none">{score}</span>
        <span className="text-xs uppercase tracking-wide text-muted-foreground">ready</span>
      </div>
    </div>
  );
}

const FEEDBACK: Record<string, string> = {
  RECOVERY_IN_PROGRESS: "Recovery in progress",
  WELL_RECOVERED: "Well recovered",
  READY_FOR_HARD: "Ready for a hard session",
  GOOD_SLEEP_LAST_NIGHT: "Good sleep last night",
  HIGH_RECOVERY_NEEDS: "High recovery needs",
  POOR_SLEEP: "Poor sleep last night",
};

export function TodayCard({
  today,
  wellness,
  statusLabel,
  signals,
  planStale,
  mileageRisk,
}: {
  today: PlanDayLite | null;
  wellness: Wellness | null;
  statusLabel: string | null;
  signals: RecoverySignal[];
  planStale: boolean;
  /** Stride's own mileage-based injury risk (from the plan's athlete snapshot) */
  mileageRisk?: string | null;
}) {
  const hardToday = !!today && (today.type === "workout" || today.type === "long_run" || today.type === "race");
  const done = !!today?.actual;
  // Hard days open by default so the "why" is visible without a tap
  const [open, setOpen] = useState(hardToday && !done);
  const [feedback, setFeedback] = useState(today?.feedback ?? null);
  const highMileageRisk = !!mileageRisk && mileageRisk.toUpperCase().startsWith("HIGH");
  const allSignals: RecoverySignal[] = highMileageRisk
    ? [...signals, { level: "warning", metric: "mileage", message: `Stride mileage check: ${mileageRisk}` }]
    : signals;
  const cautions = allSignals.filter((s) => s.level !== "good");

  return (
    <Card>
      <CardContent className="space-y-4 pt-4">
        {wellness?.readiness_score != null && (
          <div className="flex items-center gap-4">
            <ReadinessRing score={wellness.readiness_score} level={wellness.readiness_level} />
            <div className="min-w-0 space-y-1">
              <div className="text-sm font-medium">
                {wellness.readiness_level ? `${wellness.readiness_level.charAt(0)}${wellness.readiness_level.slice(1).toLowerCase()} readiness` : "Readiness"}
              </div>
              <div className="text-xs text-muted-foreground">
                {FEEDBACK[wellness.readiness_feedback || ""] ?? (wellness.readiness_feedback || "").replaceAll("_", " ").toLowerCase()}
                {wellness.recovery_time_min ? ` · ${Math.round(wellness.recovery_time_min / 60)}h recovery left` : ""}
              </div>
              {statusLabel && (
                <Badge variant="secondary" className="text-xs">
                  Training status: {statusLabel}
                </Badge>
              )}
            </div>
          </div>
        )}

        {allSignals.length > 0 && (
          <ul className="space-y-1.5">
            {allSignals.map((s) => (
              <li key={s.metric} className="flex gap-2 text-sm">
                {s.level === "good" ? (
                  <CircleCheck className="mt-0.5 size-4 shrink-0" style={{ color: "var(--status-good)" }} aria-label="Good" />
                ) : (
                  <TriangleAlert className="mt-0.5 size-4 shrink-0" style={{ color: "var(--status-serious)" }} aria-label="Caution" />
                )}
                <span className="leading-snug">{s.message}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="border-t pt-3">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Today&apos;s run</div>
          {planStale ? (
            <div className="mt-1 space-y-2">
              <p className="text-sm text-muted-foreground">Your last training block has ended.</p>
              <Link href="/plan" className={buttonVariants({ size: "sm" })}>
                Generate this week&apos;s plan
              </Link>
            </div>
          ) : !today ? (
            <p className="mt-1 text-sm text-muted-foreground">No plan for today yet.</p>
          ) : (
            <button type="button" className="mt-1 w-full text-left" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-lg font-semibold leading-tight">{today.title}</div>
                  <div className="text-sm text-muted-foreground">
                    {today.type === "rest" ? "Rest day" : `${formatDistance(today.distance_miles)} mi planned`}
                    {done && ` · done: ${formatDistance(today.actual!.distance_miles)} mi${today.actual!.avg_pace ? ` at ${today.actual!.avg_pace}/mi` : ""}`}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {done && <Badge className="text-xs">Done</Badge>}
                  {hardToday && !done && <Badge variant="secondary" className="text-xs">Quality</Badge>}
                  <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-180")} />
                </div>
              </div>
              {open && (
                <div className="mt-3 space-y-2 text-sm">
                  {today.warmup && <p><span className="font-medium">Warmup:</span> {today.warmup}</p>}
                  {today.description && <p className="leading-relaxed">{today.description}</p>}
                  {today.cooldown && <p><span className="font-medium">Cooldown:</span> {today.cooldown}</p>}
                  {today.purpose && <p className="text-muted-foreground italic">Why: {today.purpose}</p>}
                </div>
              )}
            </button>
          )}
          {done && today && today.type !== "rest" && !feedback?.feel_rating && (
            <div className="mt-3 rounded-lg border p-3">
              <p className="mb-2 text-sm font-medium">
                Nice — {formatDistance(today.actual!.distance_miles)} mi done. How did it feel?
              </p>
              <FeedbackForm compact date={today.date} onSubmitted={(fb) => setFeedback(fb)} />
            </div>
          )}
          {feedback?.coach_response && (
            <div className="mt-3 rounded-lg bg-muted p-3 text-sm">
              <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Coach</div>
              <p className="leading-relaxed">{feedback.coach_response}</p>
            </div>
          )}
          {hardToday && !done && cautions.length > 0 && (
            <p className="mt-3 rounded-md bg-muted p-2 text-sm">
              Your recovery numbers are down and today is a hard day. Consider running it easy and doing the session
              tomorrow. An undertrained runner races; an injured one doesn&apos;t.{" "}
              <Link href="/plan" className="font-medium underline underline-offset-2">Adjust in Plan →</Link>
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
