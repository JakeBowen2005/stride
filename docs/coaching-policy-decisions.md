# Coaching policy decisions

These are deterministic Stride defaults for one athlete, not universal exercise-science rules. See `training-principles.md`, the distance-specific training-science documents and `ARCHITECTURE.md` for the existing training rationale. The exact templates and evidence thresholds below are engineering policy; those documents do not establish that these numbers are optimal for every runner.

## Session controls and approval

Unrun prescribed days can be skipped, replaced or moved to a later unrun easy/rest day in the block. Completed activities are immutable. Every proposed schedule is validated against rest preferences, hard-day spacing and the saved weekly mileage budget; rejected requests roll back completely. Originals and explanations remain available. A move removes the source rather than adding another workout.

The UI generates an inactive persisted preview. Approve atomically activates it; Make it lighter uses the existing recovery-load policy (70% of baseline) without changing training paces. A changed date, goal, athlete preferences, activities, progression or active schedule invalidates approval. The legacy generate API remains an immediate-activation compatibility endpoint.

## Program and phase selection (ladder-v2)

Progression belongs to a versioned distance program and category, rather than a global level. Existing unscoped records belong to the former 5K ladder. A new distance starts at level 1, preserving a demonstrated category pace only when its workout date is within 84 days. Returning to an existing program resumes its own level; workout feedback updates the program that prescribed it. These are conservative transfer rules, not evidence that fitness disappears on day 85.

Base sessions use two shorter threshold repetitions (at least five minutes) or four short intervals. Build adds duration/repetitions within the program. Peak half/marathon work consolidates threshold minutes into two longer repetitions; short races change interval distance. Taper uses two four-minute threshold repetitions or three short intervals. Work pace is unchanged across these variants. Mileage/general/ultra threshold programs begin with 2×6 minutes, 5K/10K with 2×8, half/marathon with 2×10; each four-level band adds a repetition while intermediate levels extend duration. Existing 5K build templates are preserved. All are subject to the existing budget fitter; level does not override available mileage. Ultra hill and long-run periodization remains in the existing dedicated modules.

The 84-day transfer window follows the existing calibration lookback. Rep counts, durations and phase reductions are Stride heuristics motivated by gradual exposure, specificity and lower taper volume, with no claim of experimentally validated dose equivalence between levels/programs. No goal-time prediction is treated as proof of demonstrated fitness.
