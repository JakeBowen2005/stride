"use client";

import { PREFERENCES_EVENT } from "@/components/unit-preferences";
import { useState } from "react";
import Link from "next/link";
import { apiUrl, USER_ID } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { describeSchedule, scheduleChanged } from "@/lib/plan-preferences";

export interface AthletePreferences {
  name: string | null;
  age: number | null;
  experience_level?: string | null;
  units: string;
  workout_format?: string;
  days_per_week: number;
  rest_days: string | null;
  long_run_day?: string | null;
}

const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const title = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const inputClass = "mt-1 block w-full rounded-md border bg-background px-3 py-2 text-sm";

export function ProfilePreferences({ user, onSaved }: { user: AthletePreferences; onSaved: (user: AthletePreferences) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(user);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  // "drafted": the schedule changed and Stride built an updated block awaiting approval.
  const [saved, setSaved] = useState<null | "saved" | "drafted" | "draft_failed">(null);
  const [draftProblem, setDraftProblem] = useState("");
  const rest = (draft.rest_days || "").split(",").filter(Boolean);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true); setError(""); setSaved(null);
    try {
      const res = await fetch(apiUrl(`/users/${USER_ID}/profile`), {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ age: draft.age, experience_level: draft.experience_level || null, units: draft.units, workout_format: draft.workout_format || "distance",
          days_per_week: draft.days_per_week, rest_days: rest, long_run_day: draft.long_run_day || "saturday" }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "Could not save preferences. Check your selections and try again.");
      }
      onSaved(draft); window.dispatchEvent(new Event(PREFERENCES_EVENT)); setEditing(false);
      const before = { rest_days: (user.rest_days || "").split(",").filter(Boolean), days_per_week: user.days_per_week,
        long_run_day: user.long_run_day || "saturday", workout_format: user.workout_format || "distance" };
      if (!scheduleChanged(before, draft)) { setSaved("saved"); return; }
      // Run days changed: draft the smallest change to the approved block (workouts stay put). It stays a draft until approved.
      const preview = await fetch(apiUrl(`/plans/${USER_ID}/preview`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scope: "current", mode: "schedule" }) }).catch(() => null);
      if (!preview?.ok) {
        const body = await preview?.json().catch(() => ({}));
        setDraftProblem(typeof body?.detail === "string" ? body.detail : "");
      }
      setSaved(preview?.ok ? "drafted" : "draft_failed");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save preferences."); }
    finally { setSaving(false); }
  }

  return <div className="space-y-4">
    <div className="flex items-center justify-between">
      <h2 className="text-sm font-medium">Profile & training preferences</h2>
      {!editing && <Button variant="outline" size="sm" onClick={() => { setDraft(user); setError(""); setEditing(true); }}>Edit preferences</Button>}
    </div>
    {saved === "saved" && <p role="status" className="text-sm text-muted-foreground">Saved.</p>}
    {saved === "drafted" && <p role="status" className="text-sm">Saved. Stride drafted an updated block for {describeSchedule(draft.days_per_week, rest)}. <Link className="font-medium underline" href="/plan">Review and approve it</Link>. Your current plan stays active until you do.</p>}
    {saved === "draft_failed" && <p role="status" className="text-sm text-muted-foreground">Saved. Stride couldn&apos;t draft the updated block{draftProblem ? `: ${draftProblem}` : " just now."} <Link className="underline" href="/plan">Open your plan</Link> and choose Update my plan.</p>}
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {editing ? <form onSubmit={save} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm">Age<input className={inputClass} type="number" min="10" max="100" value={draft.age ?? ""} onChange={(e) => setDraft({ ...draft, age: e.target.value ? Number(e.target.value) : null })} /></label>
        <label className="text-sm">Units<select className={inputClass} value={draft.units} onChange={(e) => setDraft({ ...draft, units: e.target.value })}><option value="miles">Miles</option><option value="km">Kilometers</option></select></label>
        <label className="text-sm">Workout format<select className={inputClass} value={draft.workout_format || "distance"} onChange={(e) => setDraft({ ...draft, workout_format: e.target.value })}><option value="distance">Distance-based</option><option value="time">Time-based</option></select></label>
        <label className="text-sm">Training experience<select className={inputClass} value={draft.experience_level || ""} onChange={(e) => setDraft({ ...draft, experience_level: e.target.value || null })}><option value="">Estimate from history</option><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option><option value="expert">Expert / professional</option></select></label>
        <label className="text-sm">Days per week<select className={inputClass} value={draft.days_per_week} onChange={(e) => setDraft({ ...draft, days_per_week: Number(e.target.value) })}>{[1,2,3,4,5,6,7].map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
        <label className="text-sm">Long run day<select className={inputClass} value={draft.long_run_day || "saturday"} onChange={(e) => setDraft({ ...draft, long_run_day: e.target.value })}>{DAYS.map((d) => <option key={d} value={d}>{title(d)}</option>)}</select></label>
      </div>
      <fieldset><legend className="text-sm">Preferred rest days</legend><div className="mt-2 flex flex-wrap gap-3">{DAYS.map((d) => <label key={d} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={rest.includes(d)} onChange={() => setDraft({ ...draft, rest_days: (rest.includes(d) ? rest.filter((day) => day !== d) : [...rest, d]).join(",") })} />{title(d)}</label>)}</div></fieldset>
      <p className="text-xs text-muted-foreground">Experience describes sustained training background. Completed work and recovery still determine progression. We add rest days if fewer running days are selected. Time-based workouts use timed warmups, cooldowns and light fartleks; track repetitions and threshold intervals retain the format that suits their purpose.</p>
      <div className="flex gap-2"><Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save preferences"}</Button><Button type="button" variant="outline" disabled={saving} onClick={() => { setEditing(false); setError(""); }}>Cancel</Button></div>
    </form> : <dl className="grid gap-2 text-sm">{[
      ["Name", user.name || "—"], ["Age", user.age ?? "Not set"], ["Units", user.units === "km" ? "Kilometers" : "Miles"],
      ["Training experience", user.experience_level === "expert" ? "Expert / professional" : user.experience_level ? title(user.experience_level) : "Estimated from history"],
      ["Workout format", user.workout_format === "time" ? "Time-based" : "Distance-based"], ["Days per week", user.days_per_week],
      ["Rest days", (user.rest_days || "").split(",").filter(Boolean).map(title).join(", ") || "None"], ["Long run day", title(user.long_run_day || "saturday")],
    ].map(([label, value]) => <div className="flex justify-between gap-4" key={label}><dt className="text-muted-foreground">{label}</dt><dd>{value}</dd></div>)}</dl>}
  </div>;
}
