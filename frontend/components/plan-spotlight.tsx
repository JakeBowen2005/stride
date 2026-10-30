"use client";

import { ArrowRight, Check } from "lucide-react";
import { KindPill } from "@/components/cockpit/pill";
import { formatDateShort } from "@/lib/format";
import { distanceInUnits, unitLabel, type Units } from "@/lib/units";
import { kindColor, ranDay } from "@/lib/workout-style";
import type { Workout } from "@/lib/types";
import { pickSpotlight } from "@/lib/plan-spotlight";

/** The plan's hero: the run you're about to do, with its purpose, above the two-week block. */
export function PlanSpotlight({ days, today, units, onOpen }: {
  days: Workout[]; today: string; units: Units; onOpen: (date: string) => void;
}) {
  const { focus, todayDay, when } = pickSpotlight(days, today);
  const unit = unitLabel(units);
  if (!focus) return null;
  const { title, kind } = ranDay(focus);
  const { color } = kindColor(kind);
  const todayMiles = todayDay?.actual ? todayDay.actual.total_distance_miles ?? todayDay.actual.distance_miles : null;
  const parts = [focus.warmup && `Warm-up ${focus.warmup}`, focus.cooldown && `cool-down ${focus.cooldown}`].filter(Boolean);

  return (
    <section aria-label={`Up next: ${when}`} className="glass relative overflow-hidden p-5 sm:p-7"
      style={{ backgroundImage: `radial-gradient(520px 240px at 100% 0%, color-mix(in srgb, ${color} 22%, transparent), transparent 70%)` }}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="kicker">{when} · {formatDateShort(focus.date)}</span>
          <KindPill kind={kind} />
        </div>
        {todayDay?.actual && todayMiles != null && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--glass-inner)] px-3 py-1 text-xs font-semibold">
            <Check className="size-3.5" style={{ color: "var(--status-good)" }} aria-hidden />
            Today done · <span className="num">{distanceInUnits(todayMiles, units)} {unit}</span>
          </span>
        )}
        {todayDay && todayDay.type === "rest" && !todayDay.actual && when !== "Today" && (
          <span className="rounded-full bg-[var(--glass-inner)] px-3 py-1 text-xs font-semibold text-muted-foreground">Rest day today</span>
        )}
      </div>

      <div className="mt-5 grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
        <div className="min-w-0">
          <h2 className="text-[clamp(1.6rem,1.2rem+1.8vw,2.4rem)] font-semibold leading-[1.05] tracking-[-0.03em]">{title}</h2>
          {focus.description && <p className="mt-3 max-w-[62ch] text-[15px] leading-relaxed text-muted-foreground">{focus.description}</p>}
          {parts.length > 0 && <p className="mt-2 text-sm text-muted-foreground">{parts.join(" · ")}</p>}
          {focus.purpose && (
            <p className="mt-4 max-w-[62ch] rounded-2xl bg-[var(--glass-inner)] px-4 py-3 text-sm leading-relaxed text-muted-foreground">
              <span className="serif-em text-[17px]">Why: </span>{focus.purpose}
            </p>
          )}
        </div>
        <div className="flex items-end justify-between gap-6 lg:flex-col lg:items-end">
          <div className="lg:text-right">
            <div className="hero-num text-[clamp(3.25rem,2.5rem+3vw,4.75rem)]">{distanceInUnits(focus.distance_miles, units)}</div>
            <div className="mt-1 text-sm text-muted-foreground">{unit} planned</div>
          </div>
          <button type="button" onClick={() => onOpen(focus.date)}
            className="btn-gloss inline-flex min-h-11 items-center gap-2 rounded-full px-5 text-sm font-semibold transition-[transform,box-shadow] duration-150">
            Open session <ArrowRight className="size-4" aria-hidden />
          </button>
        </div>
      </div>
    </section>
  );
}
