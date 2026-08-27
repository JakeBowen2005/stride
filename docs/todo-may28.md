# Stride TODO — May 28, 2026

## Priority 1: Pull ALL Strava Data + Descriptions

### Problem
- Only 465 activities in the database — but Jake has way more runs going back years
- The initial sync only pulled recent pages of activities
- 200 activities (Apr 2 – Oct 7, 2025) have NULL descriptions due to Strava daily rate limit (hit 1904/2000)
- History page currently shows first run as Aug 2025 — missing everything before that
- That Apr–Oct 2025 window is the peak training block (50-70 mpw) with tons of quality workouts and long runs

### Plan

**Step 1: Test API calls first (small batch)**
- Pull descriptions for just 1-2 weeks in the Oct 2025 range to verify the API is working
- Check rate limit headers after: `x-ratelimit-usage` and `x-readratelimit-usage`
- Confirm descriptions come back with workout data (we know Oct 4 has "12 miles WU then 6 at 6:45", Sept 30 has "5x1 mile @(6:20,6:14,6:15,6:19,6:03)", etc.)

**Step 2: Pull remaining 200 descriptions**
- Run `POST /api/analysis/1/fetch-descriptions` — this only targets activities with NULL description
- Rate limit budget: 200 requests needed, Strava allows 100/15min and 2000/day
- Should take ~2 batches (10 req + 2s pause pattern) = ~40 seconds if no rate limit
- If rate limited, wait 15 min between batches

**Step 3: Pull FULL Strava history (all activities ever)**
- Current `fetch_all_activities()` paginates with 200/page but may have stopped early
- Need to verify we're getting ALL pages — Strava API returns empty array when no more pages
- Fix: add logging to see how many pages were fetched and total count
- Run `POST /api/analysis/1/full-sync` to re-sync everything
- After sync, run `POST /api/analysis/1/fetch-descriptions` for any new activities
- Then run `POST /api/analysis/1/classify` to classify all activities
- Then run `POST /api/analysis/1/detect-prs` to update PRs with new data

**Step 4: Re-run analysis pipeline**
- After all data is in: re-run pace calibration (more workout data = better paces)
- Re-run classification (more workouts and long runs will be found)
- Re-run PR detection (older races/efforts may have better times)
- The plan generator automatically uses calibrated paces, so plans will improve

### Efficient Strava Pull Strategy (for new user onboarding)

When a new user connects Strava, the full pipeline should be:

1. **OAuth callback** → store tokens
2. **Paginated activity fetch** — `GET /athlete/activities?per_page=200&page=N`
   - Keep paginating until empty response
   - This is cheap: ~3-5 API calls for 500+ activities
   - Store all activities in DB immediately
3. **Detail fetch for descriptions + splits** — `GET /activities/{id}`
   - This is expensive: 1 API call per activity
   - Rate limit: 100 requests per 15 minutes, 2000 per day
   - Strategy: fetch in batches of 10 with 2s delay between
   - For 500 activities: ~50 batches × 2s = ~100 seconds + rate limit pauses
   - If >200 activities, will need multiple 15-min windows or span across hours
   - **Optimization**: Only fetch details for activities that MIGHT have descriptions:
     - Activities with `strava_workout_type == 3` (workout)
     - Activities with `strava_workout_type == 1` (race)
     - Activities with `strava_workout_type == 2` (long run)
     - Activities over 8 miles (likely long runs with notes)
     - This could cut the detail fetch from 500 to ~100-150 calls
   - **Alternative**: Fetch ALL details but do it as a background job
     - Show the user a progress indicator
     - Use Celery/background task to fetch in batches over time
     - User sees data populate gradually
4. **Classify** all activities by type
5. **Detect PRs** across all activities
6. **Calibrate paces** from workout descriptions
7. **Run full analysis** (baseline, injury risk, etc.)

### Implementation Notes
- The `sync_all_to_db()` function already handles steps 1-3 but needs the description fetch fixed
- `fetch_all_descriptions()` was added May 27 — only targets NULL descriptions
- Need to add a progress endpoint so frontend can show sync status
- Consider adding `last_detail_fetch` timestamp to Activity model to avoid re-fetching

## Priority 2: Verify Everything Works End-to-End
- Load dashboard → should show last week miles, goal, next workout, last 7 days
- Load plan → should show 2-week plan with calibrated paces
- Load history → descriptions visible, workout analysis works, filters work
- Load settings → no race date, calibrated paces showing
- Check that re-classification picked up all workouts correctly

## Priority 2.5: Integrate Workout Analysis into Plan Generator

### Problem
- The pace calibrator parses Strava descriptions and extracts real workout paces (800m splits, tempo paces, threshold paces)
- These calibrated paces feed into plan generation for prescribing paces
- But the workout analysis (parsing interval details, avg/range calculations) displayed in the run-detail-sheet frontend component is NOT yet used by the plan generator
- The plan generator should use parsed workout data to:
  1. Understand what workouts the athlete has been doing recently (e.g., 6x800, 5x1mile, tempo runs)
  2. Prescribe similar or progressive workouts (e.g., if they've been doing 5x1mile at 6:15, prescribe 5x1mile at 6:10 or 6x1mile at 6:15)
  3. Avoid prescribing workouts that are too similar to what was just done (variety)
  4. Use actual split data to validate that prescribed paces are achievable

### Plan
- Extend `pace_calibrator.py` to return a `recent_workouts` list with structured workout data (type, reps, distance, avg pace, date)
- Pass `recent_workouts` into `plan_engine.py` so it can make smarter workout selections
- The workout library rotation in `_pick_workout()` should factor in what was recently done

## Priority 3: Polish
- The 6 activities flagged as workouts that aren't real workouts (#8 Apr 6, #19 Dec 3 4mi, #20 Dec 3 8mi, #21 Nov 28, #25 Oct 28, #31 Mar 25) — consider tightening the keyword matching
- Add a way for the user to manually flag/unflag workouts
- Make the "Re-sync Strava" button on Settings actually call the sync endpoint
