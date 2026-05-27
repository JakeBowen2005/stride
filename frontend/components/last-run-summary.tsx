"use client";

import { Card, CardContent } from "@/components/ui/card";
import { formatDate, formatDistance } from "@/lib/format";
import type { Activity } from "@/lib/types";

export function LastRunSummary({ activity }: { activity: Activity }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex items-start justify-between">
          <h3 className="text-sm font-medium">Last Run</h3>
          <span className="text-xs text-muted-foreground">
            {formatDate(activity.date)}
          </span>
        </div>
        <div className="mt-2 flex items-baseline gap-3">
          <span className="font-medium">{activity.title}</span>
          <span className="font-mono text-sm text-muted-foreground">
            {formatDistance(activity.distance_miles)} mi
          </span>
          <span className="font-mono text-sm text-muted-foreground">
            {activity.avg_pace}
          </span>
        </div>
        {activity.feel_rating && (
          <div className="mt-1.5 text-sm text-muted-foreground">
            Feel: {activity.feel_rating}/10
            {activity.notes && (
              <span className="ml-1">
                &mdash; &ldquo;{activity.notes.length > 80
                  ? activity.notes.slice(0, 80) + "..."
                  : activity.notes}&rdquo;
              </span>
            )}
          </div>
        )}
        {activity.coach_analysis && (
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            <span className="font-medium text-foreground">Coach: </span>
            &ldquo;{activity.coach_analysis.length > 150
              ? activity.coach_analysis.slice(0, 150) + "..."
              : activity.coach_analysis}&rdquo;
          </p>
        )}
      </CardContent>
    </Card>
  );
}
