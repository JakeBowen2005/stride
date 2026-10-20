# Product + coaching review — 2026-10-19

Reviewer persona: senior product manager and elite running coach. Scope: branch `claude/session-options-redesign` (menu v2 + cockpit UI).

## Direction
Right direction: deterministic plans, a single validator for every mutation, an AI that only selects server-authored options and `progression_eligible=False` for menu sessions make the system safe and auditable. Menu v2 is a real step up: at 35 mpw an advanced runner gets 4mi tempo / 4x1mi T / 3x8min cruise instead of 2x3min.

Risk: recent effort skews to plumbing (job leases, demo branches, restyles) while coaching stays generic exactly where it should become race-specific.

- **Build next:** a goal-pace / specific-endurance layer for the peak phase.
- **Defer:** multi-athlete scaling, maintaining three demo branches, further restyles. Fix doc drift (CLAUDE.md promises Claude API + VDOT; code uses OpenAI and has no VDOT).

## Coaching quality
Sound: Daniels 10% T / 8% I session caps, ~1 min rest per 5 min cruise, 2-5 min I reps; taper/deload keep intensity and cut volume; experience floors with a low-volume comeback pull-down. Cruise reps ~10 s/mi faster than continuous tempo is defensible (Daniels uses one T pace). Minor: the band is in minutes at the faster pace, so a continuous tempo can slightly exceed 10% of weekly miles.

Gaps (most important first):
1. **5K peak has no goal-pace work.** `get_ladder` returns the 5K ladder only in build/general; peak falls back to generic 800s. "Race pace" levels fall back to interval pace.
2. **Marathon specific endurance missing** from the replace menu: no MP long runs, midweek MP blocks or medium-long runs.
3. **`secondary_quality` (15-18 min) is below the new advanced floor (20 min)**: two dosing systems.
4. **Paces not anchored to race results** (fixed fractions of easy pace without calibration). VDOT from a recent race/time trial is a better anchor.
5. **Neuromuscular work thin:** strides once/week, no 8-10 s hill sprints.
6. **Ultra work shallow:** no vertical-gain targets, power-hike intervals or downhill durability progression.
Nothing unsafe; lean toward specificity rather than volume.

## Top 5 recommendations
1. Goal-pace and specific-endurance templates per distance/phase in `session_catalog` (5K goal-pace reps, marathon MP long runs + medium-long, ultra vert/hike).
2. VDOT anchoring from race/time-trial results, falling back to Garmin predictions, then easy-pace ratios.
3. Peak phase driven by the gap between current fitness and goal pace, stepping 3-5 s/mi on rep evidence.
4. Unify `secondary_quality` with `dose_band` floors and families.
5. Standing neuromuscular work: 2x/week strides for race goals, hill sprints in base.

Evidence vs opinion: Daniels caps, T/I definitions and taper practice are literature-backed. Floors, ceilings, stage gates, the 35% long-run cap and the cruise-faster-than-tempo relationship are Stride heuristics.
