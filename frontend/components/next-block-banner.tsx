"use client";

import Link from "next/link";
import { ArrowRight, CalendarRange } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatDateShort } from "@/lib/format";
import type { NextPreview } from "@/lib/plan-state";

export function NextBlockBanner({ preview, busy = false, onOpen }: {
  preview?: NextPreview; busy?: boolean; onOpen?: () => void;
}) {
  if (!preview || preview.state === "hidden") return null;
  if (preview.state === "upcoming") return <p className="text-xs text-muted-foreground">Next block preview opens {formatDateShort(preview.opens_on)}</p>;
  const blocked = preview.state === "blocked";
  const label = preview.provisional
    ? preview.state === "ready" ? "View next plan" : "Preview next plan"
    : "Review next block";
  return <section aria-label="Next training block" className="next-block-banner flex flex-wrap items-center justify-between gap-4 rounded-2xl border bg-card px-5 py-4">
    <div className="flex min-w-0 items-start gap-3">
      <CalendarRange aria-hidden className="mt-1 size-5 shrink-0 text-primary" strokeWidth={1.5} />
      <div className="min-w-0">
        <p className="text-sm font-medium">{preview.provisional ? "A look at what comes next" : "Your next block is ready to build"}</p>
        <p className="mt-1 font-mono text-xs text-muted-foreground">{formatDateShort(preview.next_start)} – {formatDateShort(preview.next_end)}</p>
        <p className="mt-2 max-w-lg text-sm text-muted-foreground">{blocked ? preview.reason : preview.provisional
          ? "Plan ahead for your next two weeks. Your current block stays active."
          : "Rebuild from your latest runs, then review and approve your next two weeks."}</p>
      </div>
    </div>
    {onOpen ? <Button variant="outline" disabled={busy || blocked} onClick={onOpen} className="min-w-40 max-sm:w-full">
      {busy ? "Building preview…" : label}<ArrowRight aria-hidden className="size-4" />
    </Button> : !blocked && <Link className="inline-flex min-h-10 items-center gap-2 rounded-lg px-3 text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-2" href="/plan">{label}<ArrowRight aria-hidden className="size-4" /></Link>}
  </section>;
}
