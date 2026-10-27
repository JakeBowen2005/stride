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
    <div className="glass mx-auto my-2 flex min-h-[70vh] w-full max-w-xl flex-col p-5 sm:my-6 sm:p-8">
      <div className="mb-8 space-y-2">
        <p className="text-xs font-semibold text-muted-foreground">Step {step + 1} of {totalSteps}</p>
        <Progress value={progress} className="h-1.5 [&_[data-slot=progress-indicator]]:bg-[var(--accent-warm)]" />
      </div>

      <div className="flex-1 space-y-6">
        <div>
          <h1 className="display">{title}</h1>
          {subtitle && (
            <p className="mt-2 text-sm text-muted-foreground">{subtitle}</p>
          )}
        </div>

        {children}
      </div>

      <div className="flex items-center justify-between pt-8">
        {step > 0 ? (
          <Button variant="ghost" size="lg" onClick={onBack}>
            Back
          </Button>
        ) : (
          <div />
        )}
        <Button size="lg" onClick={onNext} disabled={nextDisabled}>
          {nextLabel}
        </Button>
      </div>
    </div>
  );
}
