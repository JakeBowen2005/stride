"use client";

import { cn } from "@/lib/utils";

interface FeelRatingProps {
  value: number | null;
  onChange: (value: number) => void;
}

export function FeelRating({ value, onChange }: FeelRatingProps) {
  return (
    <div className="space-y-2">
      <div className="flex justify-between gap-1">
        {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onChange(n)}
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-md border font-mono text-sm font-medium transition-colors",
              value === n
                ? "border-foreground bg-foreground text-background"
                : "border-border hover:bg-secondary"
            )}
          >
            {n}
          </button>
        ))}
      </div>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>terrible</span>
        <span>amazing</span>
      </div>
    </div>
  );
}
