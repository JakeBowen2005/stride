"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { FeelRating } from "@/components/feel-rating";
import { SplitsTable } from "@/components/splits-table";
import {
  formatDistance,
  formatDateLong,
  secondsToTime,
} from "@/lib/format";
import { mockLastActivity } from "@/lib/mock-data";

export default function ReviewPage() {
  // In production, fetch activity by params.id
  const activity = mockLastActivity;
  const [feelRating, setFeelRating] = useState<number | null>(null);
  const [notes, setNotes] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [showAnalysis, setShowAnalysis] = useState(false);

  function handleSubmit() {
    setSubmitted(true);
    // Simulate coach analysis appearing after a beat
    setTimeout(() => setShowAnalysis(true), 600);
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div className="text-center">
        <h1 className="text-xl font-semibold">How did that feel?</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {activity.title} &middot;{" "}
          <span className="font-mono">
            {formatDistance(activity.distance_miles)} mi
          </span>{" "}
          &middot;{" "}
          <span className="font-mono">{activity.avg_pace} avg</span>
        </p>
        <p className="text-xs text-muted-foreground">
          {formatDateLong(activity.date)}
        </p>
      </div>

      {!submitted ? (
        <Card>
          <CardContent className="space-y-6 pt-6">
            <FeelRating value={feelRating} onChange={setFeelRating} />

            <div className="space-y-2">
              <label
                htmlFor="notes"
                className="text-sm text-muted-foreground"
              >
                Anything to note? (optional)
              </label>
              <Textarea
                id="notes"
                placeholder="Left calf felt tight, legs were heavy, felt amazing..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
              />
            </div>

            <Button
              className="w-full"
              disabled={feelRating === null}
              onClick={handleSubmit}
            >
              Submit Review
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-3">
                <span className="font-mono text-2xl font-semibold">
                  {feelRating}/10
                </span>
                {notes && (
                  <span className="text-sm text-muted-foreground">
                    &mdash; {notes}
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          {showAnalysis && activity.coach_analysis && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Coach Analysis</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {activity.coach_analysis}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Metrics */}
          <div className="grid grid-cols-3 gap-4 text-center">
            <div className="rounded-md border p-3">
              <div className="font-mono text-lg font-semibold">
                {formatDistance(activity.distance_miles)}
              </div>
              <div className="text-xs text-muted-foreground">miles</div>
            </div>
            <div className="rounded-md border p-3">
              <div className="font-mono text-lg font-semibold">
                {activity.avg_pace}
              </div>
              <div className="text-xs text-muted-foreground">avg pace</div>
            </div>
            <div className="rounded-md border p-3">
              <div className="font-mono text-lg font-semibold">
                {secondsToTime(activity.duration_seconds)}
              </div>
              <div className="text-xs text-muted-foreground">time</div>
            </div>
          </div>

          {activity.avg_heart_rate && (
            <div className="grid grid-cols-3 gap-4 text-center">
              <div className="rounded-md border p-3">
                <div className="font-mono text-sm font-medium">
                  {activity.avg_heart_rate}
                </div>
                <div className="text-xs text-muted-foreground">avg HR</div>
              </div>
              {activity.elevation_gain_ft && (
                <div className="rounded-md border p-3">
                  <div className="font-mono text-sm font-medium">
                    {activity.elevation_gain_ft} ft
                  </div>
                  <div className="text-xs text-muted-foreground">
                    elevation
                  </div>
                </div>
              )}
              {activity.cadence && (
                <div className="rounded-md border p-3">
                  <div className="font-mono text-sm font-medium">
                    {activity.cadence}
                  </div>
                  <div className="text-xs text-muted-foreground">cadence</div>
                </div>
              )}
            </div>
          )}

          <SplitsTable splits={activity.splits} />
        </div>
      )}
    </div>
  );
}
