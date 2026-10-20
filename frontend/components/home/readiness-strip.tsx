"use client";

import { useState } from "react";
import { ChevronDown, CircleCheck, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RecoverySignal, Wellness } from "@/components/home/types";

const LEVEL_COLOR: Record<string, string> = {
  PRIME: "var(--status-good)",
  HIGH: "var(--status-good)",
  MODERATE: "var(--status-warning)",
  LOW: "var(--status-serious)",
  POOR: "var(--status-critical)",
};

const FEEDBACK: Record<string, string> = {
  RECOVERY_IN_PROGRESS: "Recovery in progress",
  WELL_RECOVERED: "Well recovered",
  READY_FOR_HARD: "Ready for a hard session",
  GOOD_SLEEP_LAST_NIGHT: "Good sleep last night",
  HIGH_RECOVERY_NEEDS: "High recovery needs",
  POOR_SLEEP: "Poor sleep last night",
};

function ReadinessRing({ score, level }: { score: number; level: string | null | undefined }) {
  const r = 13;
  const c = 2 * Math.PI * r;
  const color = LEVEL_COLOR[(level || "").toUpperCase()] ?? "var(--viz-series-1)";
  return (
    <div className="relative size-8 shrink-0" role="img" aria-label={`Training readiness ${score} of 100${level ? `, ${level.toLowerCase()}` : ""}`}>
      <svg viewBox="0 0 32 32" className="size-8 -rotate-90">
        <circle cx="16" cy="16" r={r} fill="none" stroke="var(--color-muted)" strokeWidth="3.5" />
        <circle cx="16" cy="16" r={r} fill="none" stroke={color} strokeWidth="3.5" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - Math.min(score, 100) / 100)} />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center font-mono text-[11px] font-semibold">{score}</span>
    </div>
  );
}

/** One compact line: Garmin readiness plus any recovery cautions. Good signals fold away. */
export function ReadinessStrip({ wellness, signals, mileageRisk }: {
  wellness: Wellness | null; signals: RecoverySignal[]; mileageRisk?: string | null;
}) {
  const [showGood, setShowGood] = useState(false);
  const all: RecoverySignal[] = mileageRisk?.toUpperCase().startsWith("HIGH")
    ? [...signals, { level: "warning", metric: "mileage", message: `Stride mileage check: ${mileageRisk}` }]
    : signals;
  const cautions = all.filter((s) => s.level !== "good");
  const goods = all.filter((s) => s.level === "good");
  if (wellness?.readiness_score == null && all.length === 0) return null;
  const text = wellness?.readiness_feedback
    ? FEEDBACK[wellness.readiness_feedback] ?? wellness.readiness_feedback.replaceAll("_", " ").toLowerCase()
    : "";
  return (
    <div className="space-y-1.5 rounded-md border bg-card px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {wellness?.readiness_score != null && (
          <div className="flex items-center gap-2">
            <ReadinessRing score={wellness.readiness_score} level={wellness.readiness_level} />
            <span className="text-sm">
              <span className="font-medium">Readiness</span>
              <span className="text-muted-foreground">
                {[text, wellness.recovery_time_min ? `${Math.round(wellness.recovery_time_min / 60)}h recovery left` : ""].filter(Boolean).map((t) => ` · ${t}`).join("")}
              </span>
            </span>
          </div>
        )}
        {goods.length > 0 && (
          <button type="button" onClick={() => setShowGood((v) => !v)} aria-expanded={showGood}
            className="ml-auto flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <CircleCheck className="size-3.5" style={{ color: "var(--status-good)" }} aria-hidden />
            {goods.length} good
            <ChevronDown className={cn("size-3.5 transition-transform", showGood && "rotate-180")} />
          </button>
        )}
      </div>
      {[...cautions, ...(showGood ? goods : [])].map((s) => (
        <p key={s.metric} className="flex gap-2 text-xs leading-snug">
          {s.level === "good"
            ? <CircleCheck className="mt-px size-3.5 shrink-0" style={{ color: "var(--status-good)" }} aria-label="Good" />
            : <TriangleAlert className="mt-px size-3.5 shrink-0" style={{ color: "var(--status-serious)" }} aria-label="Caution" />}
          <span>{s.message}</span>
        </p>
      ))}
    </div>
  );
}
