"use client";

import { useState, useEffect } from "react";
import { GoalEditor } from "@/components/goal-editor";
import { GarminConnectionCard } from "@/components/garmin-connection-card";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const API = process.env.NEXT_PUBLIC_API_URL || "";

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
  const [editingGoal, setEditingGoal] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [prRes, analysisRes, goalRes] = await Promise.all([
          fetch(`${API}/api/analysis/1/prs`),
          fetch(`${API}/api/analysis/1/baseline`),
          fetch(`${API}/api/plans/1/goal`),
        ]);

        if (prRes.ok) setPrs(await prRes.json());
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
            <Row label="Name" value="Jake Bowen" />
            <Row label="Age" value="21" />
            <Row label="Units" value="Miles" />
            <Row label="Workout format" value="Distance-based" />
          </div>
        </CardContent>
      </Card>

      {/* Training Preferences */}
      <Card>
        <CardContent className="space-y-4 pt-4">
          <h2 className="text-sm font-medium">Training</h2>
          <div className="space-y-2 text-sm">
            <Row label="Days per week" value="6" />
            <Row label="Rest day" value="Sunday" />
            <Row label="Long run day" value="Saturday" />
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
                label="Acute:Chronic ratio"
                value={String(analysis.injury_risk.acute_chronic_ratio)}
              />
              <div className="rounded-md bg-secondary/50 p-2 text-sm text-muted-foreground">
                {analysis.injury_risk.assessment}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Connections */}
      <GarminConnectionCard />

      {/* Data */}
      <Card>
        <CardContent className="space-y-4 pt-4">
          <h2 className="text-sm font-medium">Data</h2>
          <div className="flex gap-2">
            <Button variant="outline" size="sm">
              Re-run Onboarding
            </Button>
          </div>
        </CardContent>
      </Card>
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
