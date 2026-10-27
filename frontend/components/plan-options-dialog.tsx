"use client";

import { useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { PlanChangeRequest } from "@/components/plan-change-request";
import { cn } from "@/lib/utils";
import type { Units } from "@/lib/units";
import type { Workout } from "@/lib/types";

// Life events go through "What's coming up?"; these are about the training itself.
const REASONS = ["Too much volume", "Too hard", "Too easy", "Want more speed", "Feeling run down"];
export const CONCERN_LIMIT = 500;

/** Joins the tapped chips and the typed note into the one sentence the coach reads. */
export function concernText(reasons: string[], note: string): string {
  return [reasons.join(", "), note.trim()].filter(Boolean).join(". ").slice(0, CONCERN_LIMIT);
}

/**
 * One entry point for changing the block: describe what's coming up (Stride rearranges the
 * week), tell the coach what isn't working, move one session, or rebuild the block.
 */
export function PlanOptionsDialog({ aiConfigured, busy, nextBlockLabel, days, today, units, onPlanChanged,
  onAskCoach, onLighter, onRevise, onNextBlock, onMoveSession }: {
  aiConfigured: boolean | null;
  busy: boolean;
  /** Set when the next block can be previewed, e.g. "Starts after Nov 2" */
  nextBlockLabel: string | null;
  days: Workout[];
  today: string;
  units: Units;
  onPlanChanged: () => void;
  onAskCoach: (concern: string) => void;
  onLighter: () => void;
  onRevise: () => void;
  onNextBlock: () => void;
  onMoveSession?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [reasons, setReasons] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const concern = concernText(reasons, note);
  const toggle = (reason: string) => setReasons((r) => (r.includes(reason) ? r.filter((x) => x !== reason) : [...r, reason]));
  const run = (action: () => void) => { setOpen(false); action(); };

  return (
    <>
      <Button variant="outline" className="h-10 sm:h-8" onClick={() => setOpen(true)} disabled={busy}>
        <SlidersHorizontal aria-hidden="true" /> Plan options
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[92dvh] overflow-y-auto max-sm:top-auto max-sm:bottom-0 max-sm:max-w-full max-sm:translate-y-0 max-sm:rounded-b-none sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Plan options</DialogTitle>
            <DialogDescription>Fit training around your life, tell the coach what isn&apos;t working, or rebuild the block.</DialogDescription>
          </DialogHeader>

          <PlanChangeRequest days={days} today={today} units={units} onChanged={onPlanChanged} />

          <details className="group space-y-3 border-t pt-3">
            <summary className="cursor-pointer list-none text-sm font-medium">
              <span className="underline-offset-4 group-open:underline">Something about the training isn&apos;t working?</span>
            </summary>
            <div className="mt-3 space-y-3">
              <p className="text-xs text-muted-foreground">
                The coach reviews your block and suggests safe swaps from Stride&apos;s checked options. Nothing changes until you apply one.
              </p>
              <div className="flex flex-wrap gap-2" role="group" aria-label="Quick reasons">
                {REASONS.map((reason) => {
                  const on = reasons.includes(reason);
                  return (
                    <button key={reason} type="button" aria-pressed={on} onClick={() => toggle(reason)}
                      className={cn("min-h-9 rounded-full border px-3.5 py-1 text-sm transition-colors hover:bg-[var(--row-hover)] focus-visible:outline-2 focus-visible:outline-primary",
                        on ? "border-foreground bg-foreground text-background" : "hover:bg-muted")}>
                      {reason}
                    </button>
                  );
                })}
              </div>
              <div className="space-y-1">
                <label htmlFor="plan-concern" className="text-sm font-medium">Details <span className="font-normal text-muted-foreground">(optional)</span></label>
                <Textarea id="plan-concern" value={note} maxLength={CONCERN_LIMIT} rows={2}
                  placeholder="e.g. My legs are still heavy from Saturday."
                  onChange={(e) => setNote(e.target.value)} />
              </div>
              <Button variant="outline" className="h-10 w-full sm:h-9" disabled={busy || !concern || aiConfigured !== true} onClick={() => run(() => onAskCoach(concern))}>
                Ask coach to review
              </Button>
              {aiConfigured === false && <p className="text-xs text-muted-foreground">The AI coach isn&apos;t configured. You can still rebuild the block below.</p>}
            </div>
          </details>

          <div className="space-y-2 border-t pt-3">
            <p className="stat-label">Or change it by hand</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" disabled={!onMoveSession || busy} onClick={() => run(() => onMoveSession?.())}>Move a session</Button>
              <Button variant="outline" size="sm" disabled={busy} onClick={() => run(onLighter)}>Make it lighter</Button>
              <Button variant="outline" size="sm" disabled={busy} onClick={() => run(onRevise)}>Revise with latest runs</Button>
              {nextBlockLabel && <Button variant="outline" size="sm" disabled={busy} onClick={() => run(onNextBlock)}>Preview next block</Button>}
            </div>
            <p className="text-xs text-muted-foreground">
              Rebuilds create a draft for you to approve. Your current plan stays active until then.{nextBlockLabel ? ` Next block: ${nextBlockLabel}.` : ""}
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
