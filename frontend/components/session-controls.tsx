"use client";

import { useAthleteToday, useUnits } from "@/components/unit-preferences";
import { distanceInUnits, unitLabel } from "@/lib/units";
import { useEffect, useState } from "react";
import { apiUrl, USER_ID } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { KindPill } from "@/components/cockpit/pill";
import { StructureBar, type Prescription } from "@/components/cockpit/structure-bar";
import { sessionKind, kindColor } from "@/lib/workout-style";
import { cn } from "@/lib/utils";
import type { Workout } from "@/lib/types";

interface Option {
  id: string; title: string; description: string; purpose?: string | null; distance_miles: number;
  warmup: string | null; cooldown: string | null; shape?: string; prescription?: Prescription | null;
  changes: { date: string; before: { distance_miles: number }; replacement: { distance_miles: number } }[];
}
interface Menu { category: string; options: Option[]; reasons: string[]; quality_stage: string }

interface SwitchTarget {
  date: string; label: string; type: string; title: string; distance_miles: number; ok: boolean; reason?: string; rearranged?: boolean; pair?: boolean;
  changes?: { date: string; before: string; after: string; distance_miles: number }[];
}

type Action = "skip" | "replace" | "switch";
type Replacement = "easy" | "rest" | "threshold" | "intervals" | "long_run";

const ACTIONS: { value: Action; label: string }[] = [
  { value: "replace", label: "Replace" }, { value: "switch", label: "Switch" }, { value: "skip", label: "Skip" },
];
const REPLACEMENTS: { value: Replacement; label: string; kind: Parameters<typeof kindColor>[0] }[] = [
  { value: "threshold", label: "Threshold", kind: "threshold" },
  { value: "intervals", label: "Intervals", kind: "intervals" },
  { value: "long_run", label: "Long run", kind: "long" },
  { value: "easy", label: "Easy run", kind: "easy" },
  { value: "rest", label: "Rest", kind: "rest" },
];
const SHAPE_LABEL: Record<string, string> = {
  cruise_time: "Time reps", cruise_distance: "Distance reps", continuous: "Continuous", ladder: "Ladder",
  short_reps: "Short reps", middle_reps: "800m–1K reps", long_reps: "Long reps", time_reps: "Time reps",
  pyramid: "Pyramid", hills: "Hills", cruise: "Cruise reps", cruise_short: "Short cruise reps",
  intervals_short: "1-min reps", intervals_medium: "2-min reps", intervals_long: "3-min reps",
};
const shapeLabel = (shape?: string) =>
  !shape ? null : SHAPE_LABEL[shape] ?? (shape.startsWith("easy-") ? `${shape.slice(5)} min` : shape.startsWith("steady-") ? "Steady finish" : shape.replace(/_/g, " "));

function Segmented<T extends string>({ label, value, options, onChange, disabled }: {
  label: string; value: T; options: { value: T; label: string; kind?: Parameters<typeof kindColor>[0] }[];
  onChange: (v: T) => void; disabled?: boolean;
}) {
  // Radiogroup pattern: one tab stop, arrow keys move and select.
  const index = options.findIndex((o) => o.value === value);
  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step || disabled) return;
    e.preventDefault();
    const next = options[(index + step + options.length) % options.length];
    onChange(next.value);
    (e.currentTarget.querySelector(`[data-value="${next.value}"]`) as HTMLButtonElement | null)?.focus();
  }
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5" onKeyDown={onKeyDown}>
      {options.map((o) => {
        const active = o.value === value;
        const color = o.kind ? kindColor(o.kind).color : "var(--primary)";
        return (
          <button key={o.value} data-value={o.value} type="button" role="radio" aria-checked={active} tabIndex={active ? 0 : -1}
            disabled={disabled} onClick={() => onChange(o.value)}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3 text-xs font-semibold transition-colors hover:bg-[var(--row-hover)] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
            style={active ? { background: color, borderColor: color, color: o.kind ? "var(--type-on)" : "var(--primary-foreground)" } : { borderColor: "var(--border)" }}>
            {o.kind && !active && <span aria-hidden="true" className="size-2 rounded-full" style={{ background: color }} />}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** Start Replace on the session's own type so its alternatives load straight away. */
function defaultReplacement(workout: Workout): Replacement {
  if (workout.type === "long_run") return "long_run";
  const category = workout.prescription?.category;
  if (category === "threshold" || category === "intervals") return category;
  const kind = sessionKind(workout.type, workout.title, category);
  return kind === "intervals" ? "intervals" : kind === "long" ? "long_run" : "threshold";
}

const shortDay = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });

export function SessionControls({ workout, onChanged, initialAction = "replace" }: { workout: Workout; onChanged?: () => void; initialAction?: Action }) {
  const units = useUnits();
  const today = useAthleteToday();
  const past = workout.date < today;
  const unit = unitLabel(units);
  const distance = (miles: number) => distanceInUnits(miles, units);
  const [action, setAction] = useState<Action>(initialAction);
  const [target, setTarget] = useState("");
  const [replacement, setReplacement] = useState<Replacement>(() => defaultReplacement(workout));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [menu, setMenu] = useState<Menu | null>(null);
  const [optionId, setOptionId] = useState("");
  const [loadingOptions, setLoadingOptions] = useState(false);
  const needsOptions = action === "replace" && ["threshold", "intervals", "long_run"].includes(replacement);
  const [targets, setTargets] = useState<SwitchTarget[] | null>(null);

  useEffect(() => {
    if (action !== "switch" || past) return;
    const abort = new AbortController();
    const timer = setTimeout(async () => {
      setTargets(null); setTarget(""); setError(null);
      try {
        const res = await fetch(apiUrl(`/plans/${USER_ID}/sessions/${workout.date}/switch-targets`), { signal: abort.signal });
        const data = await res.json();
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not load days");
        if (!abort.signal.aborted) setTargets(data.targets);
      } catch (e) { if (!abort.signal.aborted) setError(e instanceof Error ? e.message : "Could not load days"); }
    }, 0);
    return () => { clearTimeout(timer); abort.abort(); };
  }, [action, past, workout.date]);
  const chosen = targets?.find((t) => t.date === target);

  useEffect(() => {
    if (!needsOptions) return;
    const abort = new AbortController();
    const timer = setTimeout(async () => {
      setLoadingOptions(true); setMenu(null); setOptionId(""); setError(null);
      try {
        const res = await fetch(apiUrl(`/plans/${USER_ID}/sessions/${workout.date}/options?category=${replacement}`), { signal: abort.signal });
        const data = await res.json();
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not load workout options");
        if (!abort.signal.aborted) setMenu(data);
      } catch (e) { if (!abort.signal.aborted) setError(e instanceof Error ? e.message : "Could not load options"); }
      finally { if (!abort.signal.aborted) setLoadingOptions(false); }
    }, 0);
    return () => { clearTimeout(timer); abort.abort(); };
  }, [needsOptions, replacement, workout.date]);

  const currentMenu = menu?.category === replacement ? menu : null;

  async function submit() {
    setBusy(true); setError(null);
    try {
      const res = await fetch(apiUrl(`/plans/${USER_ID}/sessions/${workout.date}`), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: past ? "skip" : action, target_date: action === "switch" ? target : null,
          replacement: action === "replace" ? replacement : null,
          option_id: needsOptions ? optionId : null, reason: reason || "Changed by athlete" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Couldn't change this session");
      onChanged?.();
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't reach Stride"); }
    finally { setBusy(false); }
  }

  const canApply = !busy && !(action === "switch" && !chosen?.ok) && !(needsOptions && (!currentMenu || !optionId || loadingOptions));

  if (past) {
    // Only "didn't run it" makes sense for a past day; a run you did gets logged instead.
    return (
      <div className="space-y-2 border-t border-[var(--glass-border)] pt-3" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
        <p className="text-sm text-muted-foreground">This day has passed. If you didn&apos;t run, mark it skipped so the plan reflects it.</p>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <Button size="sm" variant="outline" disabled={busy} onClick={submit}>{busy ? "Saving…" : "I didn't run this"}</Button>
      </div>
    );
  }

  return (
    <div className="space-y-3 border-t border-[var(--glass-border)] pt-3" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="stat-label">Change this session</span>
        <Segmented label="Change type" value={action} options={ACTIONS} disabled={busy} onChange={(v) => { setAction(v); setOptionId(""); }} />
      </div>
      {action === "switch" && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">Swap {workout.title} with another day. Days that would break hard-day spacing or your long-run rules are greyed out.</p>
          {!targets && !error && <div className="h-16 animate-pulse rounded-2xl bg-muted" role="status" aria-label="Loading days" />}
          <div role="radiogroup" aria-label="Switch with" className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {targets?.map((t) => {
              const kind = sessionKind(t.type, t.title);
              const checked = target === t.date;
              return (
                <button key={t.date} type="button" role="radio" aria-checked={checked} aria-disabled={!t.ok} disabled={busy} title={t.reason}
                  onClick={() => setTarget(t.date)}
                  className={cn("min-h-14 rounded-2xl border-[1.5px] px-3 py-2 text-left text-xs transition-colors focus-visible:outline-2 focus-visible:outline-primary",
                    t.ok ? "hover:bg-[var(--row-hover)]" : "opacity-45")}
                  style={{ borderColor: checked ? kindColor(kind).color : "var(--glass-border)", background: checked ? kindColor(kind).tint : undefined,
                    boxShadow: checked ? `0 0 0 2px ${kindColor(kind).color}` : undefined }}>
                  <span className="block font-semibold">{t.label}</span>
                  <span className="block truncate text-muted-foreground">{t.type === "rest" ? "Rest" : `${t.title} · ${distance(t.distance_miles)} ${unit}`}</span>
                  {t.ok && (t.rearranged || t.pair) && <span className="block text-[11px]" style={{ color: "var(--warn)" }}>also moves {(t.changes?.length ?? 3) - 2} more</span>}
                </button>
              );
            })}
          </div>
          {chosen && !chosen.ok && <p role="status" className="text-xs" style={{ color: "var(--warn)" }}>Can&apos;t switch with {chosen.label}: {chosen.reason}</p>}
          {chosen?.ok && chosen.changes && (
            <ul className="space-y-1 rounded-2xl bg-[var(--glass-inner)] p-3 text-xs" aria-label="What changes">
              {chosen.rearranged && <li className="text-muted-foreground">A straight swap would put two hard days together, so Stride also shifts another session:</li>}
              {chosen.pair && <li className="text-muted-foreground">Back-to-back long runs move together:</li>}
              {chosen.changes.map((c) => (
                <li key={c.date}><span className="font-medium">{shortDay(c.date)}:</span> <span className="text-muted-foreground line-through">{c.before}</span> → {c.after}{c.distance_miles ? ` · ${distance(c.distance_miles)} ${unit}` : ""}</li>
              ))}
            </ul>
          )}
          {targets && targets.every((t) => !t.ok) && <p className="text-xs text-muted-foreground">No day in this block can take this session without breaking a training rule. {targets[0]?.reason ?? ""}</p>}
        </div>
      )}
      {action === "replace" && (
        <Segmented label="Replacement session" value={replacement} options={REPLACEMENTS} disabled={busy}
          onChange={(v) => { setReplacement(v); setOptionId(""); }} />
      )}
      {needsOptions && (
        <div className="space-y-2" aria-busy={loadingOptions}>
          {loadingOptions && <div className="space-y-2" role="status" aria-label="Loading options">
            {[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-muted" />)}
          </div>}
          {currentMenu?.reasons.map((text, i) => <p key={i} className="text-xs text-muted-foreground">{text}</p>)}
          <div role="radiogroup" aria-label="Workout options" className="space-y-2">
            {currentMenu?.options.map((option, index) => {
              const kind = sessionKind(replacement === "long_run" ? "long_run" : "workout", option.title, option.prescription?.category);
              const { color, tint } = kindColor(kind);
              const checked = optionId === option.id;
              return (
                <label key={option.id} htmlFor={`opt-${option.id}`}
                  className={cn("lift block cursor-pointer rounded-2xl border-[1.5px] bg-[var(--glass-inner)] p-3.5", checked && "shadow-md")}
                  style={{ borderColor: checked ? color : "var(--glass-border)", background: checked ? tint : "var(--glass-inner)" }}>
                  <span className="flex items-start gap-2">
                    <input type="radio" id={`opt-${option.id}`} aria-labelledby={`opt-${option.id}-t`} aria-describedby={`opt-${option.id}-d`}
                      className="mt-1 accent-current" style={{ color }} name={`session-${workout.id}`} value={option.id}
                      checked={checked} disabled={busy} onChange={() => setOptionId(option.id)} />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[10.5px] text-muted-foreground">{String.fromCharCode(65 + index)}</span>
                        <span id={`opt-${option.id}-t`} className="font-semibold">{option.title}, {distance(option.distance_miles)} {unit}</span>
                        {shapeLabel(option.shape) && <KindPill kind={kind} label={shapeLabel(option.shape)!} />}
                        
                      </span>
                      {option.prescription && <span className="mt-2 block"><StructureBar prescription={option.prescription} kind={kind} height={28} /></span>}
                      <span id={`opt-${option.id}-d`} className="mt-1.5 block text-xs leading-relaxed text-muted-foreground">{option.description}</span>
                      {option.purpose && <span className="mt-1 block text-xs"><span className="font-medium" style={{ color }}>Why: </span>{option.purpose}</span>}
                      {(option.warmup || option.cooldown) && <span className="mt-1 block font-mono text-[11px] text-muted-foreground">WU {option.warmup ?? "—"} · CD {option.cooldown ?? "—"}</span>}
                      {option.changes.filter((c) => c.date !== workout.date).map((c) => (
                        <span key={c.date} className="mt-1 block text-xs" style={{ color: "var(--warn)" }}>
                          Budget: {c.date} easy run {distance(c.before.distance_miles)} → {distance(c.replacement.distance_miles)} {unit}
                        </span>
                      ))}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        </div>
      )}
      <Input aria-label="Reason for change" placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] text-muted-foreground">Warmups, recoveries and cooldowns count toward the weekly budget.</p>
        <Button size="sm" disabled={!canApply} onClick={submit}>{busy ? "Saving…" : "Apply change"}</Button>
      </div>
    </div>
  );
}
