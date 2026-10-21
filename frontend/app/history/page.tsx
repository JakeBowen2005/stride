"use client";

import { apiUrl, USER_ID } from "@/lib/api";
import { useState, useEffect } from "react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RunList } from "@/components/run-list";
import { RunDetailSheet } from "@/components/run-detail-sheet";
import { MileageOverTimeChartWrapper } from "@/components/charts-wrapper";
import type { Activity, WeeklyMileage } from "@/lib/types";


type FilterType = "all" | "workouts" | "long_runs" | "easy";

export default function HistoryPage() {
  const [revision, setRevision] = useState(0);
  const [filter, setFilter] = useState<FilterType>("all");
  const [selected, setSelected] = useState<Activity | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [weeklyMileage, setWeeklyMileage] = useState<WeeklyMileage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [actRes, mileageRes] = await Promise.all([
          fetch(apiUrl(`/analysis/${USER_ID}/activities?type=${filter}&limit=200`)),
          fetch(apiUrl(`/analysis/${USER_ID}/weekly-mileage?weeks=16`)),
        ]);

        if (!actRes.ok || !mileageRes.ok) throw new Error("Could not load history. Reload to retry.");
        if (actRes.ok) {
          const data = await actRes.json();
          setActivities(
            data.map((a: Record<string, unknown>) => ({
              ...a,
              splits: a.splits || [],
            }))
          );
        }

        if (mileageRes.ok) {
          const data = await mileageRes.json();
          setWeeklyMileage(data.map((d: Record<string, unknown>) => ({ ...d, planned: 0 })));
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load data");
        console.error("Failed to load history:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [filter, revision]);

  if (error) return <p role="alert" className="text-destructive">{error}</p>;

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold">History</h1>
        <div className="flex items-center justify-center py-20 text-muted-foreground">
          Loading your runs...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">History</h1>

      <MileageOverTimeChartWrapper data={weeklyMileage} />

      <Tabs
        value={filter}
        onValueChange={(v) => setFilter(v as FilterType)}
      >
        <TabsList>
          <TabsTrigger value="all">All ({activities.length})</TabsTrigger>
          <TabsTrigger value="workouts">Workouts</TabsTrigger>
          <TabsTrigger value="long_runs">Long Runs</TabsTrigger>
          <TabsTrigger value="easy">Easy</TabsTrigger>
        </TabsList>
      </Tabs>

      <RunList activities={activities} onSelect={setSelected} />

      <RunDetailSheet
        activity={selected}
        open={!!selected}
        onClose={() => setSelected(null)}
        onClassificationChanged={() => setRevision(value => value + 1)}
      />
    </div>
  );
}
