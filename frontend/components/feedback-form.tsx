"use client";

import { apiUrl, USER_ID } from "@/lib/api";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { DayFeedback } from "@/lib/types";

const COMMENT_MIN = 3;

/** Garmin's five-step "how did you feel" answer, on Stride's 1-10 scale (2/4/6/8/10). */
const WATCH_FEEL: Record<number, string> = { 2: "Very weak", 4: "Weak", 6: "Normal", 8: "Strong", 10: "Very strong" };

interface FeedbackFormProps {
  date: string;
  activityId?: number;
  /** A Garmin recording exists for the day; otherwise offer manual logging */
  hasRecording?: boolean;
  /** The rating entered on the watch after the run (Stride's 1-10 scales); it is the true data */
  watch?: { feel?: number | null; effort?: number | null };
  onSubmitted: (feedback: DayFeedback) => void;
  /** Parent supplies its own heading */
  compact?: boolean;
  /** Editing an earlier comment */
  initial?: { notes?: string | null };
}

/** The one thing the athlete adds after a run: a comment. Feel and effort come from the
 * Garmin watch's post-run prompt. Saving starts the AI review of the run. */
export function FeedbackForm({ date, activityId, onSubmitted, compact = false, hasRecording = true, watch, initial }: FeedbackFormProps) {
  const [manualMiles, setManualMiles] = useState("");
  const [manualMinutes, setManualMinutes] = useState("");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validNumber = (v: string) => v !== "" && Number.isFinite(Number(v)) && Number(v) > 0;
  const manualReady = validNumber(manualMiles) && validNumber(manualMinutes);
  const manualMissing = !hasRecording && !manualReady;
  const commentReady = notes.trim().length >= COMMENT_MIN;
  const canSubmit = commentReady && !manualMissing;
  const watchFeel = watch?.feel != null ? `${WATCH_FEEL[watch.feel] ?? `${watch.feel}/10`}` : null;

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(apiUrl(activityId ? `/analysis/${USER_ID}/activities/${activityId}/feedback` : `/plans/${USER_ID}/feedback/${date}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          feel_notes: notes.trim(),
          manual_distance_miles: !hasRecording && manualReady ? Number(manualMiles) : null,
          manual_duration_minutes: !hasRecording && manualReady ? Number(manualMinutes) : null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(typeof data.detail === "string" ? data.detail : "Could not save your comment");
        return;
      }
      onSubmitted({
        feel_rating: data.feel_rating ?? null,
        effort_rating: data.effort_rating ?? null,
        reported_completion: data.reported_completion ?? null,
        feel_notes: notes.trim(),
        pace_assessment: data.pace_assessment ?? null,
        swapped: !!data.swapped,
        swap_reason: data.swap_reason || null,
        actual_workout_type: data.actual_workout_type || null,
        coach_response: data.coach_response ?? null,
        evaluation: data.evaluation ?? null,
        changes: data.changes ?? [],
      });
    } catch {
      setError("Failed to connect to server");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-3">
      {!compact && <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">How&apos;d it go?</p>}

      {hasRecording && (
        <p className="text-xs text-muted-foreground">
          {watchFeel || watch?.effort != null
            ? <>From your watch: {watchFeel && <>felt <span className="font-medium text-foreground">{watchFeel}</span></>}
                {watchFeel && watch?.effort != null && " · "}
                {watch?.effort != null && <>effort <span className="num font-medium text-foreground">{watch.effort}/10</span></>}</>
            : "Your watch didn't record a post-run rating for this run."}
        </p>
      )}

      {!hasRecording && (
        <div className="space-y-1.5" onClick={(e) => e.stopPropagation()}>
          <p className="text-sm text-muted-foreground">No watch recording. Log the run yourself:</p>
          <div className="flex gap-2">
            <label className="flex-1 text-xs text-muted-foreground">
              Distance (mi)
              <input inputMode="decimal" value={manualMiles}
                onChange={(e) => setManualMiles(e.target.value.replace(/[^0-9.]/g, ""))}
                className="mt-1 h-11 w-full rounded-md border bg-background px-3 font-mono text-sm text-foreground" />
            </label>
            <label className="flex-1 text-xs text-muted-foreground">
              Time (min)
              <input inputMode="decimal" value={manualMinutes}
                onChange={(e) => setManualMinutes(e.target.value.replace(/[^0-9.]/g, ""))}
                className="mt-1 h-11 w-full rounded-md border bg-background px-3 font-mono text-sm text-foreground" />
            </label>
          </div>
          {manualMissing && (manualMiles || manualMinutes) && (
            <p className="text-xs text-destructive">Enter distance and time as numbers (e.g. 3.1 and 32).</p>
          )}
        </div>
      )}

      <div onClick={(e) => e.stopPropagation()}>
        <label className="mb-1.5 block text-sm text-muted-foreground" htmlFor={`comment-${activityId ?? date}`}>
          How did it go? <span className="text-xs">(required)</span>
        </label>
        <Textarea
          id={`comment-${activityId ?? date}`}
          placeholder="e.g. Legs heavy the first mile, reps felt smooth, recoveries felt short"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="h-20 resize-none text-sm"
          aria-required="true"
        />
        <p className="mt-1 text-xs text-muted-foreground">Saving sends your comment and the watch data to your coach for a review.</p>
      </div>

      {error && <p role="alert" className="text-xs text-destructive">{error}</p>}

      <Button size="sm" onClick={(e) => { e.stopPropagation(); handleSubmit(); }} disabled={!canSubmit || submitting} className="w-full">
        {submitting ? "Saving..." : "Save comment"}
      </Button>
    </div>
  );
}
