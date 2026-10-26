"use client";

import { apiUrl, getJson, USER_ID } from "@/lib/api";
import { useState, useEffect } from "react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TrainingTrends } from "@/components/training-trends";
import { HistoryProfile } from "@/components/history-profile";
import { RunList } from "@/components/run-list";
import { RunDetailSheet } from "@/components/run-detail-sheet";
import { AerobicEfficiencyChartWrapper, MileageOverTimeChartWrapper } from "@/components/charts-wrapper";
import type { Activity } from "@/lib/types";


type FilterType = "all" | "workouts" | "long_runs" | "easy";

export default function HistoryPage() {
  const [revision, setRevision] = useState(0);
  const [filter, setFilter] = useState<FilterType>("all");
  const [selected, setSelected] = useState<Activity | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [hasMore,setHasMore]=useState(false);
  const [loadingMore,setLoadingMore]=useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const actRes = await fetch(apiUrl(`/analysis/${USER_ID}/activities?type=${filter}&limit=200`));

        if (!actRes.ok) throw new Error("Could not load history. Reload to retry.");
        if (actRes.ok) {
          const data = await actRes.json();
          setHasMore(data.length===200);
          setSelected(previous=>previous ? data.find((a:Activity)=>a.id===previous.id) || previous : null);
          setActivities(
            data.map((a: Record<string, unknown>) => ({
              ...a,
              splits: a.splits || [],
            }))
          );
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

  async function loadOlder(){
    const last=activities.at(-1);if(!last)return;
    setLoadingMore(true);
    try{const query=new URLSearchParams({type:filter,limit:"200",before_date:last.date,before_id:String(last.id)});
      const rows=await getJson<Activity[]>(`/analysis/${USER_ID}/activities?${query}`)||[];
      setHasMore(rows.length===200);setActivities(previous=>[...previous,...rows.filter(r=>!previous.some(a=>a.id===r.id))]);
    }catch{setError("Could not load older runs. Reload to retry.");}finally{setLoadingMore(false);}
  }

  if (error) return <p role="alert" className="glass p-5 text-destructive">{error}</p>;

  if (loading) {
    return (
      <div className="space-y-4">
        <h1 className="display pt-1">History</h1>
        <div className="glass flex items-center justify-center py-20 text-muted-foreground">
          Loading your runs...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="display pt-1">History</h1>

      <div className="grid items-start gap-4 lg:grid-cols-2">
      <HistoryProfile revision={revision} onInspect={async (id) => {
        const activity = await getJson<Activity>(`/analysis/${USER_ID}/activities/${id}`);
        if (activity) setSelected({ ...activity, splits: activity.splits || [] });
      }} />

      <TrainingTrends revision={revision} onInspect={async id=>{const a=await getJson<Activity>(`/analysis/${USER_ID}/activities/${id}`);if(a)setSelected({...a,splits:a.splits||[]});}} />
      </div>
      <MileageOverTimeChartWrapper revision={revision} />
      <AerobicEfficiencyChartWrapper revision={revision} />

      <div className="flex flex-wrap items-end justify-between gap-3 pt-2">
      <h2 className="text-lg font-bold tracking-tight">Runs</h2>
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
      </div>

      <RunList activities={activities} onSelect={setSelected} />

      {hasMore && <button className="glass lift min-h-11 rounded-full px-5 text-sm font-semibold" disabled={loadingMore} onClick={loadOlder}>{loadingMore?"Loading…":"Load older runs"}</button>}
      <RunDetailSheet
        activity={selected}
        open={!!selected}
        onClose={() => setSelected(null)}
        onClassificationChanged={() => setRevision(value => value + 1)}
      />
    </div>
  );
}
