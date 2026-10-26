"use client";

import { distanceInUnits, unitLabel, type Units } from "@/lib/units";
import { formatDateShort, localDateStr } from "@/lib/format";
import { QUALITY_KINDS, kindColor, ranDay } from "@/lib/workout-style";
import type { PlanWeek, Workout } from "@/lib/types";
import { cn } from "@/lib/utils";


function status(w: Workout, today: string): { text: string; color?: string } | null {
  if (w.actual) return { text: "✓ Done", color: "var(--accent-warm)" };
  if (w.session_status === "replaced") return { text: "Replaced" };
  if (w.session_status === "skipped") return { text: "Skipped" };
  if (w.session_status === "moved") return { text: w.moved_to ? `Moved → ${formatDateShort(w.moved_to)}` : "Moved here" };
  if (w.date < today && w.type !== "rest" && w.prescribed !== false) return { text: "Not logged", color: "var(--warn)" };
  return null;
}

/** Block at a glance: one row per week, Mon–Sun plus a total with a progress bar. */
export function PlanCalendar({ weeks, units, selectedDate, onSelect }: {
  weeks: PlanWeek[]; units: Units; selectedDate: string | null; onSelect: (w: Workout) => void;
}) {
  const today = localDateStr();
  const unit = unitLabel(units);
  // Blocks normally start Monday; label columns from the real dates in case one doesn't.
  const days = (weeks[0]?.workouts ?? []).map((w) => new Date(`${w.date}T12:00:00`).toLocaleDateString("en-US", { weekday: "short" }));
  return (
    <>
    <CompactCalendar weeks={weeks} units={units} selectedDate={selectedDate} onSelect={onSelect} today={today} />
    <div className="hidden space-y-3 lg:block">
      {weeks.map((week) => {
        const current = week.workouts.some((w) => w.date === today);
        const logged = week.workouts.reduce((s, w) => s + (w.actual?.total_distance_miles ?? w.actual?.distance_miles ?? 0), 0);
        const pct = week.total_miles > 0 ? Math.min(1, logged / week.total_miles) : 0;
        return (
          <section key={week.week_number} aria-label={`Week ${week.week_number}`} className="glass-tile space-y-3 rounded-[24px] p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-[13px]">
              <h3 className="font-bold">
                Week {week.week_number} · <span className="num">{formatDateShort(week.workouts[0]?.date ?? "")}</span>
                {current && <span className="font-medium" style={{ color: "var(--accent-warm)" }}> · current</span>}
                {week.phase && week.phase.phase !== "general" && <span className="font-medium capitalize text-muted-foreground"> · {week.phase.phase.replace("_", " ")}</span>}
              </h3>
              <div className="flex items-center gap-3 text-muted-foreground">
                <span className="num">{logged > 0 ? <><span className="font-semibold text-foreground">{distanceInUnits(logged, units)}</span> of </> : null}{distanceInUnits(week.total_miles, units)} {unit}{logged > 0 ? "" : " planned"}</span>
                <span className="h-1.5 w-20 overflow-hidden rounded-full bg-[var(--glass-inner)]" role="progressbar" aria-label={`Week ${week.week_number} logged`} aria-valuenow={Math.round(pct * 100)} aria-valuemin={0} aria-valuemax={100}>
                  <span className="block h-full rounded-full" style={{ width: `${pct * 100}%`, background: "var(--accent-warm)" }} />
                </span>
              </div>
            </div>
            <div className="grid gap-2.5" style={{ gridTemplateColumns: `repeat(${Math.max(days.length, week.workouts.length)}, minmax(0, 1fr))` }}>
              {week.workouts.map((w) => {
                // A completed day shows what was actually run (threshold on an interval day, a swapped long run).
                const { title, kind, offPlan, swapNote } = ranDay(w);
                const { color, tint } = kindColor(kind);
                const hard = QUALITY_KINDS.includes(kind);
                const st = status(w, today);
                const selected = selectedDate === w.date;
                const isToday = w.date === today;
                const miles = w.actual ? w.actual.total_distance_miles ?? w.actual.distance_miles : w.distance_miles;
                const dow = new Date(`${w.date}T12:00:00`).toLocaleDateString("en-US", { weekday: "short" });
                return (
                  <button key={w.date} type="button" onClick={() => onSelect(w)} aria-pressed={selected}
                    aria-label={`${formatDateShort(w.date)}: ${w.actual ? `ran ${title}` : title}${offPlan ? ` instead of ${w.title}` : ""}${swapNote ? `, ${swapNote}` : ""}, ${distanceInUnits(miles, units)} ${unit}${st ? `, ${st.text}` : ""}`}
                    className={cn("lift flex min-h-[148px] w-full flex-col gap-1.5 rounded-[20px] border px-3 py-3 text-left",
                      hard && "hatch", w.type === "rest" && "opacity-75", w.skipped && "opacity-55",
                      selected && "ring-2 ring-[var(--ring)] ring-offset-0")}
                    style={{
                      background: hard ? tint : "var(--glass-inner)",
                      borderColor: isToday ? "var(--foreground)" : "var(--glass-border)",
                      borderWidth: isToday ? 1.5 : 1,
                      ["--hatch" as string]: hard ? `color-mix(in srgb, ${color} 14%, transparent)` : undefined,
                    }}>
                    <span className="flex items-center justify-between gap-1 text-[11px] text-muted-foreground">
                      <span className="num">{dow} {formatDateShort(w.date)}</span>
                      {w.actual && <span aria-hidden="true" style={{ color: "var(--accent-warm)" }}>✓</span>}
                    </span>
                    <span className="line-clamp-3 break-words text-[13px] font-semibold leading-snug">{title}</span>
                    {offPlan && (
                      <span className="line-clamp-3 text-[11px] leading-snug text-muted-foreground">
                        {swapNote ? <>{swapNote} · </> : null}planned <span className="line-through">{w.title}</span>
                      </span>
                    )}
                    <span className="mt-auto flex items-center gap-1.5">
                      <span aria-hidden="true" className="dot" style={{ background: color }} />
                      {w.type !== "rest" ? <span className="num text-xl font-semibold leading-none">{distanceInUnits(miles, units)}</span> : <span className="text-sm text-muted-foreground">Rest</span>}
                    </span>
                    {st && st.text !== "✓ Done" && <span className="text-[11px] font-semibold" style={{ color: st.color ?? "var(--muted-foreground)" }}>{st.text}</span>}
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
    </>
  );
}


/** Phones and tablets: each week fits the screen as 7 compact cells; tap one for the inspector. */
function CompactCalendar({ weeks, units, selectedDate, onSelect, today }: {
  weeks: PlanWeek[]; units: Units; selectedDate: string | null; onSelect: (w: Workout) => void; today: string;
}) {
  return (
    <div className="space-y-2 lg:hidden">
      {weeks.map((week) => {
        const logged = week.workouts.reduce((sum, w) => sum + (w.actual?.total_distance_miles ?? w.actual?.distance_miles ?? 0), 0);
        return (
          <div key={week.week_number} className="glass-tile space-y-2 rounded-[20px] p-2.5">
            <div className="flex items-baseline justify-between px-0.5 text-xs">
              <span>
                <span className="font-bold">Week {week.week_number}</span>
                <span className="text-muted-foreground"> · {formatDateShort(week.workouts[0]?.date ?? "")}</span>
                {week.phase && week.phase.phase !== "general" && <span className="capitalize text-muted-foreground"> · {week.phase.phase.replace("_", " ")}</span>}
              </span>
              <span className="num">{logged > 0 ? `${distanceInUnits(logged, units)} / ` : ""}{distanceInUnits(week.total_miles, units)} {unitLabel(units)}</span>
            </div>
            <div className="grid grid-cols-7 gap-1">
              {week.workouts.map((w) => {
                const { title, kind } = ranDay(w);
                const { color, tint } = kindColor(kind);
                const hard = QUALITY_KINDS.includes(kind);
                const miles = w.actual ? w.actual.total_distance_miles ?? w.actual.distance_miles : w.distance_miles;
                const selected = selectedDate === w.date;
                const day = new Date(`${w.date}T12:00:00`).toLocaleDateString("en-US", { weekday: "narrow" });
                return (
                  <button key={w.date} type="button" onClick={() => onSelect(w)} aria-pressed={selected}
                    aria-label={`${formatDateShort(w.date)}: ${title}${w.type !== "rest" ? `, ${distanceInUnits(miles, units)} ${unitLabel(units)}` : ""}${w.actual ? ", done" : ""}`}
                    className={cn("flex min-h-[4.25rem] flex-col items-center gap-1 rounded-[14px] border px-0.5 py-1.5 text-center transition-colors",
                      hard && "hatch", w.type === "rest" && "opacity-75", w.skipped && "opacity-55",
                      selected && "ring-2 ring-[var(--ring)]")}
                    style={{
                      background: hard ? tint : "var(--glass-inner)",
                      borderColor: w.date === today ? "var(--foreground)" : "transparent",
                      borderWidth: w.date === today ? 1.5 : 1,
                      ["--hatch" as string]: hard ? `color-mix(in srgb, ${color} 14%, transparent)` : undefined,
                    }}>
                    <span className={cn("text-[11px]", w.date === today ? "font-bold" : "text-muted-foreground")}>{day}</span>
                    <span className="num text-sm font-semibold leading-none">{w.type === "rest" ? "–" : distanceInUnits(miles, units)}</span>
                    <span aria-hidden="true" className="flex h-2.5 items-center gap-0.5">
                      <span className="size-1.5 rounded-full" style={{ background: color }} />
                      {w.actual && <span className="text-[10px] leading-none" style={{ color: "var(--accent-warm)" }}>✓</span>}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
