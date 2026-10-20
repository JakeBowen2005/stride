"use client";

import { useCallback, useEffect, useState } from "react";
import { apiUrl, getJson, USER_ID } from "@/lib/api";
import { Button } from "@/components/ui/button";

interface Review {
  id: number;
  created_at: string;
  status: "pending" | "ready" | "fallback";
  model: string | null;
  stale: boolean;
  applied_candidate_id: string | null;
  summary: string;
  plan_fit: "consistent" | "consider_change" | "insufficient_evidence";
  observations: string[];
  uncertainties: string[];
  research: { id: string; path: string }[];
  suggestions: { id: string; date: string; reason: string;
    before: { title: string; distance_miles: number };
    changes?: { session_id:number; date:string; before:{distance_miles:number}; replacement:{distance_miles:number} }[];
    replacement: { title: string; description: string; distance_miles: number; warmup: string | null; cooldown: string | null } }[];
}

async function post<T>(path: string, data: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Could not complete the coaching request.");
  return result;
}

export function CoachingReview({ activityId, planId, onPlanChanged }: {
  activityId?: number; planId?: number; onPlanChanged?: () => void;
}) {
  const [review, setReview] = useState<Review | null>(null);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [autoJob, setAutoJob] = useState<{status:string|null;message:string|null} | null>(null);
  const [error, setError] = useState<string | null>(null);
  const query = activityId ? `activity_id=${activityId}` : `plan_id=${planId}`;
  const load = useCallback(async () => {
    try {
      const [saved, status, job] = await Promise.all([
        getJson<Review>(`/coaching/${USER_ID}/latest?${query}`),
        getJson<{ configured: boolean }>(`/coaching/${USER_ID}/status`),
        activityId ? getJson<{status:string|null;message:string|null}>(`/coaching/${USER_ID}/jobs/${activityId}`) : Promise.resolve(null),
      ]);
      setReview(saved); setConfigured(status?.configured ?? false); setAutoJob(job);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load the saved coaching review."); }
  }, [query, activityId]);
  useEffect(() => { const timer = setTimeout(load, 0); return () => clearTimeout(timer); }, [load]);

  const autoPending = autoJob?.status && ["waiting_sync", "queued", "running"].includes(autoJob.status);
  useEffect(() => {
    if (!autoPending && review?.status !== "pending") return;
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [autoPending, review?.status, load]);

  async function generate() {
    setBusy(true); setError(null);
    try { setReview(await post<Review>(`/coaching/${USER_ID}/review`, { activity_id: activityId, plan_id: planId })); }
    catch (e) { setError(e instanceof Error ? e.message : "Coach review failed. Your plan is unchanged."); }
    finally { setBusy(false); }
  }
  async function accept(id: string) {
    if (!review) return;
    setBusy(true); setError(null);
    try {
      await post(`/coaching/${USER_ID}/reviews/${review.id}/accept`, { candidate_id: id });
      setReview({ ...review, applied_candidate_id: id });
      onPlanChanged?.();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not apply this suggestion."); }
    finally { setBusy(false); }
  }
  return <section className="space-y-3 rounded-xl border bg-card p-4" aria-label="AI coaching review" aria-busy={busy}>
    <div>
      <p className="eyebrow">Coach perspective</p>
      <h3 className="mt-1 text-sm font-semibold">{activityId ? "This run and what comes next" : "Does this block fit?"}</h3>
      <p className="mt-1 text-xs text-muted-foreground">Reviews training, recovery and your coaching research. Suggested changes need your approval.</p>
    </div>
    {configured === false && <p className="text-sm text-muted-foreground">OpenAI isn&apos;t configured. Your training rules and saved feedback still work.</p>}
    {autoPending && <p role="status" className="text-xs text-muted-foreground">New Garmin run received · {autoJob?.status === "running" ? "coach is reviewing it and your upcoming plan" : "automatic coach review queued"}. You can add how it felt afterward.</p>}
    {autoJob?.status === "failed" && <p role="status" className="text-xs text-muted-foreground">Automatic review could not finish. You can request a review manually.</p>}
    {review && <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span>{review.status === "ready" ? "OpenAI review" : review.status === "pending" ? "Review in progress" : "Fallback · AI unavailable"}</span>
        {review.model && <span>{review.model}</span>}
        <span>{new Date(review.created_at + (review.created_at.endsWith("Z") || review.created_at.includes("+") ? "" : "Z")).toLocaleString()}</span>
      </div>
      {review.stale && <p role="status" className="rounded-md bg-muted p-2">Training has changed since this review. Request an updated review before applying an option.</p>}
      <p className="leading-relaxed">{review.summary}</p>
      {review.observations.length > 0 && <ul className="list-disc space-y-1 pl-4">{review.observations.map((text, i) => <li key={i}>{text}</li>)}</ul>}
      {review.uncertainties.length > 0 && <details><summary className="cursor-pointer text-muted-foreground">What the coach couldn&apos;t establish</summary><ul className="mt-2 list-disc space-y-1 pl-4">{review.uncertainties.map((text, i) => <li key={i}>{text}</li>)}</ul></details>}
      {review.research.length > 0 && <p className="break-words text-xs text-muted-foreground">Research used: {review.research.map(s => s.path.split("/").pop()?.replace(/\.md$/, "").replaceAll("-", " ")).join(" · ")}</p>}
      {review.suggestions.map(option => <div key={option.id} className="space-y-2 rounded-md border p-3">
        <p className="font-medium">{option.date}: {option.replacement.title}</p>
        <p className="text-xs text-muted-foreground">Replaces {option.before.title} ({option.before.distance_miles} mi) → {option.replacement.distance_miles} mi total</p>
        <p>{option.replacement.description}</p>
        {(option.replacement.warmup || option.replacement.cooldown) && <p className="text-xs text-muted-foreground">Warmup: {option.replacement.warmup ?? "none"} · Cooldown: {option.replacement.cooldown ?? "none"}</p>}
        {option.changes?.filter(change => change.date !== option.date).map(change => <p key={change.date} className="text-xs text-muted-foreground">Also adjusts {change.date}: {change.before.distance_miles} → {change.replacement.distance_miles} mi to preserve the weekly budget.</p>)}
        <p className="text-muted-foreground">{option.reason}</p>
        <Button size="sm" variant="outline" disabled={busy || review.stale || !!review.applied_candidate_id} onClick={() => accept(option.id)}>{review.applied_candidate_id === option.id ? "Applied" : "Apply this change"}</Button>
      </div>)}
      {review.applied_candidate_id && <p role="status" className="text-primary">Change saved. Stride rechecked the schedule and mileage budget.</p>}
    </div>}
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {error && configured === null && <Button size="sm" variant="outline" onClick={load}>Retry loading coach</Button>}
    <Button size="sm" variant="outline" disabled={busy || configured !== true} onClick={generate}>{busy ? "Reviewing…" : review?.status === "pending" ? "Check review" : review ? "Review with latest training" : activityId ? "Review run & upcoming plan" : "Ask coach to review this block"}</Button>
    <p className="text-[11px] text-muted-foreground">Training summaries, feedback and research excerpts are sent to OpenAI when a new Garmin run syncs, you request a review, or submit run feedback. No GPS routes or account credentials are sent. Unchanged reviews are reused.</p>
  </section>;
}
