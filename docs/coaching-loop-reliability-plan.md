# Stride: dependable coaching from one block to the next

Reviewed October 19, 2026 against commit `3fe185760ac7c3abc103f2a5fa8f8a2e233ed8bf` (`Apply engineering and product review fixes`).

This is an implementation handoff, not a record of completed fixes. Creating this document did not change application code. The review used source inspection; the previously reported 134 passing tests and other checks were not independently rerun for this document.

## Objective and first milestone

Make this cycle dependable:

**Set goal → receive achievable block → complete, skip, or modify sessions → receive accurate evaluation → receive an appropriate next block.**

Start with Jake's single-athlete mileage-building workflow, including the saved destination of 75 miles/week. The destination is not an instruction to prescribe 75 immediately. Preserve race, taper, recovery, and ultra functionality while improving the foundation.

The first delivery is a complete mileage-building cycle through two blocks, with evidence explaining why the second block builds, holds, or reduces training. Complete that before expanding race-specific libraries or adding dashboard features.

## Instructions for the implementing agent

1. Finish your current task before starting this work. Inspect the branch, working tree, recent commits, and this document's baseline commit. Re-read the current implementation; do not assume these findings remain unchanged.
2. Read `CLAUDE.md`, `ARCHITECTURE.md`, applicable `AGENTS.md` files, `docs/training-principles.md`, and `docs/workout-progression-system.md`. Treat older Strava-era handoffs as historical context. Follow the frontend's installed-version documentation requirements when editing Next.js code.
3. Review each finding and mark it confirmed, already fixed, or superseded. Identify contradictions between research documents and implemented policies. Resolve routine implementation decisions yourself; explain material training-policy choices and avoid presenting unverified heuristics as universal science.
4. Implement in focused stages below. Add meaningful regression tests with each behavior change. Keep training decisions in deterministic code and use the LLM to explain the resulting decisions.
5. Preserve the improvements listed below. Do not change workout intensity merely to fix terminology or displayed labels. The recent pace-consistency work deliberately restored the original intensity calculation after an unintended slowdown.
6. Use isolated databases and mocked Garmin/Anthropic services for verification. Do not reset Jake's database, rewrite real training history, perform a live re-import, or call paid/external services merely to test a change. Test schema changes on a disposable copy.
7. Review the final diff and the entire data flow, not only individual functions. Report completed stages, checks actually run, policy decisions, and remaining limitations. Do not mark this plan complete just because existing tests pass.

## Already implemented: preserve rather than duplicate

The baseline now includes:

- Real profile/preferences displayed in Settings; the obsolete Settings pace cards are removed.
- Readiness, wellness trends, race predictions, weekly progress, and inline post-run feedback on Today.
- Stale-plan handling and completed-week hiding on the Plan page.
- Shared frontend `lib/api.ts`, with an intentional single-athlete `USER_ID`.
- Pacing-guide keys aligned with workout values through `effective_paces()`; per-repetition split-time descriptions; legacy guide-key fallbacks.
- A labeled feel scale: low means the run felt bad, high means it felt good.
- Removal of the mock activity-review route and unused mock components/data. The onboarding route still exists and still needs persistence.
- Sequential feedback resubmission protection, feel-rating validation, feedback saved before the coach call, and LLM fallback behavior.
- Resumable first Garmin import, rate-limit backoff, authentication handling, SQLite WAL/indexes, and more efficient activity lookup.
- LAN password protection, test database isolation, API tests, and `.github/workflows/ci.yml`.

Multi-user authentication, official Garmin webhooks, a job queue, and a Postgres/Alembic migration are separate scaling work in `ARCHITECTURE.md`. They are not prerequisites for this single-athlete milestone.

## Priority 1: make mileage goals and constraints govern the plan

### Relevant code

- `backend/app/api/users.py`: `GoalData`, `set_goal()`.
- `backend/app/api/plans.py`: `generate_training_plan()`, goal snapshot.
- `backend/app/core/plan_engine.py`: `generate_plan()`, `_calculate_target_mileage()`, `_build_week()`, `_distribute_mileage()`, `_rebalance_ultra_easy_days()`.
- `backend/app/core/special_weeks.py`: `enforce_no_back_to_back_hard()`.

### Confirmed gaps

- `target_weekly_mileage` is saved and returned by the goal API, but is absent from the generator input and plan goal snapshot.
- `_calculate_target_mileage()` uses `min(peak * 0.9, current * 1.5)` as a ceiling. This can permanently prevent building above the historical peak, and can produce a zero ceiling when history is zero.
- Fixed ladder workouts bypass the legacy library's mileage eligibility filtering. The three-mile minimum for easy runs can then force the scheduled week above its calculated budget.
- `_distribute_mileage()` associates `[wo1_miles, wo2_miles]` by position. A threshold-only week stores its workout in `workout2`, but its sole assignment is budgeted against `wo1_miles`.
- Fixed long-run templates can replace the allocated long-run distance without a complete rebalance. A later step grows the long run simply to force the next week above the previous week.
- The returned `target_mileage` becomes the sum of scheduled runs, concealing whether the original budget was exceeded.
- The hard-day safeguard is applied per generated week. It permits any adjacent long-run pair rather than only an explicitly planned ultra pair.

### Changes

1. Carry the mileage destination through validated goal input, engine arguments, persisted snapshot, and UI. Define separate concepts for demonstrated baseline, permitted next-block load, and long-term destination.
2. Make historical peak inform progression rather than act as a permanent ceiling. Define behavior for approaching/holding the destination, a destination below current volume, zero history, and inconsistent schedule preferences.
3. Establish a baseline policy using recent completed training and interruptions. Preserve the recent correction that includes non-running time in rolling averages; do not inflate a baseline by dividing only over days containing runs. Add explicit fallback behavior for insufficient history and invalid/non-finite pace estimates.
4. Choose and size sessions within the weekly budget. Allocate by actual day/session identity, not positional workout numbers. Include warmup, recovery running, and cooldown using a documented accounting policy. Keep segment sums, descriptions, and stored totals consistent.
5. Remove unconditional week-to-week growth and long-run deficit compensation. Prefer a smaller workout, fewer quality sessions, or shorter easy days when the available budget cannot support the proposed schedule.
6. Retain intended budget and scheduled total separately. Define rounding tolerance explicitly and repair rounding without creating a load increase. For a partial current week, account for already completed mileage and prescribe only the remaining appropriate load; do not count hypothetical historical prescriptions as completed training.
7. Introduce a shared validator used after generation and all schedule mutations. Check weekly and individual-session limits, hard-day separation, availability, quality-work budget, and progression levers across week/block boundaries. Include relevant actual recent hard efforts, not only planned types. Mark intentional ultra back-to-back blocks explicitly and validate the easy/recovery space around them.

### Acceptance

- A goal of 75 changes the long-term direction without forcing the next block to 75.
- Plans fit their budget for low mileage, high ladder levels, threshold-only weeks, limited running days, and ultra weekends.
- Reaching the destination stops automatic growth; changing to a lower destination has defined behavior.
- Impossible schedules are explained without silently violating constraints.
- Rest days and completed history are respected; Sunday/Monday conflicts are covered.

## Priority 2: evaluate actual work accurately before progressing it

### Relevant code

- `backend/app/services/lap_analyzer.py`: `_find_work_laps()`, `summarize_workout()`.
- `backend/app/services/pace_calibrator.py`: `calibrate_paces()` and text extractors.
- `backend/app/core/workout_evaluator.py`: `evaluate_workout()`, `identify_workout_type()`, `extract_rep_count()`, `determine_starting_level()`.
- `backend/app/core/workout_ladders.py`: prescription templates and formatting.
- `backend/app/api/plans.py`: `_detect_workout_category()`, `_extract_prescribed_pace()`, feedback evaluation.
- `backend/app/models/plan.py`, `backend/app/models/progression.py`.

### Confirmed gaps

- Structured Garmin laps are rendered as text and then parsed again for training decisions. Category and prescribed pace are also inferred from presentation strings.
- `evaluate_workout()` records rep counts without using completion as a condition for advancement. Its zero defaults can make missing evidence look like perfect execution.
- In the earlier isolated review, prescribed `6x800m` with only `3x800 (2:58, 2:58, 2:58)`, target 360 seconds/mile, and feel 8 returned `advance`. Feel 8 with no execution metrics also returned `advance`. These examples should become regressions; reproduce against your current version first.
- Recalibration is checked before large-fade regression. Whole-run average pace is used when work splits cannot be parsed, even though it may include warmup/cooldown.
- Feedback chooses the longest activity as the workout evidence. On split-recording days that can be the warmup or cooldown.
- The calibration result is discarded unless `interval_pace` exists, losing valid threshold-only evidence. Continuous and broken threshold evidence is not consistently distinguished.

### Changes

1. First add regression tests and conservative evidence/completion gates to the existing evaluator. Do not wait for the larger representation change to stop false advancement.
2. Add a versioned structured prescription and execution representation: category, format, ladder identity/version, work/recovery segments, repetitions, distance/duration, numeric pace range, actual work measurements, evidence source, confidence, and matched activity IDs. Use canonical units and generate display text from the structure.
3. Have lap analysis produce structured results for both evaluation and calibration. Retain legacy text parsing for old data; uncertain old rows should remain uncertain instead of receiving invented evidence. Preserve raw laps and original prescriptions.
4. Evaluate completion and evidence sufficiency before pace-based advancement/recalibration. Consider fade and subjective response before faster paces can trigger progression. Missing metrics or a different session means an explained hold/uncertain result, not assumed success or automatic fitness regression.
5. Match work across all activities recorded for the session. Keep daily mileage aggregation separate from identification of quality segments. Do not compare a mixed whole-run average with the prescribed work pace.
6. Handle time intervals, continuous tempo, distance repeats, and combination sessions explicitly. Normalize comparisons by relevant segment units; do not compare unlike rep durations as if raw seconds represented equivalent fade.
7. Keep the feel scale semantics unchanged. Do not reinterpret it as effort/RPE. Distinguish an incomplete session due to schedule from physiological failure where evidence permits.
8. Calibrate each category independently, with recency, evidence quality, and minimum evidence policies. Do not use short sprint reps as VO2 interval evidence. Review goal-pace blending in `_build_current_paces()`; additional mileage alone does not prove the ability to execute goal training speeds.
9. Preserve `effective_paces()`, guide/display consistency, and split-time formatting. Separate any justified training-policy change from label cleanup and show numeric before/after examples. The current `tempo = threshold * 0.96` was deliberately restored in the baseline; do not silently revert it while renaming fields.
10. Persist evaluation evidence, reason, applied change, and policy version. Feed the same result to the coach and UI. Enforce one progression lever per decision; current excellent-session/recalibration paths can increase both level and pace.

### Acceptance

- Partial or missing execution cannot advance a ladder.
- A short fast subset with substantial fade cannot trigger an unchecked recalibration.
- Warmup/workout/cooldown recordings yield correct daily mileage and work-only evaluation.
- Threshold-only data remains usable; legacy plans still render.
- Every decision explains the evidence used or the reason evidence was insufficient.

## Priority 3: make adjustments and block lifecycle durable

### Relevant code

- `backend/app/api/plans.py`: `submit_feedback()`, `_load_progression_state()`, `_update_progression_from_evaluation()`, `_find_safe_easy_day()`, `_find_next_easy_day()`, `_copy_workout_to_day()`.
- `backend/app/core/plan_engine.py`: `calculate_plan_params()`, deload scheduling, `_pick_workout_progressive()`.
- `backend/app/core/workout_ladders.py`: `get_week2_variant()`.
- `backend/app/services/coach.py`, `backend/app/api/wellness.py`.
- `frontend/components/feedback-form.tsx`, `frontend/components/home/today-card.tsx`, `frontend/components/garmin-sync.tsx`.

### Confirmed gaps

- "Don't reschedule" becomes `null`; the backend can interpret that as copying the original session forward.
- `_find_safe_easy_day()` checks only neighboring workouts, not long runs/races. If it finds no safe day, code can fall back to an unchecked easy day. Candidate dates are constrained relative to the feedback date, not necessarily the current date or actual activity presence.
- `plan_adjusted` is `not is_edit`, even when no scheduled day changed.
- Sequential feedback edits are guarded, but there is no durable evaluation/event identity preventing concurrent or regeneration-related duplicate application.
- `_load_progression_state()` commits after the old plan is deactivated but before the replacement is fully generated/persisted. A later failure can leave no active plan.
- Overlapping regeneration reuses the block number. Normal rolling use can keep overlapping; elapsed/completed blocks and deload cadence need explicit semantics.
- Deload session reduction requires week zero not to overlap today, while default plans start in the current week. Inspect both mileage reduction and workout reduction together: a deload label must reflect an actual coherent deload.
- Week two previews the next ladder level regardless of week-one execution. There is no persisted complete block assessment.
- The coach is called before evaluation and schedule changes, so it cannot explain the final deterministic action.
- Wellness falls back to an older row under `today`. Home inline feedback updates local feedback only, and sync reloads dashboard data only for new/merged activities; changes to upcoming sessions or wellness can remain stale.

### Changes

1. Validate explicit actions: skip without rescheduling, move original, or substitute another category. Respect the chosen action without guessing intent from notes when an explicit action exists.
2. Route every mutation through the shared validator. Never fall back to an unsafe date. Do not overwrite completed sessions, actual training, rest preferences, taper restrictions, or race days. Return a useful reason when no slot exists.
3. Preserve original prescription, adjustment reason, timestamps, source session, and changed fields. Return actual changed dates and accurate `plan_adjusted` information.
4. Keep feedback saving independent of coach availability. Apply evaluation/progression and deterministic schedule changes transactionally with a durable deduplication identity. Specify feedback-edit behavior, crash/retry behavior, and concurrent submission behavior. Do not blindly replay side effects when notes are edited.
5. Make replacement-plan activation atomic and enforce one active plan per athlete appropriately for SQLite. Change helper commits to flush/outer transaction ownership where necessary. Failed generation must leave the prior plan usable.
6. Define block identity, regeneration versus next-block generation, assessment window, and completion rules. Preserve completed sessions and feedback during overlap; avoid counting the same real session as a fresh progression event in multiple plan versions.
7. Base the next block on an explicit assessment: completed versus planned volume, quality execution, interruptions, feel trends, and recent available recovery context. Return build/hold/reduce/recovery with reasons. Missing feedback is not a bad rating; missed training is not mileage debt to make up.
8. Schedule deloads from completed training history and policy, not accidental regeneration counts. Reconsider future week-two sessions after hold/regress results without rewriting completed work.
9. Distinguish fresh, stale, and absent wellness. Keep Garmin load/readiness and Stride mileage-derived metrics labeled separately, including their different time windows. Do not let missing/stale values imply readiness. Use recovery trends conservatively; document the chosen policy rather than hardcoding a diagnosis from one reading.
10. Generate the coach explanation after the evaluation/action, passing its structured reason. Preserve saved feedback and the deterministic result if the LLM fails.
11. Refresh affected home/plan data after feedback and wellness updates, including no-new-run syncs. Ensure local component state follows a changed date/session or refreshed feedback rather than only its first props.

### Acceptance

- Explicitly skipping never creates an unwanted replacement session.
- No safe reschedule slot produces an explanation, not a hard-day stack.
- Duplicate/concurrent/retried feedback applies each evaluation/adjustment once.
- Replacement failures preserve the old active plan.
- Deloads occur during normal rolling use; regeneration alone does not earn progression.
- Successful, mixed, fatigued, and interrupted blocks produce appropriately different next blocks.
- Coach wording and both screens agree with the persisted decisions after reload.

## Priority 4: connect race goals and phases to session selection

### Relevant code

- `backend/app/core/workout_ladders.py`: `get_ladder()`.
- `backend/app/core/workouts.py`: libraries and `requires_mp_readiness`.
- `backend/app/core/periodization.py`, `backend/app/core/pacing.py`, `backend/app/core/special_weeks.py`.
- `backend/app/models/progression.py`, goal-change handling in `backend/app/api/users.py`.

### Changes

1. `get_ladder(category, distance)` currently returns the same 5K ladders for all distances. Introduce goal/phase-aware selection while reusing genuinely shared stimuli. Scope/version progression state so a level has a defined meaning for the selected program.
2. Mileage/general goals must not silently default to advanced 5K race-specific sessions. Define the role and permitted number of quality days while building volume.
3. Make base/build/peak/taper/recovery affect workout content and quality volume, not only labels and mileage multipliers. Count quality long-run work in the same weekly stress budget as weekday workouts.
4. Enforce readiness metadata when present; `requires_mp_readiness` must either control eligibility or be replaced by an explicit tested rule. Retain terrain-specific ultra work and intentional back-to-back recovery constraints.
5. On a goal change, preserve demonstrated fitness but assess how much specific work transfers. Do not blindly reuse a ladder level or abruptly introduce a new high-intensity program.
6. Review research conflicts and support new numerical policies with appropriate evidence. This plan specifies software behavior, not a universal prescription for ramp rates or training intensity.

### Acceptance

The same athlete with different goals/phases receives appropriately different sessions. Existing race-week, taper, recovery, and ultra tests remain valid or are deliberately updated with explained policy changes.

## Priority 5: finish onboarding and the visible control loop

### Relevant code

- `frontend/app/onboarding/page.tsx`: `handleFinish()` still only navigates home.
- `backend/app/api/users.py`: `onboard_user()` always creates a new user despite its create/update docstring.
- `frontend/lib/api.ts`, `frontend/lib/types.ts`, onboarding components.
- `frontend/app/plan/page.tsx`, `frontend/components/plan-day.tsx`, `frontend/components/home/today-card.tsx`, `frontend/components/goal-editor.tsx`.

### Changes

1. Wire profile/preferences → goal → initial generation with validated payloads, loading/error states, and safe retry behavior. Re-running setup must update the intended single athlete and preserve their Garmin history, not create a new profile that the fixed frontend user ID never reads.
2. Align frontend/backend enums and units (`half_marathon`/`half`, `general_fitness`/`general`, comeback naming, kilometers representation, weekday numbering). Respect workout-format and schedule preferences or clearly describe supported behavior.
3. Keep the working real Settings profile and inline Today feedback. Remove remaining presentation hardcodes where appropriate, such as the home greeting. Do not recreate the deleted mock review route.
4. Persist session status and implement skip/replace/move controls for sessions with no activity. The current Plan mapping sets `skipped: false`; existing feedback forms require an actual run. Distinguish not logged, intentionally skipped, replaced, and completed without inventing a workout failure.
5. Show evaluation reasons, original versus adjusted prescriptions, and block assessment/next-block rationale. Add preview/approval or "make lighter" on top of reliable generation and atomic activation, preserving the athlete's control.
6. Handle new athletes without imported history through an explicit onboarding baseline or clear prerequisites. Do not imply manual logging works without an implemented path.
7. Preserve completed/history views and meaningful API errors. A failed request should not masquerade as no activities or no plan. Keep the LAN password gate and intentional single-athlete architecture; full account/tenancy work remains separate.

### Acceptance

The complete cycle can be performed through Today/Plan/Settings, survives reloads, explains changes, and does not require database edits. Onboarding failures are retryable without duplicate users/goals/plans.

## Priority 6: verify continuously and review the finished loop

Use `backend/tests/conftest.py`, existing API/periodization/lap/PR/wellness tests, and the CI workflow as the starting point. The baseline's 134 reported passing cases include parameterized cases; they do not establish coverage of every coaching decision. Add regressions alongside priorities 1–5 rather than postponing tests to this stage.

Suggested focused test modules, adjusted to the resulting design:

- `test_plan_constraints.py`: actual budget enforcement, session sizing, partial weeks, boundary spacing.
- `test_workout_evaluator.py`: complete/partial/ambiguous work, time intervals, combinations, fade, missing evidence.
- `test_plan_adjustments.py`: explicit skip/move actions, unsafe slots, repeat/concurrent feedback.
- `test_block_transitions.py`: atomic generation, block identity, deloads, interruptions, goal transitions.

### Required scenario matrix

| Scenario | Expected behavior |
|---|---|
| Low current mileage, destination 75 | Achievable block; no jump to destination |
| Destination reached or lowered | Defined maintenance/reduction; no endless ramp |
| Zero history/peak or missing pace data | Explicit baseline/fallback; no zero-ceiling or non-finite failure |
| High ladder level with low mileage | Session resized/reselected within budget |
| Threshold-only, limited-day, and fixed long-run weeks | All session distances accounted for correctly |
| Midweek generation with completed runs | Remaining prescription accounts for real work already done |
| Sunday/Monday or block-boundary conflict | Shared validator catches actual/planned hard-day adjacency |
| Partial reps at target pace | No false advancement |
| Feel only; no trustworthy work evidence | Explained insufficient-evidence hold |
| Fast early reps with large fade | No unchecked recalibration |
| Separate warmup/workout/cooldown recordings | Correct totals and work-only evaluation |
| "Don't reschedule" | No replacement session |
| No safe replacement date | Explanation without unsafe fallback |
| Duplicate/concurrent submission or retry after failure | One applied evaluation/adjustment |
| Regeneration overlaps completed work | History/feedback preserved and no duplicate progression |
| Replacement generation fails | Prior active plan remains usable |
| Deload due under default current-week generation | Coherent reduced-load week actually scheduled |
| Goal/distance change | Appropriate transition and progression context |
| Missing/stale wellness or wellness-only sync | Conservative handling and refreshed UI |
| Coach unavailable | Feedback, evaluation, and deterministic adjustments survive |
| Two completed blocks with different outcomes | Next block responds to evidence and explains why |

### Verification and final review

Run applicable backend tests and the frontend checks already specified by CI (type-check, lint, production build). Exercise a seeded, isolated browser scenario covering goal input → generation → activity evidence → feedback → adjustment → next block. Use a controllable clock for date-sensitive tests and test relevant local-midnight/ISO-year boundaries.

Review additive migrations on a disposable old-schema database. Historical plans without structured prescriptions must still load, and uncertain history must not be upgraded into falsely certain evaluations. Audit new uniqueness rules against existing data before applying them.

Perform an engineering review of transactions, matching, units, progression idempotency, schema compatibility, and cross-boundary constraints. Perform a product review of whether the athlete can understand and control the decisions. Separate reviewer agents may be used if explicitly authorized by the user or applicable instructions; otherwise do both review passes without delegation. Verify findings before applying them, then rerun affected checks.

Final handoff should name completed priorities, explain policy/pace changes with examples, list actual verification results, and state remaining gaps. Update `ARCHITECTURE.md` and relevant training/design docs only as needed to describe the final behavior accurately.

## Scope mapping to the six original gaps

| Original gap | Work above |
|---|---|
| Training principles not enforced everywhere | Priority 1 validator and allocation; priority 3 mutations |
| Goal inputs do not drive prescriptions | Priority 1 mileage destination; priority 4 race specificity |
| Fragile workout understanding | Priority 2 shared structure, confidence, and evaluation |
| Adaptation narrower than the vision | Priority 3 block assessment/lifecycle and durable decisions |
| Product depends on founder setup | Priority 5 real onboarding and session controls; preserve intentional single-athlete scope |
| Validation trails coaching complexity | Regression tests throughout; priority 6 integration and final reviews |
