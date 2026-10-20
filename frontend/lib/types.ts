export type WorkoutType =
  | "easy"
  | "long_run"
  | "tempo"
  | "intervals"
  | "threshold"
  | "workout"
  | "fartlek"
  | "hill_repeats"
  | "progression"
  | "recovery"
  | "time_trial"
  | "rest"
  | "strides"
  | "race";

// Same values the backend stores (users.GoalData / RACE_DISTANCES)
export type GoalType = "race" | "mileage" | "general" | "comeback";

export type RaceDistance = "5k" | "10k" | "half" | "marathon" | "50k" | "50mi" | "100k" | "100mi";

export type TrainingPhase = "general" | "base" | "build" | "peak" | "taper" | "race_week" | "recovery";

export interface WeekPhaseInfo {
  phase: TrainingPhase;
  label: string;
  weeks_to_race: number | null;
  back_to_back: boolean;
  fueling_g_per_hr: number | null;
  notes: string[];
}

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

/** What Garmin's laps show was actually run (null for steady runs). */
export interface ExecutedWorkout {
  title: string;
  label: string;
  category: "threshold" | "intervals" | "speed" | "fartlek";
  kind: "reps" | "tempo";
  reps: { distance_m: number; duration_s: number; pace_sec_per_mile: number; average_hr: number | null }[];
  recovery_seconds: number | null;
  /** True when it differs from the prescribed session (e.g. threshold on an interval day) */
  off_plan: boolean;
}

export interface ActualRun {
  workout?: ExecutedWorkout | null;
  distance_miles: number;
  avg_pace: string | null;
  duration_seconds: number;
  average_heartrate: number | null;
  description: string | null;
  feel_rating: number | null;
  name: string | null;
  activity_count?: number;
  activities?: {
    name: string;
    distance_miles: number;
    avg_pace: string | null;
    duration_seconds: number;
  }[];
}

export interface DayFeedback {
  feel_rating: number | null;
  feel_notes: string | null;
  pace_assessment: string | null;
  swapped: boolean;
  swap_reason: string | null;
  actual_workout_type: string | null;
  coach_response: string | null;
  evaluation?: { decision: string; reason: string; evidence: string } | null;
  changes?: { date: string | null; change: string; reason: string }[];
}

export interface RunComparison {
  distance_diff_miles: number;
  summary: string;
}

export interface Workout {
  id: number;
  date: string;
  type: WorkoutType;
  title: string;
  description: string | null;
  purpose: string | null;
  distance_miles: number;
  target_pace?: string;
  warmup?: string;
  cooldown?: string;
  intervals?: string;
  completed: boolean;
  skipped: boolean;
  session_status?: "completed" | "not_logged" | "skipped" | "replaced" | "moved";
  moved_to?: string | null;
  prescribed?: boolean;
  actual?: ActualRun | null;
  comparison?: RunComparison | null;
  feedback?: DayFeedback | null;
  adjustment_note?: string | null;
  /** Versioned numeric prescription (null for legacy or unprescribed days). */
  prescription?: import("@/components/cockpit/structure-bar").Prescription | null;
}

export interface PlanWeek {
  week_number: number;
  total_miles: number;
  actual_miles?: number;
  phase?: WeekPhaseInfo | null;
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
  external_id?: string;
  source?: "garmin" | "strava" | "manual";
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
  event_type?: string | null;
  activity_subtype?: string | null;
  aerobic_training_effect?: number | null;
  anaerobic_training_effect?: number | null;
  training_effect_label?: string | null;
  training_load?: number | null;
  vo2max?: number | null;
  avg_ground_contact_time?: number | null;
  avg_vertical_oscillation?: number | null;
  calories?: number | null;
}

export interface Split {
  mile: number; // split/lap number
  pace: string;
  heart_rate?: number;
  // Garmin laps
  distance_miles?: number;
  duration_seconds?: number;
  intensity?: string | null;
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
