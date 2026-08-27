"use client";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  workoutTypeLabel,
  isHardWorkout,
  formatDistance,
  formatDateLong,
  secondsToTime,
} from "@/lib/format";
import type { Activity } from "@/lib/types";

interface RunDetailSheetProps {
  activity: Activity | null;
  open: boolean;
  onClose: () => void;
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

export function RunDetailSheet({ activity, open, onClose }: RunDetailSheetProps) {
  if (!activity) return null;

  const workoutAnalysis = activity.description
    ? parseWorkoutDetails(activity.description)
    : null;

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent className="overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
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

        <div className="mt-6 space-y-4 px-4 pb-6">
          {/* Metrics grid */}
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <div className="font-mono text-lg font-semibold">
                {formatDistance(activity.distance_miles)}
              </div>
              <div className="text-xs text-muted-foreground">miles</div>
            </div>
            <div>
              <div className="font-mono text-lg font-semibold">
                {activity.avg_pace}
              </div>
              <div className="text-xs text-muted-foreground">avg pace</div>
            </div>
            <div>
              <div className="font-mono text-lg font-semibold">
                {secondsToTime(activity.duration_seconds)}
              </div>
              <div className="text-xs text-muted-foreground">time</div>
            </div>
          </div>

          {(activity.avg_heart_rate || activity.elevation_gain_ft || activity.cadence) && (
            <div className="grid grid-cols-3 gap-4 text-center">
              {activity.avg_heart_rate && (
                <div>
                  <div className="font-mono text-sm font-medium">
                    {activity.avg_heart_rate}
                  </div>
                  <div className="text-xs text-muted-foreground">avg HR</div>
                </div>
              )}
              {activity.elevation_gain_ft && (
                <div>
                  <div className="font-mono text-sm font-medium">
                    {activity.elevation_gain_ft} ft
                  </div>
                  <div className="text-xs text-muted-foreground">elevation</div>
                </div>
              )}
              {activity.cadence && (
                <div>
                  <div className="font-mono text-sm font-medium">
                    {activity.cadence}
                  </div>
                  <div className="text-xs text-muted-foreground">cadence</div>
                </div>
              )}
            </div>
          )}

          {/* Strava Description */}
          {activity.description && (
            <>
              <Separator />
              <div>
                <h4 className="text-sm font-medium">Description</h4>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground whitespace-pre-line">
                  {activity.description}
                </p>
              </div>
            </>
          )}

          {/* Workout Analysis */}
          {workoutAnalysis && (
            <>
              <Separator />
              <div>
                <h4 className="text-sm font-medium flex items-center gap-2">
                  Workout Analysis
                  <Badge variant="secondary" className="text-[10px]">
                    {workoutAnalysis.type}
                  </Badge>
                </h4>
                <div className="mt-2 space-y-1">
                  {workoutAnalysis.details.map((detail, i) => (
                    <div
                      key={i}
                      className="rounded bg-secondary/50 px-2 py-1.5 text-sm font-mono"
                    >
                      {detail}
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {activity.feel_rating && (
            <>
              <Separator />
              <div>
                <h4 className="text-sm font-medium">How it felt</h4>
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
            </>
          )}

          {activity.coach_analysis && (
            <>
              <Separator />
              <div>
                <h4 className="text-sm font-medium">Coach Analysis</h4>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                  {activity.coach_analysis}
                </p>
              </div>
            </>
          )}

          {activity.splits.length > 0 && (
            <>
              <Separator />
              <div>
                <h4 className="text-sm font-medium">Splits</h4>
                <div className="mt-2 space-y-1">
                  {activity.splits.map((split) => (
                    <div
                      key={split.mile}
                      className="flex items-center justify-between rounded px-2 py-1.5 text-sm odd:bg-secondary/30"
                    >
                      <span className="text-muted-foreground">
                        Mile {split.mile}
                      </span>
                      <div className="flex items-center gap-4">
                        <span className="font-mono">{split.pace}</span>
                        {split.heart_rate && (
                          <span className="font-mono text-xs text-muted-foreground">
                            {Math.round(split.heart_rate)} bpm
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
