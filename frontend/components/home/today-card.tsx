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
  feedback?: {
    feel_rating: number | null;
    coach_response: string | null;
    evaluation?: { decision: string; reason: string } | null;
    changes?: { date: string | null; change: string; reason: string }[];
  } | null;
}

const LEVEL_COLOR: Record<string, string> = {
  PRIME: "var(--status-good)",
  HIGH: "var(--status-good)",
  MODERATE: "var(--status-warning)",
  LOW: "var(--status-serious)",
  POOR: "var(--status-critical)",
};

function ReadinessRing({ score, level }: { score: number; level: string | null | undefined }) {
  const r = 16;
  const c = 2 * Math.PI * r;
  const color = LEVEL_COLOR[(level || "").toUpperCase()] ?? "var(--viz-series-1)";
  return (
    <div className="relative size-10 shrink-0" role="img" aria-label={`Training readiness ${score} of 100${level ? `, ${level.toLowerCase()}` : ""}`}>
      <svg viewBox="0 0 40 40" className="size-10 -rotate-90">
        <circle cx="20" cy="20" r={r} fill="none" stroke="var(--color-muted)" strokeWidth="4" />
        <circle
          cx="20" cy="20" r={r} fill="none" stroke={color} strokeWidth="4" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - Math.min(score, 100) / 100)}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center font-mono text-xs font-semibold">{score}</span>
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
  onFeedbackSaved,
}: {
  today: PlanDayLite | null;
  wellness: Wellness | null;
  statusLabel: string | null;
  signals: RecoverySignal[];
  planStale: boolean;
  /** Stride's own mileage-based injury risk (from the plan's athlete snapshot) */
  mileageRisk?: string | null;
  /** Feedback can change upcoming days and the plan — let the page reload its data */
  onFeedbackSaved?: () => void;
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

  const goods = allSignals.filter((s) => s.level === "good");
  const [showGood, setShowGood] = useState(false);
  const level = wellness?.readiness_level;
  const readinessText = wellness?.readiness_feedback
    ? FEEDBACK[wellness.readiness_feedback] ?? wellness.readiness_feedback.replaceAll("_", " ").toLowerCase()
    : level
      ? `${level.charAt(0)}${level.slice(1).toLowerCase()} readiness`
      : "";

  return (
    <Card>
      <CardContent className="space-y-4 pt-4">
        <div>
          {planStale ? (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">Your last training block has ended.</p>
              <Link href="/plan" className={buttonVariants({ size: "sm" })}>
                Generate this week&apos;s plan
              </Link>
            </div>
          ) : !today ? (
            <p className="text-sm text-muted-foreground">No plan for today yet.</p>
          ) : (
            <button type="button" className="w-full text-left" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <div className="text-xl font-semibold leading-tight sm:text-2xl">{today.title}</div>
                  <div className="font-mono text-base font-medium sm:text-lg">
                    {today.type === "rest" ? "Rest day" : `${formatDistance(today.distance_miles)} mi planned`}
                    {done && (
                      <span className="text-muted-foreground">
                        {` · done ${formatDistance(today.actual!.distance_miles)} mi${today.actual!.avg_pace ? ` at ${today.actual!.avg_pace}/mi` : ""}`}
                      </span>
                    )}
                  </div>
                  {today.purpose && <p className="text-sm text-muted-foreground">{today.purpose}</p>}
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
                </div>
              )}
            </button>
          )}
          {done && today && today.type !== "rest" && !feedback?.feel_rating && (
            <div className="mt-3 rounded-lg border p-3">
              <p className="mb-2 text-sm font-medium">
                Nice — {formatDistance(today.actual!.distance_miles)} mi done. How did it feel?
              </p>
              <FeedbackForm
                compact
                date={today.date}
                onSubmitted={(fb) => {
                  setFeedback(fb);
                  onFeedbackSaved?.();
                }}
              />
            </div>
          )}
          {feedback?.evaluation && (
            <p className="mt-3 text-sm">
              <span className="font-medium">Progression: </span>
              <span className="text-muted-foreground">{feedback.evaluation.reason}</span>
            </p>
          )}
          {feedback?.changes?.map((c) => (
            <p key={`${c.change}-${c.date}`} className="mt-1 text-sm text-muted-foreground">
              {c.reason}
            </p>
          ))}
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

        {(wellness?.readiness_score != null || statusLabel || allSignals.length > 0) && (
          <div className="space-y-2 border-t pt-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              {wellness?.readiness_score != null && (
                <div className="flex items-center gap-2">
                  <ReadinessRing score={wellness.readiness_score} level={wellness.readiness_level} />
                  <div className="text-sm leading-tight">
                    <div className="font-medium">Readiness {wellness.readiness_score}</div>
                    <div className="text-xs text-muted-foreground">
                      {[readinessText, wellness.recovery_time_min ? `${Math.round(wellness.recovery_time_min / 60)}h recovery left` : ""]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                  </div>
                </div>
              )}
              {statusLabel && (
                <Badge variant="secondary" className="text-xs">
                  Training status: {statusLabel}
                </Badge>
              )}
            </div>
            {cautions.length > 0 && (
              <ul className="space-y-1.5">
                {cautions.map((s) => (
                  <li key={s.metric} className="flex gap-2 text-sm">
                    <TriangleAlert className="mt-0.5 size-4 shrink-0" style={{ color: "var(--status-serious)" }} aria-label="Caution" />
                    <span className="leading-snug">{s.message}</span>
                  </li>
                ))}
              </ul>
            )}
            {goods.length > 0 && (
              <div>
                <button
                  type="button"
                  onClick={() => setShowGood((v) => !v)}
                  aria-expanded={showGood}
                  className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                >
                  <CircleCheck className="size-3.5" style={{ color: "var(--status-good)" }} aria-hidden />
                  {goods.length} good signal{goods.length === 1 ? "" : "s"}
                  <ChevronDown className={cn("size-3.5 transition-transform", showGood && "rotate-180")} />
                </button>
                {showGood && (
                  <ul className="mt-1.5 space-y-1.5">
                    {goods.map((s) => (
                      <li key={s.metric} className="flex gap-2 text-sm">
                        <CircleCheck className="mt-0.5 size-4 shrink-0" style={{ color: "var(--status-good)" }} aria-label="Good" />
                        <span className="leading-snug">{s.message}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
