"use client";

import { useUnits } from "@/components/unit-preferences";
import { distanceValueInUnits, paceInUnits, unitLabel } from "@/lib/units";
import type { Split } from "@/lib/types";

export function SplitsTable({ splits: all }: { splits: Split[] }) {
  const units = useUnits();
  const unit = unitLabel(units);
  // Drop the stub lap Garmin records when you stop the watch a few steps late
  const splits = all.filter((s, i) => !(i === all.length - 1 && s.distance_miles !== undefined && s.distance_miles < 0.05));
  if (splits.length === 0) return null;
  // Garmin rows are laps (any length); legacy Strava rows are 1-mile splits
  const isLaps = splits.some((s) => s.distance_miles !== undefined);

  return (
    <div className="space-y-1">
      <h4 className="text-sm font-medium">{isLaps ? "Laps" : "Splits"}</h4>
      <div className="space-y-0.5">
        {splits.map((split) => (
          <div
            key={split.mile}
            className="flex items-center justify-between rounded px-2 py-1 text-sm odd:bg-secondary/30"
          >
            <span className="text-muted-foreground">
              {isLaps ? `Lap ${split.mile}` : `Mile ${split.mile}`}
              {isLaps && split.distance_miles !== undefined && (
                <span className="ml-2 text-xs">{distanceValueInUnits(split.distance_miles, units).toFixed(2)} {unit}</span>
              )}
              {split.intensity && split.intensity !== "ACTIVE" && (
                <span className="ml-2 text-[10px] uppercase tracking-wide">{split.intensity.toLowerCase()}</span>
              )}
            </span>
            <div className="flex items-center gap-4">
              <span className="font-mono">
                {split.pace && split.pace !== "—" ? `${paceInUnits(split.pace.replace(/\/mi$/, ""), units)}/${unit}` : "—"}
              </span>
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
  );
}
