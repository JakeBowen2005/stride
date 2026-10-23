import { Panel } from "@/components/cockpit/panel";
import { cn } from "@/lib/utils";

export interface Milestone {
  key: string;
  label: string;
  current: number | null;
  target: number | null;
  unit: string;
  status: "done" | "in_progress";
  est_weeks: number;
  detail: string;
}

export interface Outlook {
  milestones: Milestone[];
  gaps: { milestone: string; message: string }[];
  est_weeks_to_ready: number;
  note: string;
}

export interface BlockReview {
  decision: string | null;
  completed: string[];
  learned: string;
  changes: string[];
  why: string[];
  earned: string[];
  missing: string[];
}

function weeks(n: number) {
  return n === 0 ? "reached" : `~${n} wk${n === 1 ? "" : "s"}`;
}

/** Where the rolling blocks are heading: milestones, not a fixed 16-week plan. */
export function GoalRoute({ outlook }: { outlook: Outlook }) {
  if (!outlook.milestones.length) return null;
  return (
    <Panel label="Route to your goal" meta={outlook.est_weeks_to_ready ? `~${outlook.est_weeks_to_ready} wks` : "On track"} bodyClassName="px-3 py-2">
      {outlook.gaps.map((g) => (
        <p key={g.milestone} role="alert" className="mb-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs leading-relaxed">
          {g.message}
        </p>
      ))}
      <ol className="space-y-2">
        {outlook.milestones.map((m) => {
          const pct = m.target ? Math.min(100, Math.round(((m.current ?? 0) / m.target) * 100)) : 0;
          return (
            <li key={m.key} className="text-sm">
              <div className="flex items-baseline justify-between gap-3">
                <span className={cn(m.status === "done" && "text-muted-foreground line-through decoration-1")}>{m.label}</span>
                <span className="num shrink-0 text-xs text-muted-foreground">{m.status === "done" ? "Done ✓" : weeks(m.est_weeks)}</span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-secondary" aria-hidden="true">
                <div className="h-1.5 rounded-full bg-foreground" style={{ width: `${pct}%` }} />
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                <span className="num">{m.current ?? 0}</span> / <span className="num">{m.target}</span> {m.unit} · {m.detail}
              </p>
            </li>
          );
        })}
      </ol>
      <p className="mt-2 text-xs text-muted-foreground">{outlook.note}</p>
    </Panel>
  );
}

const DECISION_LABEL: Record<string, string> = {
  build: "Building", hold: "Holding steady", reduce: "Easing back", recovery: "Recovery block",
};

/** Last block → what we learned → what changes → why. */
export function BlockReviewPanel({ review }: { review: BlockReview }) {
  const sections: [string, string[]][] = [
    ["What you completed", review.completed],
    ["What we learned", [review.learned]],
    ["What changes next", review.changes],
    ["Earned", review.earned],
    ["Still needed", review.missing],
  ];
  return (
    <Panel label="Last block review" meta={review.decision ? DECISION_LABEL[review.decision] ?? review.decision : undefined} bodyClassName="space-y-2 px-3 py-2">
      {sections.filter(([, items]) => items.length).map(([title, items]) => (
        <div key={title}>
          <p className="stat-label">{title}</p>
          <ul className="mt-0.5 space-y-0.5 text-sm">
            {items.map((t) => <li key={t}>{t}</li>)}
          </ul>
        </div>
      ))}
      {review.why.length > 0 && (
        <details className="text-xs text-muted-foreground" open>
          <summary className="cursor-pointer">Why</summary>
          <ul className="mt-1 space-y-0.5">{review.why.map((t) => <li key={t}>{t}</li>)}</ul>
        </details>
      )}
    </Panel>
  );
}
