import type { Split } from "@/lib/types";

export function SplitsTable({ splits }: { splits: Split[] }) {
  if (splits.length === 0) return null;

  return (
    <div className="space-y-1">
      <h4 className="text-sm font-medium">Splits</h4>
      <div className="space-y-0.5">
        {splits.map((split) => (
          <div
            key={split.mile}
            className="flex items-center justify-between rounded px-2 py-1 text-sm odd:bg-secondary/30"
          >
            <span className="text-muted-foreground">Mile {split.mile}</span>
            <div className="flex items-center gap-4">
              <span className="font-mono">{split.pace}</span>
              {split.heart_rate && (
                <span className="font-mono text-xs text-muted-foreground">
                  {split.heart_rate} bpm
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
