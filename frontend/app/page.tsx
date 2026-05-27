"use client";

import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { WeeklyMileageChartWrapper } from "@/components/charts-wrapper";
import { formatDistance, formatDate, secondsToTime } from "@/lib/format";
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

  useEffect(() => {
    async function load() {
      try {
        const [actRes, mileageRes, goalRes, planRes] = await Promise.all([
          fetch(`${API}/api/analysis/1/activities?limit=20`),
          fetch(`${API}/api/analysis/1/weekly-mileage?weeks=8`),
          fetch(`${API}/api/plans/1/goal`),
          fetch(`${API}/api/plans/1/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
          }),
        ]);

        // Last 7 days of runs
        if (actRes.ok) {
          const data = await actRes.json();
          const sevenDaysAgo = new Date();
          sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
          const recent = data
            .map((a: Record<string, unknown>) => ({ ...a, splits: a.splits || [] }))
            .filter((a: Activity) => new Date(a.date) >= sevenDaysAgo);
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

        // Plan — extract next workout and next run
        if (planRes.ok) {
          const plan = await planRes.json();
          const today = new Date().toISOString().split("T")[0];
          const allDays: PlanDay[] = [
            ...(plan.week1?.days || []),
            ...(plan.week2?.days || []),
          ];
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
      <div className="flex items-baseline justify-between">
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

      {/* Hero stats */}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <CardContent className="pt-4 text-center">
            <div className="font-mono text-2xl font-bold">
              {formatDistance(lastWeekMiles)}
            </div>
            <div className="text-xs text-muted-foreground">last week mi</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 text-center">
            <div className="text-lg font-bold leading-tight">
              {goal ? goal.description : "No goal set"}
            </div>
            <div className="text-xs text-muted-foreground">
              {goal?.race_date ? `Race: ${goal.race_date}` : "current goal"}
            </div>
          </CardContent>
        </Card>
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

      <WeeklyMileageChartWrapper data={weeklyMileage} />

      {/* Last 7 Days */}
      <div>
        <h3 className="text-sm font-medium mb-2">Last 7 Days</h3>
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
