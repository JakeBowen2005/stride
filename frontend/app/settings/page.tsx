"use client";
import { TimeAvailability } from "@/components/time-availability";
import { FitImport } from "@/components/fit-import";
import { AccountSettings } from "@/components/account-settings";

import { scheduleChanged, type SchedulePreferences } from "@/lib/plan-preferences";
import Link from "next/link";
import { apiUrl, USER_ID } from "@/lib/api";
import { useState, useEffect } from "react";
import { ProfilePreferences } from "@/components/profile-preferences";
import { GoalEditor } from "@/components/goal-editor";
import { GarminConnectionCard } from "@/components/garmin-connection-card";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";


interface PR {
  id: number;
  distance: string;
  time_formatted: string;
  pace_per_mile: string;
  date: string | null;
}

interface Workload { acute_week_start?: string; acute_week_end?: string; acute_miles?: number; chronic_week_starts?: string[]; baseline_miles?: number; ratio?: number | null; label?: string; as_of?: string }
interface Operations { ai_usage?:{attempts_today:number;input_tokens_today:number;output_tokens_today:number;mean_latency_ms:number|null}; queue: { queued: number; running: number; failed: number; oldest_queued_at: string | null }; backup: { configured: boolean; offsite_configured: boolean; last_success_at: string | null; restore_verified: boolean; offsite_last_success_at?: string | null; offsite_error_type?: string | null; last_error_type: string | null; storage?:{database_bytes:number;backup_bytes:number;free_bytes:number;warning:boolean;budget_exceeded?:boolean} }; app: { policy_version: string } }
interface AnalysisData {
  workload?: Workload;
  overview: {
    total_runs: number;
    total_miles: number;
    total_hours: number;
    running_since: string;
    experience_level: string;
  };
  current_fitness: {
    weekly_mileage_4w_avg: number;
    weekly_mileage_8w_avg: number;
    peak_weekly_mileage: number;
    peak_week_date: string;
    runs_per_week: number;
  };
  paces: {
    easy_pace: string;
    recent_easy_pace: string;
    workout_pace_estimate: string;
    fastest_pace_ever: string;
  };
  long_runs: {
    longest_run_miles: number;
    longest_run_date: string;
    long_runs_10plus: number;
  };
  injury_risk: Workload & {
    acute_chronic_ratio: number;
    assessment: string;
  };
}

interface UserData {
  name: string | null;
  age: number | null;
  experience_level?: string | null;
  units: string;
  workout_format?: string;
  days_per_week: number;
  rest_days: string | null;
  long_run_day?: string | null;
}

interface GoalData {
  description: string;
  type: string;
  distance: string | null;
  target_time: number | null;
  race_date: string | null;
  terrain?: string | null;
  elevation_gain_ft?: number | null;
  target_weekly_mileage?: number | null;
}



export default function SettingsPage() {
  const [approvedSchedule, setApprovedSchedule] = useState<SchedulePreferences | undefined>(undefined);
  const [operations, setOperations] = useState<Operations | null>(null);
  const [prs, setPrs] = useState<PR[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [goal, setGoal] = useState<GoalData | null>(null);
  const [user, setUser] = useState<UserData | null>(null);
  const [editingGoal, setEditingGoal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [prRes, analysisRes, goalRes, userRes, planRes, operationsRes] = await Promise.all([
          fetch(apiUrl(`/analysis/${USER_ID}/prs`)),
          fetch(apiUrl(`/analysis/${USER_ID}/baseline`)),
          fetch(apiUrl(`/plans/${USER_ID}/goal`)),
          fetch(apiUrl(`/users/${USER_ID}`)),
          fetch(apiUrl(`/plans/${USER_ID}/current`)).catch(() => null),
          fetch(apiUrl(`/analysis/${USER_ID}/operations`)).catch(() => null),
        ]);

        if (![prRes, analysisRes, goalRes, userRes].every((r) => r.ok)) throw new Error("Could not load settings. Reload to retry.");
        if (planRes?.ok) setApprovedSchedule((await planRes.json()).athlete?.schedule_preferences);
        if (operationsRes?.ok) setOperations(await operationsRes.json());
        if (prRes.ok) setPrs(await prRes.json());
        if (userRes.ok) setUser(await userRes.json());
        if (analysisRes.ok) setAnalysis(await analysisRes.json());
        if (goalRes.ok) {
          const data = await goalRes.json();
          if (data) setGoal(data);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load data");
        console.error("Failed to load settings data:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (error) return <p role="alert" className="text-destructive">{error}</p>;

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold">Settings</h1>
        <div className="py-20 text-center text-muted-foreground">Loading...</div>
      </div>
    );
  }

  const unit = user?.units === 'km' ? 'km' : 'mi';
  const distance = (miles: number) => (miles * (unit === 'km' ? 1.60934 : 1)).toFixed(1);
  const workload = analysis?.workload ?? analysis?.injury_risk;
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between"><h1 className="text-xl font-semibold">Settings</h1><form action="/auth/logout" method="post"><Button type="submit" variant="outline" size="sm">Sign out</Button></form></div>
      {user && scheduleChanged(approvedSchedule, user) && <p role="status" className="rounded-md border p-3 text-sm">Your preferences have changed since this block was approved. <Link href="/plan" className="underline">Review a revised block</Link> to apply the new schedule. Your current sessions keep their approved schedule.</p>}

      {/* Profile */}
      <Card>
        <CardContent className="space-y-4 pt-4">
          {user && <ProfilePreferences user={user} onSaved={setUser} />}
        </CardContent>
      </Card>

      {/* Training Preferences */}
      <Card>
        <CardContent className="space-y-4 pt-4">
          <h2 className="text-sm font-medium">Training</h2>
          <div className="space-y-2 text-sm">
            <Row
              label="Latest baseline (four completed calendar weeks)"
              value={analysis ? `${distance(analysis.current_fitness.weekly_mileage_4w_avg)} ${unit}/week` : "—"}
            />
            <Row
              label="Peak mileage"
              value={
                analysis
                  ? `${distance(analysis.current_fitness.peak_weekly_mileage)} ${unit}/week (${analysis.current_fitness.peak_week_date})`
                  : "—"
              }
            />
            <Row
              label="Experience"
              value={user?.experience_level || analysis?.overview.experience_level || "—"}
            />
          </div>
        </CardContent>
      </Card>

      {/* Current Goal */}
      <Card>
        <CardContent className="space-y-4 pt-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium">Current Goal</h2>
            {!editingGoal && (
              <Button variant="outline" size="sm" onClick={() => setEditingGoal(true)}>
                Change
              </Button>
            )}
          </div>
          {editingGoal ? (
            <GoalEditor
              initial={goal}
              onCancel={() => setEditingGoal(false)}
              onSaved={() => window.location.reload()}
            />
          ) : (
            <div className="text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">
                  {goal ? goal.description : "No goal set"}
                </span>
                {goal?.race_date && (
                  <>
                    <span className="text-muted-foreground">&middot;</span>
                    <span className="text-muted-foreground">Race: {goal.race_date}</span>
                  </>
                )}
                {goal && goal.type === "race" && !goal.race_date && (
                  <>
                    <span className="text-muted-foreground">&middot;</span>
                    <span className="text-muted-foreground">No race date — add one to get base → peak → taper</span>
                  </>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Personal Records */}
      <Card>
        <CardContent className="space-y-4 pt-4">
          <h2 className="text-sm font-medium">Personal Records</h2>
          <div className="space-y-1 text-sm">
            {prs.map((pr) => (
              <div
                key={pr.id}
                className="flex items-center justify-between rounded px-2 py-1.5 odd:bg-secondary/30"
              >
                <span>{pr.distance}</span>
                <div className="flex items-center gap-3">
                  <span className="font-mono font-medium">{pr.time_formatted}</span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {pr.pace_per_mile}
                  </span>
                  {pr.date && (
                    <span className="text-xs text-muted-foreground">
                      {new Date(pr.date).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })}
                    </span>
                  )}
                </div>
              </div>
            ))}
            {prs.length === 0 && (
              <p className="text-muted-foreground">
                No PRs detected yet. Run a sync first.
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Running Stats */}
      {analysis && (
        <Card>
          <CardContent className="space-y-4 pt-4">
            <h2 className="text-sm font-medium">Running Stats</h2>
            <div className="space-y-2 text-sm">
              <Row label="Total runs" value={String(analysis.overview.total_runs)} />
              <Row label="Total distance" value={`${distance(analysis.overview.total_miles)} ${unit}`} />
              <Row label="Total hours" value={`${analysis.overview.total_hours} hrs`} />
              <Row label="Running since" value={analysis.overview.running_since} />
              <Row label="Runs per week" value={String(analysis.current_fitness.runs_per_week)} />
              <Row
                label="Longest run"
                value={`${distance(analysis.long_runs.longest_run_miles)} ${unit} (${analysis.long_runs.longest_run_date})`}
              />
              <Row
                label="10+ mile runs"
                value={String(analysis.long_runs.long_runs_10plus)}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Injury Risk */}
      {analysis && (
        <Card>
          <CardContent className="space-y-4 pt-4">
            <h2 className="text-sm font-medium">Training load · Stride policy heuristic</h2>
            <div className="space-y-2 text-sm">
              <Row
                label="Last completed week / four completed weeks"
                value={workload?.ratio == null ? "Not enough baseline evidence" : String(workload.ratio)}
              />
              <p className="text-xs text-muted-foreground">
                {workload?.acute_week_start && <>Week {workload.acute_week_start}–{workload.acute_week_end}: {distance(workload.acute_miles ?? 0)} {unit}; four-week baseline (including that week): {distance(workload.baseline_miles ?? 0)} {unit}/week. As of {workload.as_of}. </>}This compares running distance, not injury probability. Garmin Load uses a different intensity-weighted measure. A low ratio does not establish that increasing training is safe.
              </p>
              <div className="rounded-md bg-secondary/50 p-2 text-sm text-muted-foreground">
                {analysis.injury_risk.assessment}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Card><CardContent className="space-y-3 pt-4"><h2 className="text-sm font-medium">Operations</h2>
        {!operations ? <p className="text-sm text-muted-foreground">Operational status is unavailable. Backup and review status could not be verified.</p> : <>
          {operations.ai_usage && <p className="text-sm">AI today: {operations.ai_usage.attempts_today} attempts · {operations.ai_usage.input_tokens_today} input / {operations.ai_usage.output_tokens_today} output tokens{operations.ai_usage.mean_latency_ms!=null?` · mean ${(operations.ai_usage.mean_latency_ms/1000).toFixed(1)} seconds`:''}.</p>}
          {operations.backup.storage && <p role={operations.backup.storage.warning?'alert':undefined} className="text-sm">Storage: {(operations.backup.storage.database_bytes/1024**2).toFixed(1)} MiB database · {(operations.backup.storage.backup_bytes/1024**2).toFixed(1)} MiB local backups · {(operations.backup.storage.free_bytes/1024**3).toFixed(1)} GiB free.{operations.backup.storage.warning?' Low free space: operator attention needed.':''}</p>}
          <p className="text-sm">Coaching jobs: {operations.queue.queued} queued · {operations.queue.running} running · {operations.queue.failed} failed{operations.queue.oldest_queued_at ? ` · oldest queued ${operations.queue.oldest_queued_at}` : ""}</p>
          <p className="text-sm">Local backups: {operations.backup.configured ? "configured" : "not configured"}. Offsite export: {operations.backup.offsite_configured ? "configured" : "not configured"}.</p>
          <p className="text-xs text-muted-foreground">Last successful backup: {operations.backup.last_success_at ?? "none reported"}. Restore verification: {operations.backup.restore_verified ? "passed for the last successful backup" : "not verified"}.{operations.backup.last_error_type ? ` Last backup error: ${operations.backup.last_error_type}.` : ""}</p>
          <p className="text-xs text-muted-foreground">Last successful offsite export: {operations.backup.offsite_last_success_at ?? "none verified"}.{operations.backup.offsite_error_type ? ` Offsite export error: ${operations.backup.offsite_error_type}.` : ""}</p>
          <p className="text-xs text-muted-foreground">Configuration alone does not prove recovery. Keep a verified offsite backup. Coaching policy {operations.app.policy_version}.</p>
        </>}
      </CardContent></Card>
      <TimeAvailability />
      <AccountSettings />
      {/* Connections */}
      <GarminConnectionCard />
      <FitImport />

    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  );
}
