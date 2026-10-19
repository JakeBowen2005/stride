"use client";

import { apiUrl, USER_ID } from "@/lib/api";
import { useState, useEffect } from "react";
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

interface AnalysisData {
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
  injury_risk: {
    acute_chronic_ratio: number;
    assessment: string;
  };
}

interface UserData {
  name: string | null;
  age: number | null;
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
  const [prs, setPrs] = useState<PR[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [goal, setGoal] = useState<GoalData | null>(null);
  const [user, setUser] = useState<UserData | null>(null);
  const [editingGoal, setEditingGoal] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [prRes, analysisRes, goalRes, userRes] = await Promise.all([
          fetch(apiUrl(`/analysis/${USER_ID}/prs`)),
          fetch(apiUrl(`/analysis/${USER_ID}/baseline`)),
          fetch(apiUrl(`/plans/${USER_ID}/goal`)),
          fetch(apiUrl(`/users/${USER_ID}`)),
        ]);

        if (prRes.ok) setPrs(await prRes.json());
        if (userRes.ok) setUser(await userRes.json());
        if (analysisRes.ok) setAnalysis(await analysisRes.json());
        if (goalRes.ok) {
          const data = await goalRes.json();
          if (data) setGoal(data);
        }
      } catch (e) {
        console.error("Failed to load settings data:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold">Settings</h1>
        <div className="py-20 text-center text-muted-foreground">Loading...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Settings</h1>

      {/* Profile */}
      <Card>
        <CardContent className="space-y-4 pt-4">
          <h2 className="text-sm font-medium">Profile</h2>
          <div className="space-y-2 text-sm">
            <Row label="Name" value={user?.name || "—"} />
            <Row label="Age" value={user?.age ? String(user.age) : "Not set"} />
            <Row label="Units" value={user?.units === "km" ? "Kilometers" : "Miles"} />
            <Row label="Workout format" value={user?.workout_format === "time" ? "Time-based" : "Distance-based"} />
          </div>
        </CardContent>
      </Card>

      {/* Training Preferences */}
      <Card>
        <CardContent className="space-y-4 pt-4">
          <h2 className="text-sm font-medium">Training</h2>
          <div className="space-y-2 text-sm">
            <Row label="Days per week" value={user ? String(user.days_per_week) : "—"} />
            <Row label="Rest day" value={titleList(user?.rest_days) || "None"} />
            <Row label="Long run day" value={titleList(user?.long_run_day) || "—"} />
            <Row
              label="Current mileage (4wk avg)"
              value={analysis ? `${analysis.current_fitness.weekly_mileage_4w_avg} mi/week` : "—"}
            />
            <Row
              label="Peak mileage"
              value={
                analysis
                  ? `${analysis.current_fitness.peak_weekly_mileage} mi/week (${analysis.current_fitness.peak_week_date})`
                  : "—"
              }
            />
            <Row
              label="Experience"
              value={analysis?.overview.experience_level || "—"}
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
              <Row label="Total miles" value={`${analysis.overview.total_miles} mi`} />
              <Row label="Total hours" value={`${analysis.overview.total_hours} hrs`} />
              <Row label="Running since" value={analysis.overview.running_since} />
              <Row label="Runs per week" value={String(analysis.current_fitness.runs_per_week)} />
              <Row
                label="Longest run"
                value={`${analysis.long_runs.longest_run_miles} mi (${analysis.long_runs.longest_run_date})`}
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
            <h2 className="text-sm font-medium">Injury Risk</h2>
            <div className="space-y-2 text-sm">
              <Row
                label="Stride mileage ratio (last week vs 4-week avg)"
                value={String(analysis.injury_risk.acute_chronic_ratio)}
              />
              <p className="text-xs text-muted-foreground">
                Based on miles. The &quot;Garmin Load&quot; tile on Today uses Garmin&apos;s training-load ratio, which weighs intensity, so the two can differ.
              </p>
              <div className="rounded-md bg-secondary/50 p-2 text-sm text-muted-foreground">
                {analysis.injury_risk.assessment}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Connections */}
      <GarminConnectionCard />

    </div>
  );
}

function titleList(csv?: string | null): string {
  return (csv || "")
    .split(",")
    .map((d) => d.trim())
    .filter(Boolean)
    .map((d) => d.charAt(0).toUpperCase() + d.slice(1))
    .join(", ");
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  );
}
