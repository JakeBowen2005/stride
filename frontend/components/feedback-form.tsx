"use client";

import { apiUrl, USER_ID } from "@/lib/api";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { DayFeedback } from "@/lib/types";


const FEEL_OPTIONS = [
  { value: 1, label: "1" },
  { value: 2, label: "2" },
  { value: 3, label: "3" },
  { value: 4, label: "4" },
  { value: 5, label: "5" },
  { value: 6, label: "6" },
  { value: 7, label: "7" },
  { value: 8, label: "8" },
  { value: 9, label: "9" },
  { value: 10, label: "10" },
];

const PACE_OPTIONS = [
  { value: "above", label: "Faster" },
  { value: "on_target", label: "On Target" },
  { value: "below", label: "Slower" },
];

const SWAP_TYPES = [
  "easy",
  "recovery",
  "tempo",
  "intervals",
  "long_run",
  "rest",
];

const RESCHEDULE_TYPES = [
  { value: "threshold", label: "Threshold" },
  { value: "intervals", label: "Intervals" },
  { value: "tempo", label: "Tempo" },
  { value: "skip", label: "Don't reschedule" },
];

const COMPLETION_OPTIONS = [
  { value: "full", label: "Did it all" },
  { value: "partial", label: "Did part" },
  { value: "not_done", label: "Didn't do it" },
];

interface FeedbackFormProps {
  date: string;
  activityId?: number;
  /** A Garmin recording exists for the day; otherwise offer manual logging */
  hasRecording?: boolean;
  /** Workout days ask how hard the session was */
  isWorkout?: boolean;
  /** Only sessions with a prescribed pace ask about pace */
  hasPaceTarget?: boolean;
  onSubmitted: (feedback: DayFeedback) => void;
  /** Parent already asks "how did it feel?" — hide the form's own headings */
  compact?: boolean;
  /** Start from earlier answers (editing) or the watch's own post-run rating */
  initial?: { feel?: number | null; effort?: number | null; notes?: string | null; completion?: string | null };
  /** The initial feel/effort came from the Garmin watch, not the app */
  fromWatch?: boolean;
}

export function FeedbackForm({ date, activityId, onSubmitted, compact = false, hasRecording = true, isWorkout = false, hasPaceTarget = false, initial, fromWatch = false }: FeedbackFormProps) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [feel, setFeel] = useState<number | null>(initial?.feel ?? null);
  const [effort, setEffort] = useState<number | null>(initial?.effort ?? null);
  const [completion, setCompletion] = useState<string | null>(initial?.completion ?? null);
  const [manualMiles, setManualMiles] = useState("");
  const [manualMinutes, setManualMinutes] = useState("");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [pace, setPace] = useState<string | null>(null);
  const [swapped, setSwapped] = useState(false);
  const [swapType, setSwapType] = useState<string | null>(null);
  const [swapReason, setSwapReason] = useState("");
  const [rescheduleType, setRescheduleType] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validNumber = (v: string) => v !== "" && Number.isFinite(Number(v)) && Number(v) > 0;
  const manualReady = validNumber(manualMiles) && validNumber(manualMinutes);
  // Logging without a watch needs the run itself (or an explicit "didn't do it")
  const manualMissing = !hasRecording && completion !== "not_done" && !manualReady;
  const canSubmit = feel !== null && !manualMissing;

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(apiUrl(activityId ? `/analysis/${USER_ID}/activities/${activityId}/feedback` : `/plans/${USER_ID}/feedback/${date}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          feel_rating: feel,
          feel_notes: notes || null,
          pace_assessment: pace,
          swapped,
          swap_reason: swapReason || null,
          actual_workout_type: swapped ? swapType : null,
          // "skip" is sent explicitly: the backend only reschedules on an explicit workout choice
          desired_reschedule_type: swapped ? rescheduleType : null,
          effort_rating: completion === "not_done" ? null : effort,
          completion,
          manual_distance_miles: !hasRecording && manualReady ? Number(manualMiles) : null,
          manual_duration_minutes: !hasRecording && manualReady ? Number(manualMinutes) : null,
        }),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || "Failed to submit feedback");
        return;
      }
      const data = await res.json();
      onSubmitted({
        feel_rating: data.feel_rating,
        effort_rating: data.effort_rating ?? null,
        reported_completion: data.reported_completion ?? null,
        feel_notes: notes || null,
        pace_assessment: data.pace_assessment,
        swapped: data.swapped,
        swap_reason: data.swap_reason || null,
        actual_workout_type: data.actual_workout_type || null,
        coach_response: data.coach_response,
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
      {!compact && (
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          How&apos;d it go?
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        {fromWatch
          ? "Prefilled from the rating you gave on your watch. Confirm or change it, and add a comment."
          : "Your answers adjust the next few days of your plan."}
      </p>

      {!hasRecording && (
        <div className="space-y-1.5" onClick={(e) => e.stopPropagation()}>
          <p className="text-sm text-muted-foreground">No watch recording. Log the run yourself:</p>
          <div className="flex gap-2">
            <label className="flex-1 text-xs text-muted-foreground">
              Distance (mi)
              <input
                inputMode="decimal"
                value={manualMiles}
                onChange={(e) => setManualMiles(e.target.value.replace(/[^0-9.]/g, ""))}
                className="mt-1 h-11 w-full rounded-md border bg-background px-3 font-mono text-sm text-foreground"
              />
            </label>
            <label className="flex-1 text-xs text-muted-foreground">
              Time (min)
              <input
                inputMode="decimal"
                value={manualMinutes}
                onChange={(e) => setManualMinutes(e.target.value.replace(/[^0-9.]/g, ""))}
                className="mt-1 h-11 w-full rounded-md border bg-background px-3 font-mono text-sm text-foreground"
              />
            </label>
          </div>
          {manualMissing && (manualMiles || manualMinutes) && (
            <p className="text-xs text-destructive">Enter distance and time as numbers (e.g. 3.1 and 32).</p>
          )}
        </div>
      )}

      {(isWorkout || !hasRecording) && (
        <div>
          <p className="mb-1.5 text-sm text-muted-foreground">{isWorkout ? "Did you complete the workout?" : "Did you run it?"}</p>
          <div className="grid grid-cols-3 gap-1.5">
            {COMPLETION_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                aria-pressed={completion === opt.value}
                onClick={(e) => { e.stopPropagation(); setCompletion(opt.value); if (opt.value === "not_done") setEffort(null); }}
                className={`h-11 rounded-md text-xs transition-colors ${
                  completion === opt.value ? "bg-foreground text-background" : "bg-secondary hover:bg-secondary/80"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {isWorkout && (
            <p className="mt-1 text-xs text-muted-foreground">
              Counts even without watch laps. It&apos;s kept separate from what your watch measures.
            </p>
          )}
        </div>
      )}

      {/* Effort — how HARD the session was. Separate from how you felt afterward. */}
      {isWorkout && completion !== "not_done" && (
        <div>
          <p className="mb-1.5 text-sm text-muted-foreground">How hard was the workout?</p>
          <div className="grid grid-cols-5 gap-1.5" role="radiogroup" aria-label="How hard was the workout, 1 to 10">
            {FEEL_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={effort === opt.value}
                onClick={(e) => { e.stopPropagation(); setEffort(opt.value); }}
                className={`h-11 rounded-md font-mono text-sm transition-colors ${
                  effort === opt.value ? "bg-foreground text-background" : "bg-secondary hover:bg-secondary/80"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <div className="mt-1 flex justify-between text-xs text-muted-foreground">
            <span>1 = very easy</span>
            <span>6 = controlled</span>
            <span>10 = all-out</span>
          </div>
        </div>
      )}

      {/* Feel rating — how you FELT afterward, not effort (low scores trigger extra recovery) */}
      <div>
        {(!compact || isWorkout) && <p className="mb-1.5 text-sm text-muted-foreground">How do you feel afterward?</p>}
        <div className="grid grid-cols-5 gap-1.5" role="radiogroup" aria-label="How do you feel afterward, 1 to 10">
          {FEEL_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={feel === opt.value}
              onClick={(e) => { e.stopPropagation(); setFeel(opt.value); }}
              className={`h-11 rounded-md font-mono text-sm transition-colors ${
                feel === opt.value
                  ? "bg-foreground text-background"
                  : "bg-secondary hover:bg-secondary/80"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="mt-1 flex justify-between text-xs text-muted-foreground">
          <span>1 = awful</span>
          <span>5 = okay</span>
          <span>10 = felt amazing</span>
        </div>
      </div>

      {/* Pace assessment: only meaningful when the session prescribed a pace */}
      {hasPaceTarget && (
      <div>
        <p className="text-xs text-muted-foreground mb-1.5">Pace vs target?</p>
        <div className="flex gap-1.5">
          {PACE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={(e) => { e.stopPropagation(); setPace(opt.value); }}
              className={`rounded px-3 py-1 text-xs transition-colors ${
                pace === opt.value
                  ? "bg-foreground text-background"
                  : "bg-secondary hover:bg-secondary/80"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
      )}

      {/* Notes */}
      <div onClick={(e) => e.stopPropagation()}>
        <Textarea
          placeholder="Comments for your coach (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="h-16 text-xs resize-none"
        />
      </div>

      <button
        type="button"
        aria-expanded={moreOpen}
        onClick={(e) => { e.stopPropagation(); setMoreOpen(!moreOpen); setSwapped(!moreOpen); }}
        className="text-xs text-muted-foreground underline underline-offset-2"
      >
        {moreOpen ? "Never mind, I didn't swap it" : "I swapped this workout…"}
      </button>

      {moreOpen && (<>
      {swapped && (
        <div className="space-y-2 pl-2 border-l-2 border-yellow-500/30">
          <div>
            <p className="text-xs text-muted-foreground mb-1">What did you do instead?</p>
            <div className="flex flex-wrap gap-1">
              {SWAP_TYPES.map((t) => (
                <button
                  key={t}
                  onClick={(e) => { e.stopPropagation(); setSwapType(t); }}
                  className={`rounded px-2 py-0.5 text-xs transition-colors ${
                    swapType === t
                      ? "bg-foreground text-background"
                      : "bg-secondary hover:bg-secondary/80"
                  }`}
                >
                  {t.replace("_", " ")}
                </button>
              ))}
            </div>
          </div>
          <div onClick={(e) => e.stopPropagation()}>
            <Textarea
              placeholder="Why did you swap? (optional)"
              value={swapReason}
              onChange={(e) => setSwapReason(e.target.value)}
              className="h-16 text-xs resize-none"
            />
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">Reschedule as?</p>
            <div className="flex flex-wrap gap-1">
              {RESCHEDULE_TYPES.map((t) => (
                <button
                  key={t.value}
                  onClick={(e) => { e.stopPropagation(); setRescheduleType(t.value); }}
                  className={`rounded px-2 py-0.5 text-xs transition-colors ${
                    rescheduleType === t.value
                      ? "bg-foreground text-background"
                      : "bg-secondary hover:bg-secondary/80"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}


      </>)}

      {error && <p className="text-xs text-destructive">{error}</p>}

      <Button
        size="sm"
        onClick={(e) => { e.stopPropagation(); handleSubmit(); }}
        disabled={!canSubmit || submitting}
        className="w-full"
      >
        {submitting ? "Saving..." : "Save"}
      </Button>
    </div>
  );
}
