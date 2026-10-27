"use client";

import { useEffect, useState } from "react";
import { getJson, USER_ID } from "@/lib/api";
import { useUnits } from "@/components/unit-preferences";
import { distanceInUnits, unitLabel } from "@/lib/units";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Profile {
  as_of: string;
  coverage: { recorded_runs: number; first_recorded_run: string | null; fit_status: Record<string, number> };
  current: { recorded_mpw_last_4_weeks: number };
  historical_capacity: {
    sustained_blocks: { start: string; end: string; average_mpw: number; run_days_per_week: number; activity_ids: number[] }[];
    longest_runs: { date: string; miles: number; activity_ids: number[] }[];
  };
  recording_gaps: { after: string; before: string; unrecorded_days: number }[];
}

const historyDate = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

export function HistoryProfile({ revision, onInspect }: { revision: number; onInspect: (id: number) => Promise<void> }) {
  const units = useUnits();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    getJson<Profile>(`/analysis/${USER_ID}/history`).then(data => {
      if (active) { setProfile(data); setError(null); }
    }).catch(() => { if (active) setError("Training overview unavailable. Your runs are still shown below."); });
    return () => { active = false; };
  }, [revision]);
  if (error) return <p role="status" className="glass p-4 text-sm text-muted-foreground">{error}</p>;
  if (!profile) return <p role="status" className="glass p-4 text-sm text-muted-foreground">Reading your training history…</p>;
  const missing = (profile.coverage.fit_status.pending || 0) + (profile.coverage.fit_status.retry || 0);
  const unavailable = profile.coverage.fit_status.unavailable || 0;
  const distance = (miles: number) => `${distanceInUnits(miles, units)} ${unitLabel(units)}`;
  const inspect = async (id: number) => {
    try { await onInspect(id); }
    catch { setError("Could not open that run. Reload to retry."); }
  };
  return <Card>
    <CardHeader><CardTitle className="text-[13px] font-bold">What your history shows</CardTitle></CardHeader>
    <CardContent className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="glass-tile px-3.5 py-3"><p className="text-xs text-muted-foreground">Recent recorded average</p>
          <p className="num text-2xl font-semibold tracking-tight">{distance(profile.current.recorded_mpw_last_4_weeks)} / week</p>
          <p className="text-xs text-muted-foreground">Last four completed weeks</p></div>
        <div className="glass-tile px-3.5 py-3"><p className="text-xs text-muted-foreground">Recorded history</p>
          <p className="num text-2xl font-semibold tracking-tight">{profile.coverage.recorded_runs} runs</p>
          <p className="text-xs text-muted-foreground">{profile.coverage.first_recorded_run ? `Since ${historyDate(profile.coverage.first_recorded_run)}` : "No runs recorded yet"}</p></div>
      </div>
      {profile.historical_capacity.sustained_blocks.length > 0 && <details className="glass-tile px-3.5 py-2.5">
        <summary className="cursor-pointer text-sm font-semibold">Previously sustained training</summary>
        <p className="mt-2 text-xs text-muted-foreground">Past capacity provides context. Current training determines the next step.</p>
        <ul className="mt-2 space-y-3">{profile.historical_capacity.sustained_blocks.map(block => <li key={block.start} className="text-sm">
          <p>{distance(block.average_mpw)} / week · {historyDate(block.start)}–{historyDate(block.end)}</p>
          <p className="text-xs text-muted-foreground">{block.run_days_per_week} running days/week · four recorded weeks</p>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">{block.activity_ids.slice(0, 5).map((id, index) => <button key={id} type="button" onClick={() => inspect(id)} aria-label={`View run ${index + 1} from block starting ${historyDate(block.start)}`} className="text-xs underline underline-offset-2">View run {index + 1}</button>)}</div>
        </li>)}</ul>
      </details>}
      {(missing > 0 || unavailable > 0) && <p className="text-xs text-muted-foreground">Lap evidence: {missing} awaiting repair{unavailable ? ` · ${unavailable} unavailable` : ""}. Those runs still contribute their recorded mileage.</p>}
      {profile.recording_gaps.length > 0 && <p className="text-xs text-muted-foreground">Some stretches have no recorded runs. That can mean time off, missing uploads, or training without a watch.</p>}
    </CardContent>
  </Card>;
}
