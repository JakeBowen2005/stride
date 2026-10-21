# Offline coaching evaluation cases

`backend/tests/fixtures/coaching_cases.json` is a versioned, deterministic set of synthetic evidence scenarios and reviewed example responses. It covers truncated repetitions, a different quality session, split recordings, goal-pace work, taper work, effort-based trail climbing, missing feel, poor feel and a walk after a workout. All normal tests disable real Garmin and model providers.

Run `cd backend && venv/bin/pytest -q tests/test_coaching_evals.py tests/test_execution_assessment.py`.

The tests build the genuine local coaching context, check objective prescription/execution/phase/feedback facts, substitute a bounded mock model response and verify no schedule or progression mutation occurred. The example responses illustrate the desired coaching meaning; they are **not evidence that a live model produces those answers**. The existing model-boundary tests separately reject invented candidate IDs, unknown research IDs, stale advice acceptance and provider failures.

Before a later model or prompt change is promoted, compare its responses against this case set in an explicitly authorized, budgeted staging run. Review at least: source activity identity; factual pace/rep/duration/feel claims; recognition of partial versus different work; unknown recovery when feel is missing; no unsupported speed inference from hills; no taper escalation; no fabricated application of changes; and whether any suggested candidate matches the deterministic policy. Retain case IDs, model/prompt versions, failures and token usage. Do not call an offline mocked test result a live-model quality score.

## Evidence rules added in this change

- A changed rep shape with less than 80% of planned hard-work minutes stays a partial attempt unless the athlete explicitly confirms substitution. Eighty percent is a Stride matching heuristic to stop truncated work bypassing completion checks; it is not a physiologic safety threshold. Comparable different work holds the prescribed ladder and does not infer intent from laps alone.
- Work minutes sum every segment and its rep count. Mixed ladders do not use median rep length multiplied by total reps.
- Block assessment reports prescribed quality verified, substituted, unknown and incomplete separately. Workout distance alone never verifies hard work. Paced threshold/interval work additionally needs target-pace evidence and controlled execution; effort-based hills verify the prescribed duration without inventing flat-pace evidence. Missing subjective feel is unknown, not a negative rating.
- Easy long-run distance adherence is separate from hard-work evidence; the 90% distance criterion is an authored Stride adherence rule. A different session is not silently counted as successful completion of the prescribed ladder. The existing block threshold holds volume when fewer than half the prescribed quality sessions are verified, while mileage interruption and poor-feel rules retain precedence.
