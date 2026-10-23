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
