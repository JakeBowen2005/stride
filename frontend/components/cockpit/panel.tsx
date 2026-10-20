import { useId } from "react";
import { cn } from "@/lib/utils";

/** Dark header bar over a white body: the cockpit's basic container. */
export function Panel({ label, meta, accent, className, bodyClassName, children }: {
  label: string; meta?: React.ReactNode; accent?: string; className?: string; bodyClassName?: string; children: React.ReactNode;
}) {
  const id = useId();
  return (
    <section className={cn("panel", className)} aria-labelledby={id}>
      <header className="panel-head" style={accent ? { boxShadow: `inset 3px 0 0 ${accent}` } : undefined}>
        <h2 id={id}>{label}</h2>
        {meta != null && <span className="meta">{meta}</span>}
      </header>
      <div className={cn("p-3", bodyClassName)}>{children}</div>
    </section>
  );
}

/** Label / big mono number / one status line. Missing values render "—". */
export function StatCell({ label, value, sub, tone, size = "md" }: {
  label: string; value?: React.ReactNode; sub?: React.ReactNode; tone?: string; size?: "sm" | "md";
}) {
  return (
    <div className={cn("min-w-0", size === "sm" ? "px-3 py-1.5" : "px-3 py-2")}>
      <div className="stat-label">{label}</div>
      <div className={cn("num mt-0.5 font-semibold leading-tight", size === "sm" ? "text-base" : "text-xl")} style={tone ? { color: tone } : undefined}>{value ?? "—"}</div>
      {sub != null && <div className="truncate text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

/** Dark label strip over components that already render their own Card. */
export function Section({ label, meta, accent, className, children }: {
  label: string; meta?: React.ReactNode; accent?: string; className?: string; children: React.ReactNode;
}) {
  const id = useId();
  return (
    <section className={cn("section-stack", className)} aria-labelledby={id}>
      <header className="panel-head" style={accent ? { boxShadow: `inset 3px 0 0 ${accent}` } : undefined}>
        <h2 id={id}>{label}</h2>
        {meta != null && <span className="meta">{meta}</span>}
      </header>
      {children}
    </section>
  );
}
