import { KIND_LABEL, QUALITY_KINDS, kindColor, type SessionKind } from "@/lib/workout-style";

/** Filled for quality and long runs; a tinted pill with a type dot for everything else. */
export function KindPill({ kind, label }: { kind: SessionKind; label?: string }) {
  const { color, tint } = kindColor(kind);
  const filled = QUALITY_KINDS.includes(kind);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-px text-[11px] font-semibold leading-4 whitespace-nowrap"
      style={filled ? { background: color, borderColor: color, color: "var(--type-on)" } : { background: tint, borderColor: "transparent", color }}
    >
      {!filled && <span aria-hidden="true" className="size-1.5 rounded-full" style={{ background: color }} />}
      {label ?? KIND_LABEL[kind]}
    </span>
  );
}
