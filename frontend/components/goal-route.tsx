"use client";
import { useState } from "react";
import { apiUrl, USER_ID } from "@/lib/api";
import { Panel } from "@/components/cockpit/panel";
import { cn } from "@/lib/utils";

export interface Milestone {
  key: string;
  label: string;
  current: number | null;
  target: number | null;
  unit: string;
  status: "done" | "in_progress";
  est_weeks: number;
  detail: string;
}

export interface OutlookDecision {
  key: string;
  required: boolean;
  question: string;
  options: { key: string; label: string; detail: string }[];
}

export interface Outlook {
  schedule_gap?: {capacity_mpw:number;target_mpw:number;message:string};
  goal_id?: number;
  intent?: string;
  accepted_decision?: { choice: string } | null;
  milestones: Milestone[];
  gaps: { milestone: string; message: string }[];
  decision?: OutlookDecision | null;
  est_weeks_to_ready: number;
  note: string;
}

export interface BlockReview {
  decision: string | null;
  completed: string[];
  learned: string;
  changes: string[];
  why: string[];
  earned: string[];
  missing: string[];
}

function weeks(n: number) {
  return n === 0 ? "reached" : `~${n} wk${n === 1 ? "" : "s"}`;
}

/** Where the rolling blocks are heading: milestones, not a fixed 16-week plan. */
export function GoalRoute({ outlook }: { outlook: Outlook }) {
  const [choice, setChoice] = useState("completion");
  const [raceDate, setRaceDate] = useState("");
  const [distance, setDistance] = useState("5k");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  async function saveDecision() {
    setSaving(true); setMessage("");
    try {
      const res = await fetch(apiUrl(`/users/${USER_ID}/goal/decision`), { method: "POST", headers: {"Content-Type":"application/json"},
        body: JSON.stringify({goal_id: outlook.goal_id, choice, race_date: choice === "later_race" ? raceDate : null, race_distance: choice === "shorter" ? distance : null}) });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Check your choice.");
      setMessage(data.message);
      window.dispatchEvent(new Event("stride:synced"));
    } catch(e) { setMessage(e instanceof Error ? e.message : "Could not save decision."); }
    finally { setSaving(false); }
  }
  if (!outlook.milestones.length) return null;
  return (
    <Panel label="Route to your goal" meta={outlook.schedule_gap ? "Availability decision" : outlook.est_weeks_to_ready ? `~${outlook.est_weeks_to_ready} wks` : "On track"} bodyClassName="px-3 py-2">
      {outlook.schedule_gap && <p role="alert" className="mb-2 rounded border p-2 text-sm">{outlook.schedule_gap.message} <a className="underline" href="/settings">Review daily time and goal</a></p>}
      {outlook.decision && (
        <div role="alert" className="mb-2 rounded-md border border-amber-500/60 bg-amber-500/15 p-2 text-xs leading-relaxed">
          <p className="font-medium">Decision needed: {outlook.decision.question}</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            {outlook.decision.options.map((o) => (
              <li key={o.key}>
                {o.label} <span className="text-muted-foreground">({o.detail})</span>
              </li>
            ))}
          </ul>
          <label className="block mt-2">Your decision
            <select className="block w-full min-h-11 rounded border bg-background p-2" value={choice} onChange={e=>setChoice(e.target.value)}>
              {outlook.decision.options.map(o=><option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
          </label>
          {choice === "later_race" && <label className="block">New race date<input type="date" className="block min-h-11 rounded border p-2" value={raceDate} onChange={e=>setRaceDate(e.target.value)}/></label>}
          {choice === "shorter" && <label className="block">New distance<select className="block min-h-11 rounded border p-2" value={distance} onChange={e=>setDistance(e.target.value)}>{["5k","10k","half","marathon","50k","50mi","100k"].map(d=><option key={d}>{d}</option>)}</select></label>}
          <p className="my-2">Your current block stays approved until you preview and approve a revision.</p>
          <button className="min-h-11 rounded border px-3" disabled={saving} onClick={saveDecision}>{saving ? "Saving…" : "Save goal decision"}</button>
        </div>
      )}
      {message && <p role="status" className="mb-2 text-sm">{message}</p>}
      {outlook.accepted_decision && <p className="text-xs mb-2">Saved decision: {outlook.accepted_decision.choice.replaceAll("_", " ")}</p>}
      {outlook.gaps.map((g) => (
        <p key={g.milestone} role="alert" className="mb-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs leading-relaxed">
          {g.message}
        </p>
      ))}
      <ol className="space-y-2">
        {outlook.milestones.map((m) => {
          const pct = m.target ? Math.min(100, Math.round(((m.current ?? 0) / m.target) * 100)) : 0;
          return (
            <li key={m.key} className="text-sm">
              <div className="flex items-baseline justify-between gap-3">
                <span className={cn(m.status === "done" && "text-muted-foreground line-through decoration-1")}>{m.label}</span>
                <span className="num shrink-0 text-xs text-muted-foreground">{m.status === "done" ? "Done ✓" : outlook.schedule_gap && ["volume","long_run"].includes(m.key) ? "Review availability" : weeks(m.est_weeks)}</span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-secondary" aria-hidden="true">
                <div className="h-1.5 rounded-full bg-foreground" style={{ width: `${pct}%` }} />
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                <span className="num">{m.current ?? 0}</span> / <span className="num">{m.target}</span> {m.unit} · {m.detail}
              </p>
            </li>
          );
        })}
      </ol>
      <p className="mt-2 text-xs text-muted-foreground">{outlook.note}</p>
    </Panel>
  );
}

const DECISION_LABEL: Record<string, string> = {
  build: "Building", hold: "Holding steady", reduce: "Easing back", recovery: "Recovery block",
};

/** Last block → what we learned → what changes → why. */
export function BlockReviewPanel({ review }: { review: BlockReview }) {
  const sections: [string, string[]][] = [
    ["What you completed", review.completed],
    ["What we learned", [review.learned]],
    ["What changes next", review.changes],
    ["Earned", review.earned],
    ["Still needed", review.missing],
  ];
  return (
    <Panel label="Last block review" meta={review.decision ? DECISION_LABEL[review.decision] ?? review.decision : undefined} bodyClassName="space-y-2 px-3 py-2">
      {sections.filter(([, items]) => items.length).map(([title, items]) => (
        <div key={title}>
          <p className="stat-label">{title}</p>
          <ul className="mt-0.5 space-y-0.5 text-sm">
            {items.map((t) => <li key={t}>{t}</li>)}
          </ul>
        </div>
      ))}
      {review.why.length > 0 && (
        <details className="text-xs text-muted-foreground" open>
          <summary className="cursor-pointer">Why</summary>
          <ul className="mt-1 space-y-0.5">{review.why.map((t) => <li key={t}>{t}</li>)}</ul>
        </details>
      )}
    </Panel>
  );
}
