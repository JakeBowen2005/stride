"use client";

import { useState } from "react";
import { ArrowRight, Check, ChevronDown, Circle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface QualityProgression {
  stage: "single" | "support" | "dual";
  sessions: number;
  reason: string;
  criteria: { label: string; met: boolean }[];
  evidence: { primary_successes?: number; support_successes?: number; recovery_days?: number };
}
const stages = [
  {id:"single", label:"Establish", detail:"One controlled workout. Build repeatable volume and recover well between sessions."},
  {id:"support", label:"Add support", detail:"Keep the primary workout and introduce a lighter second stimulus. Demonstrate completion and recovery."},
  {id:"dual", label:"Two quality days", detail:"Two substantial sessions tailored to your goal. A demanding long run uses one of the week's quality slots."},
];

export function TrainingProgression({ policy, experience }: {policy: QualityProgression; experience?: string}) {
  const [expanded, setExpanded] = useState(false);
  const [explore, setExplore] = useState(policy.stage);
  const current = stages.findIndex((s) => s.id===policy.stage);
  const viewed = stages.find((s) => s.id===explore)!;
  return <Card className="border-l-4 border-l-primary ring-foreground/5">
    <CardContent className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div><p className="eyebrow">Your training progression</p><h2 className="mt-1 text-lg font-semibold tracking-tight">{stages[current].label}</h2></div>
        {experience && <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium capitalize text-primary">{experience==="expert"?"Expert / professional":experience}</span>}
      </div>
      <div className="grid grid-cols-3 gap-2" aria-label="Explore training stages">
        {stages.map((stage,i) => <button key={stage.id} type="button" aria-pressed={explore===stage.id} onClick={() => {setExplore(stage.id as QualityProgression['stage']); setExpanded(true);}} className={cn("min-h-14 rounded-lg border p-2 text-left transition-colors hover:border-primary/50 focus-visible:outline-2 focus-visible:outline-primary",i===current?"border-primary/30 bg-primary/10":"border-border bg-muted/30")}>
          <span className="mb-1 flex items-center gap-1.5 text-xs text-muted-foreground"><span className={cn("flex size-5 items-center justify-center rounded-full text-[11px]",i<=current?"bg-primary text-primary-foreground":"bg-muted")}>{i<current?<Check className="size-3"/>:i+1}</span>{i===current?"Current":"Stage"}</span>
          <span className="text-xs font-medium sm:text-sm">{stage.label}</span>
        </button>)}
      </div>
      <p className="text-sm leading-relaxed text-muted-foreground">{policy.reason}</p>
      <button type="button" onClick={() => setExpanded(!expanded)} aria-expanded={expanded} className="flex min-h-10 items-center gap-2 text-sm font-medium text-primary">{expanded?"Hide progression details":"What unlocks the next stage?"}<ChevronDown className={cn("size-4 transition-transform",expanded&&"rotate-180")}/></button>
      {expanded && <div className="space-y-4 rounded-lg bg-muted/50 p-4">
        <p className="text-sm"><span className="font-medium">{viewed.label} <ArrowRight className="mx-1 inline size-3"/></span>{viewed.detail}</p>
        <div className="grid gap-2 text-sm sm:grid-cols-2">{policy.criteria.map((c) => <div key={c.label} className="flex items-start gap-2">{c.met?<Check className="mt-0.5 size-4 shrink-0 text-primary"/>:<Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground"/>}<span>{c.label}<span className="sr-only">: {c.met?"demonstrated":"not yet demonstrated"}</span></span></div>)}</div>
        <p className="text-xs leading-relaxed text-muted-foreground">Last 8 weeks: {policy.evidence.primary_successes??0} evidenced quality days · {policy.evidence.support_successes??0} support days. {policy.evidence.recovery_days??0} rated run days in the last 2 weeks. Stage eligibility stays subject to this week&apos;s budget, phase and schedule.</p>
      </div>}
    </CardContent>
  </Card>;
}
