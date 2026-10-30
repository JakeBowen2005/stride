/** Which run the Plan page puts first: today's while it's still to do, otherwise the next one. */
interface SpotlightDay {
  date: string; type: string; skipped?: boolean; moved_to?: string | null; actual?: unknown;
}

const runnable = (w: SpotlightDay) => w.type !== "rest" && !w.actual && !w.skipped && !w.moved_to;

function nextDate(iso: string) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function pickSpotlight<T extends SpotlightDay>(days: T[], today: string): { focus: T | null; todayDay: T | null; when: string | null } {
  const todayDay = days.find((w) => w.date === today) ?? null;
  if (todayDay && runnable(todayDay)) return { focus: todayDay, todayDay, when: "Today" };
  const next = days.find((w) => w.date > today && runnable(w)) ?? null;
  if (!next) return { focus: null, todayDay, when: null };
  const when = next.date === nextDate(today) ? "Tomorrow"
    : new Date(`${next.date}T12:00:00`).toLocaleDateString("en-US", { weekday: "long" });
  return { focus: next, todayDay, when };
}
