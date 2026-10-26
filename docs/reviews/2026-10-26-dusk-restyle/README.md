# Dusk glass restyle (2026-10-26)

The frontend now follows the "Stride running app wireframes" artifact. It has two themes:

- **Dusk** (dark): the wireframe's peach → slate → navy gradient, with frosted navy glass.
- **Daybreak** (light): a pale peach → sky gradient, with white glass and navy text.

By default the theme follows the system setting. Settings → Appearance can force Light or Dark (stored per device in `localStorage["stride-theme"]`). The theme is applied before first paint by an inline script in `app/layout.tsx`.

Other changes:
- Type is Manrope: light 300 for titles and hero numbers, 800 for the wordmark, tabular figures for numbers.
- The cockpit's black strips and dark sidebar are replaced by a sticky glass top bar with a pill switcher. The bar firms up on scroll. Phones get a floating glass tab bar.

**One deliberate departure from the wireframe:** a navy scrim darkens the top of the dusk gradient. With the wireframe's pale peach, white and 72%-white text measure roughly 2–4:1. With the scrim, body text and muted text stay at or above about 4.5:1.

Screenshots are in this folder. They come from a synthetic demo database (`demo/seed.py --scenario sub17-5k`) in a scratch directory, never `backend/stride.db`.

## Checklist: every piece of information and every action, confirmed after the restyle

Method: before restyling, each page's code was inventoried. After restyling, every line removed from the restyled files was checked against the new markup (all are re-rendered with the same data and handlers), and each page was opened in the preview at 1440px and 375px, in both themes.

### Global / nav
- [x] Today / Plan / History / Settings links with `aria-current` (desktop pill bar, phone tab bar)
- [x] Garmin status: health dot, "synced X ago" / "not connected" / sync message. It now also shows on phones, which previously saw it only on Today.
- [x] Garmin "Sync now" button, or a "Connect" link when no key is set
- [x] Sign out: icon button in the bar on tablet/desktop; on phones, the Settings button (unchanged)
- [x] Login/auth pages show the wordmark only, no nav
- [x] Demo-scenario banner (glass pill)
- [x] NEW: nav scroll state; hover/press states on cards, rows and buttons (`.lift`); reduced-motion respected

### Today
- [x] Date heading, greeting + first name, goal, phase label
- [x] This week: done / target, % (warm accent); GarminSync button with synced time and reconnect/failed link; Connect Garmin link
- [x] Loading skeleton; error + Retry
- [x] Stale-wellness warning
- [x] TodayCard, stale plan: "Generate this week's plan"; "No plan for today yet"
- [x] Not run yet: title, planned distance (now a hero number) or Rest day, Quality badge, expand → warmup/description/cooldown, coach preview, recovery caution + "Adjust in Plan →", "Ran without your watch? Log it"
- [x] Done: activity tabs (runs, walks, Day total), Ran today / Walk recorded / All activities, Off plan badge, title opens the sheet, Miles (hero) / Pace / Time / Avg BPM, total-view four stats, work reps table + recovery, walk/total notes, "View … details & Garmin laps"
- [x] Training context: Planned line (line-through when off plan), expandable details
- [x] Feedback: "How did it go?" with watch feel/effort, "Edit your comment", evaluation, change reasons (right column on wide screens)
- [x] Coach analysis: refresh button and all states, stale notice, reviewed time, Review details, not configured, auto-job states, summary, You asked, suggestions + Apply/Applied, More/Less/Show previous advice, details, error + Retry
- [x] Activity load error; Runs waiting for your comment + expandable forms
- [x] This week: 7 day buttons with distance/actual, now also a type dot, plus selected-day details
- [x] Recent runs: 5 latest, kind pill / walk, date · distance · pace, opens the sheet; empty state
- [x] Recovery: readiness ring (larger), score, feedback, recovery hours, "N good" toggle, cautions incl. mileage risk
- [x] Metric tiles + trend chart (band, change, hide), +N more / Show fewer
- [x] Weekly mileage chart: 4/8/12w toggle, total, tooltip, See/Hide weekly totals. NEW: a 12-week mileage strip under the header (hover/focus a bar for its week; screen-reader labels)
- [x] Race predictions: predicted / PR / Goal
- [x] Run detail sheet

### Plan
- [x] Loading; no plan + Generate; no plan available; stale block + Generate + Show/Hide last block (PlanWeek list)
- [x] Title: the mode label is now the big title, and "Current Plan" stays in the accessible name. Goal, dates, phase badge, race date, Deload badge, draft/approved line.
- [x] Plan options dialog (all reasons, details, ask coach, move session, lighter, revise, next block)
- [x] Error, notice, preference-mismatch banner + Update my plan
- [x] Draft review panel + Approve / Make it lighter / Keep current plan
- [x] Stat tiles: W1/W2 plan/act + % vs W1, block baseline + as-of, Goal (solid blue tile)
- [x] Desktop calendar: one glass panel per week (number, start date, current, phase, logged of planned, progress bar). Day tiles show date, title, type dot, miles, ✓, status text (Replaced/Skipped/Moved/Not logged), off-plan "planned ~~x~~", hatch on quality days, today border, selected ring. Every aria-label is kept, including the full status.
- [x] Phone compact calendar: week header, 7 cells with day, miles, dot, ✓
- [x] Inspector: inline on phones, side sheet on desktop; PlanDay with structure bar, session controls (Replace/Move/Skip, options), feedback
- [x] Coach perspective collapsible (stays mounted); training expectations; block review; goal route (decision form, gaps, milestones); change log (clickable dates, reasons, empty state); pacing guide

### History (layout and styling only)
- [x] Title, loading, error
- [x] HistoryProfile (recent average, recorded runs + since, sustained blocks with View run N, lap evidence, gaps)
- [x] TrainingTrends (windows, note, quality execution + View run, long-run follow-up, comparable easy runs)
- [x] Mileage over time chart (colors via tokens only; `components/charts/*` untouched)
- [x] Filter tabs All (count) / Workouts / Long Runs / Easy, now pills next to a "Runs" heading
- [x] Run list by month: date, type dot, title, walk tag, hard badge, distance, pace, feel, description; click or Enter opens the sheet
- [x] Load older runs; detail sheet + reclassification refresh

### Settings
- [x] Title + Sign out; loading; error; schedule-changed notice + link
- [x] NEW: Appearance (System / Daybreak / Dusk radiogroup, arrow keys)
- [x] Profile & training preferences (view rows, edit form, save/cancel, draft messages)
- [x] Training (baseline, peak, experience, empty note)
- [x] Current goal (description, race date, no-date hint, Change → GoalEditor)
- [x] Personal records; Running stats (7 rows); Training load (ratio, detail, assessment)
- [x] Operations (AI usage, storage alert, jobs, backups, restore, offsite, policy; unavailable state)
- [x] Garmin Connect card, FIT import, Daily training time, Account and privacy (incl. delete account)

### Onboarding
- [x] All steps and their controls unchanged, inside a glass card with "Step N of M" and the progress bar
- [x] Goal cards (now `aria-pressed`), day picker (now `aria-pressed` + day name), continuous-minutes chips, PR inputs, Garmin/FIT step, review + warnings, save error

### Login / account pages
- [x] Login: description, email (accounts mode), password, error, Sign in, register/recover links, local-password hint
- [x] Register and Reset pages: same fields and links, in a glass card

### Run detail sheet
- [x] Title + hard badge, long date
- [x] Classification: kind, reason, needs-review note, Count as run / Mark as walk / Use automatic type, error
- [x] Distance (hero), pace, time, HR, elevation, cadence, training effect, VO2max, ground contact
- [x] Your run feedback form; Notes; Workout analysis; How it felt; Coach analysis; CoachingReview
- [x] Laps / splits

## Known issue (pre-existing, not changed here)
Synthetic demo runs with laps crash the run sheet. `SplitsTable` expects `pace`, but `demo_seed` writes laps as `distance_m` / `duration_s`. Real Garmin laps are unaffected.
