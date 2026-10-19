"use client";

import { apiUrl, USER_ID } from "@/lib/api";
import { useState } from "react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";


export interface EditableGoal {
  type: string;
  distance: string | null;
  target_time: number | null;
  race_date: string | null;
  terrain?: string | null;
  elevation_gain_ft?: number | null;
  target_weekly_mileage?: number | null;
}

interface Readiness {
  ready: boolean;
  reasons: string[];
  suggestion: string | null;
}

const DISTANCES = [
  { value: "5k", label: "5K" },
  { value: "10k", label: "10K" },
  { value: "half", label: "Half Marathon" },
  { value: "marathon", label: "Marathon" },
  { value: "50k", label: "50K" },
  { value: "50mi", label: "50 Mile" },
  { value: "100k", label: "100K" },
  { value: "100mi", label: "100 Mile" },
];
const ULTRAS = new Set(["50k", "50mi", "100k", "100mi"]);

const selectClass =
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

function splitTime(total: number | null) {
  if (!total) return { h: "", m: "", s: "" };
  return {
    h: String(Math.floor(total / 3600) || ""),
    m: String(Math.floor((total % 3600) / 60)),
    s: String(Math.round(total % 60)),
  };
}

export function GoalEditor({
  initial,
  onSaved,
  onCancel,
}: {
  initial: EditableGoal | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [goalType, setGoalType] = useState(initial?.type ?? "race");
  const [distance, setDistance] = useState(initial?.distance ?? "5k");
  const t = splitTime(initial?.target_time ?? null);
  const [hours, setHours] = useState(t.h);
  const [minutes, setMinutes] = useState(t.m);
  const [seconds, setSeconds] = useState(t.s);
  const [raceDate, setRaceDate] = useState(initial?.race_date ?? "");
  const [terrain, setTerrain] = useState(initial?.terrain ?? "trail");
  const [vert, setVert] = useState(initial?.elevation_gain_ft ? String(initial.elevation_gain_ft) : "");
  const [mileage, setMileage] = useState(initial?.target_weekly_mileage ? String(initial.target_weekly_mileage) : "");

  const [saving, setSaving] = useState(false);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState(false);

  const ultra = goalType === "race" && ULTRAS.has(distance);

  function payload(override: boolean) {
    const total = (Number(hours) || 0) * 3600 + (Number(minutes) || 0) * 60 + (Number(seconds) || 0);
    return {
      goal_type: goalType,
      race_distance: goalType === "race" ? distance : null,
      target_time_seconds: goalType === "race" && total > 0 ? total : null,
      race_date: goalType === "race" && raceDate ? raceDate : null,
      target_weekly_mileage: goalType === "mileage" && mileage ? Number(mileage) : null,
      terrain: ultra ? terrain : goalType === "race" ? "road" : null,
      elevation_gain_ft: ultra && vert ? Number(vert) : null,
      override_readiness: override,
    };
  }

  async function save(override = false) {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(apiUrl(`/users/${USER_ID}/goal`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload(override)),
      });
      const data = await res.json().catch(() => ({}));
      if (res.status === 409 && data.detail?.readiness) {
        setReadiness(data.detail.readiness);
      } else if (!res.ok) {
        setError(typeof data.detail === "string" ? data.detail : "Couldn't save goal");
      } else {
        setReadiness(null);
        setSaved(true);
      }
    } catch {
      setError("Can't reach the Stride backend");
    } finally {
      setSaving(false);
    }
  }

  async function regenerate() {
    setGenerating(true);
    try {
      const res = await fetch(apiUrl(`/plans/${USER_ID}/preview`), { method: "POST" });
      if (res.ok) setGenerated(true);
      else setError("Plan preview failed");
    } catch { setError("Could not reach Stride"); } finally {
      setGenerating(false);
    }
  }

  if (saved) {
    return (
      <div className="space-y-3 text-sm">
        <p className="font-medium">Goal saved.</p>
        <p className="text-muted-foreground">
          Your current plan was built for the old goal. Generate a new 2-week block so it follows the new phases.
        </p>
        <div className="flex flex-wrap gap-2">
          {generated ? (
            <Link href="/plan" className={buttonVariants({ size: "sm" })}>
              Review new block
            </Link>
          ) : (
            <Button size="sm" onClick={regenerate} disabled={generating}>
              {generating ? "Generating…" : "Preview new block"}
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={onSaved}>
            Done
          </Button>
        </div>
        {error && <p className="text-destructive">{error}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-4 text-sm">
      <div className="space-y-1.5">
        <Label htmlFor="goal-type">Goal type</Label>
        <select id="goal-type" className={selectClass} value={goalType} onChange={(e) => setGoalType(e.target.value)}>
          <option value="race">Race</option>
          <option value="mileage">Build weekly mileage</option>
          <option value="general">General fitness</option>
          <option value="comeback">Return from injury / break</option>
        </select>
      </div>

      {goalType === "race" && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="goal-distance">Distance</Label>
              <select
                id="goal-distance"
                className={selectClass}
                value={distance}
                onChange={(e) => setDistance(e.target.value)}
              >
                {DISTANCES.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="goal-date">Race date</Label>
              <Input id="goal-date" type="date" value={raceDate} onChange={(e) => setRaceDate(e.target.value)} />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Goal time (optional)</Label>
            <div className="flex items-center gap-2">
              <Input aria-label="hours" inputMode="numeric" placeholder="h" value={hours} onChange={(e) => setHours(e.target.value)} />
              <span>:</span>
              <Input aria-label="minutes" inputMode="numeric" placeholder="mm" value={minutes} onChange={(e) => setMinutes(e.target.value)} />
              <span>:</span>
              <Input aria-label="seconds" inputMode="numeric" placeholder="ss" value={seconds} onChange={(e) => setSeconds(e.target.value)} />
            </div>
          </div>

          {ultra && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="goal-terrain">Terrain</Label>
                <select
                  id="goal-terrain"
                  className={selectClass}
                  value={terrain}
                  onChange={(e) => setTerrain(e.target.value)}
                >
                  <option value="road">Road / flat</option>
                  <option value="trail">Runnable trail</option>
                  <option value="mountain">Mountain</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="goal-vert">Total climbing (ft)</Label>
                <Input id="goal-vert" inputMode="numeric" placeholder="e.g. 18000" value={vert} onChange={(e) => setVert(e.target.value)} />
              </div>
            </div>
          )}
        </>
      )}

      {goalType === "mileage" && (
        <div className="space-y-1.5">
          <Label htmlFor="goal-mileage">Target miles per week</Label>
          <Input id="goal-mileage" inputMode="numeric" value={mileage} onChange={(e) => setMileage(e.target.value)} />
        </div>
      )}

      {readiness && !readiness.ready && (
        <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          <p className="font-medium">This goal looks like a stretch right now:</p>
          <ul className="list-disc space-y-1 pl-5">
            {readiness.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          {readiness.suggestion && <p>{readiness.suggestion}</p>}
          <Button size="sm" variant="outline" onClick={() => save(true)} disabled={saving}>
            Set it anyway
          </Button>
        </div>
      )}

      {error && <p className="text-destructive">{error}</p>}

      <div className="flex gap-2">
        <Button size="sm" onClick={() => save(false)} disabled={saving || (goalType === "race" && !raceDate)}>
          {saving ? "Saving…" : "Save goal"}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
      {goalType === "race" && !raceDate && (
        <p className="text-xs text-muted-foreground">Pick a race date so the plan can build base → peak → taper.</p>
      )}
    </div>
  );
}
