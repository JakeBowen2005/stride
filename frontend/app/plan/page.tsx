"use client";

import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PlanWeek } from "@/components/plan-week";
import { formatDateShort } from "@/lib/format";
import type { PlanWeek as PlanWeekType, Workout } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ApiPlanDay {
  date: string;
  day: string;
  type: string;
  title: string;
  description: string;
  purpose: string;
  distance_miles: number;
  warmup: string | null;
  cooldown: string | null;
}

interface ApiPlan {
  start_date: string;
  end_date: string;
  block_number: number;
  is_deload: boolean;
  week1: { target_mileage: number; days: ApiPlanDay[] };
  week2: { target_mileage: number; days: ApiPlanDay[] };
  pacing_guide: Record<string, string>;
  notes: string[];
  goal: {
    type: string;
    distance: string;
    target_time: number | null;
    race_date: string | null;
    description: string;
  };
  athlete: {
    name: string;
    current_weekly_mileage: number;
    peak_weekly_mileage: number;
    experience_level: string;
    injury_risk: string;
  };
}

function mapApiToWeek(
  apiWeek: { target_mileage: number; days: ApiPlanDay[] },
  weekNum: number
): PlanWeekType {
  return {
    week_number: weekNum,
    total_miles: apiWeek.target_mileage,
    workouts: apiWeek.days.map((d, i) => ({
      id: weekNum * 100 + i,
      date: d.date,
      type: d.type === "workout" ? "threshold" : (d.type as Workout["type"]),
      title: d.title,
      description: d.description,
      purpose: d.purpose,
      distance_miles: d.distance_miles,
      warmup: d.warmup || undefined,
      cooldown: d.cooldown || undefined,
      completed: false,
      skipped: false,
    })),
  };
}

export default function PlanPage() {
  const [plan, setPlan] = useState<ApiPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch(`${API}/api/plans/1/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        if (!res.ok) {
          const data = await res.json();
          setError(data.detail || "Failed to generate plan");
          return;
        }
        setPlan(await res.json());
      } catch (e) {
        console.error("Failed to load plan:", e);
        setError("Failed to connect to server");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold">Current Plan</h1>
        <div className="py-20 text-center text-muted-foreground">
          Generating your plan...
        </div>
      </div>
    );
  }

  if (error || !plan) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold">Current Plan</h1>
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {error || "No plan available"}
          </CardContent>
        </Card>
      </div>
    );
  }

  const weeks: PlanWeekType[] = [
    mapApiToWeek(plan.week1, 1),
    mapApiToWeek(plan.week2, 2),
  ];

  const today = new Date().toISOString().split("T")[0];
  const currentWeekIndex = weeks.findIndex((w) =>
    w.workouts.some((wo) => wo.date >= today)
  );

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">Current Plan</h1>
          <Button variant="outline" size="sm">
            Regenerate
          </Button>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">
            {plan.goal.description}
          </span>
          <span>&middot;</span>
          <span>
            {formatDateShort(plan.start_date)} &ndash;{" "}
            {formatDateShort(plan.end_date)}
          </span>
          {plan.is_deload && (
            <>
              <span>&middot;</span>
              <Badge variant="secondary" className="text-xs">
                Deload
              </Badge>
            </>
          )}
        </div>
      </div>

      {/* Pacing Guide */}
      <Card>
        <CardContent className="pt-4">
          <h3 className="text-sm font-medium mb-2">Pacing Guide</h3>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Easy</span>
              <span className="font-mono">{plan.pacing_guide.easy}/mi</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tempo</span>
              <span className="font-mono">{plan.pacing_guide.current_tempo}/mi</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Threshold</span>
              <span className="font-mono">{plan.pacing_guide.current_threshold}/mi</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Intervals</span>
              <span className="font-mono">{plan.pacing_guide.current_interval}/mi</span>
            </div>
            {plan.pacing_guide.goal_race_pace && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Goal Race</span>
                <span className="font-mono">{plan.pacing_guide.goal_race_pace}/mi</span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {weeks.map((week, i) => (
        <PlanWeek
          key={week.week_number}
          week={week}
          isCurrent={i === (currentWeekIndex >= 0 ? currentWeekIndex : 0)}
        />
      ))}

      {plan.notes.length > 0 && (
        <Card>
          <CardContent className="pt-4">
            <h3 className="text-sm font-medium">Plan Notes</h3>
            <div className="mt-1 space-y-1">
              {plan.notes.map((note, i) => (
                <p key={i} className="text-sm leading-relaxed text-muted-foreground">
                  {note}
                </p>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
