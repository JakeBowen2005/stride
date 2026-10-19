"use client";

import { useState } from "react";
import { apiUrl, USER_ID } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Workout } from "@/lib/types";

export function SessionControls({ workout, onChanged }: { workout: Workout; onChanged?: () => void }) {
  const [action, setAction] = useState("skip");
  const [target, setTarget] = useState("");
  const [replacement, setReplacement] = useState("easy");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(apiUrl(`/plans/${USER_ID}/sessions/${workout.date}`), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, target_date: action === "move" ? target : null,
          replacement: action === "replace" ? replacement : null, reason: reason || "Changed by athlete" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Couldn't change this session");
      onChanged?.();
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't reach Stride"); }
    finally { setBusy(false); }
  }
  return (
    <div className="space-y-2 border-t pt-3" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
      <label className="block text-sm">Change this session
        <select className="ml-2 rounded border p-2" value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="skip">Skip</option><option value="replace">Replace</option><option value="move">Move to a later day</option>
        </select>
      </label>
      {action === "move" && <Input aria-label="Move to date" type="date" value={target} onChange={(e) => setTarget(e.target.value)} />}
      {action === "replace" && <select aria-label="Replacement session" className="rounded border p-2" value={replacement} onChange={(e) => setReplacement(e.target.value)}>
        <option value="easy">Easy run</option><option value="rest">Rest</option><option value="threshold">Threshold</option><option value="intervals">Intervals</option>
      </select>}
      <Input aria-label="Reason for change" placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
      <p className="text-xs text-muted-foreground">Changes must fit your weekly budget and leave space between hard days.</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <Button size="sm" disabled={busy || (action === "move" && !target)} onClick={submit}>{busy ? "Saving…" : "Apply change"}</Button>
    </div>
  );
}
