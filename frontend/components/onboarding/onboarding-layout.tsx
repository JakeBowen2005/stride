"use client";

import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";

interface OnboardingLayoutProps {
  step: number;
  totalSteps: number;
  title: string;
  subtitle?: string;
  onNext: () => void;
  onBack: () => void;
  nextDisabled?: boolean;
  nextLabel?: string;
  children: React.ReactNode;
}

export function OnboardingLayout({
  step,
  totalSteps,
  title,
  subtitle,
  onNext,
  onBack,
  nextDisabled,
  nextLabel = "Continue",
  children,
}: OnboardingLayoutProps) {
  const progress = ((step + 1) / totalSteps) * 100;

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-lg flex-col">
      <Progress value={progress} className="mb-8 h-1" />

      <div className="flex-1 space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">{title}</h1>
          {subtitle && (
            <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
          )}
        </div>

        {children}
      </div>

      <div className="flex items-center justify-between pt-8">
        {step > 0 ? (
          <Button variant="ghost" onClick={onBack}>
            Back
          </Button>
        ) : (
          <div />
        )}
        <Button onClick={onNext} disabled={nextDisabled}>
          {nextLabel}
        </Button>
      </div>
    </div>
  );
}
