export interface SchedulePreferences { rest_days: string[]; days_per_week: number; long_run_day: string; workout_format?: string }
export function scheduleChanged(saved: SchedulePreferences | undefined, current: { rest_days: string | null; days_per_week: number; long_run_day?: string | null; workout_format?: string }): boolean {
  if (!saved) return false; // Legacy blocks cannot prove what changed.
  const rest = (items: string[]) => items.map(d => d.trim()).filter(Boolean).sort().join(",");
  return saved.days_per_week !== current.days_per_week || rest(saved.rest_days) !== rest((current.rest_days || "").split(",")) || saved.long_run_day !== (current.long_run_day || "saturday") || (!!saved.workout_format && saved.workout_format !== (current.workout_format || "distance"));
}
