"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { FeedbackForm } from "@/components/feedback-form";
import {
  workoutTypeLabel,
  isHardWorkout,
  formatDistance,
  formatDate,
  secondsToTime,
  localDateStr,
} from "@/lib/format";
import type { Workout, DayFeedback } from "@/lib/types";

interface PlanDayProps {
  workout: Workout;
  isToday: boolean;
  expanded: boolean;
  onToggle: () => void;
  onPlanChanged?: () => void;
}

function ComparisonBadge({ diffMiles }: { diffMiles: number }) {
  const pct = Math.abs(diffMiles);
  if (pct <= 0.3) {
    return <Badge variant="secondary" className="text-[10px] bg-green-500/15 text-green-600">On target</Badge>;
  }
  return <Badge variant="secondary" className="text-[10px] bg-yellow-500/15 text-yellow-600">Off target</Badge>;
}

/**
 * Extract a workout title from a Strava activity description.
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
 * Uses the Strava description to check for workout patterns.
 */
function actualIsWorkout(description: string | null): boolean {
  if (!description) return false;
  return /\d+x\d+|threshold|tempo|intervals|fartlek|hill|progression/i.test(description);
}

export function PlanDay({ workout, isToday, expanded, onToggle, onPlanChanged }: PlanDayProps) {
  const today = localDateStr();
  const isPast = workout.date < today;
  const hasActual = !!workout.actual;
  const isPrescribed = workout.prescribed !== false;

  // For completed days, derive the display title from what was actually done
  const actualWorkoutTitle = hasActual ? extractWorkoutTitle(workout.actual?.description ?? null) : null;
  const actualWasWorkout = hasActual && actualIsWorkout(workout.actual?.description ?? null);
  // Show actual title if completed: workout title from description, Strava name, or fallback
  const displayTitle = hasActual
    ? (actualWorkoutTitle || workout.actual?.name || workout.title)
    : workout.title;
  const displayIsHard = hasActual ? actualWasWorkout : isHardWorkout(workout.type);
  const [localFeedback, setLocalFeedback] = useState<DayFeedback | null>(workout.feedback || null);
  const hasFeedback = !!localFeedback;
  const showFeedbackForm = hasActual && !hasFeedback && workout.type !== "rest";

  return (
    <div
      className={cn(
        "cursor-pointer rounded-md border p-3 transition-colors hover:bg-secondary/50",
        isToday && "border-foreground",
        hasActual && "bg-secondary/30",
        !isPrescribed && !hasActual && "opacity-40",
        workout.skipped && "opacity-50"
      )}
      onClick={onToggle}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onToggle()}
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
              {displayIsHard && (
                <Badge variant="default" className="text-[10px] px-1.5 py-0">
                  Quality
                </Badge>
              )}
            </div>
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
              mi
            </span>
          )}
          {hasActual && (
            <span className="text-xs font-medium text-green-600">Done</span>
          )}
          {isToday && !hasActual && (
            <Badge variant="secondary" className="text-[10px]">Today</Badge>
          )}
          {isPast && !hasActual && !workout.skipped && !isToday && workout.type !== "rest" && isPrescribed && (
            <span className="text-xs text-destructive">Missed</span>
          )}
          {workout.skipped && (
            <span className="text-xs text-muted-foreground">Skipped</span>
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
                    <ComparisonBadge diffMiles={workout.comparison.distance_diff_miles} />
                  )}
                </div>

                {/* Actual metrics grid */}
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Distance</span>
                    <span className="font-mono">{formatDistance(workout.actual.distance_miles)} mi</span>
                  </div>
                  {workout.actual.avg_pace && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Pace</span>
                      <span className="font-mono">{workout.actual.avg_pace}/mi</span>
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

                {/* Strava description */}
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
                        <span className="font-mono">{formatDistance(a.distance_miles)} mi</span>
                        {a.avg_pace && <span className="font-mono">{a.avg_pace}/mi</span>}
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
                    <span> — {formatDistance(workout.distance_miles)} mi</span>
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
                    Pace: {localFeedback.pace_assessment.replace("_", " ")}
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
              {localFeedback.coach_response && (
                <div className="rounded-md bg-secondary/50 p-2.5 text-xs leading-relaxed">
                  <span className="font-medium">Coach: </span>
                  <span className="text-muted-foreground">{localFeedback.coach_response}</span>
                </div>
              )}
            </div>
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
