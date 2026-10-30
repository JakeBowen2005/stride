"use client";

import { useUnits } from "@/components/unit-preferences";
import { hoursLabel } from "@/lib/format";
import { distanceInUnits, unitLabel } from "@/lib/units";
import { activityKind, kindColor } from "@/lib/workout-style";
import type { Activity } from "@/lib/types";
import { cn } from "@/lib/utils";

const DAYS = 7;

function shiftDate(iso: string, days: number) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const isRun = (a: Activity) => (a.classification?.kind ?? (a.type === "walk" ? "walk" : "run")) === "run";

/** The last seven days of running at a glance: one column per day, the run's type as its color.
 * Tap a day to open its run. Seen many times a day, so it doesn't animate in. */
export function RecentWeek({ runs, today, onOpen }: { runs: Activity[]; today: string; onOpen: (run: Activity) => void }) {
  const units = useUnits();
  const unit = unitLabel(units);
  const days = Array.from({ length: DAYS }, (_, i) => {
    const date = shiftDate(today, i - (DAYS - 1));
    const ran = runs.filter((a) => a.date.startsWith(date) && isRun(a));
    const miles = ran.reduce((sum, a) => sum + a.distance_miles, 0);
    // The day's headline run: a quality session if there was one, otherwise the longest.
    const main = ran.find((a) => a.session) ?? ran.reduce<Activity | undefined>((best, a) => (!best || a.distance_miles > best.distance_miles ? a : best), undefined);
    const kind = main ? activityKind(main.session?.category === "fartlek" || main.session?.category === "speed" ? "intervals" : main.session?.category ?? main.type, main.title) : null;
    return { date, ran, miles, main, kind };
  });
  const total = days.reduce((sum, d) => sum + d.miles, 0);
  const seconds = days.reduce((sum, d) => sum + d.ran.reduce((s, a) => s + a.duration_seconds, 0), 0);
  const count = days.reduce((sum, d) => sum + d.ran.length, 0);
  const max = Math.max(1, ...days.map((d) => d.miles));

  return (
    <section aria-label="Your last seven days of running" className="glass flex flex-col gap-4 px-4 py-4 sm:flex-row sm:items-stretch sm:gap-7 sm:px-6">
      <div className="flex items-end justify-between gap-4 sm:w-44 sm:flex-none sm:flex-col sm:items-start sm:justify-between">
        <div>
          <div className="kicker">Last 7 days</div>
          <div className="hero-num mt-2 text-[40px]">{distanceInUnits(total, units)}<span className="ml-1.5 font-sans text-sm font-normal tracking-normal text-muted-foreground">{unit}</span></div>
        </div>
        <div className="text-right text-xs text-muted-foreground sm:text-left">
          {count} {count === 1 ? "run" : "runs"}{seconds > 0 && <> · {hoursLabel(seconds)}</>}
        </div>
      </div>
      <ol className="grid flex-1 grid-cols-7 gap-1.5 sm:gap-2.5">
        {days.map((d) => {
          const isToday = d.date === today;
          const label = new Date(`${d.date}T12:00:00`).toLocaleDateString("en-US", { weekday: "short" });
          const color = d.kind ? kindColor(d.kind).color : undefined;
          const body = (
            <>
              <span className="relative flex h-16 w-full items-end overflow-hidden rounded-[12px] bg-[var(--glass-inner)] sm:h-20">
                {d.miles > 0 && (
                  <span aria-hidden="true" className="block w-full rounded-[10px]"
                    style={{ height: `${Math.max(10, (d.miles / max) * 100)}%`, background: `linear-gradient(180deg, ${color}, color-mix(in srgb, ${color} 35%, transparent))` }} />
                )}
              </span>
              <span className={cn("mt-1.5 block text-[11px]", isToday ? "font-bold text-foreground" : "text-muted-foreground")}>{isToday ? "Today" : label}</span>
              <span className="num block text-[13px] font-semibold leading-tight">{d.miles > 0 ? distanceInUnits(d.miles, units) : "–"}</span>
              <span className="hidden truncate text-[11px] text-muted-foreground sm:block">{d.main ? d.main.session?.title ?? d.main.title : "Rest"}</span>
            </>
          );
          return (
            <li key={d.date} className="min-w-0 text-center">
              {d.main ? (
                <button type="button" onClick={() => onOpen(d.main!)} className="lift block w-full rounded-[14px] p-1 text-center"
                  aria-label={`${label}: ${distanceInUnits(d.miles, units)} ${unit}, ${d.main.session?.title ?? d.main.title}`}>
                  {body}
                </button>
              ) : (
                <div className="p-1">{body}</div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
