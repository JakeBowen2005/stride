"use client";

import { useEffect, useState } from "react";
import { Check, Loader2, ShieldAlert, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiUrl, getJson, USER_ID } from "@/lib/api";
import { formatDateShort } from "@/lib/format";
import { distanceInUnits, type Units } from "@/lib/units";
import { cn } from "@/lib/utils";
import type { Workout } from "@/lib/types";

export const REQUEST_LIMIT = 500;
const STARTERS = ["Busy weekend", "Traveling", "Night out", "Feeling sick"];
const WINDOW_DAYS = 14;

type Kind = "no_run" | "no_hard";
type DayChange = { date: string; day: string; before: Session; after: Session };
type Session = { type: string; title: string; distance_miles: number };
export type ChangeRequest = {
  id: number;
  status: "clarifying" | "proposed" | "no_safe_change" | "safety" | "out_of_scope" | "no_change" | "applied"
    | "declined" | "undone" | "stale" | "ai_unavailable" | "working";
  source: string | null;
  safety: "none" | "illness" | "injury" | "red_flag";
  request_text: string;
  understood: string | null;
  changes: DayChange[];
  summary: string[];
  checks: string[];
  explanation: string | null;
  question: string | null;
  choices: string[];
  reasons: string[];
  note: string | null;
  ops: { op: string; date: string }[];
  cached?: boolean;
  /** Applied changes only: false once a changed day is run, past or edited again */
  undoable?: boolean;
};
type Listing = { requests: ChangeRequest[]; ai_available: boolean; remaining_today: number; daily_limit: number };

async function post<T>(path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(apiUrl(path), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
  } catch { throw new Error("Can't reach Stride. Check your connection and try again."); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Stride request failed (${res.status}).`);
  return data as T;
}

/** The days a request may touch: today through 13 days ahead, unrun, not race day. */
export function editableDays(days: Workout[], today: string): Workout[] {
  const last = new Date(`${today}T12:00:00`);
  last.setDate(last.getDate() + WINDOW_DAYS - 1);
  const end = last.toISOString().slice(0, 10);
  return days.filter((d) => d.date >= today && d.date <= end && !d.actual && d.type !== "race" && d.prescribed !== false);
}

function weekday(date: string) {
  return new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { weekday: "short" });
}

/**
 * "What's coming up?": the athlete describes their week in their own words (or taps days in the
 * quick picker), Stride proposes a rearranged week that passed every training rule, and nothing
 * changes until they approve it. Applied changes can be undone.
 */
export function PlanChangeRequest({ days, today, units, onChanged }: {
  days: Workout[];
  today: string;
  units: Units;
  onChanged: () => void;
}) {
  const [text, setText] = useState("");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState<ChangeRequest | null>(null);
  const [listing, setListing] = useState<Listing | null>(null);
  const [picker, setPicker] = useState(false);
  const [picked, setPicked] = useState<Record<string, Kind>>({});
  const open = editableDays(days, today);

  useEffect(() => {
    let live = true;
    getJson<Listing>(`/plans/${USER_ID}/requests`).then((l) => { if (live) setListing(l); }).catch(() => {});
    return () => { live = false; };
  }, [current?.status]);
  const lastApplied = listing?.requests.find((r) => r.status === "applied" && r.undoable) ?? null;
  const aiOff = listing !== null && !listing.ai_available;
  const outOfRequests = listing !== null && listing.ai_available && listing.remaining_today <= 0;

  async function run(action: () => Promise<ChangeRequest>) {
    setBusy(true); setError(null);
    try { setCurrent(await action()); }
    catch (e) { setError(e instanceof Error ? e.message : "Something went wrong."); }
    finally { setBusy(false); }
  }
  const suggest = () => run(() => post(`/plans/${USER_ID}/requests`, { text }));
  const pickerSuggest = () => run(() => post(`/plans/${USER_ID}/requests`, {
    text, constraints: Object.entries(picked).map(([date, kind]) => ({ date, kind })),
  }));
  const reply = (value: string) => current && run(() => post(`/plans/${USER_ID}/requests/${current.id}/answer`, { answer: value }));
  const approve = () => current && run(async () => { const r = await post<ChangeRequest>(`/plans/${USER_ID}/requests/${current.id}/apply`); onChanged(); return r; });
  const discard = () => current && run(() => post(`/plans/${USER_ID}/requests/${current.id}/discard`));
  const undo = (id: number) => run(async () => { const r = await post<ChangeRequest>(`/plans/${USER_ID}/requests/${id}/undo`); onChanged(); return r; });
  const reset = () => { setCurrent(null); setAnswer(""); setError(null); };
  const cycle = (date: string) => setPicked((p) => {
    const next = { ...p };
    if (!p[date]) next[date] = "no_hard"; else if (p[date] === "no_hard") next[date] = "no_run"; else delete next[date];
    return next;
  });

  const showResult = current && !["declined", "working"].includes(current.status);
  return (
    <section aria-labelledby="coming-up" className="space-y-3">
      <div className="space-y-1">
        <label id="coming-up" htmlFor="plan-request" className="text-sm font-medium">What&apos;s coming up?</label>
        <p className="text-xs text-muted-foreground">
          Describe your week and Stride rearranges or lightens it. Every proposal passes the training rules, and nothing changes until you approve it.
        </p>
      </div>

      {!showResult && (
        <>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Starters">
            {STARTERS.map((s) => (
              <button key={s} type="button" onClick={() => setText((t) => (t ? `${t} ${s}.` : `${s}: `).slice(0, REQUEST_LIMIT))}
                className="min-h-9 rounded-full border px-3.5 py-1 text-sm transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-primary">
                {s}
              </button>
            ))}
          </div>
          <Textarea id="plan-request" value={text} maxLength={REQUEST_LIMIT} rows={3} disabled={busy}
            placeholder="e.g. Halloween weekend: out Friday and Saturday night, and I don't want my long run hungover."
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && text.trim() && !aiOff) suggest(); }} />
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>{text.length}/{REQUEST_LIMIT}</span>
            {listing && listing.ai_available && <span>{listing.remaining_today} of {listing.daily_limit} AI requests left today</span>}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button className="h-10 flex-1 sm:h-9" disabled={busy || !text.trim() || aiOff || outOfRequests} onClick={suggest}>
              {busy && !picker ? <><Loader2 className="animate-spin" aria-hidden="true" /> Reading your week…</> : "Suggest changes"}
            </Button>
            <Button variant="outline" className="h-10 sm:h-9" aria-expanded={picker} onClick={() => setPicker((p) => !p)} disabled={busy}>
              Quick picker
            </Button>
          </div>
          {aiOff && !picker && <p className="text-xs text-muted-foreground">AI plan changes are off. The quick picker uses Stride&apos;s rules only and always works.</p>}
          {outOfRequests && !picker && <p className="text-xs text-muted-foreground">You&apos;ve used today&apos;s AI requests. The quick picker still works, and the count resets at midnight.</p>}
          {picker && (
            <div className="glass-tile space-y-2 p-3.5">
              <p className="text-sm">Tap a day once for <strong>nothing hard</strong>, twice for <strong>no running</strong>.</p>
              <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-7">
                {open.map((d) => {
                  const kind = picked[d.date];
                  return (
                    <button key={d.date} type="button" onClick={() => cycle(d.date)} aria-pressed={!!kind}
                      aria-label={`${weekday(d.date)} ${formatDateShort(d.date)}: ${kind === "no_run" ? "no running" : kind === "no_hard" ? "nothing hard" : "no limit"}`}
                      className={cn("flex min-h-12 flex-col items-center justify-center rounded-lg border px-1 py-1 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-primary",
                        kind === "no_run" ? "border-foreground bg-foreground text-background" : kind === "no_hard" ? "border-foreground bg-muted" : "hover:bg-muted")}>
                      <span className="font-medium">{weekday(d.date)}</span>
                      <span className="tabular-nums">{formatDateShort(d.date).replace(/^\w+ /, "")}</span>
                      <span className="text-[10px] opacity-80">{kind === "no_run" ? "no run" : kind === "no_hard" ? "easy only" : " "}</span>
                    </button>
                  );
                })}
              </div>
              <Button variant="outline" className="h-10 w-full sm:h-9" disabled={busy || !Object.keys(picked).length} onClick={pickerSuggest}>
                {busy && picker ? <><Loader2 className="animate-spin" aria-hidden="true" /> Checking…</> : "Rearrange around these days"}
              </Button>
            </div>
          )}
        </>
      )}

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

      {showResult && current && (
        <Result request={current} units={units} busy={busy} answer={answer} setAnswer={setAnswer}
          onReply={reply} onApprove={approve} onDiscard={discard} onUndo={() => undo(current.id)} onReset={reset} />
      )}

      {!showResult && lastApplied && (
        <div className="flex items-center justify-between gap-2 border-t pt-2 text-xs text-muted-foreground">
          <span className="min-w-0 truncate">Last change: {lastApplied.understood || lastApplied.request_text}</span>
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => undo(lastApplied.id)}><Undo2 aria-hidden="true" /> Undo</Button>
        </div>
      )}
    </section>
  );
}

function Result({ request, units, busy, answer, setAnswer, onReply, onApprove, onDiscard, onUndo, onReset }: {
  request: ChangeRequest; units: Units; busy: boolean; answer: string; setAnswer: (v: string) => void;
  onReply: (v: string) => void; onApprove: () => void; onDiscard: () => void; onUndo: () => void; onReset: () => void;
}) {
  const s = request.status;
  const dist = (miles: number) => miles > 0 ? distanceInUnits(miles, units) : "";
  const note = request.note && (
    <div className="flex gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
      <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" /><p>{request.note}</p>
    </div>
  );
  return (
    <div className="space-y-3" aria-live="polite">
      {request.understood && s !== "applied" && (
        <div><p className="stat-label">Here&apos;s what I understood</p><p className="text-sm">{request.understood}</p></div>
      )}
      {note}
      {s === "clarifying" && (
        <div className="space-y-2">
          <p className="text-sm font-medium">{request.question}</p>
          <div className="flex flex-wrap gap-2">
            {request.choices.map((c) => <Button key={c} variant="outline" size="sm" className="h-10 sm:h-8" disabled={busy} onClick={() => onReply(c)}>{c}</Button>)}
          </div>
          <div className="flex gap-2">
            <input value={answer} maxLength={500} onChange={(e) => setAnswer(e.target.value)} placeholder="Or answer in your words"
              enterKeyHint="send" onKeyDown={(e) => { if (e.key === "Enter" && answer.trim()) onReply(answer); }}
              className="h-10 min-w-0 flex-1 rounded-md border bg-transparent px-3 text-sm sm:h-9" />
            <Button className="h-10 sm:h-9" disabled={busy || !answer.trim()} onClick={() => onReply(answer)}>Send</Button>
          </div>
        </div>
      )}
      {(s === "proposed" || s === "safety" || s === "applied") && request.changes?.length > 0 && (
        <ul className="divide-y rounded-lg border text-sm" aria-label="Changed days">
          {request.changes.map((c) => (
            <li key={c.date} className="flex flex-wrap items-baseline gap-x-2 px-3 py-2">
              <span className="w-24 shrink-0 font-medium">{weekday(c.date)} {formatDateShort(c.date).replace(/^\w+ /, "")}</span>
              <span className="text-muted-foreground line-through">{c.before.title} {dist(c.before.distance_miles)}</span>
              <span aria-hidden="true">→</span><span className="sr-only">becomes</span>
              <span className="font-medium">{c.after.title} {dist(c.after.distance_miles)}</span>
            </li>
          ))}
        </ul>
      )}
      {s === "proposed" && (
        <>
          {units === "miles" && request.summary.map((line) => <p key={line} className="text-xs text-muted-foreground">{line}</p>)}
          {request.explanation && <p className="text-sm">{request.explanation}</p>}
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer">Checks passed</summary>
            <ul className="mt-1 space-y-0.5">{request.checks.map((c) => <li key={c} className="flex gap-1.5"><Check className="size-3.5" aria-hidden="true" />{c}</li>)}</ul>
          </details>
        </>
      )}
      {s === "no_safe_change" && (
        <div className="space-y-1 text-sm">
          <p className="font-medium">I couldn&apos;t fit that without breaking a training rule.</p>
          <ul className="list-disc pl-5 text-muted-foreground">{request.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          <p className="text-muted-foreground">You can still move or skip a single session from the day&apos;s detail.</p>
        </div>
      )}
      {s === "out_of_scope" && <p className="text-sm">This tool rearranges or lightens your week. For more training, open &ldquo;Something about the training isn&apos;t working?&rdquo; below, or preview the next block.</p>}
      {s === "no_change" && <p className="text-sm">{request.explanation || "Your plan already fits that. Nothing needs to change."}</p>}
      {s === "ai_unavailable" && <p className="text-sm">{request.reasons[0]}</p>}
      {s === "stale" && <p className="text-sm">Your plan changed since this was suggested. Ask again for an up-to-date proposal.</p>}
      {s === "undone" && <p className="text-sm">Change undone. Your week is back to how it was.</p>}
      {s === "applied" && <p className="text-sm font-medium">Week updated. The changed days are marked in your plan.</p>}

      <div className="sticky bottom-0 -mx-1 flex flex-wrap gap-2 bg-popover px-1 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] backdrop-blur">
        {(s === "proposed" || (s === "safety" && request.ops.length > 0)) && (
          <>
            <Button className="h-10 flex-1 sm:h-9" disabled={busy} onClick={onApprove}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}{s === "safety" ? "Skip these days" : "Approve"}
            </Button>
            <Button variant="outline" className="h-10 sm:h-9" disabled={busy} onClick={onDiscard}>Discard</Button>
          </>
        )}
        {s === "applied" && request.undoable !== false && <Button variant="outline" className="h-10 sm:h-9" disabled={busy} onClick={onUndo}><Undo2 aria-hidden="true" /> Undo</Button>}
        {s !== "clarifying" && <Button variant="ghost" className="h-10 sm:h-9" disabled={busy} onClick={onReset}>{s === "proposed" ? "Try different wording" : "New request"}</Button>}
      </div>
    </div>
  );
}
