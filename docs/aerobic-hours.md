# Aerobic hours: evidence, protocol and the hours chart

> Status: proposal (October 2026). Nothing in this document is implemented yet.
> It answers two notes from Jake:
> "Total number of hours of running / all activity is a good metric / chart to have up there;
> we can use that in determining future volume too," and
> "Do research on how more hours of aerobic work truly leads to greater fitness, and how to
> implement that into our protocol and guidelines."

## Summary

- **More aerobic time does produce more fitness, with diminishing returns.** The evidence is
  strongest for the mechanism (training volume drives mitochondrial content; higher weekly
  dose removes "non-response") and for associations between volume and performance. There
  are no long randomized trials in runners that isolate volume, so the exact shape of the
  curve for one athlete is unknown.
- **Time and distance measure different things.** Time at a given intensity is a better
  measure of the aerobic stimulus. Distance (steps) is a better measure of tissue load, and
  every running-injury study cited here measured distance. Stride should therefore keep miles
  as the injury budget and add hours as a second budget. **The stricter of the two always wins.**
  Time never authorizes extra miles.
- **The best current running-specific injury signal is the single session.** It is not the
  weekly ratio. In a cohort of 5,205 Garmin runners, a run more than 10% longer than the longest
  run of the previous 30 days was associated with more overuse injury. Weekly ACWR and
  week-to-week change were not. Stride's weekly ramp rules are conservative policy, not proven
  injury protection. This proposal adds a longest-session guard, measured in both distance and time.
- **The metric:** weekly, monthly and yearly running hours from moving time, shown as a
  *Distance | Time* toggle on the existing History volume chart. It reuses the
  `/analysis/{id}/mileage` buckets with extra fields. A small "this week" time figure can go on
  Today once PR #51 has landed. Non-running activity is out of plan load and is not synced today.
  If Jake wants it, it is shown separately, labeled, off by default and never counted as running.

---

## 1. Research

Evidence grades used below:

- **Strong:** randomized trials, meta-analyses or consistent mechanistic work.
- **Moderate:** large prospective cohorts or meta-regressions of observational data.
- **Weak:** small or post-hoc findings, or results that conflict.
- **Opinion:** coaching practice and books. These are valuable but untested.

### 1.1 Does more aerobic volume lead to more fitness?

| Finding | Source | Grade |
|---|---|---|
| Training volume appears to be the main driver of mitochondrial *content*. Relative intensity matters more for mitochondrial *respiratory function*. | Granata, Jamnick & Bishop 2018, *Sports Med* (review) | Strong (mechanism) |
| 78 adults did 1–5 × 60 min sessions per week for 6 weeks, and the share of "non-responders" fell as weekly dose rose. Adding 120 min per week for another 6 weeks removed non-response in everyone. The gains came mainly from haemoglobin mass. | Montero & Lundby 2017, *J Physiol* | Strong (RCT, untrained adults) |
| Across 85 studies (137 cohorts), weekly running distance and other volume measures were associated with faster marathon times (R² 0.38–0.81). | Doherty et al. 2020, *J Sci Med Sport* (meta-regression) | Moderate (between-runner, observational) |
| In 85 male runners, performance was best predicted by the volume of easy running plus deliberate practice of tempo and short intervals over the first 7 years of training. | Casado et al. 2021, *J Strength Cond Res* | Moderate (retrospective, self-report) |
| World-class runners run 160–220 km per week (marathon) or 130–190 km per week (track), with ≥80% of volume at low intensity. Marathoners differ mainly by running *longer sessions*. | Haugen et al. 2022, *Sports Med Open* | Moderate (narrative integration of literature and practice) |
| A model fitted to about 14,000 runners and 1.6 M sessions of real-world watch data linked training volume and intensity to its aerobic-power and endurance indices, and hinted at an optimal training dose. | Emig & Peltonen 2020, *Nat Commun* | Moderate (observational) |

**What this supports:** more weekly time at mostly easy intensity is a real cause of aerobic
adaptation. Over years it is the main difference between better and worse distance runners.

**What it does not support:** a precise hours-to-minutes-saved curve for one athlete. The
performance studies compare *different runners*, and runners who can handle more volume may
also be more talented or more durable. Montero & Lundby used untrained adults over 12 weeks, not
trained runners.

### 1.2 Diminishing returns

- In impulse-response models (Banister's fitness-fatigue model and Busso's 2003 extension in
  *Med Sci Sports Exerc*), the fatigue cost of each extra unit of training grows with load. The
  net gain per added hour therefore shrinks as total load rises. **Grade:** moderate. The models
  fit individual data well but are descriptive.
- Seiler (2010, *IJSPP*) reviewed intensification studies in already well-trained athletes. They
  gave no convincing evidence that more high-intensity work brings long-term gains. Elite
  athletes instead "self-organize" toward high volume with controlled amounts of hard work.
  **Grade:** moderate (review).
- **Practical reading:** the return on an added hour is largest for a runner well below their
  own sustainable volume. That describes Jake rebuilding from 25–40 toward 50–70 mpw. The return
  is smallest near a runner's ceiling, where fatigue and injury risk rise faster than fitness.
  This matches the existing `load_policy` idea of *headroom below a previous peak*.

### 1.3 Time versus mileage as the unit of load

| Question | Better unit | Why |
|---|---|---|
| Aerobic stimulus (cardiac, mitochondrial, metabolic) | **Time** at an intensity | Physiology responds to how long the system works. Internal-load methods are built on duration, for example session RPE = minutes × RPE (Foster et al. 2001, *JSCR*), which Haddad et al. 2017 (*Front Neurosci*) found valid and reliable across 36 studies. |
| Tissue load (bone, tendon, muscle) | **Distance / steps**, plus per-step force | Running-injury frameworks model injury as cumulative structure-specific load (steps × load per step) exceeding tissue capacity (Bertelsen et al. 2017; Nielsen et al. 2018, *BJSM*). |
| Injury evidence base | **Distance** | Nielsen 2014, Damsted 2019 and Frandsen 2025 all measured distance. Using time for ramp limits would mean extrapolating from studies that did not measure it. |
| Comparing runners of different speed | **Time** | 40 mi at 10:00/mi is 6 h 40 min. At 7:30/mi it is 5 h. Equal miles are not equal aerobic work. |
| Trail and mountain | **Time** | Grade and terrain make pace unreliable, which is why ultra coaches commonly prescribe time on feet. **Grade:** opinion, but widely shared, and Stride already does this in `special_weeks.ultra_long_run`. |

**Conclusion for Stride:** use **both**. Miles stay the musculoskeletal budget and keep every
existing ramp and guard. Hours become the aerobic-stimulus and life-availability budget. Where
they disagree, the lower one decides.

### 1.4 Easy-intensity share (80/20)

- Elite endurance athletes put about 80% of *sessions* at low intensity. This is descriptive
  (Seiler 2010; Haugen 2022). **Grade:** moderate.
- RCTs in sub-elite runners: Esteve-Lanao et al. 2007 (*JSCR*) found more improvement with more
  zone-1 time. Muñoz et al. 2014 (*IJSPP*) found 10K improved 5.0% polarized vs 3.6%
  between-thresholds, a difference that was *not* significant. The larger benefit in the most
  polarized subset was post hoc. Rosenblat et al. 2019 (*JSCR*) meta-analysed polarized vs
  threshold distributions in RCTs. **Grade:** weak to moderate. Small trials and short durations
  make the direction consistent but the size uncertain.
- **Counting method matters.** "80/20 by sessions" and "80/20 by time" are different numbers.
  Measured by time, warmups, cooldowns and recoveries count as easy. A week that is 80/20 by
  sessions is usually closer to 85–90% easy by time.
- **For Stride:** the existing rule ("~80% of weekly mileage easy") stays. Time adds a better way
  to *check* it, because laps already carry intensity labels from `lap_analyzer`.

### 1.5 Injury risk from rapid increases (and the ACWR critique)

| Finding | Source | Grade |
|---|---|---|
| A 13-week graded program following the 10% rule did **not** reduce injuries compared with an 8-week program in 532 novices (20.8% vs 20.3%). | Buist et al. 2008, *Am J Sports Med* (GRONORUN RCT) | Strong (null result, for novices over short distances) |
| In 874 novices, a >30% two-week increase was associated with more *distance-related* injuries (HR 1.59, 95% CI 0.96–2.66). Overall injury rates did not differ. | Nielsen et al. 2014, *JOSPT* | Weak to moderate |
| In 261 half-marathon runners, weekly increases of 20–60% raised injury risk compared with <20% at day 21 (risk difference 22.6%). The difference was not significant at days 56 or 98. | Damsted et al. 2019, *JOSPT* | Moderate |
| 5,205 Garmin runners, 588,071 sessions. A session longer than the longest run of the prior 30 days was associated with overuse injury, compared with ≤10% longer: HR 1.64 for >10–30%, 1.52 for >30–100% and 2.28 for >100%. Weekly ACWR showed an *inverse* association, and week-to-week change showed none. | Frandsen et al. 2025, *BJSM* (Garmin-RUNSAFE) | Moderate (large prospective cohort, distance only, self-reported injuries) |
| ACWR has conceptual problems: ratio artefacts, mathematical coupling of acute and chronic load, and no causal estimates. Changing ACWR to prevent injury is conjecture, and the authors recommend dismissing it as a framework. | Impellizzeri et al. 2020 (*IJSPP*) and 2021 (*Sports Med*); Lolli et al. 2019 (*BJSM*) | Strong (methodological critique) |

**What this means:**

1. Stride's weekly ramp rates (10–20%) and its ACWR-style display are **conservative policy**.
   They are reasonable to keep because they fail safe, but they are not proven injury protection.
   `load_history.py` already labels its ratio as "not a diagnosis or an injury probability". Keep
   that honesty.
2. The best-supported running-specific guard is **per session**: do not make one run much longer
   than anything done in the last month. Stride does not enforce this generally today. Only the
   developmental half/marathon path caps the long run against the recent longest (+1 mi, ≤180 min,
   in `developmental.long_run_cap`), plus the pre-taper repeat. The evidence is in distance, so
   the guard should be in distance first, with time as a second check.
3. Nothing here argues for loosening any existing rule.

### 1.6 How the coaches Stride follows treat time

All entries in this section are **opinion** (books and coaching practice).

| Coach | Volume unit | Time-related rules |
|---|---|---|
| **Jack Daniels** | Mostly miles, with weekly quality caps as % of mileage (T ≤10%, I ≤ min(8%, 10 km), R ≤ min(5%, 8 km)) | The long run is capped at the lesser of ~25–30% of weekly mileage or about 150 min (*Daniels' Running Formula*; secondary sources disagree on the exact percentage). The time cap means slower runners do not run 3+ hours on modest mileage. |
| **Pete Pfitzinger** | Miles | Volume is the main marathon stimulus, delivered through medium-long runs and long runs. Progression is in miles, with recovery weeks. |
| **Hanson** | Miles and time | Long run is ≤~16 mi and ~25–30% of the week, with roughly a 3 h ceiling. The rationale is that runs past ~2.5–3 h cost more recovery than they return. Cumulative fatigue comes from frequency and total time, not one huge run. |
| **Renato Canova** | Km at % of race pace | High general volume first, then a growing amount of race-specific work. "Time" appears as the duration of specific work, not as a weekly-hours budget. |
| **Phil Maffetone** | Time at a heart-rate cap | Aerobic base built with time below MAF HR. Effectively time-based easy running. |
| **Ultra practice** (e.g. Koop, Uphill Athlete) | Hours | Weekly hours and time-on-feet long runs are the standard units. Hours progress gradually, and back-to-back weekends are counted by total time. |

**The shared idea:** every school caps the single longest run in *time* as well as in share of
the week, and most build weekly volume gradually with periodic lighter weeks. None prescribes
weekly *hours* for road runners as the primary unit. Ultra coaching does.

---

## 2. Principles for Stride

1. **Two budgets, the lower wins.** A week's prescription must fit the mileage budget
   (`load_policy`, unchanged) **and** an hours budget. Hours can only hold or cut a plan, never
   expand it.
2. **Same rates, same modes.** The hours budget uses the same ramp rate, deload factor, hold,
   reduce and recovery factors and spike guard as miles. No new ramp numbers are invented.
3. **Single-session guard in both units.** No planned run is much longer, in distance or time,
   than the longest run of the last 30 days.
4. **Hours are measured, never imagined.** Baselines come from moving time on completed runs.
   Plans estimate time with `time_budget.estimated_minutes` at the athlete's current easy pace.
5. **Running only.** Walks and non-running activity never enter running load, which keeps the
   existing `runs_only()` rule. They may be *shown*, clearly separated.
6. **Policy, not science.** Every number below is a conservative Stride default and should be
   documented as such, as `load_policy.py` already does.

## 3. Proposed protocol changes

### R1 — Measure weekly running hours (no behavior change)

- `hours_baseline` uses the definition of `load_history.completed_week_load`: the last four
  completed Monday–Sunday weeks of `runs_only()` moving time (`Activity.duration_seconds`),
  divided by 4, with empty weeks counting as zero.
- `hours_level` mirrors `load_policy.training_level`: deload weeks are excluded and spikes are
  not chased, computed over weekly hours.
- Add both to `LoadPlan.to_dict()` and to the athlete snapshot, so the coach and block review
  can mention them.

### R2 — Weekly hours budget (cap only)

```
hours_budget[w] = hours_level × the same growth/mode factor load_policy applied to miles in week w
projected_minutes[w] = Σ estimated_minutes(day, easy_pace) over the week's planned days
if projected_minutes[w] > hours_budget[w] × 60 × (1 + HOURS_TOLERANCE):
    trim easy days in the existing give-way order (easy-day length → number of easy days),
    never the long run or a quality session first
```

- `HOURS_TOLERANCE = 0.05` absorbs estimate error, because a planned easy pace is a range.
- **When it binds:** the athlete's recent running was faster than the planned easy pace, or more
  time was planned on slower terrain. In both cases the miles would quietly turn into more hours
  than the athlete has shown they can handle. The cap is a hold, which is the fail-safe direction.
- **When it never applies:** it never raises miles. A week that is light in hours but at its
  mileage budget stays at the mileage budget.
- This is separate from the existing per-day `day_time_budgets` (availability), which keeps
  working as today in `fit_availability`. A weekly availability total (Σ of daily limits) is a
  third ceiling that already falls out of the per-day limits.

### R3 — Longest-session guard

```
longest_30d_miles, longest_30d_minutes = max over completed runs in the last 30 days (races excluded)
cap_miles   = max(longest_30d_miles   × 1.10, longest_30d_miles   + 1.0)
cap_minutes = max(longest_30d_minutes × 1.10, longest_30d_minutes + 10)
planned run (distance, estimated minutes) must fit both caps
```

- The additive floors (+1 mi, +10 min) let short runs grow. Without them, a runner whose longest
  recent run is 3 mi could only add 0.3 mi. The +1 mi matches the existing developmental step.
- **Exemptions:** race days and race-week events.
- **Within a block:** week 2 may step once more from week 1's *planned* long run. When the block
  is regenerated, the guard uses what was actually run, so a missed long run never unlocks two
  steps.
- After a break with no runs in 30 days, the guard falls back to the R1 start rules and the
  existing comeback rate.
- This adds a guard on top of the 180-min cap already used on the developmental path. It extends
  to every path, including the established and ultra paths.
- **Evidence:** Frandsen 2025 (distance). The time check is Stride's addition and is labeled as
  policy.

### R4 — Deloads in time

- A deload week applies `DELOAD_FACTOR` (0.75) to both miles and hours. The week after a deload
  returns to `hours_level`, matching the existing mileage behavior.
- `deload_due` stays mileage-triggered. **Additionally**, a week counts as loaded if it is
  loaded in *either* unit. If anything this makes deloads come sooner, never later, which is the
  fail-safe direction.

### R5 — Ultra and trail: hours as the primary weekly unit

- Ultra long runs are already time-based (`ULTRA_LONG_RUN_CAP_MIN`, a minimum of 75 min, and a
  1.12 trail pace factor). Add R3's time guard to `ultra_long_run` and `back_to_back_day`. For
  back-to-back weekends, the pair's combined minutes may not exceed the previous 30 days' longest
  *weekend* total by more than 10%.
- For `terrain in {trail, mountain}`, show weekly targets as hours first and miles second
  ("~7 h 30 min · ~38 mi"). The budget check still requires both. Trail pace makes miles a poor
  guide for aerobic time, and road-based miles a poor guide for trail tissue load. Keeping both
  is the conservative choice.
- Moving time includes hiking inside a run activity. That is correct for ultra preparation,
  because power-hiking is prescribed.

### R6 — Intensity distribution by time (monitoring, later)

- From labeled laps, compute weekly easy-time share = easy minutes ÷ total running minutes, where
  warmups, cooldowns and recoveries count as easy.
- Flag, but do not auto-adjust, when the 2-week easy share falls below 75% by time. That usually
  means easy runs drifted too fast, which already feeds the aerobic-efficiency view.
- The Daniels-style quality caps stay as they are.

### R7 — Using hours to choose future volume

Jake wants hours to help decide future volume. Proposed uses, all conservative:

- **Ramp headroom in both units.** `ramp_rate` uses `baseline / peak` headroom. Compute it in
  miles and hours and use the **larger** ratio, meaning the one closer to peak and so the slower
  rate. A runner whose hours are already near their historical peak, because they are running
  slower, does not get the fast "far below peak" rate.
- **Sustainable-volume suggestion.** Show the highest weekly hours held for ≥6 consecutive weeks
  in the last 2 years as "your demonstrated sustainable volume". This is display only. It helps
  Jake and the coach set a mileage destination, and it is never prescribed directly.
- **Availability reality check.** If a mileage goal at the current easy pace would need more
  weekly time than Σ `day_time_budgets` allows, say so when the goal is set, before any plan
  stalls against it.
- **Hours goal type (open question).** For example, "build to 7 h/week" for trail or ultra
  athletes. It would be a destination in hours, capped by miles in the same way.

### Proposed wording for `docs/training-principles.md` (after Jake approves)

> **Principle 4b: Time is a second budget.** Weekly volume is checked in miles (tissue load) and
> in hours (aerobic load and availability); the lower allowance wins, and time never permits
> extra miles. No single run is planned more than ~10% (min +1 mi / +10 min) longer than the
> longest run of the last 30 days, in distance or time; races are exempt. Deload weeks reduce
> both. These are Stride policy defaults drawn from `docs/aerobic-hours.md`, not validated
> injury thresholds.

---

## 4. The metric and chart

### 4.1 Definition

| Quantity | Definition | Notes |
|---|---|---|
| **Running hours** (primary) | Σ `Activity.duration_seconds` over `runs_only()` | This is moving time, which Garmin calls `movingDuration`, falling back to `duration`. It is consistent with pace, laps and the mileage chart, and it excludes stops at lights and auto-pause. |
| Elapsed hours (secondary) | Σ `Activity.elapsed_seconds` | Shown in the tooltip only. It is useful for long runs and ultras, where aid-station stops are real time on feet. It is `None` on some legacy rows, which count as moving time and are marked. |
| Walk hours | Σ `duration_seconds` for activities where `is_walk()` | Excluded from running hours and plan load, the same as mileage. Shown only as an optional separate segment. |
| Other activity hours | Not available today | See 4.3. |
| Planned hours | Σ `estimated_minutes(day, easy_pace)` for planned days of approved blocks | Planned hours are an estimate. Store `estimated_minutes` on `PlannedWorkout` when a block is approved, so the planned line does not shift whenever easy pace recalibrates. |

**Edge cases:**

- Manual entries and FIT imports already store `duration_seconds`.
- Legacy Strava rows carry Strava moving time.
- Rows with `duration_seconds` of 0 or missing are counted as "runs without time", so the hours
  bar does not silently under-report.
- Bucketing uses the athlete clock and run start date, the same as `compute_mileage`.

### 4.2 Where it lives

- **History (phase 1):** add a **Distance | Time** toggle to `MileageOverTimeChart`
  (`frontend/components/charts/mileage-over-time-chart.tsx`) and keep its Weekly / Monthly /
  Yearly views from PR #43. Distance and time share buckets and the planned-vs-actual pattern, so
  one chart with a toggle is more useful than a second chart scrolled next to it. The y-axis shows
  hours with one decimal ("5.4 h"). Tooltips use h:mm ("5 h 24 min · 38.2 mi · 6 runs").
- **Today (phase 2, after PR #51 lands):** next to the weekly-mileage hero, add a secondary line
  "This week: 32.4 mi · 4 h 51 min". Mileage stays the hero number per `CLAUDE.md`. Time is
  context, and becomes the lead figure only for trail or ultra goals (R5). This avoids the Today
  and Plan run panels PR #51 is changing.
- **Plan (phase 3):** week headers show "≈ 6 h 10 min" beside planned miles. Ultra and trail
  weeks show hours first.

### 4.3 Non-running activity (Stride is running-only)

- **Today:** `PersonalApiClient.search_runs` (`services/garmin_api.py`) requests `activityType=running`, so Garmin
  filters out cycling, strength, hiking and walking on its side. Stride only has walks that were
  recorded as runs and later reclassified. The daily wellness summary Stride reads (`flatten_summary`)
  does not map any activity-minute fields.
- **If Jake wants all-activity hours** (open question 2), the least invasive design is:
  - A second date-windowed search with no `activityType` filter. It runs in the same sync and
    keeps only non-running activities.
  - Store them in a separate `other_activities` table: date, Garmin `typeKey`, moving seconds,
    distance, average HR and training effect. **Never** use `activities`, because `runs_only()`
    and every load query would then need to defend against them.
  - Do not download FIT files and do not trigger reviews or plan effects.
  - Display: a separately colored stacked segment labeled "Other activity (not in your plan)",
    **off by default**, behind the same toggle.
  - Plan load: none. A possible later step is to give the coach review the context (e.g. "you
    cycled 2 h yesterday"), but deterministic load stays running-only.
  - Cost: one extra request per sync. Whether the Personal API allows an unfiltered search for a
    personal key needs checking against the live API before building.

### 4.4 API shape

Extend the existing endpoint instead of adding a second one. This keeps the query and the
bucketing in one place and is backward compatible:

`GET /analysis/{user_id}/mileage?bucket=week|month|year&count=N&include=walks,other`

```json
[
  {
    "period_start": "2026-10-19",
    "partial": true,
    "runs": 6,
    "actual": 38.2,
    "planned": 41.0,
    "actual_seconds": 19440,
    "elapsed_seconds": 20110,
    "planned_seconds": 20700,
    "runs_without_time": 0,
    "walk_seconds": 2700,
    "other_seconds": null
  }
]
```

- `actual` and `planned` keep their meaning (miles), so the existing chart is unchanged.
- `walk_seconds` and `other_seconds` are present only when requested in `include`.
  `other_seconds` stays `null` until 4.3 exists.
- Frontend type: extend `MileagePeriod` in `frontend/lib/types.ts`.

---

## 5. Phased implementation plan

| Phase | Scope | Behavior change | Done when |
|---|---|---|---|
| **0** | This document. Jake answers the open questions. | None | Decisions recorded in `docs/coaching-policy-decisions.md` |
| **1. Metric** | API fields (4.4), Distance/Time toggle on History, `estimated_minutes` stored on approval. Tests use disposable DBs: bucket sums, walks excluded, missing durations counted, planned seconds stable after pace recalibration. | Display only | History shows hours. pytest and the frontend build pass. |
| **2. Shadow budgets** | R1 plus R2/R3/R4 computed and recorded in `LoadPlan.to_dict()` / the block preview "reasons", but **not enforced**. Log where hours or the session guard *would* have bound. | None to plans | 4–6 weeks of Jake's blocks reviewed: how often each guard would bind and whether the result looks right |
| **3. Enforce** | R2 cap, R3 guard (all paths), R4 deload in time, R7 headroom in both units. `change_guard` checks projected minutes. Update `training-principles.md` (wording above), `ARCHITECTURE.md` and `coaching-policy-decisions.md`. Today secondary time line (after PR #51). | Can only hold or cut | Validator rejects plans breaking either budget or the session guard. Existing tests are unchanged except where a guard now binds, with each change explained. |
| **4. Ultra/trail** | R5: hours-first display, back-to-back weekend guard, Plan week headers in hours | Can only hold or cut | 100-mile demo program (`docs/demo-programs`) re-generated and reviewed |
| **5. Optional** | 4.3 other-activity ingest and display, R6 easy-share-by-time monitor, R7 sustainable-volume tile, hours goal type | Display or coach context only | Per Jake's answers |

Phase 1 touches `services/analyzer.compute_mileage`, `api/analysis.py`,
`components/charts/mileage-over-time-chart.tsx`, `lib/types.ts`, and the plan approval path that
stores `estimated_minutes`. It does not touch the Today/Plan run panels (PR #51), multi-user
Garmin, or the AI week-restructure work.

## 6. Open questions for Jake

1. **"Up there":** did you mean on Today, next to weekly mileage, or is the History chart enough
   to start?
2. **All activity:** do you want non-running Garmin activities, such as cycling, strength and
   hikes, pulled in at all, given that Stride is running-only? If so, is display-only (off by
   default, never in plan load) right?
3. **Moving vs elapsed:** moving time as the main number, with elapsed in the tooltip, or elapsed
   for long runs and ultras?
4. **Session guard:** is +10% (min +1 mi / +10 min) over your longest run of the last 30 days the
   right default? It would slow some long-run progressions on the established path.
5. **Hours goal:** do you want a "build to X hours/week" goal type, for example for the 100-miler
   build?
6. **Walks:** show walk time as a separate segment, or leave walks out of the chart entirely?
7. **Shadow period:** is 4–6 weeks of shadow budgets (phase 2) acceptable before anything
   constrains your plans?

## References

- Bertelsen ML, Hulme A, Petersen J, et al. A framework for the etiology of running-related injuries. *Scand J Med Sci Sports*. 2017;27(11):1170–1180.
- Buist I, Bredeweg SW, van Mechelen W, et al. No effect of a graded training program on the number of running-related injuries in novice runners: a randomized controlled trial. *Am J Sports Med*. 2008;36(1):33–39. [RUG record](https://research.rug.nl/en/publications/no-effect-of-a-graded-training-program-on-the-number-of-running-r/)
- Busso T. Variable dose-response relationship between exercise training and performance. *Med Sci Sports Exerc*. 2003;35(7):1188–1195.
- Casado A, Hanley B, Santos-Concejero J, Ruiz-Pérez LM. World-class long-distance running performances are best predicted by volume of easy runs and deliberate practice of short-interval and tempo runs. *J Strength Cond Res*. 2021;35(9):2525–2531. [Accepted manuscript](https://eprints.leedsbeckett.ac.uk/id/eprint/5885/1/WorldClassLongDistanceRunningPerformancesAM-HANLEY.pdf)
- Damsted C, Parner ET, Sørensen H, Malisoux L, Hulme A, Nielsen RO. The association between changes in weekly running distance and running-related injury: preparing for a half marathon. *J Orthop Sports Phys Ther*. 2019;49(4):230–238. [LIH record](https://researchportal.lih.lu/en/publications/the-association-between-changes-in-weekly-running-distance-and-ru/)
- Daniels J. *Daniels' Running Formula*. Human Kinetics (3rd/4th ed.).
- Doherty C, Keogh A, Davenport J, Lawlor A, Smyth B, Caulfield B. An evaluation of the training determinants of marathon performance: a meta-analysis with meta-regression. *J Sci Med Sport*. 2020;23(2):182–188. [PubMed 31704026](https://pubmed.ncbi.nlm.nih.gov/31704026/)
- Emig T, Peltonen J. Human running performance from real-world big data. *Nat Commun*. 2020;11:4936. [PMC7538888](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7538888/)
- Esteve-Lanao J, Foster C, Seiler S, Lucia A. Impact of training intensity distribution on performance in endurance athletes. *J Strength Cond Res*. 2007;21(3):943–949.
- Foster C, Florhaug JA, Franklin J, et al. A new approach to monitoring exercise training. *J Strength Cond Res*. 2001;15(1):109–115.
- Frandsen JSB, Hulme A, Parner ET, et al. How much running is too much? Single-session spikes and running-related injury (Garmin-RUNSAFE). *Br J Sports Med*. 2025;59(17). [PMC12421110](https://pmc.ncbi.nlm.nih.gov/articles/PMC12421110/)
- Granata C, Jamnick NA, Bishop DJ. Training-induced changes in mitochondrial content and respiratory function in human skeletal muscle. *Sports Med*. 2018;48(8):1809–1828. [Accepted manuscript](https://vuir.vu.edu.au/37369/)
- Haddad M, Stylianides G, Djaoui L, Dellal A, Chamari K. Session-RPE method for training load monitoring: validity, ecological usefulness, and influencing factors. *Front Neurosci*. 2017;11:612. [PMC5673663](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5673663/)
- Haugen T, Sandbakk Ø, Seiler S, Tønnessen E. The training characteristics of world-class distance runners: an integration of scientific literature and results-proven practice. *Sports Med Open*. 2022;8:46. [UiT record](https://munin.uit.no/handle/10037/26245)
- Impellizzeri FM, Tenan MS, Kempton T, Novak A, Coutts AJ. Acute:chronic workload ratio: conceptual issues and fundamental pitfalls. *Int J Sports Physiol Perform*. 2020;15(6):907–913. [UTS record](https://opus.lib.uts.edu.au/handle/10453/141898)
- Impellizzeri FM, Woodcock S, Coutts AJ, et al. What role do chronic workloads play in the acute to chronic workload ratio? Time to dismiss ACWR and its underlying theory. *Sports Med*. 2021;51:581–592. [Full text](https://iris.univr.it/retrieve/e34cfb98-e922-4c2f-aab5-18583ab7e31b/Impellizzeri_What%20Role%20Do%20Chronic%20Workloads%20Play_SportMed_2021.pdf)
- Lolli L, Batterham AM, Hawkins R, et al. Mathematical coupling causes spurious correlation within the conventional acute-to-chronic workload ratio calculations. *Br J Sports Med*. 2019;53(15):921–922.
- Montero D, Lundby C. Refuting the myth of non-response to exercise training: 'non-responders' do respond to higher dose of training. *J Physiol*. 2017;595(11):3377–3387. [PMC5451738](https://pmc.ncbi.nlm.nih.gov/articles/PMC5451738)
- Muñoz I, Seiler S, Bautista J, et al. Does polarized training improve performance in recreational runners? *Int J Sports Physiol Perform*. 2014;9(2):265–272.
- Nielsen RO, Parner ET, Nohr EA, et al. Excessive progression in weekly running distance and risk of running-related injuries: an association which varies according to type of injury. *J Orthop Sports Phys Ther*. 2014;44(10):739–747. [AAU record](https://vbn.aau.dk/da/publications/excessive-progression-in-weekly-running-distance-and-risk-of-runn)
- Nielsen RO, Bertelsen ML, Møller M, et al. Training load and structure-specific load: applications for sport injury causality and data analyses. *Br J Sports Med*. 2018;52(16):1016–1017.
- Rosenblat MA, Perrotta AS, Vicenzino B. Polarized vs. threshold training intensity distribution on endurance sport performance: a systematic review and meta-analysis of randomized controlled trials. *J Strength Cond Res*. 2019;33(12):3491–3500.
- Seiler S. What is best practice for training intensity and duration distribution in endurance athletes? *Int J Sports Physiol Perform*. 2010;5(3):276–291. [PubMed 20861519](https://pubmed.ncbi.nlm.nih.gov/20861519/)
- Hanson coaching guidance (long-run cap ~16 mi / ~25–30% of the week / ~3 h): Humphrey L, Hanson K, Hanson K. *Hansons Marathon Method*. VeloPress.
- Pfitzinger P, Douglas S. *Advanced Marathoning*. Human Kinetics.
- Maffetone P. *The Big Book of Endurance Training and Racing*. Skyhorse.

Some records above were checked only at the abstract or record level. Where a claim depends on a
detail beyond the abstract, it is attributed to the source that gave it (e.g. Frandsen 2025 hazard
ratios from the PMC full text). The Daniels 150-minute long-run cap is quoted from the book and
was not confirmed in the online sources searched. Treat it as coaching guidance.
