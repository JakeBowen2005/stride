"use client";

import { cn } from "@/lib/utils";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

interface DayPickerProps {
  selected: number[];
  onChange: (days: number[]) => void;
  label?: string;
  single?: boolean;
}

export function DayPicker({
  selected,
  onChange,
  label,
  single = false,
}: DayPickerProps) {
  function toggle(day: number) {
    if (single) {
      onChange([day]);
      return;
    }
    if (selected.includes(day)) {
      onChange(selected.filter((d) => d !== day));
    } else {
      onChange([...selected, day]);
    }
  }

  return (
    <div className="space-y-2">
      {label && (
        <label className="text-sm text-muted-foreground">{label}</label>
      )}
      <div className="flex gap-1.5">
        {DAYS.map((name, i) => (
          <button
            key={name}
            type="button"
            onClick={() => toggle(i)}
            aria-pressed={selected.includes(i)}
            aria-label={name}
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-full border text-sm font-semibold transition-colors",
              selected.includes(i)
                ? "border-primary bg-primary text-primary-foreground"
                : "border-[var(--glass-border)] bg-[var(--glass-inner)] hover:bg-[var(--row-hover)]"
            )}
          >
            {name.charAt(0)}
          </button>
        ))}
      </div>
    </div>
  );
}
