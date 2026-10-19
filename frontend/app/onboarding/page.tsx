"use client";

import { useState } from "react";
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

  function handleFinish() {
    // In production, POST to /api/onboarding
    router.push("/");
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
                    <SelectItem value="half_marathon">Half Marathon</SelectItem>
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
      onNext={handleFinish}
      onBack={back}
      nextLabel="Generate My Plan"
    >
      <div className="space-y-3 text-sm">
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
              ? `${raceDistance?.replace("_", " ").toUpperCase()} in ${targetHours || "0"}:${targetMinutes || "00"}:${targetSeconds || "00"}`
              : goalType === "mileage"
                ? `${targetMileage[0]} mi/week`
                : goalType?.replace("_", " ") || "Not set"
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
