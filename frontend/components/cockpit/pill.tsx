import { KIND_LABEL, QUALITY_KINDS, kindColor, type SessionKind } from "@/lib/workout-style";

/** Filled for quality and long runs, outlined for everything else. */
export function KindPill({ kind, label }: { kind: SessionKind; label?: string }) {
  const { color, tint } = kindColor(kind);
  const filled = QUALITY_KINDS.includes(kind);
  return (
    <span
      className="inline-flex items-center rounded-full border px-2 py-px text-[11px] font-medium leading-4 whitespace-nowrap"
      style={filled ? { background: color, borderColor: color, color: "#fff" } : { background: tint, borderColor: color, color }}
    >
      {label ?? KIND_LABEL[kind]}
    </span>
  );
}
