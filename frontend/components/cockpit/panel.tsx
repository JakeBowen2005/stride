import { useId } from "react";
import { cn } from "@/lib/utils";

function Label({ id, label, accent }: { id: string; label: string; accent?: string }) {
  return (
    <h2 id={id}>
      {accent && <span aria-hidden="true" className="dot" style={{ background: accent }} />}
      {label}
    </h2>
  );
}

/** A frosted glass panel with a quiet heading: the app's basic container. */
export function Panel({ label, meta, accent, className, bodyClassName, children }: {
  label: string; meta?: React.ReactNode; accent?: string; className?: string; bodyClassName?: string; children: React.ReactNode;
}) {
  const id = useId();
  return (
    <section className={cn("panel", className)} aria-labelledby={id}>
      <header className="panel-head">
        <Label id={id} label={label} accent={accent} />
        {meta != null && <span className="meta">{meta}</span>}
      </header>
      <div className={cn("p-3 sm:px-4 sm:pb-4", bodyClassName)}>{children}</div>
    </section>
  );
}

/** Label / big number / one status line. Missing values render "—". */
export function StatCell({ label, value, sub, tone, size = "md" }: {
  label: string; value?: React.ReactNode; sub?: React.ReactNode; tone?: string; size?: "sm" | "md";
}) {
  return (
    <div className={cn("min-w-0", size === "sm" ? "px-4 py-3" : "px-4 py-3.5")}>
      <div className="stat-label">{label}</div>
      <div className={cn("num mt-1 font-semibold leading-tight tracking-tight", size === "sm" ? "text-2xl" : "text-[26px]")} style={tone ? { color: tone } : undefined}>{value ?? "—"}</div>
      {sub != null && <div className="mt-0.5 truncate text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

/** A heading over components that already render their own Card: one glass surface. */
export function Section({ label, meta, accent, className, children }: {
  label: string; meta?: React.ReactNode; accent?: string; className?: string; children: React.ReactNode;
}) {
  const id = useId();
  return (
    <section className={cn("section-stack", className)} aria-labelledby={id}>
      <header className="panel-head">
        <Label id={id} label={label} accent={accent} />
        {meta != null && <span className="meta">{meta}</span>}
      </header>
      {children}
    </section>
  );
}
