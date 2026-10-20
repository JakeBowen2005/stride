"use client";

import { distanceInUnits, unitLabel, type Units } from "@/lib/units";
import { formatDateShort, localDateStr } from "@/lib/format";
import { QUALITY_KINDS, kindColor, sessionKind } from "@/lib/workout-style";
import type { PlanWeek, Workout } from "@/lib/types";
import { cn } from "@/lib/utils";


function status(w: Workout, today: string): { text: string; color?: string } | null {
  if (w.actual) return { text: "✓ Done", color: "var(--type-easy)" };
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
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] table-fixed border-collapse text-sm">
        <thead>
          <tr className="bg-[var(--ink)] text-left font-mono text-[10.5px] uppercase tracking-[.08em] text-[#f5f5f2]">
            <th scope="col" className="w-[84px] px-2 py-1.5 font-medium">Wk</th>
            {days.map((d) => <th scope="col" key={d} className="px-2 py-1.5 font-medium">{d}</th>)}
            <th scope="col" className="w-24 px-2 py-1.5 text-right font-medium">Total</th>
          </tr>
        </thead>
        <tbody>
          {weeks.map((week) => {
            const current = week.workouts.some((w) => w.date === today);
            const logged = week.workouts.reduce((s, w) => s + (w.actual?.distance_miles ?? 0), 0);
            const pct = week.total_miles > 0 ? Math.min(1, logged / week.total_miles) : 0;
            return (
              <tr key={week.week_number} className="border-t border-[#2a2a2a]/20 align-top">
                <th scope="row" className="px-2 py-2 text-left font-mono text-xs font-normal">
                  <div className="font-semibold">W{week.week_number}</div>
                  <div className="text-muted-foreground">{formatDateShort(week.workouts[0]?.date ?? "")}</div>
                  {current && <div className="font-medium" style={{ color: "var(--warn)" }}>current</div>}
                  {week.phase && week.phase.phase !== "general" && <div className="capitalize text-muted-foreground">{week.phase.phase.replace("_", " ")}</div>}
                </th>
                {week.workouts.map((w) => {
                  const kind = sessionKind(w.type, w.title, w.prescription?.category);
                  const { color, tint } = kindColor(kind);
                  const hard = QUALITY_KINDS.includes(kind);
                  const st = status(w, today);
                  const selected = selectedDate === w.date;
                  const miles = w.actual ? w.actual.distance_miles : w.distance_miles;
                  return (
                    <td key={w.date} className="p-0.5">
                      <button type="button" onClick={() => onSelect(w)} aria-pressed={selected}
                        aria-label={`${formatDateShort(w.date)}: ${w.title}, ${distanceInUnits(miles, units)} ${unit}${st ? `, ${st.text}` : ""}`}
                        className={cn("flex h-full min-h-[92px] w-full flex-col gap-0.5 rounded-[4px] border p-1.5 text-left transition-shadow hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary",
                          hard && "hatch", w.type === "rest" && "opacity-70", w.skipped && "opacity-50")}
                        style={{
                          background: hard ? tint : w.actual ? "var(--type-easy-tint)" : "var(--card)",
                          borderColor: selected ? "#1f1f1f" : hard ? color : "var(--border)",
                          borderWidth: selected ? 2 : 1,
                          ["--hatch" as string]: hard ? `color-mix(in srgb, ${color} 18%, transparent)` : undefined,
                          boxShadow: w.date === today ? `inset 0 3px 0 ${color}` : undefined,
                        }}>
                        <span className="font-mono text-[10.5px] text-muted-foreground">{formatDateShort(w.date)}</span>
                        <span className="flex items-start gap-1 text-[12.5px] font-medium leading-tight">
                          {hard && <span aria-hidden="true" className="mt-1 size-2 shrink-0 rounded-full" style={{ background: color }} />}
                          <span className="line-clamp-2">{w.title}</span>
                        </span>
                        {w.type !== "rest" && <span className="num mt-auto text-sm font-semibold">{distanceInUnits(miles, units)} {unit}</span>}
                        {st && <span className="text-[11px] font-medium" style={{ color: st.color ?? "var(--muted-foreground)" }}>{st.text}</span>}
                      </button>
                    </td>
                  );
                })}
                {Array.from({ length: Math.max(0, days.length - week.workouts.length) }, (_, i) => <td key={`pad-${i}`} />)}
                <td className="px-2 py-2 text-right font-mono text-xs">
                  <div className="text-base font-semibold">{distanceInUnits(week.total_miles, units)}</div>
                  {logged > 0 && <div className="text-muted-foreground">{distanceInUnits(logged, units)} act</div>}
                  <div className="ml-auto mt-1 h-1.5 w-16 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={`Week ${week.week_number} logged`} aria-valuenow={Math.round(pct * 100)} aria-valuemin={0} aria-valuemax={100}>
                    <div className="h-full rounded-full" style={{ width: `${pct * 100}%`, background: "var(--type-easy)" }} />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
