import { kindColor, type SessionKind } from "@/lib/workout-style";

const MI = 1609.34;

export interface PrescriptionSegment {
  reps: number;
  distance_meters: number | null;
  duration_seconds: number | null;
  pace_range_sec_per_mile: { fast: number; slow: number } | null;
  recovery_seconds: number | null;
  recovery_meters?: number | null;
}

export interface Prescription {
  category: string;
  segments: PrescriptionSegment[];
  warmup?: PrescriptionSegment | null;
  cooldown?: PrescriptionSegment | null;
  easy_pace_sec_per_mile?: number | null;
}

type Block = { kind: "bookend" | "work" | "recovery"; seconds: number; label: string };

function blocks(p: Prescription): Block[] {
  const easy = p.easy_pace_sec_per_mile ?? 540;
  const secs = (s: PrescriptionSegment, pace: number) => s.duration_seconds ?? ((s.distance_meters ?? 0) / MI) * pace;
  const out: Block[] = [];
  if (p.warmup) out.push({ kind: "bookend", seconds: secs(p.warmup, easy), label: "Warm-up" });
  p.segments.forEach((s, i) => {
    const pace = s.pace_range_sec_per_mile?.slow ?? easy * 0.85;
    for (let r = 0; r < s.reps; r++) {
      out.push({ kind: "work", seconds: secs(s, pace), label: "Work" });
      const last = i === p.segments.length - 1 && r === s.reps - 1;
      const rest = s.recovery_seconds ?? (s.recovery_meters ? (s.recovery_meters / MI) * easy : 0);
      if (!last && rest) out.push({ kind: "recovery", seconds: rest, label: "Recovery" });
    }
  });
  if (p.cooldown) out.push({ kind: "bookend", seconds: secs(p.cooldown, easy), label: "Cool-down" });
  return out.filter((b) => b.seconds > 0);
}

/** Warm-up / reps / recoveries / cool-down drawn to time scale; taller = harder. */
export function StructureBar({ prescription, kind, height = 40 }: { prescription: Prescription; kind: SessionKind; height?: number }) {
  const parts = blocks(prescription);
  const total = parts.reduce((sum, b) => sum + b.seconds, 0);
  if (!total || !parts.some((b) => b.kind === "work")) return null;
  const { color } = kindColor(kind);
  const workMin = Math.round(parts.filter((b) => b.kind === "work").reduce((s, b) => s + b.seconds, 0) / 60);
  return (
    <span className="block space-y-1">
      <span className="flex items-end gap-px overflow-hidden rounded-sm" style={{ height }} role="img"
        aria-label={`Session shape: ${parts.filter((b) => b.kind === "work").length} work blocks, about ${workMin} minutes of work, ${Math.round(total / 60)} minutes total`}>
        {parts.map((b, i) => (
          <span key={i} title={`${b.label} · ${Math.round(b.seconds / 60 * 10) / 10} min`}
            style={{
              flexGrow: b.seconds, flexBasis: 0, minWidth: 2,
              height: b.kind === "work" ? "100%" : b.kind === "recovery" ? "30%" : "45%",
              background: b.kind === "work" ? color : b.kind === "recovery" ? `color-mix(in srgb, ${color} 45%, white)` : "#c9ccc5",
            }} />
        ))}
      </span>
      <span className="flex justify-between font-mono text-[10.5px] text-muted-foreground">
        <span>~{workMin} min work</span><span>~{Math.round(total / 60)} min total</span>
      </span>
    </span>
  );
}
