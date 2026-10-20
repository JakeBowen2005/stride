"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl, getJson, USER_ID } from "@/lib/api";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatDateShort } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Review {
  id: number;
  created_at: string;
  status: "pending" | "ready" | "fallback";
  model: string | null;
  stale: boolean;
  applied_candidate_id: string | null;
  athlete_concern?: string | null;
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

const PRIVACY = "Training summaries, feedback and research excerpts go to OpenAI when a run syncs, you refresh, or you submit feedback. No GPS routes or credentials are sent.";

export function CoachingReview({ activityId, planId, onPlanChanged, request, bordered = false, showLabel = true, autoRefresh = false }: {
  activityId?: number; planId?: number; onPlanChanged?: () => void;
  /** Draw its own card border (when not already inside a card) */
  bordered?: boolean;
  /** The "Coach" label; off when a surrounding header already names it */
  showLabel?: boolean;
  /** Refresh once when stale. Only for today's run, so browsing old runs never spends AI calls. */
  autoRefresh?: boolean;
  /** The athlete's "what isn't working" from Plan options; a new nonce asks the coach again. */
  request?: { concern: string; nonce: number } | null;
}) {
  const [review, setReview] = useState<Review | null>(null);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [autoJob, setAutoJob] = useState<{status:string|null;message:string|null} | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
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

  const generate = useCallback(async (concern?: string | null) => {
    setBusy(true); setError(null);
    try {
      setReview(await post<Review>(`/coaching/${USER_ID}/review`,
        { activity_id: activityId, plan_id: planId, ...(concern ? { athlete_concern: concern } : {}) }));
    }
    catch (e) { setError(e instanceof Error ? e.message : "Coach review failed. Your plan is unchanged."); }
    finally { setBusy(false); }
  }, [activityId, planId]);
  // A run's review that predates newer training data refreshes itself once, so the athlete
  // never reads advice about a stale picture of their run.
  const autoRefreshed = useRef(false);
  useEffect(() => {
    if (!autoRefresh || !activityId || !review?.stale || configured !== true || busy || autoRefreshed.current || review.applied_candidate_id) return;
    autoRefreshed.current = true;
    const timer = setTimeout(() => generate(review.athlete_concern), 0);
    return () => clearTimeout(timer);
  }, [autoRefresh, activityId, review, configured, busy, generate]);
  const handled = useRef<number | null>(null);
  useEffect(() => {
    if (!request || handled.current === request.nonce) return;
    handled.current = request.nonce;
    const timer = setTimeout(() => generate(request.concern), 0);
    return () => clearTimeout(timer);
  }, [request, generate]);
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
  const when = review ? new Date(review.created_at + (review.created_at.endsWith("Z") || review.created_at.includes("+") ? "" : "Z")) : null;
  const hasDetails = !!review && (review.observations.length > 0 || review.uncertainties.length > 0 || review.research.length > 0);
  const refreshLabel = busy ? "Reviewing…" : review?.status === "pending" ? "Check review" : review ? "Refresh" : activityId ? "Review this run" : "Review this block";
  return <section className={cn("space-y-2 text-sm", bordered && "rounded-xl border bg-card p-3")} aria-label="AI coaching review" aria-busy={busy}>
    <div className={cn("flex items-center gap-2", showLabel ? "justify-between" : "justify-end -mb-1")}>
      {showLabel && <span className="stat-label">Coach</span>}
      <Button size="xs" variant="ghost" className="h-8 px-2 text-xs sm:h-6" disabled={busy || configured !== true}
        title={PRIVACY} onClick={() => generate(review?.athlete_concern)}>
        <RefreshCw className={cn("size-3", busy && "animate-spin")} aria-hidden /> {refreshLabel}
      </Button>
    </div>
    {configured === false && !review && <p className="text-xs text-muted-foreground">AI coach isn&apos;t configured. Your training rules and feedback still work.</p>}
    {busy && request && <p role="status" className="text-xs text-muted-foreground">Coach is reviewing your request…</p>}
    {autoPending && <p role="status" className="text-xs text-muted-foreground">New run received · {autoJob?.status === "running" ? "coach is reviewing it" : "review queued"}.</p>}
    {autoJob?.status === "failed" && !review && <p role="status" className="text-xs text-muted-foreground">Automatic review couldn&apos;t finish. Tap Refresh to try again.</p>}
    {!review && configured === true && !busy && !autoPending && <p className="text-xs text-muted-foreground">No review yet.</p>}
    {review && <>
      {review.athlete_concern && <p className="rounded-md bg-muted px-2.5 py-1.5 text-xs"><span className="font-medium">You asked:</span> {review.athlete_concern}</p>}
      <p className={cn("leading-relaxed", !expanded && "line-clamp-3", busy && review.stale && "opacity-50")}>{review.summary}</p>
      {(hasDetails || review.summary.length > 220) && (
        <button type="button" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}
          className="-my-1.5 py-1.5 text-xs font-medium text-muted-foreground underline underline-offset-2 hover:text-foreground">
          {expanded ? "Less" : "More"}
        </button>
      )}
      {expanded && <div className="space-y-2 text-xs text-muted-foreground">
        {review.observations.length > 0 && <ul className="list-disc space-y-1 pl-4 text-foreground">{review.observations.map((text, i) => <li key={i}>{text}</li>)}</ul>}
        {review.uncertainties.length > 0 && <ul className="list-disc space-y-1 pl-4">{review.uncertainties.map((text, i) => <li key={i}>{text}</li>)}</ul>}
        {review.research.length > 0 && <p className="break-words">Research: {review.research.map(s => s.path.split("/").pop()?.replace(/\.md$/, "").replaceAll("-", " ")).join(" · ")}</p>}
        <p>{review.status === "ready" ? "AI review" : review.status === "pending" ? "Review in progress" : "AI unavailable · rules-based fallback"}{when ? ` · ${when.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}` : ""}</p>
      </div>}
      {review.stale && review.suggestions.length > 0 && !review.applied_candidate_id && <p role="status" className="text-xs text-muted-foreground">Training changed since this review. Refresh before applying a change.</p>}
      {review.suggestions.map(option => <div key={option.id} className="space-y-1.5 rounded-md border p-2.5">
        <p className="font-medium">{formatDateShort(option.date)}: {option.before.title} → {option.replacement.title} <span className="num font-normal text-muted-foreground">({option.replacement.distance_miles} mi)</span></p>
        <p className="text-xs text-muted-foreground">{option.reason}</p>
        {option.changes?.filter(change => change.date !== option.date).map(change => <p key={change.date} className="text-xs text-muted-foreground">Also {formatDateShort(change.date)}: {change.before.distance_miles} → {change.replacement.distance_miles} mi to keep the weekly budget.</p>)}
        <Button size="sm" variant="outline" disabled={busy || review.stale || !!review.applied_candidate_id} onClick={() => accept(option.id)}>{review.applied_candidate_id === option.id ? "Applied" : "Apply"}</Button>
      </div>)}
      {review.applied_candidate_id && <p role="status" className="text-xs text-primary">Change saved. Stride rechecked the schedule and budget.</p>}
    </>}
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {error && configured === null && <Button size="sm" variant="outline" onClick={load}>Retry loading coach</Button>}
  </section>;
}
