"use client";

import { useEffect, useState } from "react";
import { apiUrl, getJson, USER_ID } from "@/lib/api";
import { useGarminStatus } from "@/components/garmin-sync";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { OnboardingLayout } from "@/components/onboarding/onboarding-layout";
import { DayPicker } from "@/components/onboarding/day-picker";
import { GoalCards } from "@/components/onboarding/goal-card";
import { PRInput, type PREntry } from "@/components/onboarding/pr-input";
import type { GoalType, RaceDistance } from "@/lib/types";

const TOTAL_STEPS = 8;
// DayPicker numbers days Sunday = 0 (JS convention); the backend stores names
const PICKER_DAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];

function toSeconds(h: string, m: string, s: string): number | null {
  const total = (Number(h) || 0) * 3600 + (Number(m) || 0) * 60 + (Number(s) || 0);
  return total > 0 ? total : null;
}

interface Readiness {
  ready: boolean;
  reasons: string[];
  suggestion: string | null;
}

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);

  // Step 1: About you
  const [age, setAge] = useState("21");
  const [units, setUnits] = useState<"miles" | "kilometers">("miles");
  const [workoutFormat, setWorkoutFormat] = useState<"distance" | "time">("distance");

  // Step 2: Running background
  const [yearsRunning, setYearsRunning] = useState("2");
  const [currentMileage, setCurrentMileage] = useState([42]);
  const [peakMileage, setPeakMileage] = useState([65]);

  // Step 3: Race history
  const [prs, setPrs] = useState<PREntry[]>([
    { distance: "", hours: "", minutes: "", seconds: "" },
  ]);

  // Step 4: Availability
  const [daysPerWeek, setDaysPerWeek] = useState([6]);
  const [restDays, setRestDays] = useState<number[]>([5]);
  const [longRunDay, setLongRunDay] = useState<number[]>([6]);

  // Step 5: Goal
  const [goalType, setGoalType] = useState<GoalType | null>(null);
  const [raceDistance, setRaceDistance] = useState<RaceDistance | "">("");
  const [targetHours, setTargetHours] = useState("");
  const [targetMinutes, setTargetMinutes] = useState("");
  const [targetSeconds, setTargetSeconds] = useState("");
  const [raceDate, setRaceDate] = useState("");
  const [targetMileage, setTargetMileage] = useState([50]);

  // Step 6: Garmin
  const garmin = useGarminStatus();
  const garminConnected = !!garmin?.tokens_present;

  function next() {
    if (step < TOTAL_STEPS - 1) setStep(step + 1);
  }
  function back() {
    if (step > 0) setStep(step - 1);
  }

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);

  // Re-running setup starts from what's already saved
  useEffect(() => {
    getJson<{
      age: number | null; units: string; workout_format?: string; years_running: number | null;
      current_weekly_mileage: number | null; peak_weekly_mileage: number | null;
      days_per_week: number; rest_days: string | null; long_run_day?: string | null;
    }>(`/users/${USER_ID}`).then((u) => {
      if (!u) return;
      if (u.age) setAge(String(u.age));
      setUnits(u.units === "km" ? "kilometers" : "miles");
      if (u.workout_format === "time" || u.workout_format === "distance") setWorkoutFormat(u.workout_format);
      if (u.years_running != null) setYearsRunning(String(u.years_running));
      if (u.current_weekly_mileage) setCurrentMileage([u.current_weekly_mileage]);
      if (u.peak_weekly_mileage) setPeakMileage([u.peak_weekly_mileage]);
      if (u.days_per_week) setDaysPerWeek([u.days_per_week]);
      if (u.rest_days) setRestDays(u.rest_days.split(",").map((d) => PICKER_DAYS.indexOf(d.trim())).filter((i) => i >= 0));
      if (u.long_run_day) setLongRunDay([PICKER_DAYS.indexOf(u.long_run_day)].filter((i) => i >= 0));
    });
  }, []);

  async function send(path: string, method: string, body?: unknown) {
    const res = await fetch(apiUrl(path), {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    return { res, data };
  }

  /** Profile → goal → first plan. Each step is safe to retry (profile is an
   * idempotent update of this athlete; a new goal replaces the active one; plan
   * generation replaces the active plan atomically). */
  async function handleFinish(overrideReadiness = false) {
    setSaving(true);
    setSaveError(null);
    try {
      const prSeconds: Record<string, number> = {};
      for (const p of prs) {
        const t = toSeconds(p.hours, p.minutes, p.seconds);
        if (p.distance && t) prSeconds[`pr_${p.distance === "half" ? "half" : p.distance}_seconds`] = t;
      }
      const profile = await send(`/users/${USER_ID}/profile`, "PUT", {
        age: Number(age) || null,
        units: units === "kilometers" ? "km" : "miles",
        workout_format: workoutFormat,
        years_running: Number(yearsRunning) || 0,
        current_weekly_mileage: currentMileage[0],
        peak_weekly_mileage: peakMileage[0],
        days_per_week: daysPerWeek[0],
        rest_days: restDays.map((i) => PICKER_DAYS[i]),
        long_run_day: PICKER_DAYS[longRunDay[0] ?? 6],
        ...prSeconds,
      });
      if (!profile.res.ok) throw new Error(typeof profile.data.detail === "string" ? profile.data.detail : "Couldn't save your profile");

      const goal = await send(`/users/${USER_ID}/goal`, "POST", {
        goal_type: goalType,
        race_distance: goalType === "race" ? raceDistance || null : null,
        target_time_seconds: goalType === "race" ? toSeconds(targetHours, targetMinutes, targetSeconds) : null,
        race_date: goalType === "race" && raceDate ? raceDate : null,
        target_weekly_mileage: goalType === "mileage" ? targetMileage[0] : null,
        override_readiness: overrideReadiness,
      });
      if (goal.res.status === 409 && goal.data.detail?.readiness) {
        setReadiness(goal.data.detail.readiness);
        return;
      }
      if (!goal.res.ok) throw new Error(typeof goal.data.detail === "string" ? goal.data.detail : "Couldn't save your goal");

      const plan = await send(`/plans/${USER_ID}/generate`, "POST", {});
      if (!plan.res.ok) {
        throw new Error(
          typeof plan.data.detail === "string" ? plan.data.detail : "Saved your profile and goal, but the plan couldn't be generated",
        );
      }
      router.push("/plan");
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setSaving(false);
    }
  }

  if (step === 0) {
    return (
      <OnboardingLayout
        step={step}
        totalSteps={TOTAL_STEPS}
        title="Welcome to Stride"
        subtitle="Let's build your training plan. This takes about 2 minutes."
        onNext={next}
        onBack={back}
      >
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <h2 className="text-4xl font-bold tracking-tight">STRIDE</h2>
          <p className="mt-3 max-w-xs text-muted-foreground">
            Your AI running coach. Simple workouts, specific to your goals, backed by data.
          </p>
        </div>
      </OnboardingLayout>
    );
  }

  if (step === 1) {
    return (
      <OnboardingLayout
        step={step}
        totalSteps={TOTAL_STEPS}
        title="About You"
        onNext={next}
        onBack={back}
        nextDisabled={!age}
      >
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="age">Age</Label>
            <Input
              id="age"
              type="number"
              value={age}
              onChange={(e) => setAge(e.target.value)}
              className="w-24 font-mono"
              min={13}
              max={99}
            />
          </div>
          <div className="space-y-2">
            <Label>Preferred units</Label>
            <div className="flex gap-2">
              <Button
                variant={units === "miles" ? "default" : "outline"}
                size="sm"
                onClick={() => setUnits("miles")}
              >
                Miles
              </Button>
              <Button
                variant={units === "kilometers" ? "default" : "outline"}
                size="sm"
                onClick={() => setUnits("kilometers")}
              >
                Kilometers
              </Button>
            </div>
          </div>
          <div className="space-y-2">
            <Label>Workout format</Label>
            <div className="flex gap-2">
              <Button
                variant={workoutFormat === "distance" ? "default" : "outline"}
                size="sm"
                onClick={() => setWorkoutFormat("distance")}
              >
                Distance (6x800m)
              </Button>
              <Button
                variant={workoutFormat === "time" ? "default" : "outline"}
                size="sm"
                onClick={() => setWorkoutFormat("time")}
              >
                Time (6x2:30)
              </Button>
            </div>
          </div>
        </div>
      </OnboardingLayout>
    );
  }

  if (step === 2) {
    return (
      <OnboardingLayout
        step={step}
        totalSteps={TOTAL_STEPS}
        title="Running Background"
        onNext={next}
        onBack={back}
      >
        <div className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="years">Years running</Label>
            <Input
              id="years"
              type="number"
              value={yearsRunning}
              onChange={(e) => setYearsRunning(e.target.value)}
              className="w-24 font-mono"
              min={0}
              max={50}
            />
          </div>
          <div className="space-y-2">
            <Label>
              Current weekly mileage:{" "}
              <span className="font-mono font-semibold">{currentMileage[0]} mi</span>
            </Label>
            <Slider
              value={currentMileage}
              onValueChange={(v) => setCurrentMileage(Array.isArray(v) ? [...v] : [v])}
              min={0}
              max={120}
              step={1}
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>0 (not running)</span>
              <span>120+</span>
            </div>
          </div>
          <div className="space-y-2">
            <Label>
              Peak weekly mileage ever:{" "}
              <span className="font-mono font-semibold">{peakMileage[0]} mi</span>
            </Label>
            <Slider
              value={peakMileage}
              onValueChange={(v) => setPeakMileage(Array.isArray(v) ? [...v] : [v])}
              min={0}
              max={150}
              step={1}
            />
          </div>
        </div>
      </OnboardingLayout>
    );
  }

  if (step === 3) {
    return (
      <OnboardingLayout
        step={step}
        totalSteps={TOTAL_STEPS}
        title="Race History"
        subtitle="Add your PRs. Approximate times are fine. You can skip this."
        onNext={next}
        onBack={back}
      >
        <PRInput entries={prs} onChange={setPrs} />
      </OnboardingLayout>
    );
  }

  if (step === 4) {
    return (
      <OnboardingLayout
        step={step}
        totalSteps={TOTAL_STEPS}
        title="Availability"
        onNext={next}
        onBack={back}
      >
        <div className="space-y-6">
          <div className="space-y-2">
            <Label>
              Days per week:{" "}
              <span className="font-mono font-semibold">{daysPerWeek[0]}</span>
            </Label>
            <Slider
              value={daysPerWeek}
              onValueChange={(v) => setDaysPerWeek(Array.isArray(v) ? [...v] : [v])}
              min={3}
              max={7}
              step={1}
            />
          </div>
          <DayPicker
            selected={restDays}
            onChange={setRestDays}
            label="Preferred rest days (tap to toggle)"
          />
          <DayPicker
            selected={longRunDay}
            onChange={setLongRunDay}
            label="Preferred long run day"
            single
          />
        </div>
      </OnboardingLayout>
    );
  }

  if (step === 5) {
    return (
      <OnboardingLayout
        step={step}
        totalSteps={TOTAL_STEPS}
        title="What's Your Goal?"
        onNext={next}
        onBack={back}
        nextDisabled={!goalType}
      >
        <div className="space-y-4">
          <GoalCards selected={goalType} onChange={setGoalType} />

          {goalType === "race" && (
            <div className="space-y-4 rounded-md border p-4">
              <div className="space-y-2">
                <Label>Distance</Label>
                <Select
                  value={raceDistance}
                  onValueChange={(v) => setRaceDistance(v as RaceDistance)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select distance" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="5k">5K</SelectItem>
                    <SelectItem value="10k">10K</SelectItem>
                    <SelectItem value="half">Half Marathon</SelectItem>
                    <SelectItem value="marathon">Marathon</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Target time</Label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    placeholder="H"
                    className="w-16 font-mono"
                    value={targetHours}
                    onChange={(e) => setTargetHours(e.target.value)}
                  />
                  <span>:</span>
                  <Input
                    type="number"
                    placeholder="MM"
                    className="w-16 font-mono"
                    value={targetMinutes}
                    onChange={(e) => setTargetMinutes(e.target.value)}
                  />
                  <span>:</span>
                  <Input
                    type="number"
                    placeholder="SS"
                    className="w-16 font-mono"
                    value={targetSeconds}
                    onChange={(e) => setTargetSeconds(e.target.value)}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="raceDate">Race date</Label>
                <Input
                  id="raceDate"
                  type="date"
                  value={raceDate}
                  onChange={(e) => setRaceDate(e.target.value)}
                  className="w-44 font-mono"
                />
              </div>
            </div>
          )}

          {goalType === "mileage" && (
            <div className="space-y-2 rounded-md border p-4">
              <Label>
                Target weekly mileage:{" "}
                <span className="font-mono font-semibold">
                  {targetMileage[0]} mi/week
                </span>
              </Label>
              <Slider
                value={targetMileage}
                onValueChange={(v) => setTargetMileage(Array.isArray(v) ? [...v] : [v])}
                min={10}
                max={120}
                step={5}
              />
            </div>
          )}
        </div>
      </OnboardingLayout>
    );
  }

  if (step === 6) {
    return (
      <OnboardingLayout
        step={step}
        totalSteps={TOTAL_STEPS}
        title="Connect Garmin"
        subtitle="We'll pull your run history from Garmin Connect to understand your fitness level."
        onNext={next}
        onBack={back}
      >
        <div className="flex flex-col items-center gap-4 py-8">
          {garminConnected ? (
            <div className="text-center">
              <div className="text-lg font-semibold text-foreground">
                Connected{garmin?.display_name ? ` as ${garmin.display_name}` : ""}
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                Your Garmin runs sync automatically — new activities show up a few minutes after upload.
              </p>
            </div>
          ) : (
            <>
              <div className="w-full max-w-sm space-y-2 rounded-md bg-secondary/40 p-4 text-sm">
                <p className="font-medium">On your computer, run:</p>
                <pre className="overflow-x-auto rounded bg-background p-2 text-xs">
                  cd backend{"\n"}venv/bin/python garmin_login.py
                </pre>
                <p className="text-muted-foreground">Sign in with your Garmin account there, then reload this page.</p>
              </div>
              <button
                className="text-sm text-muted-foreground underline underline-offset-2"
                onClick={next}
              >
                Skip — I&apos;ll enter data manually
              </button>
            </>
          )}
        </div>
      </OnboardingLayout>
    );
  }

  // Step 7: Review
  return (
    <OnboardingLayout
      step={step}
      totalSteps={TOTAL_STEPS}
      title="Review"
      subtitle="Everything look good? We'll generate your first 2-week plan."
      onNext={() => handleFinish(false)}
      onBack={back}
      nextLabel={saving ? "Building your plan…" : saveError ? "Try again" : "Generate My Plan"}
      nextDisabled={saving || !goalType || (goalType === "race" && !raceDistance)}
    >
      <div className="space-y-3 text-sm">
        {saveError && (
          <p role="alert" className="rounded-md bg-destructive/10 p-2 text-destructive">
            {saveError}. Your answers are still here; tap Try again.
          </p>
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
            <Button size="sm" variant="outline" onClick={() => handleFinish(true)} disabled={saving}>
              Set it anyway
            </Button>
          </div>
        )}
        <ReviewRow label="Age" value={age} />
        <ReviewRow label="Units" value={units === "miles" ? "Miles" : "Kilometers"} />
        <ReviewRow label="Format" value={workoutFormat === "distance" ? "Distance-based" : "Time-based"} />
        <ReviewRow label="Years running" value={yearsRunning} />
        <ReviewRow label="Current mileage" value={`${currentMileage[0]} mi/week`} />
        <ReviewRow label="Peak mileage" value={`${peakMileage[0]} mi/week`} />
        <ReviewRow label="Days per week" value={String(daysPerWeek[0])} />
        <ReviewRow
          label="Goal"
          value={
            goalType === "race"
              ? `${raceDistance?.toUpperCase()}${toSeconds(targetHours, targetMinutes, targetSeconds) ? ` in ${targetHours || "0"}:${(targetMinutes || "0").padStart(2, "0")}:${(targetSeconds || "0").padStart(2, "0")}` : ""}`
              : goalType === "mileage"
                ? `${targetMileage[0]} mi/week`
                : goalType === "general" ? "General fitness" : goalType === "comeback" ? "Return from injury/break" : "Not set"
          }
        />
        <ReviewRow label="Garmin" value={garminConnected ? "Connected" : "Not connected"} />
      </div>
    </OnboardingLayout>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded px-2 py-1.5 odd:bg-secondary/30">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
