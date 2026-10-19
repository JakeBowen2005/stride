export interface Wellness {
  date: string;
  resting_hr?: number | null;
  resting_hr_7d_avg?: number | null;
  hrv_last_night?: number | null;
  hrv_weekly_avg?: number | null;
  hrv_status?: string | null;
  hrv_baseline_low?: number | null;
  hrv_baseline_high?: number | null;
  sleep_seconds?: number | null;
  sleep_score?: number | null;
  sleep_quality?: string | null;
  deep_sleep_seconds?: number | null;
  rem_sleep_seconds?: number | null;
  light_sleep_seconds?: number | null;
  awake_sleep_seconds?: number | null;
  body_battery_now?: number | null;
  body_battery_wake?: number | null;
  stress_avg?: number | null;
  steps?: number | null;
  step_goal?: number | null;
  readiness_score?: number | null;
  readiness_level?: string | null;
  readiness_feedback?: string | null;
  recovery_time_min?: number | null;
  training_status?: string | null;
  acwr?: number | null;
  vo2max?: number | null;
  predicted_5k?: number | null;
  predicted_10k?: number | null;
  predicted_half?: number | null;
  predicted_marathon?: number | null;
  updated_at?: string | null;
}

export interface RecoverySignal {
  level: "good" | "caution" | "warning";
  metric: string;
  message: string;
}

export interface WellnessResponse {
  /** Today's Garmin data only (null if today hasn't synced) */
  today: Wellness | null;
  /** Most recent day, for trends/tiles; may be older than today */
  latest: Wellness | null;
  freshness: "fresh" | "stale" | "absent";
  as_of: string | null;
  training_status_label: string | null;
  signals: RecoverySignal[];
  history: Wellness[];
}
