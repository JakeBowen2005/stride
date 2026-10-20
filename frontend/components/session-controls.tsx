"use client";

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

type Action = "skip" | "replace" | "move";
type Replacement = "easy" | "rest" | "threshold" | "intervals" | "long_run";

const ACTIONS: { value: Action; label: string }[] = [
  { value: "replace", label: "Replace" }, { value: "move", label: "Move" }, { value: "skip", label: "Skip" },
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
  pyramid: "Pyramid", hills: "Hills",
};
const shapeLabel = (shape?: string) =>
  !shape ? null : SHAPE_LABEL[shape] ?? (shape.startsWith("easy-") ? "Easy long" : shape.startsWith("steady-") ? "Steady finish" : shape.replace(/_/g, " "));

function Segmented<T extends string>({ label, value, options, onChange, disabled }: {
  label: string; value: T; options: { value: T; label: string; kind?: Parameters<typeof kindColor>[0] }[];
  onChange: (v: T) => void; disabled?: boolean;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1">
      {options.map((o) => {
        const active = o.value === value;
        const color = o.kind ? kindColor(o.kind).color : "#1f1f1f";
        return (
          <button key={o.value} type="button" role="radio" aria-checked={active} disabled={disabled} onClick={() => onChange(o.value)}
            className="rounded-full border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
            style={active ? { background: color, borderColor: color, color: "#fff" } : { borderColor: "var(--border)" }}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function SessionControls({ workout, onChanged }: { workout: Workout; onChanged?: () => void }) {
  const [action, setAction] = useState<Action>("replace");
  const [target, setTarget] = useState("");
  const [replacement, setReplacement] = useState<Replacement>(workout.type === "workout" ? "easy" : "threshold");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [menu, setMenu] = useState<Menu | null>(null);
  const [optionId, setOptionId] = useState("");
  const [loadingOptions, setLoadingOptions] = useState(false);
  const needsOptions = action === "replace" && ["threshold", "intervals", "long_run"].includes(replacement);

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
        body: JSON.stringify({ action, target_date: action === "move" ? target : null,
          replacement: action === "replace" ? replacement : null,
          option_id: needsOptions ? optionId : null, reason: reason || "Changed by athlete" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Couldn't change this session");
      onChanged?.();
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't reach Stride"); }
    finally { setBusy(false); }
  }

  const canApply = !busy && !(action === "move" && !target) && !(needsOptions && (!currentMenu || !optionId || loadingOptions));

  return (
    <div className="space-y-3 border-t pt-3" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="stat-label">Change this session</span>
        <Segmented label="Change type" value={action} options={ACTIONS} disabled={busy} onChange={(v) => { setAction(v); setOptionId(""); }} />
      </div>
      {action === "move" && <Input aria-label="Move to date" type="date" value={target} onChange={(e) => setTarget(e.target.value)} />}
      {action === "replace" && (
        <Segmented label="Replacement session" value={replacement} options={REPLACEMENTS} disabled={busy}
          onChange={(v) => { setReplacement(v); setOptionId(""); }} />
      )}
      {needsOptions && (
        <div className="space-y-2" aria-busy={loadingOptions}>
          {loadingOptions && <div className="space-y-2" role="status" aria-label="Loading options">
            {[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-md bg-muted" />)}
          </div>}
          {currentMenu?.reasons.map((text, i) => <p key={i} className="text-xs text-muted-foreground">{text}</p>)}
          <div role="radiogroup" aria-label="Workout options" className="space-y-2">
            {currentMenu?.options.map((option, index) => {
              const kind = sessionKind(replacement === "long_run" ? "long_run" : "workout", option.title, option.prescription?.category);
              const { color, tint } = kindColor(kind);
              const checked = optionId === option.id;
              return (
                <label key={option.id}
                  className={cn("block cursor-pointer rounded-md border-[1.5px] p-3 transition-shadow hover:shadow-md", checked && "shadow-md")}
                  style={{ borderColor: checked ? color : "var(--border)", background: checked ? tint : "var(--card)" }}>
                  <span className="flex items-start gap-2">
                    <input type="radio" className="mt-1 accent-current" style={{ color }} name={`session-${workout.id}`} value={option.id}
                      checked={checked} disabled={busy} onChange={() => setOptionId(option.id)} />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[10.5px] text-muted-foreground">{String.fromCharCode(65 + index)}</span>
                        <span className="font-semibold">{option.title}</span>
                        {shapeLabel(option.shape) && <KindPill kind={kind} label={shapeLabel(option.shape)!} />}
                        <span className="num ml-auto text-sm font-semibold">{option.distance_miles} mi</span>
                      </span>
                      {option.prescription && <span className="mt-2 block"><StructureBar prescription={option.prescription} kind={kind} height={28} /></span>}
                      <span className="mt-1.5 block text-xs leading-relaxed text-muted-foreground">{option.description}</span>
                      {option.purpose && <span className="mt-1 block text-xs"><span className="font-medium" style={{ color }}>Why: </span>{option.purpose}</span>}
                      {(option.warmup || option.cooldown) && <span className="mt-1 block font-mono text-[11px] text-muted-foreground">WU {option.warmup ?? "—"} · CD {option.cooldown ?? "—"}</span>}
                      {option.changes.filter((c) => c.date !== workout.date).map((c) => (
                        <span key={c.date} className="mt-1 block text-xs" style={{ color: "var(--warn)" }}>
                          Budget: {c.date} easy run {c.before.distance_miles} → {c.replacement.distance_miles} mi
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
