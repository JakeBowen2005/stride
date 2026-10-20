"use client";

import { distanceInUnits, paceInUnits, unitLabel, type Units } from "@/lib/units";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { KindPill } from "@/components/cockpit/pill";
import { StructureBar } from "@/components/cockpit/structure-bar";
import { sessionKind } from "@/lib/workout-style";
import { SessionControls } from "@/components/session-controls";
import { FeedbackForm } from "@/components/feedback-form";
import {
  formatDate,
  secondsToTime,
  localDateStr,
} from "@/lib/format";
import type { Workout, DayFeedback } from "@/lib/types";

interface PlanDayProps {
  workout: Workout;
  units?: Units;
  isToday: boolean;
  expanded: boolean;
  onToggle?: () => void;
  /** Always expanded (e.g. the Plan inspector): no toggle affordance. */
  pinned?: boolean;
  onPlanChanged?: () => void;
  readOnly?: boolean;
}

function ComparisonBadge({ diffMiles, units }: { diffMiles: number; units: Units }) {
  const diff = Math.abs(diffMiles);
  if (diff <= 0.3) {
    return <Badge variant="secondary" className="text-xs">On distance</Badge>;
  }
  return (
    <Badge variant="secondary" className="text-xs">
      Ran {distanceInUnits(diff, units)} {unitLabel(units)} {diffMiles > 0 ? "long" : "short"}
    </Badge>
  );
}

const PACE_LABELS: Record<string, string> = { above: "Faster than target", on_target: "On target", below: "Slower than target", skipped: "Skipped" };

/**
 * Extract a workout title from an activity description (user notes or Garmin lap summary).
 * Looks for patterns like "6x800", "3x10min", "4x200", "2x1mile" etc.
 * Returns null if no workout pattern found (plain easy run).
 */
function extractWorkoutTitle(description: string | null): string | null {
  if (!description) return null;

  // Match patterns like "6x800", "4x200", "3x1k", "2x1mile", "3x10min", "2x10min"
  const patterns = description.match(/\d+x\d+(?:m|k|mi|mile|min)?(?:\s*(?:hard|fast))?/gi);
  if (!patterns || patterns.length === 0) return null;

  // Build a combined title from all workout segments
  // e.g. "6x800 then 4x200" -> "6x800 + 4x200"
  return patterns.join(" + ");
}

/**
 * Determine whether the actual run was a workout or an easy/recovery run.
 * Uses the activity description to check for workout patterns.
 */
function actualIsWorkout(description: string | null): boolean {
  if (!description) return false;
  return /\d+x\d+|threshold|tempo|intervals|fartlek|hill|progression/i.test(description);
}

export function PlanDay({ workout, isToday, expanded, onToggle, pinned, onPlanChanged, readOnly, units = "miles" }: PlanDayProps) {
  const formatDistance = (miles: number) => distanceInUnits(miles, units);
  const unit = unitLabel(units);
  const today = localDateStr();
  const isPast = workout.date < today;
  const hasActual = !!workout.actual;
  const isPrescribed = workout.prescribed !== false;

  // For completed days, derive the display title from what was actually done
  const actualWorkoutTitle = hasActual ? extractWorkoutTitle(workout.actual?.description ?? null) : null;
  const actualWasWorkout = hasActual && actualIsWorkout(workout.actual?.description ?? null);
  // Keep the planned session as the title (it's what the athlete recognizes); what was
  // actually run shows underneath — Garmin's auto-names ("Fullerton Running") say little.
  const displayTitle = workout.title;
  const actualLine = hasActual
    ? [actualWasWorkout ? actualWorkoutTitle : null, workout.actual?.name, workout.actual?.avg_pace ? `${paceInUnits(workout.actual.avg_pace, units)}/${unit}` : null]
        .filter(Boolean)
        .join(" · ")
    : null;
  const kind = sessionKind(workout.type, workout.title, workout.prescription?.category);
  const [localFeedback, setLocalFeedback] = useState<DayFeedback | null>(workout.feedback || null);
  const hasFeedback = !!localFeedback;
  const showFeedbackForm = !readOnly && hasActual && !hasFeedback && workout.type !== "rest";

  return (
    <div
      id={`session-${workout.id}`}
      className={cn(
        "rounded-md border bg-card p-3 transition-colors",
        !pinned && "cursor-pointer hover:border-primary/30 hover:bg-secondary/50",
        isToday && "border-primary bg-primary/5",
        hasActual && "bg-secondary/30",
        !isPrescribed && !hasActual && "opacity-40",
        workout.skipped && "opacity-50"
      )}
      onClick={pinned ? undefined : onToggle}
      role={pinned ? undefined : "button"}
      tabIndex={pinned ? undefined : 0}
      aria-expanded={pinned ? undefined : expanded}
      onKeyDown={pinned ? undefined : (e) => { if (e.target===e.currentTarget && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onToggle?.(); } }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-20 text-sm">
            <div className="font-medium">{formatDate(workout.date).split(",")[0]}</div>
            <div className="text-xs text-muted-foreground">
              {formatDate(workout.date).split(", ")[1]}
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium">{displayTitle}</span>
              {workout.type !== "easy" && <KindPill kind={kind} />}
            </div>
            {actualLine && <div className="text-xs text-muted-foreground">{actualLine}</div>}
            {workout.adjustment_note && (
              <div className="text-xs text-muted-foreground">Adjusted: {workout.adjustment_note}</div>
            )}
            {workout.intervals && !hasActual && (
              <div className="font-mono text-xs text-muted-foreground">
                {workout.intervals}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 text-right">
          {workout.type !== "rest" && (
            <span className="font-mono text-sm font-medium">
              {hasActual && workout.actual
                ? formatDistance(workout.actual.distance_miles)
                : formatDistance(workout.distance_miles)}{" "}
              {unit}
            </span>
          )}
          {hasActual && (
            <span className="text-xs font-medium" style={{ color: "var(--type-easy)" }}>Done</span>
          )}
          {isToday && !hasActual && (
            <Badge variant="secondary" className="text-xs">Today</Badge>
          )}
          {isPast && !hasActual && !workout.skipped && !isToday && workout.type !== "rest" && isPrescribed && (
            <span className="text-xs text-muted-foreground">Not logged</span>
          )}
          {workout.skipped && !hasActual && (
            <span className="text-xs text-muted-foreground">Skipped</span>
          )}
          {!hasActual && workout.session_status === "moved" && (
            <span className="text-xs text-muted-foreground">{workout.moved_to ? `Moved to ${workout.moved_to}` : "Moved here"}</span>
          )}
          {!hasActual && workout.session_status === "replaced" && (
            <span className="text-xs text-muted-foreground">Replaced</span>
          )}
        </div>
      </div>

      {expanded && (
        <div className="mt-3 space-y-2 border-t pt-3 text-sm">
          {/* Completed day: show Actual first, then Planned below for comparison */}
          {hasActual && workout.actual && (
            <>
              {/* Actual run data */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">What you did</span>
                  {workout.comparison && (
                    <ComparisonBadge units={units} diffMiles={workout.comparison.distance_diff_miles} />
                  )}
                </div>

                {/* Actual metrics grid */}
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Distance</span>
                    <span className="font-mono">{formatDistance(workout.actual.distance_miles)} {unit}</span>
                  </div>
                  {workout.actual.avg_pace && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Pace</span>
                      <span className="font-mono">{paceInUnits(workout.actual.avg_pace, units)}/{unit}</span>
                    </div>
                  )}
                  {workout.actual.average_heartrate && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">HR</span>
                      <span className="font-mono">{Math.round(workout.actual.average_heartrate)} bpm</span>
                    </div>
                  )}
                  {workout.actual.duration_seconds > 0 && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Time</span>
                      <span className="font-mono">{secondsToTime(workout.actual.duration_seconds)}</span>
                    </div>
                  )}
                </div>

                {/* Activity notes / Garmin lap summary */}
                {workout.actual.description && (
                  <p className="text-xs text-muted-foreground italic whitespace-pre-line">
                    {workout.actual.description}
                  </p>
                )}

                {/* Comparison summary */}
                {workout.comparison && (
                  <p className="text-xs text-muted-foreground">
                    {workout.comparison.summary}
                  </p>
                )}

                {/* Multi-activity breakdown */}
                {workout.actual.activity_count && workout.actual.activity_count > 1 && workout.actual.activities && (
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground font-medium">{workout.actual.activity_count} activities:</p>
                    {workout.actual.activities.map((a, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground pl-2">
                        <span>{a.name}</span>
                        <span className="font-mono">{formatDistance(a.distance_miles)} {unit}</span>
                        {a.avg_pace && <span className="font-mono">{paceInUnits(a.avg_pace, units)}/{unit}</span>}
                      </div>
                    ))}
                  </div>
                )}

                {/* Feel rating from activity (only if no feedback submitted yet) */}
                {!hasFeedback && workout.actual.feel_rating && (
                  <div className="text-xs">
                    <span className="text-muted-foreground">Felt: </span>
                    <span className="font-mono font-medium">{workout.actual.feel_rating}/10</span>
                  </div>
                )}
              </div>

              {/* Planned section for comparison */}
              {isPrescribed && (
                <div className="border-t pt-2 space-y-1">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Planned</span>
                  <div className="text-xs text-muted-foreground">
                    <span className="font-medium">{workout.title}</span>
                    <span> — {formatDistance(workout.distance_miles)} {unit}</span>
                  </div>
                  {workout.description && (
                    <p className="text-xs text-muted-foreground">{workout.description}</p>
                  )}
                  {workout.purpose && (
                    <p className="text-xs text-muted-foreground">
                      <span className="font-medium">Why: </span>{workout.purpose}
                    </p>
                  )}
                </div>
              )}
            </>
          )}

          {/* Not completed yet: show the planned workout details */}
          {!hasActual && isPrescribed && (
            <>
              {workout.type === "workout" && workout.prescription && <StructureBar prescription={workout.prescription} kind={kind} />}
              <p className="text-muted-foreground">{workout.description}</p>
              {workout.target_pace && (
                <div>
                  <span className="text-muted-foreground">Target: </span>
                  <span className="font-mono">{workout.target_pace}</span>
                </div>
              )}
              {workout.warmup && (
                <div>
                  <span className="text-muted-foreground">Warmup: </span>
                  {workout.warmup}
                </div>
              )}
              {workout.cooldown && (
                <div>
                  <span className="text-muted-foreground">Cooldown: </span>
                  {workout.cooldown}
                </div>
              )}
              <div className="border-t pt-2">
                <span className="font-medium">Why: </span>
                <span className="text-muted-foreground">{workout.purpose}</span>
              </div>
            </>
          )}
          {!isPrescribed && !hasActual && (
            <p className="text-muted-foreground italic">No plan existed yet for this day.</p>
          )}

          {/* Existing feedback display */}
          {hasFeedback && localFeedback && (
            <div className="border-t pt-3 space-y-2">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Feedback</span>
              <div className="flex flex-wrap gap-2 text-xs">
                {localFeedback.feel_rating && (
                  <span className="rounded bg-secondary px-2 py-0.5 font-mono">
                    Feel: {localFeedback.feel_rating}/10
                  </span>
                )}
                {localFeedback.pace_assessment && (
                  <span className="rounded bg-secondary px-2 py-0.5">
                    Pace: {PACE_LABELS[localFeedback.pace_assessment] ?? localFeedback.pace_assessment}
                  </span>
                )}
                {localFeedback.swapped && (
                  <span className="rounded bg-yellow-500/15 text-yellow-600 px-2 py-0.5">
                    Swapped{localFeedback.actual_workout_type ? ` to ${localFeedback.actual_workout_type.replace("_", " ")}` : ""}
                  </span>
                )}
              </div>
              {localFeedback.feel_notes && (
                <p className="text-xs text-muted-foreground italic">
                  &ldquo;{localFeedback.feel_notes}&rdquo;
                </p>
              )}
              {localFeedback.swap_reason && (
                <p className="text-xs text-muted-foreground italic">
                  Swap reason: {localFeedback.swap_reason}
                </p>
              )}
              {localFeedback.evaluation && (
                <p className="text-xs">
                  <span className="font-medium">Progression: </span>
                  <span className="text-muted-foreground">{localFeedback.evaluation.reason}</span>
                </p>
              )}
              {localFeedback.changes?.map((c) => (
                <p key={`${c.change}-${c.date}`} className="text-xs text-muted-foreground">
                  {c.date ? `${c.date}: ` : ""}{c.reason}
                </p>
              ))}
              {localFeedback.coach_response && (
                <div className="rounded-md bg-secondary/50 p-2.5 text-xs leading-relaxed">
                  <span className="font-medium">Coach: </span>
                  <span className="text-muted-foreground">{localFeedback.coach_response}</span>
                </div>
              )}
            </div>
          )}

          {workout.session_status && !hasActual && workout.session_status !== "not_logged" && (
            <p className="text-sm">Status: {workout.session_status.replace("_", " ")}{workout.moved_to ? ` to ${workout.moved_to}` : ""}</p>
          )}
          {!readOnly && !hasActual && isPrescribed && workout.type !== "race" && !["skipped", "moved"].includes(workout.session_status ?? "") && (
            <SessionControls workout={workout} onChanged={onPlanChanged} />
          )}
          {/* Feedback form for completed days without feedback */}
          {showFeedbackForm && expanded && (
            <div className="border-t pt-3">
              <FeedbackForm
                date={workout.date}
                onSubmitted={(fb) => {
                  setLocalFeedback(fb);
                  // Re-fetch plan to reflect any adjustments from feedback
                  onPlanChanged?.();
                }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
