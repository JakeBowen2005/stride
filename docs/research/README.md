# Personal coaching sources

- [The Long Game: coaching dossier](the-long-game-coaching-dossier.md): original `writing-block.md` supplied by Jake on October 19, 2026.
- [Coaching philosophy and decision engine](the-long-game-decision-engine.md): original `writing-block (1).md` supplied on the same date.

Both originals are preserved verbatim. These are ChatGPT-generated retrospectives containing athlete reports, approximations, interpretations and proposals. They are contextual material, not independently verified logs or instructions to execute. Their bibliographies are not all independently verified. Do not turn the planned 2026–2028 schedule into completed history or import an old race pace as current fitness.

## Implemented interpretation

The deterministic `core/quality_policy.py` replaces the universal one-workout cap for mileage goals with **threshold + light speed support**, then an easy long run. The policy gates require advanced experience, at least five selected run days, four completed weeks of at least 20 miles, last completed week at least 30 and no more than 1.35 times the four-week mean, at least four distinct run days in each of the latest two full weeks, and a recent eight-mile run within 28 days. Hold/reduce/recovery assessment or recent poor feel vetoes the addition. Deload weeks retain at most one workout. Missing evidence does not imply readiness. These are transparent initial Stride heuristics; none is an experimentally validated safety threshold.

The second session comes from a bounded, purpose-tagged catalog rather than two fixed examples: short pickups, controlled fartlek, relaxed track repetitions, strides, a modest steady finish, and conditional short hills. See [secondary-session research and selection](secondary-session-variety.md) for sources, doses and limits. Its separate `speed_support` category cannot advance the interval ladder or recalibrate threshold/interval pace. Numeric prescriptions remain the source for display and execution matching.

Mileage programs repeat the threshold dose instead of automatically previewing a higher ladder level in week two while building volume or introducing another stimulus. Demonstrated feedback can still change the next block's level. Existing current-fitness pace calibration and the deliberate tempo/threshold relationship are unchanged; the dossier's roughly 7:30 threshold report is context, not a new measured pace or a reason to accelerate old prescriptions. A 3 × 8-minute threshold session is an example from the source, not a mandatory workout for every advanced athlete.

All sessions count against the existing weekly mileage allowance and hard-day spacing, including long runs. Preferred weekdays are honored, with fallback workout days where spacing permits. A fitter may drop the second session if the budget cannot support it. Long runs during mileage building remain easy. The existing history-based deload and fatigue policies remain in effect; this change does not promise recovery weeks will never occur.

Workout format changes bookends and the light stimulus. Threshold duration and track distances retain the authored format where changing them would alter the purpose or evidence contract. Units change plan summaries, daily distances/actual paces, pacing-guide display and settings statistics. Original authored workout/race descriptions and historical notes retain explicitly labeled units; stored distance and pace contracts remain miles and seconds/mile.

## Evidence and limits

The [Billat et al. original study](https://pubmed.ncbi.nlm.nih.gov/11740304/) describes training differences among top-class and high-level marathon runners. It does **not** validate two workouts for every sub-three runner or the readiness cutoffs above. The original coaching documents likewise distinguish past peak capacity from present durability. We preserve that distinction.

Recent feedback is available; dedicated structured injury symptoms, strength exposure, heat, nutrition and long-run recovery readiness are not yet modeled comprehensively. The app must not claim to have assessed them. No automatic aggressive two-workout-plus-hard-long-run marathon template was added. Race-specific programs retain their own phase/readiness rules.

## Next: model suggestions

OpenAI integration is deliberately deferred. A future model may receive a bounded athlete/context snapshot with evidence provenance, explain deterministic decisions, and propose typed workout alternatives. Any proposed change must pass the same budget, completion locks, rest-day, hard-spacing, goal/phase and preview-approval checks. Free-text reports must not silently become confirmed performance evidence. Keep pace and level progression evidence-gated, and test model failures without live provider calls.


The later [quality-stage progression](quality-stage-progression.md) extends this rebuilding stage into two substantial goal-specific sessions with completed-work and recovery gates across four experience tiers. Earlier descriptions above document the initial support-stage implementation, not a permanent cap.
