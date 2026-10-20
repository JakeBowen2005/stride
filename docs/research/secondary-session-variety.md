# Selecting the second stimulus: variety with a purpose

The athlete's examples (8 × 1 minute or 6 × 400m) illustrate the role, not a complete workout library. The Long Game dossier chapters 18–19 and supplemental chapters 3, 12–14 describe threshold, light faster aerobic running, hills and mechanics work, coordinated with the long run and current recovery.

## Coaching sources consulted October 19, 2026

- [Greg McMillan's training-plan guide](https://www.mcmillanrunning.com/training-plan-guide/), especially strides, hill repeats, fartlek, progression and optimal-versus-maximal training. These distinguish brief mechanics work with substantial recovery from demanding aerobic intervals. The guide also describes full sessions far harder than a light rebuild stimulus; those are not all appropriate for this slot.
- [McMillan: Six training tweaks](https://www.mcmillanrunning.com/6-training-tweaks-for-your-season/): keeping small amounts of leg-speed work during base development instead of losing faster mechanics entirely.

These are primary coaching sources, not trials proving that these particular prescriptions are equivalent or optimal. The exact modest doses below are Stride coaching choices. The source documents' historical workouts remain reports, not newly confirmed completions.

## Implemented catalog

Every session has easy warmup and cooldown, with format-appropriate bookends. Effort descriptions are part of the numeric prescription; pace estimates used for mileage accounting are not targets.

| Family | Example dose | Intended role | Recovery |
|---|---|---|---|
| Short fartlek | 8 × 60 seconds | Controlled faster aerobic rhythm | 60-second easy jog |
| Short pickups | 10 × 30 seconds | Brief changes of rhythm | 90-second easy jog |
| Longer light fartlek | 6 × 90 seconds | Controlled aerobic repetitions | 90-second easy jog |
| Strides | 6 × 20 seconds | Relaxed mechanics and coordination | 100 seconds, extend for full recovery |
| Modest steady finish | 10 minutes, gradually easy to steady | Aerobic rhythm below threshold | Followed by easy cooldown |
| Relaxed short repetitions | 8 × 200m or 6 × 300m | Rhythm and mechanics, without sprinting | 90-second easy jog |
| Relaxed aerobic repetitions | 6 × 400m or 4 × 600m | Controlled faster running | 90 or 120-second easy jog |
| Conditional short hills | 6 × 20 seconds | Small uphill coordination stimulus | 120 seconds walk/jog down, extend as needed |

The varied doses serve different purposes. They are **not** interchangeable physiological loads. A two-minute stride set can be useful without becoming an eight-minute fartlek set. No maximal sprints, all-out descending, full VO2 sessions, long tempos or race simulations are automatically added to this light slot.

## Selection rules

`quality_policy.SUPPORT_SESSIONS` stores family, template ID, numeric work and recovery, and effort guidance. Existing experience/history/frequency/long-run and fatigue gates determine whether a second stimulus is allowed at all. Weekday separation and mileage fitting remain mandatory.

Time preference selects timed variants; distance preference favors measured repetitions. If estimated work for a distance template exceeds ten minutes at current reference pace, exclude it; if none fits, use short strides. This is a dose bound for selection, not a universal safety rule or a measured intensity limit. A slightly slower actual effort is allowed; log actual mileage normally.

Hills enter the pool only with explicit trail/mountain terrain. Terrain alone does not prove hill tolerance: the description requires a familiar gentle incline and offers flat relaxed strides for unfamiliar hills or persisting soreness. Road/unspecified terrain never auto-selects hills. Dedicated hill-exposure and musculoskeletal readiness fields remain future work.

A stable calendar-week index rotates within the eligible pool. Regenerating the same week with the same preferences returns the same support template; the next week offers variety without advancing a fitness level or changing threshold pace. Rotation currently uses eligibility, purpose, dose, terrain and format; it does not claim to infer an individualized physiological need from missing recovery data. A future richer athlete-state selector can replace rotation while keeping the contract and validation.

Completed support workouts retain their own `speed_support` category; they never prove threshold/VO2 ladder advancement. Current-fitness threshold pacing and its existing volume progression remain separate.

Calibration also reserves activities on actual prescribed support days from legacy prose parsing, even before feedback supplies structured execution. Newer synthetic historical rows in a revised plan cannot mask the original support prescription. Unapproved drafts do not suppress evidence, and an explicitly recorded actual workout swap remains eligible for normal evidence checks.
