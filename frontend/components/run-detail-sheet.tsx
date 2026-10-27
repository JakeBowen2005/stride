"use client";

import { FeedbackForm } from "@/components/feedback-form";

import { useState } from "react";
import { apiUrl, USER_ID } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useUnits } from "@/components/unit-preferences";
import { distanceInUnits, paceInUnits, unitLabel } from "@/lib/units";
import { CoachingReview } from "@/components/coaching-review";

import { SplitsTable } from "@/components/splits-table";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import {
  workoutTypeLabel,
  isHardWorkout,
  formatDateLong,
  secondsToTime,
} from "@/lib/format";
import type { Activity } from "@/lib/types";

interface RunDetailSheetProps {
  activity: Activity | null;
  open: boolean;
  onClose: () => void;
  onClassificationChanged?: () => void;
}

function parseWorkoutDetails(desc: string): { type: string; details: string[] } | null {
  const lower = desc.toLowerCase();

  // Check if this is a workout description (contains paces, intervals, splits)
  const hasIntervals = /\d+x\d+/.test(lower);
  const hasSplits = /\(\d+:\d{2}/.test(desc) || /\(\d{2},\d{2}/.test(desc);
  const hasPace = /@\s*\d+:\d{2}/.test(desc);
  const hasThreshold = /threshold|tempo|progressive|main set/i.test(desc);

  if (!hasIntervals && !hasSplits && !hasPace && !hasThreshold) {
    return null;
  }

  const details: string[] = [];

  // Extract interval info (e.g., "6x800")
  const intervalMatch = desc.match(/(\d+)x(\d+)m?\b/i);
  if (intervalMatch) {
    const reps = intervalMatch[1];
    const dist = intervalMatch[2];
    details.push(`${reps}x${dist}m intervals`);
  }

  // Extract M:SS splits from parentheses
  const splitMatches = desc.match(/\(([^)]+)\)/g);
  if (splitMatches) {
    for (const m of splitMatches) {
      const inner = m.slice(1, -1);
      const times = inner.split(",").map((t) => t.trim()).filter(Boolean);
      if (times.length > 1 && (times[0].includes(":") || /^\d{2}$/.test(times[0]))) {
        // Calculate average
        const seconds = times
          .map((t) => {
            const clean = t.replace(/[^0-9:]/g, "");
            if (clean.includes(":")) {
              const [m, s] = clean.split(":");
              return parseInt(m) * 60 + parseInt(s);
            }
            return parseInt(clean);
          })
          .filter((n) => !isNaN(n));

        if (seconds.length > 0) {
          const avg = seconds.reduce((a, b) => a + b, 0) / seconds.length;
          const fastest = Math.min(...seconds);
          const slowest = Math.max(...seconds);

          if (seconds[0] > 100) {
            // M:SS format (800m, 1K, mile)
            const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
            details.push(`Avg: ${fmtTime(avg)} | Range: ${fmtTime(fastest)}-${fmtTime(slowest)}`);
          } else {
            // Seconds only (200m, 400m)
            details.push(`Avg: ${Math.round(avg)}s | Range: ${fastest}-${slowest}s`);
          }
        }
      }
    }
  }

  // Extract @ pace
  const paceMatch = desc.match(/@\s*(\d+:\d{2})/);
  if (paceMatch) {
    details.push(`Target pace: ${paceMatch[1]}/mi`);
  }

  if (details.length === 0) return null;

  const type = hasThreshold ? "Threshold/Tempo" : hasIntervals ? "Intervals" : "Workout";
  return { type, details };
}

export function RunDetailSheet({ activity, open, onClose, onClassificationChanged }: RunDetailSheetProps) {
  const units = useUnits();
  const unit = unitLabel(units);
  const [savingKind, setSavingKind] = useState(false);
  const [commentSaves, setCommentSaves] = useState(0);
  const [kindError, setKindError] = useState<string | null>(null);
  async function correctKind(kind: "run" | "walk" | "auto") {
    if (!activity) return;
    setSavingKind(true); setKindError(null);
    try {
      const response = await fetch(apiUrl(`/analysis/${USER_ID}/activities/${activity.id}/kind`), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind }) });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not save activity type");
      onClassificationChanged?.();
      onClose();
    } catch (error) { setKindError(error instanceof Error ? error.message : "Could not save activity type"); }
    finally { setSavingKind(false); }
  }
  if (!activity) return null;

  const workoutAnalysis = activity.description
    ? parseWorkoutDetails(activity.description)
    : null;

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent className="overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:w-3/4 data-[side=right]:sm:max-w-2xl data-[side=right]:lg:max-w-4xl">
        <SheetHeader className="sm:px-6 sm:pt-6">
          <SheetTitle className="flex flex-wrap items-center gap-2 pr-10 text-2xl font-light tracking-tight">
            {activity.title}
            {isHardWorkout(activity.type) && (
              <Badge variant="default" className="text-xs">
                {workoutTypeLabel(activity.type)}
              </Badge>
            )}
          </SheetTitle>
          <p className="text-sm text-muted-foreground">
            {formatDateLong(activity.date)}
          </p>
        </SheetHeader>

        {/* Wide screens: numbers and laps on the left, notes and coaching on the right.
            Phones keep a single column in the same reading order. */}
        <div className="grid gap-x-6 gap-y-4 px-4 pb-6 sm:px-6 lg:grid-cols-2 lg:grid-rows-[auto_1fr] lg:items-start">
          <div className="min-w-0 space-y-4 lg:col-start-1">
            {activity.classification && <section className="glass-tile space-y-2 p-3.5 text-sm" aria-label="Activity classification">
              <p className="font-medium">{activity.classification.kind === "walk" ? "Walk · excluded from running mileage" : "Run · included in running mileage"}{activity.classification.override ? " · corrected by you" : ""}</p>
              <p className="text-xs text-muted-foreground">{activity.classification.reason}</p>
              {activity.classification.needs_review && <p role="status" className="text-xs">Please confirm this activity. Slow pace alone cannot distinguish a walk from trail running or run/walk training.</p>}
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={savingKind || activity.classification.override === "run"} onClick={() => correctKind("run")}>Count as run</Button>
                <Button size="sm" variant="outline" disabled={savingKind || activity.classification.override === "walk"} onClick={() => correctKind("walk")}>Mark as walk</Button>
                {activity.classification.override && <Button size="sm" variant="ghost" disabled={savingKind} onClick={() => correctKind("auto")}>Use automatic type</Button>}
              </div>
              <p className="text-xs text-muted-foreground">Corrections update running totals and future coaching evidence. They do not rewrite your approved plan.</p>
              {kindError && <p role="alert" className="text-xs text-destructive">{kindError}</p>}
            </section>}

            {/* Distance is the hero number; the rest are glass tiles */}
            <div className="flex items-end gap-2">
              <span className="hero-num text-[clamp(4rem,12vw,6.5rem)]">{distanceInUnits(activity.distance_miles, units)}</span>
              <span className="pb-2 text-xl text-muted-foreground">{unit}</span>
            </div>
            <div className="grid grid-cols-2 gap-2 min-[420px]:grid-cols-3 [&>div]:rounded-2xl [&>div]:bg-[var(--glass-inner)] [&>div]:px-3 [&>div]:py-2.5 [&>div>div:last-child]:text-xs [&>div>div:last-child]:text-muted-foreground">
              <div>
                <div className="font-mono text-xl font-semibold">
                  {paceInUnits(activity.avg_pace.replace(/\/mi$/, ""), units)}/{unit}
                </div>
                <div className="text-xs text-muted-foreground">avg pace</div>
              </div>
              <div>
                <div className="font-mono text-xl font-semibold">
                  {secondsToTime(activity.duration_seconds)}
                </div>
                <div className="text-xs text-muted-foreground">time</div>
              </div>
              {activity.avg_heart_rate != null && (
                <div>
                  <div className="font-mono text-base font-semibold">{activity.avg_heart_rate}</div>
                  <div className="text-xs text-muted-foreground">avg HR</div>
                </div>
              )}
              {activity.elevation_gain_ft != null && (
                <div>
                  <div className="font-mono text-base font-semibold">
                    {units === "km" ? `${Math.round(activity.elevation_gain_ft / 3.281)} m` : `${activity.elevation_gain_ft} ft`}
                  </div>
                  <div className="text-xs text-muted-foreground">elevation</div>
                </div>
              )}
              {activity.cadence != null && (
                <div>
                  <div className="font-mono text-base font-semibold">{activity.cadence}</div>
                  <div className="text-xs text-muted-foreground">cadence</div>
                </div>
              )}
              {/* Garmin metrics */}
              {activity.aerobic_training_effect != null && (
                <div>
                  {/* Garmin's two scores (0-5): aerobic base vs. anaerobic/speed stimulus */}
                  <div className="font-mono text-base font-semibold" title="Garmin training effect, 0 to 5">
                    {activity.aerobic_training_effect.toFixed(1)} · {(activity.anaerobic_training_effect ?? 0).toFixed(1)}
                  </div>
                  <div className="text-xs text-muted-foreground">aerobic · anaerobic effect</div>
                </div>
              )}
              {activity.vo2max != null && (
                <div>
                  <div className="font-mono text-base font-semibold">{Math.round(activity.vo2max)}</div>
                  <div className="text-xs text-muted-foreground">VO2max</div>
                </div>
              )}
              {activity.avg_ground_contact_time != null && (
                <div>
                  <div className="font-mono text-base font-semibold">{Math.round(activity.avg_ground_contact_time)} ms</div>
                  <div className="text-xs text-muted-foreground">ground contact</div>
                </div>
              )}
            </div>
          </div>

          <div className="min-w-0 space-y-3 empty:hidden lg:col-start-2 lg:row-span-2 lg:row-start-1 [&>*]:rounded-[20px] [&>*]:bg-[var(--glass-inner)] [&>*]:p-4">
            <section aria-label="Your run feedback">
              <h4 className="text-[13px] font-bold">Your run feedback</h4>
              <FeedbackForm key={`${activity.id}-${activity.notes ?? ""}`} activityId={activity.id} date={activity.date.slice(0,10)}
                watch={{ feel: activity.watch_feel, effort: activity.watch_effort }} initial={{ notes: activity.notes }}
                onSubmitted={() => { setCommentSaves((n) => n + 1); onClassificationChanged?.(); }} />
            </section>
            {/* Notes / Garmin lap summary */}
            {activity.description && (
              <div>
                <h4 className="text-[13px] font-bold">Notes</h4>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground whitespace-pre-line">
                  {activity.description}
                </p>
              </div>
            )}

            {/* Workout Analysis */}
            {workoutAnalysis && (
              <div>
                <h4 className="flex items-center gap-2 text-[13px] font-bold">
                  Workout Analysis
                  <Badge variant="secondary" className="text-[10px]">
                    {workoutAnalysis.type}
                  </Badge>
                </h4>
                <div className="mt-2 space-y-1">
                  {workoutAnalysis.details.map((detail, i) => (
                    <div
                      key={i}
                      className="rounded-xl bg-secondary px-3 py-2 font-mono text-sm"
                    >
                      {detail}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {activity.feel_rating && (
              <div>
                <h4 className="text-[13px] font-bold">How it felt</h4>
                <div className="mt-1 flex items-center gap-2">
                  <span className="font-mono text-lg font-semibold">
                    {activity.feel_rating}/10
                  </span>
                  {activity.notes && (
                    <span className="text-sm text-muted-foreground">
                      &mdash; {activity.notes}
                    </span>
                  )}
                </div>
              </div>
            )}

            {activity.coach_analysis && (
              <div>
                <h4 className="text-[13px] font-bold">Coach Analysis</h4>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                  {activity.coach_analysis}
                </p>
              </div>
            )}

            {activity.type !== "walk" && <CoachingReview key={`coach-${activity.id}-${commentSaves}`} activityId={activity.id} hasComment={!!activity.notes || commentSaves > 0} />}
          </div>

          {activity.splits.length > 0 && (
            <div className="min-w-0 lg:col-start-1">
              <SplitsTable splits={activity.splits} />
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
