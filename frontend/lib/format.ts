/** Local-timezone YYYY-MM-DD string. Avoids the UTC off-by-one from toISOString(). */
export function localDateStr(d: Date = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function formatPace(paceStr: string): string {
  return paceStr;
}

export function secondsToPace(totalSeconds: number): string {
  const min = Math.floor(totalSeconds / 60);
  const sec = Math.round(totalSeconds % 60);
  return `${min}:${sec.toString().padStart(2, "0")}`;
}

export function secondsToTime(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const mins = Math.floor((totalSeconds % 3600) / 60);
  const secs = Math.round(totalSeconds % 60);
  if (hours > 0) {
    return `${hours}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function formatDistance(miles: number): string {
  return miles % 1 === 0 ? `${miles}` : miles.toFixed(1);
}

export function formatDate(dateStr: string): string {
  // Append T12:00:00 to date-only strings to avoid UTC→local timezone shift
  const safe = dateStr.includes("T") ? dateStr : `${dateStr}T12:00:00`;
  const date = new Date(safe);
  return date.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export function formatDateLong(dateStr: string): string {
  const safe = dateStr.includes("T") ? dateStr : `${dateStr}T12:00:00`;
  const date = new Date(safe);
  return date.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

export function formatDateShort(dateStr: string): string {
  const safe = dateStr.includes("T") ? dateStr : `${dateStr}T12:00:00`;
  const date = new Date(safe);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function getDayName(dayIndex: number): string {
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][dayIndex];
}

export function workoutTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    easy: "Easy Run",
    long_run: "Long Run",
    tempo: "Tempo",
    intervals: "Intervals",
    threshold: "Threshold",
    workout: "Quality",
    fartlek: "Fartlek",
    hill_repeats: "Hills",
    progression: "Progression",
    recovery: "Recovery",
    time_trial: "Time Trial",
    rest: "Rest",
    strides: "Strides",
  };
  return labels[type] || type;
}

export function workoutTypeShort(type: string): string {
  const labels: Record<string, string> = {
    easy: "Easy",
    long_run: "Long",
    tempo: "Tempo",
    intervals: "Int",
    threshold: "Thresh",
    workout: "Quality",
    fartlek: "Fart",
    hill_repeats: "Hills",
    progression: "Prog",
    recovery: "Recov",
    time_trial: "TT",
    rest: "Rest",
    strides: "Strides",
  };
  return labels[type] || type;
}

export function isHardWorkout(type: string): boolean {
  return ["tempo", "intervals", "threshold", "hill_repeats", "time_trial", "workout"].includes(type);
}
