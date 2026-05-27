# Stride Frontend Plan

> Personal AI running coach for Jake Bowen. This is a tool built for one person first — every decision optimizes for YOUR workflow, YOUR data, YOUR goals.

## Stack

- **Next.js** (App Router)
- **Tailwind CSS**
- **shadcn/ui** (Radix primitives, fully customizable)
- **Recharts** (graphs/data viz)
- **Geist Sans / Geist Mono** fonts
- **Light mode default**, dark mode toggle

## Design Language

Clean, fast, information-dense where it matters, spacious where it doesn't. Think Strava's data clarity meets Apple Health's restraint. No flashy gradients, no gamification badges, no social feed noise.

- **Colors**: Neutral zinc base, single accent color (blue or green — runner-friendly, not aggressive). Subtle use of red/amber for injury risk or missed targets.
- **Typography**: Geist Sans for UI, Geist Mono for paces/splits/numbers/distances. Large hero numbers. Small but readable labels.
- **Cards**: Clean bordered cards with subtle shadows. No heavy backgrounds.
- **Spacing**: Generous. The app should feel like it breathes — you open it mid-run-prep and need info fast.
- **Motion**: Minimal. Page transitions only if they feel instant. No loading spinners on primary data — skeleton loaders.

## Pages & Layout

### Global Layout

```
+----------------------------------------------------------+
|  STRIDE              [Today] [Plan] [History] [Settings]  |
|                                              [light/dark] |
+----------------------------------------------------------+
|                                                          |
|                      Page Content                        |
|                                                          |
+----------------------------------------------------------+
```

- Top nav bar, not sidebar. This is a focused app, not a dashboard suite.
- Nav items: **Today**, **Plan**, **History**, **Settings**
- Logo/wordmark left, nav center or right, theme toggle far right
- Mobile: bottom tab bar with same 4 items

---

### 1. Today (Dashboard) — `/`

The home screen. What you see when you open the app every morning.

```
+----------------------------------------------------------+
|  STRIDE              [Today] [Plan] [History] [Settings]  |
+----------------------------------------------------------+
|                                                          |
|  Good morning, Jake                    Mon, May 26 2026  |
|                                                          |
|  +-----------------------------------------------------+|
|  |  TODAY'S WORKOUT                                     ||
|  |                                                      ||
|  |  Easy Run                              6 mi          ||
|  |  Conversational pace, truly easy                     ||
|  |                                                      ||
|  |  Target: 8:00-8:30/mi                                ||
|  |  Warmup: 5 min walk/jog                              ||
|  |  Cooldown: 5 min walk                                ||
|  |                                                      ||
|  |  WHY: Recovery from yesterday's tempo. Keep the      ||
|  |  legs moving without adding stress. Aerobic          ||
|  |  development happens here.                           ||
|  +-----------------------------------------------------+|
|                                                          |
|  THIS WEEK                              32.4 / 42 mi    |
|  +---+---+---+---+---+---+---+                          |
|  | M | T | W | T | F | S | S |  <- mini week strip      |
|  | 6 |8x8| 5 | T | - |14 | 5 |  <- workout summaries   |
|  | . | . | . | . |   | . |   |  <- dot = completed      |
|  +---+---+---+---+---+---+---+                          |
|                                                          |
|  +-------------------------+  +-------------------------+|
|  |  WEEKLY MILEAGE         |  |  PACE VS TARGET         ||
|  |  ██ 42                  |  |    /\  target            ||
|  |  ██ 40                  |  |   /  \_/  actual         ||
|  |  ██ 38                  |  |  /                       ||
|  |  ██ 36                  |  |                          ||
|  |  last 8 weeks           |  |  last 6 workouts        ||
|  +-------------------------+  +-------------------------+|
|                                                          |
|  LAST RUN                             Yesterday, 4:15pm  |
|  Tempo Run - 8.2 mi - 6:52/mi avg                       |
|  Feel: 7/10  "Felt strong through mile 5, last 2 were.."|
|  Coach: "Solid tempo. Splits were consistent..."         |
|                                                          |
+----------------------------------------------------------+
```

**Components**:
- `TodayWorkoutCard` — the hero. Full workout details, purpose, paces. If rest day, shows "Rest Day" with a note about why.
- `WeekStrip` — 7-day mini calendar. Shows workout type abbreviation, completed dot, today highlighted.
- `WeeklyMileageChart` — bar chart, last 8 weeks, planned vs actual bars.
- `PaceVsTargetChart` — line/scatter, last 6 quality workouts, target pace line vs actual.
- `LastRunSummary` — compact view of most recent activity with feel rating and coach feedback snippet.

**Data needed from API**:
- `GET /api/plan/today` — today's workout
- `GET /api/plan/week/current` — this week's plan + completion status
- `GET /api/activities/recent?limit=1` — last run
- `GET /api/stats/weekly-mileage?weeks=8` — mileage chart data
- `GET /api/stats/pace-vs-target?limit=6` — workout pace data

---

### 2. Plan — `/plan`

View and manage your current 2-week training block.

```
+----------------------------------------------------------+
|  CURRENT PLAN              Week 1 of 2    [Approve Next] |
|  Sub-17 5K  |  May 19 - Jun 1  |  Build Phase           |
+----------------------------------------------------------+
|                                                          |
|  WEEK 1 (current)                          38 mi planned |
|  +------------------------------------------------------+|
|  | Mon May 19    Easy Run           6 mi       DONE     ||
|  | Tue May 20    800m Repeats       8 mi       DONE     ||
|  |               6x800 @ 3:24, 90s rest                 ||
|  | Wed May 21    Easy Run           5 mi       DONE     ||
|  | Thu May 22    Tempo Run          8 mi       DONE     ||
|  |               3mi @ 6:15 (threshold)                 ||
|  | Fri May 23    Rest               -                   ||
|  | Sat May 24    Long Run           14 mi      DONE     ||
|  |               Steady, last 2mi @ MP                  ||
|  | Sun May 25    Easy + Strides     5 mi       TODAY    ||
|  +------------------------------------------------------+|
|                                                          |
|  WEEK 2                                    40 mi planned |
|  +------------------------------------------------------+|
|  | Mon May 26    Easy Run           6 mi                ||
|  | Tue May 27    1K Repeats         9 mi                ||
|  |               5x1K @ 3:55, 2min rest                 ||
|  | Wed May 28    Easy Run           5 mi                ||
|  | ...                                                  ||
|  +------------------------------------------------------+|
|                                                          |
|  PLAN NOTES                                              |
|  "Building toward peak week. Mileage up 5% from last    |
|   block. Key sessions: Tuesday intervals and Saturday    |
|   long run with race-pace finish."                       |
|                                                          |
+----------------------------------------------------------+
```

**Components**:
- `PlanHeader` — goal, date range, phase, week indicator
- `PlanWeek` — expandable week view. Each day is a row.
- `PlanDay` — workout type, distance, detail line, completion status. Click to expand full workout details.
- `PlanNotes` — AI-generated summary of the block's focus
- `ApprovePlanButton` — when current block is ending, prompts to generate + approve next 2-week block

**Interactions**:
- Click a day to see full workout detail (same as TodayWorkoutCard but in a sheet/modal)
- Swap days: drag-and-drop or tap two days to swap (respects hard/easy rule — warns if violated)
- Mark a day as skipped with optional reason
- "Approve Next Block" triggers plan generation for next 2 weeks

**Data needed**:
- `GET /api/plan/current` — full current 2-week block
- `POST /api/plan/generate` — generate next block
- `PUT /api/plan/approve/{plan_id}` — approve a generated block
- `PUT /api/plan/swap-days` — swap two days
- `PUT /api/plan/skip-day/{day_id}` — mark day skipped

---

### 3. History — `/history`

All past runs. Searchable, filterable. Your training log.

```
+----------------------------------------------------------+
|  HISTORY                                                 |
|  [All] [Workouts] [Long Runs] [Easy]     [Search...]    |
+----------------------------------------------------------+
|                                                          |
|  +-------------------------+  +-------------------------+|
|  |  MILEAGE OVER TIME      |  |  LONG RUN PROGRESSION   ||
|  |  line chart, 12 weeks   |  |  line chart, 12 weeks   ||
|  +-------------------------+  +-------------------------+|
|                                                          |
|  May 2026                                                |
|  +------------------------------------------------------+|
|  | May 24   Long Run       14.1 mi   7:42/mi   Feel: 8 ||
|  | May 22   Tempo          8.2 mi    6:52/mi   Feel: 7 ||
|  | May 21   Easy Run       5.0 mi    8:15/mi   Feel: 6 ||
|  | May 20   800m Repeats   8.1 mi    7:05/mi   Feel: 8 ||
|  | May 19   Easy Run       6.0 mi    8:22/mi   Feel: 7 ||
|  +------------------------------------------------------+|
|                                                          |
|  April 2026                                              |
|  +------------------------------------------------------+|
|  | ...                                                  ||
|  +------------------------------------------------------+|
|                                                          |
+----------------------------------------------------------+
```

**Components**:
- `RunFilters` — filter pills (All, Workouts, Long Runs, Easy) + search bar
- `MileageOverTimeChart` — line chart, longer timeframe (12 weeks default)
- `LongRunProgressionChart` — just long runs, showing distance progression
- `RunList` — grouped by month, each row is a run summary
- `RunDetailSheet` — click a run to open a side sheet with full details: splits, HR, coach analysis, feel rating

**Data needed**:
- `GET /api/activities?type=&search=&page=` — paginated activity list with filters
- `GET /api/activities/{id}` — single activity detail
- `GET /api/stats/mileage-over-time?weeks=12`
- `GET /api/stats/long-run-progression?weeks=12`

---

### 4. Post-Run Flow — `/activity/{id}/review`

After a run syncs, you get prompted to review it. This can appear as a sheet overlay or a dedicated page.

```
+----------------------------------------------------------+
|  HOW DID THAT FEEL?                                      |
|                                                          |
|  Tempo Run - 8.2 mi - 6:52/mi avg                       |
|  Thursday, May 22                                        |
|                                                          |
|  +------------------------------------------------------+|
|  |  1   2   3   4   5   6   7   8   9   10             ||
|  |                          [7]                          ||
|  |  terrible                              amazing        ||
|  +------------------------------------------------------+|
|                                                          |
|  Anything to note? (optional)                            |
|  +------------------------------------------------------+|
|  | Left calf felt tight after mile 5. Loosened up after ||
|  | the cooldown.                                        ||
|  +------------------------------------------------------+|
|                                                          |
|                                        [Submit Review]   |
|                                                          |
|  --- after submit, coach analysis appears ---            |
|                                                          |
|  COACH ANALYSIS                                          |
|  "Good tempo execution. Your splits were consistent      |
|   (6:50, 6:52, 6:54) which shows discipline. The calf   |
|   tightness is worth monitoring — I'll keep tomorrow     |
|   easy and short. If it persists, we'll add an extra     |
|   rest day. HR stayed in zone 3-4 throughout, right      |
|   where we want it for threshold work."                  |
|                                                          |
|  SPLITS                                                  |
|  | Mile 1: 7:15 (warmup) | Mile 5: 6:54 |              |
|  | Mile 2: 6:50          | Mile 6: 6:52 |              |
|  | Mile 3: 6:52          | Mile 7: 7:20 (cooldown) |   |
|  | Mile 4: 6:50          | Mile 8: 7:45 (cooldown) |   |
|                                                          |
+----------------------------------------------------------+
```

**Components**:
- `FeelRatingSlider` — 1-10 scale, large tappable numbers
- `RunNoteInput` — optional textarea
- `CoachAnalysis` — AI-generated analysis, streamed in after submission
- `SplitsTable` — per-mile or per-km splits
- `RunMetrics` — avg pace, HR zones, cadence, elevation (compact grid)

**Data needed**:
- `GET /api/activities/{id}` — activity data + splits
- `POST /api/activities/{id}/review` — submit feel + notes
- `GET /api/activities/{id}/analysis` — coach analysis (may be streamed)

---

### 5. Onboarding — `/onboarding`

Multi-step flow for first-time setup. Only shown once (or accessible from settings to re-do).

**Steps**:

1. **Welcome** — "Let's build your training plan." Brief intro.
2. **About You** — Age, preferred units (mi/km), workout format preference (time/distance)
3. **Running Background** — Years running, current weekly mileage (slider: 0-100+), peak mileage ever
4. **Race History** — Add PRs. Fields: distance dropdown, time input, date (approximate OK). Can add multiple. Can skip.
5. **Availability** — Days per week available (3-7 slider), preferred rest days (tap to toggle days), preferred long run day
6. **Goal Selection** — Four cards:
   - Race Goal (pick distance + target time + race date)
   - Mileage Goal (target mpw)
   - General Fitness
   - Return from Injury/Break
7. **Connect Strava** — OAuth button. "We'll pull your run history to understand your fitness." Skip option for manual entry.
8. **Review & Start** — Summary of all inputs. "Generate My Plan" button.

**Design**: One step per screen. Progress bar at top. Back button. Clean, no clutter. Each step has a large heading and minimal inputs.

**Components**:
- `OnboardingLayout` — progress bar, step container, back/next buttons
- `StepWelcome`, `StepAboutYou`, `StepRunningBackground`, `StepRaceHistory`, `StepAvailability`, `StepGoalSelection`, `StepConnectStrava`, `StepReview`
- `PRInput` — reusable distance + time + date row for entering race results
- `DayPicker` — 7-day toggle strip for selecting rest/long run days
- `GoalCard` — selectable card for each goal type

**Data needed**:
- `POST /api/onboarding` — submit all onboarding data
- `GET /api/strava/auth-url` — get Strava OAuth URL
- `GET /api/strava/callback` — handle OAuth callback

---

### 6. Settings — `/settings`

```
+----------------------------------------------------------+
|  SETTINGS                                                |
+----------------------------------------------------------+
|                                                          |
|  PROFILE                                                 |
|  Age: 21                                    [Edit]       |
|  Units: Miles                               [Edit]       |
|  Workout format: Distance-based             [Edit]       |
|                                                          |
|  TRAINING                                                |
|  Days per week: 6                           [Edit]       |
|  Rest days: Friday                          [Edit]       |
|  Long run day: Saturday                     [Edit]       |
|                                                          |
|  CURRENT GOAL                                            |
|  Sub-17 5K  |  Race: Jun 28, 2026           [Change]     |
|                                                          |
|  CONNECTIONS                                             |
|  Strava: Connected (jake_bowen)        [Disconnect]      |
|  Garmin: Not connected                    [Connect]      |
|                                                          |
|  APPEARANCE                                              |
|  Theme: Light                          [Light/Dark]      |
|                                                          |
|  DATA                                                    |
|  Re-run onboarding                     [Start Over]      |
|  Export training data                  [Export CSV]       |
|                                                          |
+----------------------------------------------------------+
```

**Components**:
- `SettingsSection` — grouped settings with label + edit trigger
- `GoalChangeFlow` — changing goal triggers a mini wizard (similar to onboarding goal step) + transition plan generation
- `ConnectionStatus` — shows connected account, disconnect button
- `ThemeToggle` — light/dark switch

---

## File Structure

```
frontend/
├── app/
│   ├── layout.tsx                 # Root layout, nav, fonts, providers
│   ├── page.tsx                   # Today/Dashboard
│   ├── plan/
│   │   └── page.tsx               # Plan view
│   ├── history/
│   │   └── page.tsx               # History/log
│   ├── activity/
│   │   └── [id]/
│   │       └── review/
│   │           └── page.tsx       # Post-run review
│   ├── onboarding/
│   │   └── page.tsx               # Multi-step onboarding
│   ├── settings/
│   │   └── page.tsx               # Settings
│   └── globals.css                # Tailwind base + theme tokens
├── components/
│   ├── ui/                        # shadcn/ui components (auto-generated)
│   ├── nav.tsx                    # Top nav bar
│   ├── mobile-nav.tsx             # Bottom tab bar (mobile)
│   ├── today-workout-card.tsx
│   ├── week-strip.tsx
│   ├── plan-week.tsx
│   ├── plan-day.tsx
│   ├── run-list.tsx
│   ├── run-detail-sheet.tsx
│   ├── coach-analysis.tsx
│   ├── feel-rating.tsx
│   ├── splits-table.tsx
│   ├── run-metrics.tsx
│   ├── goal-card.tsx
│   ├── day-picker.tsx
│   ├── pr-input.tsx
│   ├── onboarding/
│   │   ├── onboarding-layout.tsx
│   │   ├── step-welcome.tsx
│   │   ├── step-about-you.tsx
│   │   ├── step-running-background.tsx
│   │   ├── step-race-history.tsx
│   │   ├── step-availability.tsx
│   │   ├── step-goal-selection.tsx
│   │   ├── step-connect-strava.tsx
│   │   └── step-review.tsx
│   └── charts/
│       ├── weekly-mileage-chart.tsx
│       ├── pace-vs-target-chart.tsx
│       ├── mileage-over-time-chart.tsx
│       └── long-run-progression-chart.tsx
├── lib/
│   ├── api.ts                     # API client (fetch wrapper for FastAPI backend)
│   ├── types.ts                   # TypeScript types matching backend models
│   └── utils.ts                   # Formatting helpers (pace, distance, time)
├── public/
│   └── ...
├── tailwind.config.ts
├── next.config.ts
├── package.json
└── tsconfig.json
```

## API Client Strategy

The frontend talks to the FastAPI backend at `localhost:8000` (dev) or a deployed URL (prod). Simple fetch wrapper in `lib/api.ts` — no heavy state management library. React Server Components fetch data directly; client components use `useEffect` or a lightweight hook.

No auth tokens in Phase 1 (single user, local). Phase 2 adds JWT auth.

## Responsive Behavior

- **Desktop (1024px+)**: Full layout as shown above. Charts side-by-side.
- **Tablet (768-1024px)**: Charts stack vertically. Same nav.
- **Mobile (<768px)**: Bottom tab bar replaces top nav. Charts full-width stacked. Workout card takes full screen. Onboarding steps use full viewport height.

The app should be fully usable on your phone for checking today's workout pre-run.

## Key UX Decisions (Jake-specific)

1. **No login screen in Phase 1.** Single user, local. Just open it and go.
2. **Miles, not kilometers.** Default to miles. KM is a setting but you won't use it.
3. **Distance-based workouts.** "6x800m" not "6x2:30". That's your preference.
4. **Paces in min:sec/mi.** Always. Large and readable.
5. **Coach analysis reads like a real coach.** Not clinical, not cheesy. Direct, specific, data-backed.
6. **Weekly mileage is THE metric.** It's the hero number on the dashboard. Everything else is supporting detail.
7. **Strava is the primary data source.** Garmin is Phase 2. The app syncs from Strava and never asks you to manually log unless you choose to.
8. **Fast load.** Today's page should render instantly with cached data. Background refresh for latest sync.

## Build Order

1. Project scaffold (Next.js + Tailwind + shadcn/ui + fonts)
2. Root layout + nav
3. Onboarding flow (need this first to have user data)
4. Today page (dashboard) with mock data
5. Plan page
6. Post-run review flow
7. History page
8. Settings
9. Wire up to real API endpoints
10. Charts with real data
