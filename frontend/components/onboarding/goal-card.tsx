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
    type: "general_fitness",
    title: "General Fitness",
    description: "Run consistently without a specific target",
  },
  {
    type: "return_from_injury",
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
            "cursor-pointer transition-colors hover:bg-secondary/50",
            selected === goal.type && "border-foreground bg-secondary/50"
          )}
          onClick={() => onChange(goal.type)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && onChange(goal.type)}
        >
          <CardContent className="pt-4">
            <h3 className="font-medium">{goal.title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {goal.description}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
