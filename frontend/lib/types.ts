export type WorkoutType =
  | "easy"
  | "long_run"
  | "tempo"
  | "intervals"
  | "threshold"
  | "fartlek"
  | "hill_repeats"
  | "progression"
  | "recovery"
  | "time_trial"
  | "rest"
  | "strides";

export type GoalType = "race" | "mileage" | "general_fitness" | "return_from_injury";

export type RaceDistance = "5k" | "10k" | "half_marathon" | "marathon";

export type TrainingPhase = "base" | "build" | "peak" | "taper";

export interface User {
  id: number;
  age: number;
  preferred_units: "miles" | "kilometers";
  workout_format: "distance" | "time";
  days_per_week: number;
  rest_days: number[];
  long_run_day: number;
  current_weekly_mileage: number;
  peak_weekly_mileage: number;
  years_running: number;
  strava_connected: boolean;
  garmin_connected: boolean;
  onboarded: boolean;
}

export interface PersonalRecord {
  id: number;
  distance: RaceDistance;
  time_seconds: number;
  date?: string;
}

export interface Goal {
  id: number;
  type: GoalType;
  distance?: RaceDistance;
  target_time_seconds?: number;
  target_weekly_mileage?: number;
  race_date?: string;
}

export interface Workout {
  id: number;
  date: string;
  type: WorkoutType;
  title: string;
  description: string;
  purpose: string;
  distance_miles: number;
  target_pace?: string;
  warmup?: string;
  cooldown?: string;
  intervals?: string;
  completed: boolean;
  skipped: boolean;
}

export interface PlanWeek {
  week_number: number;
  total_miles: number;
  workouts: Workout[];
}

export interface Plan {
  id: number;
  start_date: string;
  end_date: string;
  phase: TrainingPhase;
  goal_summary: string;
  notes: string;
  weeks: PlanWeek[];
  approved: boolean;
}

export interface Activity {
  id: number;
  strava_id?: number;
  date: string;
  type: WorkoutType;
  title: string;
  distance_miles: number;
  duration_seconds: number;
  avg_pace: string;
  splits: Split[];
  avg_heart_rate?: number;
  elevation_gain_ft?: number;
  cadence?: number;
  feel_rating?: number;
  notes?: string;
  coach_analysis?: string;
  description?: string;
  max_heart_rate?: number;
  suffer_score?: number;
  strava_workout_type?: number;
}

export interface Split {
  mile: number;
  pace: string;
  heart_rate?: number;
}

export interface WeeklyMileage {
  week_start: string;
  planned: number;
  actual: number;
}

export interface PaceVsTarget {
  date: string;
  workout_title: string;
  target_pace_seconds: number;
  actual_pace_seconds: number;
}

export interface OnboardingData {
  age: number;
  preferred_units: "miles" | "kilometers";
  workout_format: "distance" | "time";
  years_running: number;
  current_weekly_mileage: number;
  peak_weekly_mileage: number;
  days_per_week: number;
  rest_days: number[];
  long_run_day: number;
  personal_records: Omit<PersonalRecord, "id">[];
  goal: Omit<Goal, "id">;
}
