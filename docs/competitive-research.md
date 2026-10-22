# Competitive research: how running apps decide and adapt plans

Researched October 21, 2026. This covers how the leading apps choose workouts and paces, how they adapt, what users dislike about them and what they cost. It ends with a prioritized list of what Stride should add or keep.

**Read with care.** Most vendors do not publish their algorithms. Each claim below is marked by source type: **official** (vendor docs or manuals), **reviewer** (independent reviewers such as the5krunner and DC Rainmaker) or **forum** (anecdotes from individual users). Prices are US list prices found in October 2026. Confirm them on vendor pages before quoting them anywhere.

## Summary

| App | Plan model | Main adaptation signal | Uses HRV/sleep to change the plan? | Price (US) |
|---|---|---|---|---|
| Runna | Coach-written templates tailored by an algorithm | Repeated pace hits or misses on tempo and interval sessions | Not documented | $119.99/yr; $149.99/yr bundled with Strava |
| Garmin Coach / Run Coach | Coach-authored plans (Galloway, McMillan, Parkerson-Mitchell), then Garmin's own algorithmic Run Coach | Training load, readiness and completed runs | Yes, indirectly through Training Readiness and load | Free; Connect+ is $6.99/mo or $69.99/yr |
| Garmin Daily Suggested Workouts | No plan; one session chosen each day | Acute vs. chronic load, Training Status, Recovery Time, VO2max | Yes, through Training Readiness on supported watches | Free with a supported watch |
| Strava | No plan engine of its own; plans come from Runna | Not applicable | No | $79.99/yr; $149.99/yr with Runna |
| TrainingPeaks | Coach- or marketplace-authored plans plus the ATP planner | Human coach reading the PMC (CTL/ATL/TSB) | Only if the coach chooses to | Premium about $134.99/yr (sources conflict) |
| COROS | Coach-written plans scaled to EvoLab zones | Running Fitness (HR vs. pace) changes zones | Not in the official plans | Free with the watch |
| Polar Running Program | Heart-rate-zone plan in 3 phases | Zone-time targets reviewed every 4 weeks | **No.** Polar says the program does not adapt to recovery status | Free with the watch |
| Pfitzinger / Daniels / Hansons books | Fixed printed tables | The runner, guided by rules in the book | No | One-time book price |

**Main finding.** No product combines all three of these:

1. A real periodized plan
2. Paces built from the athlete's own recent workout splits
3. A transparent, conservative way of using recovery data

Garmin has the data but writes generic or erratic sessions. Runna writes plans people like, but its pace logic is a black box and it has drawn injury criticism. TrainingPeaks has the best load model but needs a human coach to act on it. The book plans are the most trusted and do not adapt at all. Stride already has the first two. The third is the clearest gap to close.

---

## Runna

**What it is.** A standalone coaching app that Strava bought in April 2025. The two apps still run separately, and a joint subscription has been sold since July 2025 ([Strava acquisition coverage, DC Rainmaker](https://dcrainmaker.com/2025/04/strava-acquires-runna-thoughts-forward.html); [Marathon Handbook](https://marathonhandbook.com/strava-announces-acquisition-of-personalized-training-app-runna/)).

**Inputs.** Current ability (one estimated race time), experience, days per week, race distance and race date. Runners can change volume and difficulty at any point (reviewer: [the5krunner, "Is Runna AI?", Sept 2026](https://the5krunner.com/2026/09/28/is-runna-ai/)).

**How it picks workouts and paces.**
- Coaches write the plans and an algorithm tailors them. Runna has not published how the algorithm works (reviewer: the5krunner).
- A single estimated race time sets every pace target across all distances, so raising it makes every session harder. Runna trains to current estimated fitness, not to a goal time (the5krunner).

**How it adapts.**
- **Pace Insights** on tempo and interval sessions is the main mechanism. It changes targets only after a pattern of hits or misses, so one fast session is not enough, and it ignores outlier reps (the5krunner).
- **Not Feeling 100%** handles illness, aches and busy weeks, then returns the runner to the plan without losing their place ([IT Brief on Runna's beginner plan update](https://itbrief.com.au/story/runna-revamps-beginner-plans-with-flexible-guidance)).
- **Mileage Insights** recommends volume changes based on how closely the runner follows the schedule.
- **Adapt for Heat** changes pace targets using the weather forecast, not measured heat strain (the5krunner).
- Reviewers disagree about missed weeks. Some say Runna offers to re-adapt the plan; others say it does not respond to what actually happened ([Runner Beans review](https://therunnerbeans.com/runna-coaching-app-review/); [Autonomous review](https://www.autonomous.ai/de-US/ourblog/runna-app-review-what-training-with-runna-is-really-like)).
- No documented use of HRV.

**Complaints.**
- In February 2026, the *Wall Street Journal* reported physical therapists seeing several Runna-related injuries a week, mostly stress fractures, shin splints and Achilles tendinopathy. It linked them to how Runna progresses pace and distance, distributes intensity and builds in recovery.
- Runna responded by adding ways to reduce plan intensity and by commissioning a Loughborough University review of those three areas, led by Dr Richard Blagrove ([the5krunner on the Loughborough review, Aug 2026](https://the5krunner.com/2026/08/25/runna-loughborough-university-partnership/)).
- Runna's head coach cites a self-reported injury rate 43% below a 2015 benchmark. No peer-reviewed comparison exists.
- Users and coaches say paces and mileage are aggressive by default, and some slow their progression in Training Preferences ([AOL/Women's Health on the controversy](https://www.aol.com/articles/inside-controversy-surrounding-strava-run-162700562.html); forum: [Trustpilot reviews](https://ie.trustpilot.com/review/runna.com)).
- Pace zones exported to Garmin watches have sometimes shown wrong alerts (forum: [Garmin forums, "Pace range wrong?"](https://forums.garmin.com/outdoor-recreation/outdoor-recreation/f/fenix-7-series/375386/pace-range-wrong)).

**Pricing.** $119.99/yr on its own, or $149.99/yr (£119.99) bundled with Strava (the5krunner).

**Lesson for Stride.** Runna's market proves that runners pay for plans that feel personal and specific. The WSJ story shows the risk of fast pace and distance progression that users cannot see into. Stride's evidence-gated ladders and capped ramps answer that criticism directly, and Stride should say so in the product.

## Garmin: Coach, Run Coach and Daily Suggested Workouts

Garmin bought TrainingPeaks and TrainHeroic on July 22, 2026 ([Garmin press release](https://www.garmin.com/en-US/newsroom/press-release/corporate/garmin-acquires-trainingpeaks-and-trainheroic-leading-endurance-and-strength-training-platforms-for-athletes-and-coaches/)). Garmin now owns the main coach-led platform as well as its own algorithmic coaching.

### The Firstbeat-based metrics underneath

Garmin acquired Firstbeat in 2020. Its physiology metrics come from Firstbeat's models ([the5krunner, Garmin training features](https://the5krunner.com/garmin-features/training/)).

- **Acute load.** Rolling 7-day load derived from estimated EPOC (excess post-exercise oxygen consumption). Training Status compares it with chronic load (reviewer: the5krunner).
- **HRV Status.** Compares a 7-day average of overnight HRV with the athlete's personal baseline. The bands are Balanced, Unbalanced, Low and Poor. It needs about three weeks of consistent sleep data before it shows a status (official: [Forerunner 265 manual, HRV Status](https://www8.garmin.com/manuals/webhelp/GUID-F41EAFB3-6CC9-42DE-9C6C-9E358DBB0671/EN-US/GUID-9282196F-D969-404D-B678-F48A13D8D0CB.html); [Garmin blog on HRV Status](https://www.garmin.com/en-US/blog/fitness/understanding-the-hrv-status-on-your-garmin-smartwatch/)).
- **Training Readiness.** A 1–100 score recalculated through the day from sleep score, recovery time, HRV status, acute load, three nights of sleep history and three days of stress history. Garmin does not publish the weights. Bands run from Prime (95–100) to Poor (1–24) (official: [Training Readiness manual page](https://www8.garmin.com/manuals/webhelp/GUID-F41EAFB3-6CC9-42DE-9C6C-9E358DBB0671/EN-US/GUID-C21BE0C8-A08E-4DA1-B6C6-2E0E2DDDB372.html)).
- **Training Status.** Productive, Maintaining, Overreaching, Detraining and so on, based on changes in VO2max, acute load and HRV status over time (official: [Garmin blog on Training Status](https://www.garmin.com/en-US/blog/fitness/garmin-training-status-and-how-to-use-it/)).

### Daily Suggested Workouts (DSW)

- **Inputs.** A Training Status and a VO2max estimate are required before DSW suggests anything (official: Instinct 3 manual). Suggestions are based on activities saved to Garmin Connect (official: [Forerunner 265 manual](https://www8.garmin.com/manuals/webhelp/GUID-F41EAFB3-6CC9-42DE-9C6C-9E358DBB0671/EN-US/GUID-3E98F0F7-8B88-46FC-9F82-61EB6ECEC628.html)). Reviewers add Training Load (acute and chronic), Recovery Time, Training Readiness on newer watches, load focus and an optional race goal.
- **How it picks the session.**
  - It chooses a type (recovery, base, tempo, threshold, VO2max intervals or long run) with an HR or pace target tied to VO2max-based zones (reviewer: [the5krunner, DSW](https://the5krunner.com/daily-suggested-workouts)).
  - Productive status allows hard sessions. Overreaching or unfinished Recovery Time forces easy ones.
  - A race goal shifts the mix toward race-specific intensity as the date approaches.
- **How it adapts.** It re-evaluates after every activity, one day at a time. DSW does not plan a periodized block.
- **Complaints.**
  - Workouts too hard for the runner, or at odd paces (forum: [FR265 user feedback](https://forums.garmin.com/sports-fitness/running-multisport/f/forerunner-265-series/333521/new-user-feedback-suggested-workouts-intervals-music-and-sailing/1618402); [Fenix 6 thread](https://forums.garmin.com/outdoor-recreation/outdoor-recreation/f/fenix-6-series/241500/suggested-workouts)).
  - Hard sessions placed right after hard days ([TrainerRoad forum](https://www.trainerroad.com/forum/t/garmin-daily-suggested-workout-vs-trainerroad-garmin-has-more-data/103724)).
  - The opposite as well: weeks of only base runs, and a bug that suggested seven straight rest days ([FR745 "only base"](https://forums.garmin.com/sports-fitness/running-multisport/f/forerunner-745/304320/suggested-workouts---only-base); [seven rest days](https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-web/354481/why-do-i-have-7-daily-suggested-workouts-of-all-rest/1707960)).
  - Users feel the sessions aim to fill Garmin's own load-focus charts rather than serve a goal.
  - Reviewers note DSW depends on wrist HR and VO2max estimates, which carry about 3–5 ml/kg/min of error, and that no independent study has evaluated it.
- **Pricing.** Free on supported watches.

### Garmin Coach and Run Coach

- **Original Garmin Coach.** 5K, 10K and half-marathon plans written by Jeff Galloway (run-walk), Greg McMillan (pace-based) and Amy Parkerson-Mitchell. They adapt to the runs you complete and show a confidence score for race day. Garmin aims them at beginner and intermediate runners, "up to an 8-minute mile" (official: [Garmin blog, "Which adaptive training plan is right for you"](https://www.garmin.com/en-MY/blog/running/which-adaptive-training-plan-is-right-for-you/)).
- **Run Coach** moved into Garmin Connect in 2024. Garmin's own algorithm now builds and adjusts the workouts, including for the marathon, in the same way as DSW ([Gadgets & Wearables](https://gadgetsandwearables.com/2024/08/05/garmin-run-coach-connect/)).
- **Complaints.**
  - Garmin asks for running details it already has (reviewer: [ShouldITrain review](https://www.shoulditrain.com/blog/garmin-coach-review)).
  - Bugs in the 2024 beta with rest-day scheduling and with plans that ignored chosen preferences.
  - A forum user reported a half-marathon plan that jumped from about 5:00/km to 3:00–3:59/km paces ([Garmin forums, "Garmin Coach workouts buggy and dangerous"](https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-mobile-andriod/165855/garmin-coach-workouts-buggy-and-dangerous/1061106)).
  - This matches Jake's own frustration: unrealistic paces and overly complicated sessions.
- **Pricing.** Free. **Connect+**, launched March 2025 at $6.99/mo or $69.99/yr, adds the "Active Intelligence" AI insights (beta at launch), a performance dashboard and extra coaching content for Run Coach users. A boycott post on the Garmin subreddit drew about 10,000 upvotes ([Tom's Guide](https://www.tomsguide.com/wellness/smartwatches/garmin-launches-a-paywall-here-are-all-the-premium-connect-features-that-will-cost-you-usd6-99-a-month); [DC Rainmaker walkthrough](https://dcrainmaker.com/2025/03/garmin-connect-plus-subscription-walkthrough.html); [Tom's Guide on the backlash](https://tomsguide.com/wellness/smartwatches/garmin-sparks-outrage-with-connect-subscription-paywall-have-your-say)).

**Lesson for Stride.** Garmin has the richest data (HRV, sleep, load) and the weakest workout writing. Stride already pulls the same data through `garminconnect`. The opening is to use those signals as conservative brakes inside a real plan, without copying Garmin's day-by-day roulette. Garmin's readiness score is a black box, so Stride should use the raw signals rather than the score alone.

## Strava

- **Plans.** Strava has no plan engine of its own. Training plans come from Runna, which is offered in a bundle.
  - Strava's race discovery uses Runna's race database (the5krunner, [Runna explainer](https://the5krunner.com/runna/)).
  - Deeper integrations are promised, such as sending today's Runna workout to Strava's route planner ([Believe in the Run](https://believeintherun.com/strava-runna/)).
- **Athlete Intelligence.**
  - A generative-AI summary under each activity. It covers pace, Grade Adjusted Pace, HR and zones, and Relative Effort compared with past activities, for example the previous 30 days (official: [Strava support, Athlete Intelligence](https://support.strava.com/hc/en-us/articles/26786795557005-Athlete-Intelligence-on-Strava)).
  - It comments on what happened. It does not prescribe or change training.
  - Paid subscribers only. It launched in public beta in 2024 ([Cycling Weekly](https://cyclingweekly.com/news/strava-introduces-artificial-intelligence-feature-for-subscribers)).
- **Fitness & Freshness** is Strava's own CTL/ATL/TSB-style chart built on Relative Effort. It is paid only.
- **Complaints.** AI summaries that restate obvious stats, and price rises. UK monthly went from £6.99 to £8.99 ([BikeRadar](https://www.bikeradar.com/news/strava-hikes-monthly-subscription-cost-by-more-than-25-per-cent/); [T3 hands-on](https://t3.com/active/strava-athlete-intelligence-i-tried)).
- **Pricing.** $11.99/mo, $79.99/yr, family plan $139.99/yr, or $149.99/yr with Runna ([Runner's Picks, 2026](https://www.runnerspicks.com/blog/strava-pricing-is-it-worth-it/)).

**Lesson for Stride.** Stride's post-run analysis already compares the actual reps with what was prescribed. That is more useful than Athlete Intelligence, which only knows what you ran, not what you were supposed to run.

## TrainingPeaks

- **Inputs.** Each workout's Training Stress Score (TSS): rTSS for running pace, hrTSS for heart rate, or power TSS. Each depends on an accurate threshold.
- **The model: the Performance Management Chart.** The PMC is a simplified version of the Banister impulse-response model ([TrainerRoad forum](https://www.trainerroad.com/forum/t/performance-management-chart/18713); [MyProCoach PMC explainer](https://support.myprocoach.net/hc/en-us/articles/360040589772)).
  - **CTL (Fitness)** is an exponentially weighted average of daily TSS with a 42-day time constant.
  - **ATL (Fatigue)** is the same with a 7-day constant.
  - **TSB (Form)** is CTL minus ATL. A positive value means fresh; a negative value means accumulated fatigue.
  - Caveats: a high CTL built from easy volume does not guarantee speed, and wrong thresholds make the whole chart misleading ([Uphill Athlete info sheet](https://uphillathlete.com/?p=60379); [FastTalk Labs](https://fasttalklabs.com/videos/how-to-use-trainingpeaks-performance-management-chart)).
- **ATP (Annual Training Plan).** A Premium planner that lays out weekly TSS targets and periods leading to A, B and C races. Plans themselves come from a human coach or from the marketplace.
- **How it adapts.** It doesn't, automatically. A human coach reads the PMC and changes the plan. Marketplace plans are static.
- **Complaints.** Expensive. The analysis is too complex for runners without a coach. Plans don't adapt by themselves.
- **Pricing.** Basic is free. Premium is about $19.95/mo or $134.99/yr; the same article also gives $124.99 in its FAQ ([TrainingPeaks pricing blog](https://www.trainingpeaks.com/blog/trainingpeaks-pricing/)). The ATP and PMC are Premium only.

**Lesson for Stride.** CTL/ATL/TSB is a better load model than the mileage ratio and is well understood. Stride can calculate it from data it already has, such as pace-based load or Garmin's per-activity training load, and present form plainly without TrainingPeaks' complexity.

## COROS (EvoLab)

- **Inputs.** HR and pace from every run. EvoLab unlocks after one continuous 25-minute road run and uses up to six weeks of data ([COROS EvoLab](https://coros.com/evolab)).
- **Model** ([COROS, "Recovery metrics explained"](https://coros.com/stories/coros-coaches/c/your-coros-recovery-metrics-explained); [DC Rainmaker explainer](https://dcrainmaker.com/2021/05/revamped-training-explainer.html)).
  - **Base Fitness** is long-term load over about six weeks.
  - **Load Impact** is short-term load over seven days.
  - **Fatigue** is how much Base Fitness remains after Load Impact. This is COROS's version of TSB.
  - **Intensity Trend** gives statuses such as Optimized, Maintaining and Decreasing.
  - Weekly load is shown against a suggested range, and a Recovery Timer estimates time to recover.
  - **Running Fitness** comes from how HR relates to pace and sets threshold zones and race predictions.
- **Plans.** Written by certified coaches and periodized (build, recovery, taper, peak). Workouts follow EvoLab zones, so they get faster as Running Fitness improves without manual changes ([COROS Training Hub](https://www.coros.com/stories/coros-coaches/c/welcome-to-the-training-hub)).
- **How it adapts.** Zones change. The structure, such as which day holds which session or a missed week, is not documented as adapting.
- **Complaints.** Plans are fixed templates. Zones depend on HR quality. Third-party coaches report they cannot read Training Hub plans back out ([athletedata.health](https://www.athletedata.health/guides/coros-ai-coach)).
- **Pricing.** EvoLab and plans are free with a COROS watch.

**Lesson for Stride.** COROS uses current fitness to scale paces, which is the same idea as Stride's pace calibrator. Stride goes further by using actual workout splits rather than an HR-pace estimate.

## Polar

- **Running Program.** HR-zone plans for 5K through the marathon in three phases: base building, build-up and tapering. Two to five runs a week, plus optional strength and mobility videos. Max HR is estimated from age unless the runner enters a measured value (official: [Polar Running Program support](https://support.polar.com/en/support/polar_running_program); [FAQ](https://support.polar.com/en/support/polar_running_program_faqs)).
- **How it adapts.**
  - Every four weeks during base building, it reviews how much time the runner spent in each HR zone. It then suggests moving up a level, staying, or moving down.
  - Weekly "stars" reward hitting zone targets.
  - The plan cannot be edited after it is created.
  - Polar states that the program **does not adapt when Recovery Status is strained.**
- **Other features.** **Nightly Recharge** (Sleep Status plus ANS status from early-night HRV) and **FitSpark** (daily suggestions in the style of DSW) are separate features. They do not feed the Running Program.
- **Pricing.** Free with a Polar watch.

**Lesson for Stride.** Polar has an overnight recovery measure and a plan side by side and does not connect them. That is exactly the state Stride is in today.

## The book plans: baseline

These plans are what serious runners trust and what forums compare apps against.

- **Jack Daniels (*Daniels' Running Formula*).**
  - Paces come from VDOT, calculated from a recent race. There are five intensities: E, M, T, I and R.
  - Quality volume has limits per session ([summary in a RunningAhead thread](https://www.runningahead.com/forums/post/e989f57406784efdabd375505274c770); [Active](https://www.active.com/running/Articles/Interval-Training-Tips-for-Runners)):
    - T: the lesser of 10% of weekly mileage or 60 minutes
    - I: the lesser of 8% or 10K
    - R: 5%
  - Daniels updates VDOT only after a race or a clear training improvement, and holds a training load for several weeks before raising it.
  - The 2Q marathon plans peak at about 70 mpw ([Running with Rock](https://runningwithrock.com/pfitz-vs-jack-daniels-marathon/)).
- **Pete Pfitzinger (*Advanced Marathoning*, 4th ed. 2025).**
  - Lactate-threshold tempos, medium-long midweek runs and progressive long runs.
  - Mileage bands: 18/55, 18/70, 18/85 and so on.
  - Pfitz runs threshold work before VO2 work; Daniels runs speed first ([Slowtwitch forum](https://forum.slowtwitch.com/t/pete-pfitzinger-or-jack-daniels-marathon-training/482833)).
  - It has explicit rules for interrupted training. Fewer than 10 missed days: resume the schedule. More than 10 days with 8+ weeks left: you can resume. A long gap in the last two months: likely revise the goal ([Human Kinetics excerpt](https://us.humankinetics.com/blogs/excerpt/what-to-do-when-your-marathon-training-gets-interrupted)).
- **Hansons (*Hansons Marathon Method*).**
  - Six days a week with three "Something of Substance" days: speed, then strength, a tempo at goal marathon pace, and the long run.
  - Long runs are capped at about 16 miles and run on tired legs ("cumulative fatigue") ([Laura Norris](https://lauranorrisrunning.com/marathon-monday-hansons-marathon-method-weekly-workouts/); [Luke Humphrey on the 16-miler](https://lukehumphreyrunning.com/hansons-marathon-method-the-16-miler/)).
  - Its tempo runs at goal marathon pace, where Pfitz uses lactate-threshold pace ([RunningAhead](https://www.runningahead.com/forums/post/1e67c63e307740a7a72ad0af63d854e3)).
- **How they adapt.** Through the runner following the book's rules. Nothing happens automatically.
- **Complaints.** Rigid. Missed weeks are hard to handle. Paces depend on a recent race. The plans assume the runner can already handle the mileage.

**Lesson for Stride.** Stride's workouts should look like these: simple and specific, with volume tied to weekly mileage. Daniels' quality limits and Pfitzinger's interruption rules are published, defensible rules that Stride can encode.

---

## What Stride should add or keep as differentiators

Ranked by impact on Jake's training divided by build effort. Each item says where it fits in the current code. The pattern stays the same throughout: the deterministic `backend/app/core` decides, the LLM chooses only among server-validated candidates, and every change has a written reason.

### Keep: already ahead of the field

1. **Paces from real splits, not one race estimate.**
   - Today: `services/pace_calibrator.py`, `services/lap_analyzer.py` and `core/workout_evaluator.py` (ADVANCE / HOLD / REGRESS / RECALIBRATE / INSUFFICIENT).
   - Runna drives every pace from one estimated race time, and Garmin drives paces from a VO2max estimate. Stride's evidence gating (one fast day does not advance) matches Runna's Pace Insights. The difference is that Stride shows the rep-by-rep reasons.
   - Keep the rule that one session never moves paces.
2. **Simple, specific workouts on ladders.**
   - Today: `core/workout_ladders.py`, `core/session_catalog.py` and `core/workouts.py`.
   - This answers both Garmin's complicated sessions and Runna's aggressive progression. The descriptions should stay in book form ("6×800 at 3:02, 90s jog").
3. **Conservative, visible load ramps.**
   - Today: `core/load_policy.py` (10–20% per block depending on distance from peak), `core/block_assessment.py` (missed miles are not owed back), and the spacing and budget checks in `core/plan_validator.py`.
   - Given the WSJ Runna story, this is a selling point. Show the ramp rate and the reason on the plan approval screen.
4. **Rolling 2-week blocks that the athlete approves.**
   - Today: the preview, approve and discard draft flow in `api/plans.py`.
   - No competitor asks the athlete to approve a block. TrainingPeaks needs a human coach to do it.
5. **A bounded LLM.**
   - Today: `services/openai_coach.py` and `services/session_options.py`.
   - Garmin's Active Intelligence and Strava's Athlete Intelligence are free-text summaries. Stride's model can only pick validated candidates, which is a real trust advantage. Keep it that way.

### Add: highest value first

1. **Let wellness data drive conservative, explained adjustments.**
   - **Today:** HRV, resting HR, sleep, readiness score and Garmin's ACWR are stored (`models/wellness.py`, `services/wellness.py`). `recovery_signals()` in `api/wellness.py` turns them into dashboard messages, and `services/coaching.py` passes seven days of them to the LLM as context. No deterministic rule in `core/` acts on them.
   - **Add:** a pure `core/recovery_policy.py` that takes the last 7–14 days of `DailyWellness` and returns one of `normal | caution | back_off` with reasons.
   - **Rules,** fail-safe and only ever easing:
     - Only *fresh* data counts. The freshness rule in `api/wellness.py` already enforces this.
     - Require **two or more** concurrent signals, or the same signal on **two consecutive days**, before acting. For example: HRV below the baseline-low line, resting HR at least 5 bpm above its 7-day average, or sleep under 6 hours.
     - Compare with the athlete's rolling baseline rather than population norms. Garmin's HRV Status needs three weeks for the same reason.
   - **Effect:** on `back_off`, offer a preview that turns today's or tomorrow's workout into the easy option or swaps it with the next easy day. It goes through the same `plan_validator` checks and the same preview and approve flow as feedback changes.
   - Never raise intensity because readiness is high. Polar and Garmin show that a single readiness number misleads in both directions.
   - **Why first:** no competitor does this transparently. Garmin does it opaquely through DSW and Polar not at all. The data is already in Stride's database.
2. **A real fitness/fatigue model next to the mileage ratio.**
   - **Today:** `services/load_history.py` gives one calendar-week mileage ratio (`calendar-load-v1`). By its own docstring, that is a policy ratio and not an injury predictor.
   - **Add:** CTL, ATL and TSB in the style of the PMC (42-day and 7-day exponentially weighted averages). Use a daily load from Garmin's per-activity training load when present, otherwise duration × an intensity factor from pace relative to threshold.
   - **Uses:**
     - Show "form" before races. Taper checks in `core/periodization.py` can confirm that TSB rises into race week.
     - Feed `block_assessment` as one more reason to hold.
   - **Keep the mileage ratio** as the rule that actually blocks plans. A model without validated thresholds should explain decisions, not gate them.
3. **"Not feeling 100%" and illness handling in Pfitzinger's style.**
   - **Today:** a feel rating of 4 or lower downgrades the next workout (`_apply_feedback_effects` in `api/plans.py`). The interruption logic sizes from what was actually run.
   - **Add:** an explicit "I'm sick / sore / slammed this week" action that previews a reduced block.
   - Encode published return rules for gaps: fewer than 10 days, resume; longer gaps, a reduced rebuild; a late gap before a race, warn and offer a goal change. Cite Pfitzinger in the explanation.
   - Runna's version of this is one of its most-praised features.
4. **Daniels quality limits as a validator rule.**
   - **Add** to `core/plan_validator.py`: threshold volume at most the lesser of 10% of weekly miles or 60 minutes per session; intervals at most the lesser of 8% or 10K; repetitions at most 5%.
   - This gives the "never rush" philosophy a citable source and catches ladder levels that get too big in low-mileage weeks.
5. **Weather and heat adjustments.**
   - **Today:** nothing in the backend.
   - **Add:** a forecast lookup for the run's time and place, then add 15–45 s/mi to easy and tempo paces in heat and humidity, and change interval targets to effort.
   - Runna's Adapt for Heat shows demand for this. Stride can go further by comparing post-run HR drift with the forecast. Phase 2 in `CLAUDE.md` already lists this.
6. **Taper and race readiness readout.**
   - Combine TSB (item 2), recent quality evaluations (`services/quality_history.py`) and long-run completion into a plain "ready / on track / behind" note in race week.
   - Garmin's race-day confidence score is the comparison, but Stride's version would show its inputs.
7. **Push structured workouts to the watch.**
   - Garmin Coach, Runna and COROS all put the workout on the wrist.
   - `garminconnect` exposes workout upload. Treat this as an optional, failure-tolerant step after the athlete approves a block.
   - Lower priority because it touches the athlete's Garmin account, so it needs careful confirmation.

### Don't copy

- **A single opaque readiness score that drives the day.** Garmin DSW draws complaints in both directions: too hard on tired days, and weeks of only base runs.
- **Pace from one estimated race time across all distances** (Runna). Stride's per-session calibration is better.
- **Fixed plans that ignore recovery** (Polar, the book plans, the TrainingPeaks marketplace).
- **Free-text AI that is not tied to the prescription** (Strava Athlete Intelligence, Garmin Active Intelligence).
- **Paywalling basic data.** The backlash to Garmin's Connect+ and Strava's price rises shows how users react.
