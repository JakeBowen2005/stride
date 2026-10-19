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

interface FeedbackFormProps {
  date: string;
  onSubmitted: (feedback: DayFeedback) => void;
  /** Parent already asks "how did it feel?" — hide the form's own headings */
  compact?: boolean;
}

export function FeedbackForm({ date, onSubmitted, compact = false }: FeedbackFormProps) {
  const [feel, setFeel] = useState<number | null>(null);
  const [notes, setNotes] = useState("");
  const [pace, setPace] = useState<string | null>(null);
  const [swapped, setSwapped] = useState(false);
  const [swapType, setSwapType] = useState<string | null>(null);
  const [swapReason, setSwapReason] = useState("");
  const [rescheduleType, setRescheduleType] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = feel !== null;

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(apiUrl(`/plans/${USER_ID}/feedback/${date}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          feel_rating: feel,
          feel_notes: notes || null,
          pace_assessment: pace,
          swapped,
          swap_reason: swapReason || null,
          actual_workout_type: swapped ? swapType : null,
          desired_reschedule_type: swapped && rescheduleType !== "skip" ? rescheduleType : null,
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
        feel_notes: notes || null,
        pace_assessment: data.pace_assessment,
        swapped: data.swapped,
        swap_reason: data.swap_reason || null,
        actual_workout_type: data.actual_workout_type || null,
        coach_response: data.coach_response,
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
      <p className="text-xs text-muted-foreground">Your rating adjusts the next few days of your plan.</p>

      {/* Feel rating — how it FELT, not effort (low scores trigger extra recovery) */}
      <div>
        {!compact && <p className="mb-1.5 text-sm text-muted-foreground">How did it feel?</p>}
        <div className="grid grid-cols-5 gap-1.5" role="radiogroup" aria-label="How did the run feel, 1 to 10">
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

      {/* Pace assessment */}
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

      {/* Swap toggle */}
      <div>
        <button
          onClick={(e) => { e.stopPropagation(); setSwapped(!swapped); }}
          className={`rounded px-3 py-1 text-xs transition-colors ${
            swapped
              ? "bg-yellow-500/20 text-yellow-600"
              : "bg-secondary hover:bg-secondary/80 text-muted-foreground"
          }`}
        >
          {swapped ? "Swapped workout" : "I swapped this workout"}
        </button>
      </div>

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

      {/* Notes */}
      <div onClick={(e) => e.stopPropagation()}>
        <Textarea
          placeholder="Any notes? (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="h-16 text-xs resize-none"
        />
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      <Button
        size="sm"
        onClick={(e) => { e.stopPropagation(); handleSubmit(); }}
        disabled={!canSubmit || submitting}
        className="w-full"
      >
        {submitting ? "Submitting..." : "Submit Feedback"}
      </Button>
    </div>
  );
}
