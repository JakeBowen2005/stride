# Earning a second substantial workout

A training block's age does not demonstrate adaptation. Stride now distinguishes **experience background** from the **quality stage supported by completed training**. Two substantial sessions are a developmental option, not a mandatory consequence of a fast personal best or an approved preview.

## Research context

The athlete's Long Game documents describe a progression from one controlled threshold session, through a light second stimulus, to two substantial sessions plus an easy long run. A demanding race-specific long run changes that balance.

[Esteve-Lanao et al., 2007](https://pubmed.ncbi.nlm.nih.gov/17685689/) is a small original randomized study in subelite runners examining intensity distribution. [World-class coach questionnaire/interview study, 2025](https://pubmed.ncbi.nlm.nih.gov/40278987/) reports common principles and sport-specific differences. These support reviewing the distribution and context of training; neither validates the numerical gates below or proves that every runner needs two hard workouts.

All cutoffs below are deterministic **Stride heuristics**, subject to future evaluation. Experience is training background, not a diagnosis, a race-time category or verification of professional status. Expert is an explicitly selected profile option; the analyzer never infers it from one performance.

## Stages

1. **Establish:** at most one goal-specific quality session; low-volume/comeback runners may receive none under existing readiness rules.
2. **Add support:** one primary session plus a bounded light stimulus from the sourced support catalog. Beginners need two demonstrated primary days first, intermediate one, advanced/expert zero; all still need at least four completed weeks of 15+ miles, a last week of 30+ miles for advanced/expert or 25+ for other tiers, no spike above 1.35 times the four-week mean, at least four actual run days in each of the latest two full weeks, an eight-mile run in the last 28 days and five available run days.
3. **Two quality days:** two substantial sessions coordinated for the goal and phase. The athlete must demonstrate completed work and good recovery. A past two-workout training pattern can establish this directly without repeating the light-support stage.

### Tier defaults for entering stage three

| Experience | Consistent completed weeks | Four-week baseline minimum | Successful primary days | Successful support days (unless two full dual weeks already demonstrated) | Sustained loaded weeks before planned recovery |
|---|---:|---:|---:|---:|---:|
| Beginner | 8 | 25 mpw | 4 | 4 | 3 |
| Intermediate | 6 | 30 mpw | 3 | 3 | 4 |
| Advanced | 4 | 30 mpw | 2 | 2 | 7 |
| Expert / professional | 4 | 30 mpw | 2 | 1 | 8 |

Every stable week needs at least five distinct completed run days and at least 75% of that tier's baseline minimum. The latest full week must be between 90% and 120% of the four-week baseline. At least five running days must be available in the proposed schedule. Quality history uses 56 days, with at least one successful primary and support day within 21 days, unless two completed dual weeks in the latest four full weeks establish the existing pattern.

Primary success requires matched numeric reps/duration, high/medium evidence confidence, all work completed, controlled target pace/fade, and feel at least 6/10. Matching total run mileage or a positive feel rating alone does not prove the work. Support success requires matched work completion and feel at least 6; it does not calibrate threshold or interval pace. Completed, positively rated matched hill work can establish substantial weekly tolerance without calibrating flat pace. Count distinct actual workout dates, not duplicate plans, feedback retries or previews.

Recovery requires three distinct rated actual run days in the last 14 days averaging at least 6, without a rating of 4 or below or a demonstrated recent failed workout. At least one planned long run within 28 days must reach 90% of its prescribed distance with feel at least 6; the latest completed planned long run must also have positive recovery feedback. Missing data stays unknown. Hold/reduce/recovery assessments, comeback, recent fatigue, poor feel or failed work veto promotion and can return the athlete to one quality session.

## Coordinating goals and stress

- 5K/10K: current-fitness intervals plus threshold in the two-quality stage.
- Mileage / half / marathon: threshold primary plus controlled threshold or shorter aerobic intervals, with base-phase emphasis on threshold; the secondary dose is bounded and explicitly marked as secondary.
- Trail/mountain ultras: threshold plus goal/phase-appropriate hills, with the existing readiness and fueling rules. Back-to-back long runs cap separate weekday workouts at one.
- A demanding half/marathon long run in build/peak consumes a substantial stimulus slot; reduce weekday workouts to at most one. All long runs still count as hard for spacing, including easy long runs.
- Taper, race, recovery, deload, available days and weekly budget remain independent caps. Stage eligibility does not guarantee two sessions in every week.

When introducing the second substantial workout, hold volume at the lower of the recent baseline and last completed week until two actual dual weeks demonstrate tolerance. Approving or repeatedly revising a dual-stage plan cannot escape this hold. The primary ladder stays evidence-gated. A smaller secondary prescription cannot double-advance the threshold ladder or directly recalibrate its base pace; completed work can still contribute correctly matched category evidence to the calibrator.

## Experience, mileage and rest

Existing per-block beginner/comeback ramp is 10%, intermediate 12%; advanced uses 10–20% according to historical headroom. Expert uses 12% near a demonstrated peak, 18% below it and a 20% cap far below it. These are block defaults, not universal safe weekly increases. The supported-recent-high policy, destination caps, recovery reductions and introductory-dual volume hold take priority. A faster tier does not increase workout pace without actual pace evidence.

Natural down weeks reset the loaded-week streak. All tiers can reduce training sooner from feedback. Experience never deletes preferred rest days or authorizes adjacent hard days. A runner may select seven available running days, but a professional label never forces seven or overrides the athlete's schedule.

## Implementation and next limits

- `core/experience.py`: tier defaults.
- `services/quality_history.py`: approved genuine prescriptions and completed activity evidence, ignoring synthetic historical rows and unapproved drafts.
- `core/quality_policy.py`: stage decision, evidence and transparent criteria.
- `core/plan_engine.py`: goal-specific pairing, long-run coordination and volume hold.
- `athlete_snapshot.quality_policy`: persisted stage/context; `/current` and preview agree after reload. No new database columns.

The app still lacks comprehensive structured injury, strength, heat and nutrition inputs. It must not claim to have assessed these. The current gates use available running and feedback evidence and are intentionally explainable. An OpenAI model may later explain/propose alternatives, but cannot bypass these decisions or validation.
