/** One color per kind of session, shared by pills, calendar cells and structure bars. */
export type SessionKind = "easy" | "long" | "threshold" | "intervals" | "hills" | "support" | "controlled" | "race" | "rest";

export const KIND_LABEL: Record<SessionKind, string> = {
  easy: "Easy", long: "Long run", threshold: "Threshold", intervals: "Intervals",
  hills: "Hills", support: "Speed support", controlled: "Controlled effort", race: "Race", rest: "Rest",
};

export const QUALITY_KINDS: SessionKind[] = ["threshold", "intervals", "hills", "support", "controlled", "race", "long"];

export function kindColor(kind: SessionKind) {
  return { color: `var(--type-${kind})`, tint: `var(--type-${kind}-tint)` };
}

/** Prefer the numeric prescription's category; fall back to the title for old rows. */
export function sessionKind(type: string, title = "", category?: string | null): SessionKind {
  if (type === "rest") return "rest";
  if (type === "race") return "race";
  if (type === "long_run") return "long";
  if (type !== "workout") return "easy";
  if (category === "speed_support") return "support";
  if (category === "development") return "controlled";
  if (category === "hills") return "hills";
  if (category === "threshold") return "threshold";
  if (category === "intervals") return "intervals";
  const t = title.toLowerCase();
  if (/controlled (effort|intervals)/.test(t)) return "controlled";
  if (/light (fartlek|pickups|steady)|relaxed (repetitions|strides)|controlled short hills/.test(t)) return "support";
  if (/hill|climb/.test(t)) return "hills";
  if (/tempo|threshold|cruise|sandwich|mp|pace run/.test(t)) return "threshold";
  return "intervals";
}

/** Map a synced activity's detected workout type onto the same palette. */
export function activityKind(type: string, title = ""): SessionKind {
  switch (type) {
    case "long_run": return "long";
    case "race": return "race";
    case "threshold": case "tempo": case "progression": return "threshold";
    case "intervals": case "fartlek": case "time_trial": return "intervals";
    case "hill_repeats": return "hills";
    case "workout": return sessionKind("workout", title);
    default: return "easy";
  }
}

/** What a day shows once run, from the backend's single `actual.session` record: the run's
 * title and color, plus the planned session it replaced (and a swap partner) when off plan. */
export function ranDay(day: {
  type: string; title: string; prescription?: unknown;
  actual?: { workout?: { title: string; category?: string | null } | null;
             session?: { title: string; type: string; off_plan: boolean; swapped_with: string | null } | null } | null;
}) {
  const session = day.actual?.session ?? null;
  const workout = day.actual?.workout ?? null;
  const title = session?.title ?? workout?.title ?? day.title;
  const kind = workout ? sessionKind("workout", workout.title, workout.category)
    : session ? sessionKind(session.type, session.title) : sessionKind(day.type, day.title, (day.prescription as { category?: string | null } | null | undefined)?.category);
  const offPlan = !!(session?.off_plan ?? (workout as { off_plan?: boolean } | null)?.off_plan);
  const swappedWith = session?.swapped_with ?? null;
  const swapNote = swappedWith ? `swapped with ${new Date(`${swappedWith}T12:00:00`).toLocaleDateString("en-US", { weekday: "short" })}` : null;
  return { title, kind, offPlan, plannedTitle: day.title, swappedWith, swapNote };
}
