"use client";

import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import type { GoalType } from "@/lib/types";

interface GoalOption {
  type: GoalType;
  title: string;
  description: string;
}

const GOALS: GoalOption[] = [
  {
    type: "race",
    title: "Race Goal",
    description: "Train for a specific distance and target time",
  },
  {
    type: "mileage",
    title: "Mileage Goal",
    description: "Build up to a target weekly mileage",
  },
  {
    type: "general",
    title: "General Fitness",
    description: "Run consistently without a specific target",
  },
  {
    type: "comeback",
    title: "Return from Injury",
    description: "Conservative rebuild plan to get back safely",
  },
];

interface GoalCardProps {
  selected: GoalType | null;
  onChange: (type: GoalType) => void;
}

export function GoalCards({ selected, onChange }: GoalCardProps) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {GOALS.map((goal) => (
        <Card
          key={goal.type}
          className={cn(
            "lift cursor-pointer bg-[var(--glass-inner)] shadow-none hover:bg-[var(--row-hover)]",
            selected === goal.type && "border-[var(--ring)] ring-2 ring-[var(--ring)]"
          )}
          onClick={() => onChange(goal.type)}
          role="button"
          aria-pressed={selected === goal.type}
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && onChange(goal.type)}
        >
          <CardContent className="pt-0">
            <h3 className="font-bold">{goal.title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {goal.description}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
