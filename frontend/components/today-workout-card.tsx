"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { workoutTypeLabel, isHardWorkout, formatDistance } from "@/lib/format";
import type { Workout } from "@/lib/types";

export function TodayWorkoutCard({ workout }: { workout: Workout }) {
  if (workout.type === "rest") {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Today&apos;s Workout</CardTitle>
            <Badge variant="secondary">Rest Day</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">{workout.purpose}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Today&apos;s Workout</CardTitle>
          <Badge variant={isHardWorkout(workout.type) ? "default" : "secondary"}>
            {workoutTypeLabel(workout.type)}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-baseline justify-between">
          <h3 className="text-2xl font-semibold">{workout.title}</h3>
          <span className="font-mono text-xl font-semibold">
            {formatDistance(workout.distance_miles)} mi
          </span>
        </div>

        <p className="text-muted-foreground">{workout.description}</p>

        {workout.target_pace && (
          <div className="flex gap-6 text-sm">
            <div>
              <span className="text-muted-foreground">Target </span>
              <span className="font-mono font-medium">{workout.target_pace}</span>
            </div>
          </div>
        )}

        {(workout.warmup || workout.cooldown || workout.intervals) && (
          <div className="space-y-1 rounded-md bg-secondary/50 p-3 text-sm">
            {workout.warmup && (
              <div>
                <span className="text-muted-foreground">Warmup: </span>
                {workout.warmup}
              </div>
            )}
            {workout.intervals && (
              <div>
                <span className="text-muted-foreground">Workout: </span>
                <span className="font-mono font-medium">{workout.intervals}</span>
              </div>
            )}
            {workout.cooldown && (
              <div>
                <span className="text-muted-foreground">Cooldown: </span>
                {workout.cooldown}
              </div>
            )}
          </div>
        )}

        <div className="border-t pt-3">
          <p className="text-sm leading-relaxed text-muted-foreground">
            <span className="font-medium text-foreground">Why: </span>
            {workout.purpose}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
