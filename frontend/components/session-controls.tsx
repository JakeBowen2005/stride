"use client";

import { useEffect, useState } from "react";
import { apiUrl, USER_ID } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Workout } from "@/lib/types";

interface Option { id: string; title: string; description: string; distance_miles: number;
  warmup: string | null; cooldown: string | null;
  changes: { date: string; before: {distance_miles:number}; replacement: {distance_miles:number} }[] }
interface Menu { category: string; options: Option[]; reasons: string[]; quality_stage: string }

export function SessionControls({ workout, onChanged }: { workout: Workout; onChanged?: () => void }) {
  const [action, setAction] = useState("skip");
  const [target, setTarget] = useState("");
  const [replacement, setReplacement] = useState("easy");
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
        const res = await fetch(apiUrl(`/plans/${USER_ID}/sessions/${workout.date}/options?category=${replacement}`), {signal:abort.signal});
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
  return <div className="space-y-3 border-t pt-3" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
    <label className="block text-sm">Change this session
      <select className="ml-2 rounded border p-2" value={action} disabled={busy} onChange={e => {setAction(e.target.value);setOptionId("");}}>
        <option value="skip">Skip</option><option value="replace">Replace</option><option value="move">Move to a later day</option>
      </select>
    </label>
    {action === "move" && <Input aria-label="Move to date" type="date" value={target} onChange={e => setTarget(e.target.value)} />}
    {action === "replace" && <select aria-label="Replacement session" className="rounded border p-2" value={replacement} disabled={busy} onChange={e => {setReplacement(e.target.value);setOptionId("");}}>
      <option value="easy">Easy run</option><option value="rest">Rest</option><option value="threshold">Threshold</option><option value="intervals">Intervals / light speed</option><option value="long_run">Long run</option>
    </select>}
    {needsOptions && <div className="space-y-2" aria-busy={loadingOptions}>
      {loadingOptions && <p role="status" className="text-xs text-muted-foreground">Checking current fitness, recovery, quality slots and budget…</p>}
      {currentMenu?.reasons.map((text,i) => <p key={i} className="text-xs text-muted-foreground">{text}</p>)}
      <div role="radiogroup" aria-label="Workout options" className="space-y-2">
        {currentMenu?.options.map(option => <label key={option.id} className={`block cursor-pointer rounded-md border p-3 ${optionId === option.id ? "border-primary bg-primary/5" : ""}`}>
          <span className="flex items-start gap-2"><input type="radio" name={`session-${workout.id}`} value={option.id} checked={optionId === option.id} disabled={busy} onChange={() => setOptionId(option.id)} />
            <span className="font-medium">{option.title} · {option.distance_miles} mi total</span></span>
          <span className="mt-1 block text-xs text-muted-foreground">{option.description}</span>
          {(option.warmup || option.cooldown) && <span className="mt-1 block text-xs">Warmup: {option.warmup} · Cooldown: {option.cooldown}</span>}
          {option.changes.filter(c => c.date !== workout.date).map(c => <span key={c.date} className="mt-1 block text-xs">Budget adjustment: {c.date} easy run {c.before.distance_miles} → {c.replacement.distance_miles} mi</span>)}
        </label>)}
      </div>
    </div>}
    <Input aria-label="Reason for change" placeholder="Reason (optional)" value={reason} onChange={e => setReason(e.target.value)} />
    <p className="text-xs text-muted-foreground">Options evolve with completed training and recovery. Warmups, recoveries and cooldowns count toward the budget.</p>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    <Button size="sm" disabled={busy || (action === "move" && !target) || (needsOptions && (!currentMenu || !optionId || loadingOptions))} onClick={submit}>{busy ? "Saving…" : "Apply change"}</Button>
  </div>;
}
