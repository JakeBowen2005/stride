"use client";

import { useState, useEffect, useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { WeeklyMileageChartWrapper } from "@/components/charts-wrapper";
import { DailyMileageChart } from "@/components/charts/daily-mileage-chart";
import { formatDistance, formatDate, secondsToTime, localDateStr } from "@/lib/format";
import type { Activity, WeeklyMileage } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface GoalData {
  description: string;
  distance: string;
  race_date: string | null;
}

interface PlanDay {
  date: string;
  day: string;
  type: string;
  title: string;
  description: string;
  distance_miles: number;
}

export default function TodayPage() {
  const [recentRuns, setRecentRuns] = useState<Activity[]>([]);
  const [weeklyMileage, setWeeklyMileage] = useState<WeeklyMileage[]>([]);
  const [lastWeekMiles, setLastWeekMiles] = useState<number>(0);
  const [goal, setGoal] = useState<GoalData | null>(null);
  const [nextWorkout, setNextWorkout] = useState<PlanDay | null>(null);
  const [nextRun, setNextRun] = useState<PlanDay | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);

  async function handleResync() {
    setSyncing(true);
    setSyncResult(null);
    try {
      const res = await fetch(`${API}/api/strava/sync/1`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setSyncResult(`Synced: ${data.new_activities} new runs imported.`);
        // Reload data after sync
        window.location.reload();
      } else {
        setSyncResult("Sync failed. Check your Strava connection.");
      }
    } catch {
      setSyncResult("Sync failed. Is the backend running?");
    } finally {
      setSyncing(false);
    }
  }

  useEffect(() => {
    async function load() {
      try {
        const [actRes, mileageRes, goalRes, planRes] = await Promise.all([
          fetch(`${API}/api/analysis/1/activities?limit=20`),
          fetch(`${API}/api/analysis/1/weekly-mileage?weeks=8`),
          fetch(`${API}/api/plans/1/goal`),
          fetch(`${API}/api/plans/1/current`),
        ]);

        // Last 7 days of runs
        if (actRes.ok) {
          const data = await actRes.json();
          const sevenDaysAgo = new Date();
          sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
          const recent = data
            .map((a: Record<string, unknown>) => ({ ...a, splits: a.splits || [] }))
            .filter((a: Activity) => {
              const safe = a.date.includes("T") ? a.date : `${a.date}T12:00:00`;
              return new Date(safe) >= sevenDaysAgo;
            });
          setRecentRuns(recent);
        }

        // Weekly mileage
        if (mileageRes.ok) {
          const data = await mileageRes.json();
          setWeeklyMileage(data.map((d: Record<string, unknown>) => ({ ...d, planned: 0 })));
          // Last completed week's mileage (second to last entry since current week is partial)
          if (data.length >= 2) {
            setLastWeekMiles(data[data.length - 2].actual);
          } else if (data.length === 1) {
            setLastWeekMiles(data[0].actual);
          }
        }

        // Goal
        if (goalRes.ok) {
          const data = await goalRes.json();
          if (data) setGoal(data);
        }

        // Plan — extract next workout and next run (GET /current, 404 = no plan yet)
        if (planRes.ok) {
          const plan = await planRes.json();
          const today = localDateStr();
          const allDays: PlanDay[] = plan.weeks?.flatMap((w: { days: PlanDay[] }) => w.days) || [];
          const upcoming = allDays.filter((d: PlanDay) => d.date >= today);
          const workout = upcoming.find(
            (d: PlanDay) => d.type === "workout" || d.type === "long_run"
          );
          const run = upcoming.find((d: PlanDay) => d.type !== "rest");
          if (workout) setNextWorkout(workout);
          if (run) setNextRun(run);
        }
      } catch (e) {
        console.error("Failed to load dashboard:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const today = new Date();
  const greeting =
    today.getHours() < 12
      ? "Good morning"
      : today.getHours() < 17
        ? "Good afternoon"
        : "Good evening";

  const notableWorkout = useMemo(() => {
    const notable = recentRuns.filter((run) => {
      const text = `${run.title || ""} ${run.description || ""}`.toLowerCase();
      return /\d+x\d+/.test(text) || /threshold|tempo|interval|fartlek|hill/.test(text);
    });
    if (notable.length === 0) return null;
    return notable
      .map((run) => {
        const text = run.title || run.description || "";
        const matches = text.match(/\d+x\d+\w*/gi);
        return matches ? matches.join(" + ") : run.title;
      })
      .join(", ");
  }, [recentRuns]);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold">{greeting}, Jake</h1>
        <div className="py-20 text-center text-muted-foreground">Loading your data...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">{greeting}, Jake</h1>
          <span className="text-sm text-muted-foreground">
            {today.toLocaleDateString("en-US", {
              weekday: "short",
              month: "short",
              day: "numeric",
              year: "numeric",
            })}
          </span>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={handleResync}
            disabled={syncing}
          >
            {syncing ? "Syncing..." : "Sync Strava"}
          </Button>
          {syncResult && (
            <span className="text-xs text-muted-foreground">{syncResult}</span>
          )}
        </div>
      </div>

      {/* Hero stats */}
      <div className="grid grid-cols-3 gap-3">
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground mb-1">Last Week</p>
          <Card>
            <CardContent className="pt-4 text-center">
              <div className="font-mono text-2xl font-bold">
                {formatDistance(lastWeekMiles)}
              </div>
              <div className="text-xs text-muted-foreground">miles</div>
              {notableWorkout && (
                <div className="mt-1.5 text-[10px] text-muted-foreground font-medium truncate">
                  {notableWorkout}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground mb-1">Current Goal</p>
          <Card>
            <CardContent className="pt-4 text-center">
              <div className="text-lg font-bold leading-tight">
                {goal ? goal.description : "No goal set"}
              </div>
              <div className="text-xs text-muted-foreground">
                {goal?.race_date ? `Race: ${goal.race_date}` : "\u00A0"}
              </div>
            </CardContent>
          </Card>
        </div>
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground mb-1">Next Workout</p>
          <Card>
            <CardContent className="pt-4 text-center">
              <div className="text-sm font-bold leading-tight">
                {nextWorkout ? nextWorkout.title : "—"}
              </div>
              <div className="text-xs text-muted-foreground">
                {nextWorkout
                  ? formatDate(nextWorkout.date)
                  : "no upcoming workout"}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Next Run Card */}
      {nextRun && (
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium">Next Run</h3>
              <Badge variant="secondary" className="text-xs capitalize">
                {nextRun.type === "workout" ? "Quality" : nextRun.type.replace("_", " ")}
              </Badge>
            </div>
            <div className="text-lg font-semibold">{nextRun.title}</div>
            <div className="text-sm text-muted-foreground mt-1">
              {formatDate(nextRun.date)} &middot; {formatDistance(nextRun.distance_miles)} mi
            </div>
            <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
              {nextRun.description}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Last 7 Days Chart */}
      {recentRuns.length > 0 && (
        <Card>
          <CardContent className="pt-4">
            <h3 className="text-sm font-medium mb-2">Last 7 Days</h3>
            <DailyMileageChart activities={recentRuns} />
          </CardContent>
        </Card>
      )}

      <WeeklyMileageChartWrapper data={weeklyMileage} />

      {/* Last 7 Days Listing */}
      <div>
        <h3 className="text-sm font-medium mb-2">Recent Runs</h3>
        {recentRuns.length > 0 ? (
          <div className="space-y-1.5">
            {recentRuns.map((run) => (
              <div
                key={run.id}
                className="flex items-center justify-between rounded-md border p-3"
              >
                <div className="flex items-center gap-3">
                  <div className="w-16 text-xs text-muted-foreground">
                    {formatDate(run.date)}
                  </div>
                  <span className="text-sm font-medium">{run.title}</span>
                </div>
                <div className="flex items-center gap-3 text-sm">
                  <span className="font-mono">
                    {formatDistance(run.distance_miles)} mi
                  </span>
                  <span className="font-mono text-muted-foreground">
                    {run.avg_pace}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {secondsToTime(run.duration_seconds)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="py-6 text-center text-muted-foreground">
              No runs in the last 7 days.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
