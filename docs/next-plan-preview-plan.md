# Preview next plan (planning doc)

> Status: **plan only, nothing built.** Written Oct 29 2026. Build starts the week of Nov 2.
> Everything below is based on the code on `main` at `13e5925` (Dusk redesign #72, FIT export #73).

## 1. The idea in one paragraph

Near the end of the current block (Friday or Saturday of its last week), a **Preview next plan**
button appears. The athlete sees the next two weeks early, so they can sort out logistics before
the block starts: a trip, a busy Wednesday, a race, a different rest day. What they set during
the preview are **scheduling inputs** (dates and limits), not edits to fitness. The preview is
**provisional**. Stride doesn't know yet how the last 1–3 days of the current block will go
(usually including the long run), so the block is rebuilt from real data when the current block
ends. The athlete's scheduling inputs are applied again, and the athlete confirms the final
version with a short "what changed since your preview" list. The athlete still approves every
block (CLAUDE.md, "Respect the athlete"), and nothing activates early.

---

## 2. What exists today (research)

### 2.1 Backend plan lifecycle (`backend/app/api/plans.py`)

| Piece | What it does today | Matters here because |
|---|---|---|
| `POST /{uid}/generate`, `POST /{uid}/preview` | The same function (`generate_training_plan`). Always saves an **inactive draft** (`Plan.is_active=False`, `preview_state="draft"`, `preview_data` = full JSON payload, `preview_context` = fingerprint). `PlanRequest` has `scope: current/next`, `mode: full/schedule`, `lighter`, `start_date`. | We reuse this generator. The early preview is a new kind of call to it. |
| `scope="next"` guard | Returns 409 "Finish this block before creating the next one" while `athlete_today() <= active.end_date`. Tested by `test_next_block_cannot_reopen_an_approved_current_block`. | This is the rule the feature relaxes, and only for a provisional preview. |
| Block dates | Without `start_date`, `calculate_plan_params()` starts on **Monday of the current week**: 2 weeks if today is Mon–Wed, 3 weeks if Thu–Sun, so blocks always end on a **Sunday**. With `start_date`, it's 2 weeks from that date. | The next block starts on `active.end_date + 1` (a Monday) and runs 2 full weeks. |
| Every generate call supersedes **all** drafts | `db.query(Plan).filter_by(user_id, preview_state="draft").update("superseded")`. `_revise_schedule` does the same. | A next-block preview would silently kill a pending current-block revision, and the reverse is also true. Needs a draft scope. |
| `GET /{uid}/draft` | Returns the newest draft of any kind. | The Plan page shows `preview ?? active` (`lib/plan-state.ts`), so a next-block draft would **replace the current plan on screen**. Needs a scope filter. |
| `POST /drafts/{id}/approve` | Takes the write lock, checks the fingerprint, rejects drafts with `violations`, runs `_validate_schedule`, then **deactivates the active plan and activates the draft in one commit**. | Approving a next block early would end the current block mid-week. So early approval can't use this path as it is (see §4). |
| `POST /drafts/{id}/discard` | `preview_state="discarded"`. | Reused as is. |
| `_preview_fingerprint` | Hashes `athlete_today()`, the user row, active goals, the active plan id and schedule, **every run activity**, and progression rows. | A Friday preview goes stale at midnight and on every sync. That's correct for a provisional preview, so it must be cheap to rebuild. |
| `GET /{uid}/current` → `_plan_payload` | Active plan with actuals, `is_stale` (end date passed), `outlook`, `review`, `expectations`. | We add one `next_preview` object here, so the frontend doesn't work out eligibility on its own. |
| `POST /{uid}/sessions/{date}` (`change_session`) | `skip`, `replace`, `move`, `switch` on the **active** plan only. `switch` uses `GET …/switch-targets` + `_resolve_switch` + a `switch_token`. Checked by `_validate_schedule`. Approved rest-day exceptions are kept in `load.rest_date_overrides`. | The preview's "switch two days" should use the same resolver, but on draft rows and without writing. Right now every one of these endpoints hard-codes `is_active=True`. |
| `_revise_schedule` + `core/schedule_revision.py` + `core/change_guard.py` | A schedule-only change (run days, rest days, long-run day, `day_time_budgets`) to the current block is a draft that keeps workouts and long runs and moves the fewest days. `review_change` refuses unsafe results, and `summarize_change` writes the "Week 1: 42 → 40 mi" lines. | `summarize_change` is exactly the "what changed since your preview" diff. The schedule-revision rules are the model for applying date exceptions. |
| `core/time_budget.fit_availability(weeks, limits, …)` | Fits sessions into **weekday** minute limits (moves a long run to the nearest roomy day instead of cutting it). | Needs a per-**date** variant for "Nov 5: 30 min" and "Nov 7–9: away". |
| Inputs that depend on "today" | `baseline` = last 4 **completed calendar weeks**. `deload_due(full_weeks)`. `_assess_previous_block` counts only days `< today`. `prior_hard_dates` = real hard runs in the 3 days before `fpd`. | On a Friday, the current week isn't complete, and the Saturday long run hasn't happened. An early build has to **project** the remaining planned days (§4.2). Otherwise it under-counts the baseline, misses a deload, and can put a workout on Monday right after Sunday's long run. |

### 2.2 How the next block is made today

**Manually, and only after the block ends.** Nothing runs automatically. On the Monday after
the end date, `/current` returns `is_stale: true`. The Plan page swaps to a card that says "Your
last training block ended …" with a **Generate this week's plan** button
(`generatePlan(false, "next")`). Plan options also has a **Preview next block** button gated by
`nextBlockAvailable(end, today)` = `today > end` (`lib/plan-state.ts`). Either way, a draft
appears with **Approve / Make it lighter** (no "Keep current plan", because the active plan is
stale). Until the athlete acts, Today shows no prescribed run. So today the athlete only sees
their next two weeks on Monday morning, which is the problem this feature fixes.

### 2.3 Frontend (Dusk)

- `app/(app)/plan/page.tsx`: the header (`kicker` "Block N · two weeks", `display` heading with
  `<em>`), **Plan options** button, a "Review this block" `Panel` (accent `--type-threshold`)
  when a draft is visible, with Approve / Make it lighter / Keep current plan and the
  `change_summary` and `changes` lists. Below that: `PlanSpotlight`, the "Your two weeks" `Panel`
  with `PlanCalendar` (compact list on phone, week rows on desktop), a day inspector (side `Sheet`
  on desktop ≥1024px, inline panel on phone), stats, coach perspective, expectations, goal route,
  change log and pacing guide.
- `plan-options-dialog.tsx`: bottom sheet on phone. Contains Switch two days, Ask coach, and
  Rebuild (lighter / revise / preview next block).
- `session-controls.tsx`: Replace / Switch / Skip segmented control, switch targets with reasons.
  `PlanDayDetail` takes `readOnly` (already true for drafts).
- `time-availability.tsx`: per-weekday minutes on Settings, saved to `/users/{id}/profile`.
- Look: `panel`, `glass`, `glass-tile`, `btn-gloss`, `KindPill`, the type colors
  (`--type-threshold`, `--type-easy`, `--accent-warm`), rounded-[22px] tiles.

### 2.4 Rules from docs that this feature must keep

- CLAUDE.md: rolling 2-week blocks, **the athlete confirms each block**, never back-to-back hard
  days, conservative ramp, fail safe ("when in doubt, prescribe less").
- ARCHITECTURE.md: "Next-block generation is only offered after completion; revision is a separate
  explicit action." This doc proposes changing that sentence to "the next block can be
  **previewed** from Friday of the last week, but only **built for approval** after completion."
- `plain-language-plan-changes.md`: the AI rearranger was removed on Oct 28 because it broke
  weekends. **This feature uses no AI.** Logistics go through deterministic inputs and Switch.
- `coaching-trust-hardening.md`: stale advice must be visibly stale, and page views must not
  trigger paid reviews. The provisional preview never queues a coach review.

---

## 3. When the button appears

The server decides and returns it on `/current` as `next_preview`, using `athlete_today()` (the
athlete's `User.timezone`, set per request by `athlete_zone`). The frontend renders it and never
compares dates itself. The client's clock can differ from the athlete's timezone, and the
existing `nextBlockAvailable` compares on the client.

```
opens_on = active.end_date - 2 days      # Friday when the block ends on Sunday
available = opens_on <= today <= active.end_date   (plus the exceptions below)
after end_date: existing "block ended" flow, no provisional step (data is complete)
```

`next_preview` shape (new):

```json
{ "state": "hidden" | "upcoming" | "available" | "ready" | "blocked",
  "opens_on": "2026-10-30", "next_start": "2026-11-02", "next_end": "2026-11-15",
  "reason": "Finish reviewing your current-block changes first.",
  "draft_id": 41, "stale": false, "exceptions": 2 }
```

- `upcoming`: in the last week but before Friday. No button. Optionally a quiet line in the
  header: "Next block preview opens Fri".
- `available`: button shows, no draft yet.
- `ready`: a provisional draft exists (`stale` says if it needs a refresh).
- `blocked`: button shows disabled with `reason`.

### Edge cases

| Case | Behaviour |
|---|---|
| **Block ends on a day other than Sunday** (a `start_date` block) | Same rule: the last 3 days of the block. `next_start = end_date + 1`, 2 weeks. |
| **Race in the remaining days of the current block** (e.g. goal race on Saturday) | `blocked`: "Your next block depends on how race day goes. It'll be ready the day after." After the race, the goal is complete, so the post-race block (`apply_post_race_rest`) is built after completion through the normal flow. A tune-up race that isn't the goal: there's no model for it today (see Open questions). |
| **Taper or race week in the next block** | Allowed. The preview shows the phases (`phases`, `Badge`). Race and taper days stay reduce-only: date exceptions can shorten or rest a day, never add work, and race day can't move. The header shows "Taper · Race Nov 15". |
| **Race date inside the next block** (the next block is the last one before the race, shorter than 2 weeks, or it ends with post-race rest) | Show the real length ("9 days to race day, then recovery"). Nothing special in generation, which already counts back from `Goal.race_date`. |
| **Goal race already past, or no active goal** | `hidden`. Generation already returns 400 without a goal. Goal setup comes first. |
| **The plan has ended (`is_stale`)** | No provisional preview. The existing Generate flow is final because the data is complete. The new date-exception inputs (§5) are shown there too, so it's one way to make a block, with or without the early look. |
| **Current block is behind** (week 2 completion is low so far, or `falling_behind_decision` would fire) | Still `available`, but the preview shows a notice: "Built as if you finish this week as planned. You're at 62% of this week's miles, so the final block may be smaller." If the falling-behind decision is required, `blocked` until it's answered (it changes the goal). |
| **A current-block draft exists** (schedule change, lighter, revise) | `blocked`: "Approve or discard your current-block changes first." The preview builds on the approved current block, so a pending change would make it wrong. |
| **A next-block provisional draft already exists** | `ready`. The button reads **View next plan**. If `stale` (any sync, session change, settings change, or the date rolled), opening it rebuilds it automatically (cheap and deterministic, no AI), keeping the athlete's exceptions and pins. |
| **Athlete opens it at 11:58 pm Sunday** | Still provisional. At midnight, `is_stale` flips and the page shows the final-build flow, with exceptions already applied. |
| **Athlete never confirms** | Same as today: on Monday the block is `is_stale`, and Today says there's no plan. Plus a Today card: "Your next block is ready to confirm". |
| **Runs Monday before confirming** | The final build counts Monday's run as completed (`completed_by_date`, `fpd = tomorrow`). Same as today. |
| **Two devices** | Approve/build take `_begin_schedule_write`. A stale fingerprint returns 409 and the page reloads, as today. |
| **Beginner / run-walk / developmental path** | No difference. The same generator, so the same rules. |

---

## 4. Honesty: provisional, then rebuilt

### 4.1 Decision: provisional preview, final build at block end

Three options were considered:

1. **Lock in early** (approve Friday, activate Monday). Simple, but the next block's size comes
   from `_assess_previous_block` (build / hold / reduce / recovery) and `deload_due`, and on Friday
   neither has seen Saturday's long run or the rest of the week. If the athlete skips the weekend
   or the long run goes badly, the locked block still builds. That breaks fail-safe.
2. **Provisional, rebuilt at confirmation.** *(Recommended.)* The preview is built as if the
   remaining days go as planned and is clearly labelled that way. What the athlete settles during
   the preview are scheduling inputs that survive a rebuild. When the block completes, Stride
   rebuilds from real data, applies the inputs again, and shows what moved. The athlete approves
   that version.
3. **Hybrid**: approve early, and re-check automatically on Monday. If the assessment decision,
   deload and weekly budgets are unchanged, activate it. Otherwise ask again. Nicer, but it's
   automatic activation, which conflicts with "the athlete confirms each block" unless Jake
   explicitly wants it. Kept as Open question 1.

### 4.2 How the provisional build "projects" the rest of the block

A new internal flag on `generate_training_plan` (not a public field): `projected=True`, used only
for the early preview.

- `params`: `start_date = active.end_date + 1`, 2 weeks, `first_prescribe_date = start`.
- **Projected days**: every not-yet-run day in the active block from today to `end_date` counts
  as done at its planned distance and type.
  - `completed_by_date`, the weekly mileage list for `baseline` and `deload_due`, and
    `weekly_run_days` include those planned miles. Treat the current week as completed with
    `actual + remaining planned`.
  - `prior_hard_dates` includes planned hard days (long run, workout) in the 3 days before the
    next start. This is the fix that stops a Monday workout after a Sunday long run.
  - `_assess_previous_block` gets an `as_of=end_date + 1` and a `projected_days` map, so
    unplayed days count as planned with unknown feel. `assess_block` already treats missing feel
    as "not a bad rating".
- `_recent_fatigue_assessment` still uses only real data, so a fatigue signal today still reduces
  the preview.
- The payload is marked `provisional: true` with `projected_through: end_date` and
  `projected_days: [{date, title, miles}]`, so the UI can say exactly what was assumed.

### 4.3 What happens at the final build

Triggered when the athlete opens the Plan page after `end_date`, or taps Confirm on Today (§6).
It's a normal `scope="next"` build (no projection), with the same exceptions and pins. The
response adds `since_preview`: `summarize_change(provisional.weeks, final.weeks)` plus a reason
line from the assessment difference:

> "Since your preview: Week 1 is 2 mi lighter (Saturday's long run was cut short), and Thursday
> intervals are now threshold. Your Nov 5 rest day and Nov 7–9 travel limits are kept."

If nothing material changed (same session types on the same dates, each week within ±1 mi),
the copy says "Same as your preview", and confirming is one tap.

---

## 5. What the athlete can change during the preview

All of these are **inputs to the generator**, never hand-edits to draft rows that a rebuild would
wipe out.

| Input | Stored as | Applied by |
|---|---|---|
| **Day off** ("can't run Nov 5") | `ScheduleException(date, kind="off")` | The generator treats that date as rest (`rest_date` list). The week's budget is not re-crammed into other days (same as `schedule_gap`: "missing miles will not be crammed"). Easy days absorb what fits, and any remainder is dropped. |
| **Time limit on a date** ("Nov 7–9: 30 min max, travelling") | `ScheduleException(date, kind="limit", minutes)` | `fit_availability` gets per-date limits that override weekday limits. A long run moves to the nearest roomy day, as it does now. |
| **Note** ("in Denver, altitude") | `ScheduleException.note` | Shown on the day. Not used by rules (open question: altitude). |
| **Switch two days** in the preview | `SchedulePin(source_date, target_date)` recorded on the draft | Re-applied after each rebuild with `_resolve_switch` on the draft rows. If it's no longer valid (e.g. the session on that day changed), it's dropped, with a line in `since_preview`: "Your Tue ↔ Thu switch no longer fits; Thursday is now an easy day." |
| **Change regular rest days, run days or long-run day** ("from now on") | The existing profile (`/users/{id}/profile`) | The next preview rebuilds with them. The current block gets the existing mismatch banner and "Update my plan" (schedule revision). The UI asks once: **Just these dates** vs **From now on**. |
| **Make it lighter** | The existing `lighter` flag | Kept as a sticky choice on the provisional draft, so the final build is also lighter. |

Not allowed in the preview: adding a workout, moving the race, lengthening a long run, raising
weekly miles, Replace with a harder session. Those stay as active-plan actions after approval,
through the existing session menu.

**New table `schedule_exceptions`** (created with `add_missing_columns`-style migration in
`database.py`): `id, user_id, date, kind ('off'|'limit'), minutes, note, created_at, deleted_at`.
They're per date, not per plan, so they also apply if the athlete later revises the current block
or builds without the early look, and they remain visible in history. Only dates `>= today` can
be added.

---

## 6. User stories

1. *As a runner going away next weekend*, on Friday I can see next week's long run is on Saturday
   the 7th and set Nov 7–9 to 30 minutes, so the long run moves to Wednesday or Thursday before I
   leave, not onto a travel day.
2. *As a runner with a busy Wednesday*, I can mark Nov 4 as a day off and see how the week
   rearranges before Monday, instead of skipping a session in the middle of the block.
3. *As a runner who prefers the long run on Sunday this time*, I can switch Sat ↔ Sun in the
   preview, and the switch is still there when I confirm on Monday.
4. *As a cautious runner*, I can see clearly that the preview assumes I finish this weekend as
   planned, and on Monday I see what changed because of how the weekend actually went.
5. *As a racer in taper*, the preview shows my taper and race week, and Stride doesn't let me add
   work there. A day off just makes it lighter.
6. *As Jake (owner)*, I never get a next block that activates without my tap, and nothing in the
   preview calls the AI or spends budget.
7. *As a runner who forgot*, on Monday Today says "Your next block is ready, confirm it" and keeps
   the travel limits I set on Friday.
8. *As a runner who changed my mind*, I can discard the preview and my date exceptions stay
   (or I can clear them), and nothing about my current block changes.

---

## 7. User flows

### Flow A: Preview on Friday, confirm on Monday (main flow)

1. Fri Oct 30. Plan page header shows the **Preview next plan** button (desktop: next to Plan
   options; phone: full-width under the header). Today shows a small card: "Your next block
   starts Mon Nov 2 · Preview".
2. Tap → `POST /plans/1/preview {scope:"next", provisional:true}` → the Plan page switches to a
   **Next block** tab (the current block stays one tap away; the current-block page isn't
   replaced).
3. The provisional banner: "Preview · built as if you finish this weekend as planned (Sat long run
   12 mi, Sun easy 5 mi). Final version on Mon Nov 2."
4. Calendar of Nov 2–15, read-only day details (no FIT download, no feedback), weekly totals,
   phases, and the assessment reasons ("Building: last block 96% complete").
5. The athlete taps **Adjust dates** → sheet with a mini calendar of the 14 days. Tap Nov 7 → Off
   / Time limit / Note. Picks "Time limit · 30 min · Nov 7–9", and **Just these dates**. Save →
   `POST /plans/1/schedule-exceptions` → the preview rebuilds → the changed days are highlighted,
   with a line: "Long run moved Sat Nov 7 → Thu Nov 5 to fit your 30-min limit."
6. Optional: tap a day → **Switch** (same targets UI as now, against the draft) → pick Sun ↔ Sat →
   recorded as a pin.
7. Bottom bar: **Looks good · confirm Monday** (marks the preview as reviewed; no activation),
   **Discard preview**, and **Make it lighter**.
8. Sat: the long run syncs. The draft is stale. Opening the tab rebuilds it silently. The
   banner says "Updated after Saturday's run."
9. Mon Nov 2. Today: "Your next block is ready. 1 change since your preview." → Plan page → final
   build (`scope:"next"`, real data, exceptions + pins) → **Review this block** panel with
   `since_preview` lines → **Approve** → active. The existing approve path, unchanged.

### Flow B: Adjust availability "from now on"

At step 5, choose **From now on: no Wednesday runs** → saves the profile. The preview rebuilds.
The current block shows the existing "This block was built for 6 days…" banner with **Update my
plan** (schedule revision of the remaining current days). Both are explicit, separate approvals.

### Flow C: Mark a day off and see that miles aren't crammed in

Mark Nov 10 (a Tuesday interval day) Off → the workout moves to the next safe easy day (Wed or
Thu, never next to the long run), or, if there's no safe day, it's dropped with "Intervals
dropped this week: no safe day after Nov 10 off." Week 2 total goes down. The UI shows the old
and new total ("Week 2: 44 → 39 mi").

### Flow D: Discard and regenerate

**Discard preview** → `discard` (existing) → the button returns to **Preview next plan**. A
checkbox, on by default: "Keep my date changes (2)". **Rebuild** is never needed by hand: any
staleness rebuilds on open. A "Rebuild now" link in the banner covers an explicit refresh.

### Flow E: Pending current-block change

The athlete has an unapproved "Make it lighter" draft for the current block → the Preview button
is disabled with "Approve or discard your current-block changes first" → tapping it scrolls to
the Review this block panel.

### Flow F: Block already ended

Monday, no preview made → existing card "Your last training block ended Nov 1" → **Generate this
week's plan** plus a new **Adjust dates first** link (the same sheet as step 5) → draft → Approve.

---

## 8. Wireframes

### Desktop (≥1024px), Friday, provisional preview open

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ BLOCK 7 · TWO WEEKS                                                  [ Plan options ]    │
│ Building for the 5K                                                                      │
│ Sub-17 5K · Nov 2 – Nov 15 · Build                                                       │
│                                                                                          │
│  ( This block · Oct 19–Nov 1 )  ( ● Next block · Nov 2–15  PREVIEW )     ← segmented tabs │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ ● PREVIEW · NOT ACTIVE YET                                                               │
│ Built as if you finish this weekend as planned: Sat long run 12 mi, Sun easy 5 mi.       │
│ Stride rebuilds it Mon Nov 2 from your real runs and keeps your date changes.            │
│ Building: last block 96% complete so far.                                                │
│ [ Adjust dates ]  [ Make it lighter ]                         Discard preview · Rebuild  │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ YOUR NEXT TWO WEEKS                                    hatched = quality / long · tap a day│
│ Week 1 · Nov 2                                                            42 mi planned  │
│  Mon      Tue        Wed      Thu         Fri    Sat        Sun                          │
│  Easy 6   6x800 ▨    Easy 6   Long 12 ▨   Rest   Easy 4 ⏱   Easy 4 ⏱                      │
│                               ↑ moved from Sat (30 min limit Nov 7–9)                    │
│ Week 2 · Nov 9                                                            44 mi planned  │
│  Mon ⏱    Tue        Wed      Thu         Fri    Sat        Sun                          │
│  Easy 4   Thresh ▨   Easy 6   Easy 7      Rest   Long 13 ▨  Easy 6                       │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ DATE CHANGES (2)                                                                         │
│  Nov 7–9  ⏱ 30 min max · "Denver trip"                                       Edit · ✕    │
│  Sat↔Sun  Week 2 switch kept                                                  ✕          │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│                                  [ Looks good · confirm Monday ]                         │
└──────────────────────────────────────────────────────────────────────────────────────────┘
  Day click → right Sheet (PlanDayDetail readOnly) with "Switch" and "Day off / limit" only.
```

### Phone (375px), same moment

```
┌─────────────────────────────┐
│ BLOCK 7 · TWO WEEKS         │
│ Building for the 5K         │
│ Nov 2 – 15 · Build          │
│ [This block][Next ● PREVIEW]│
├─────────────────────────────┤
│ ● PREVIEW · NOT ACTIVE YET  │
│ Assumes Sat 12 mi long +    │
│ Sun 5 mi easy go as planned.│
│ Rebuilt Mon Nov 2.          │
│ [ Adjust dates ]            │
├─────────────────────────────┤
│ WEEK 1 · NOV 2      42 mi   │
│ Mon  Easy 6                 │
│ Tue  6x800m ▨         8     │
│ Wed  Easy 6                 │
│ Thu  Long run ▨      12     │
│      moved from Sat         │
│ Fri  Rest                   │
│ Sat  Easy 4  ⏱ 30 min       │
│ Sun  Easy 4  ⏱ 30 min       │
│ WEEK 2 · NOV 9      44 mi   │
│ …                           │
├─────────────────────────────┤
│ Date changes (2)        ›   │
├─────────────────────────────┤
│[ Looks good · confirm Mon ] │  ← sticky bottom
│  Make it lighter · Discard  │
└─────────────────────────────┘
```

### Phone: Adjust dates sheet (bottom sheet, like Plan options)

```
┌─────────────────────────────┐
│ Adjust dates                │
│ Mark days you can't run or  │
│ have less time. Stride won't│
│ squeeze the miles in.       │
│  M  T  W  T  F  S  S        │
│  2  3  4  5  6 [7][8]       │
│ [9] 10 11 12 13 14 15       │
│ Nov 7–9                     │
│ ( Off ) (● Time limit )     │
│ Minutes [ 30 ]              │
│ Note  [ Denver trip      ]  │
│ ( ● Just these dates )      │
│ (   From now on (Settings)) │
│ [ Save ]                    │
└─────────────────────────────┘
```

### Monday: Today card and confirm panel

```
Today                                          Plan page (final build)
┌───────────────────────────────┐              ┌──────────────────────────────────────┐
│ ● NEXT BLOCK READY            │              │ ● REVIEW THIS BLOCK                  │
│ Nov 2 – 15 · 42 / 44 mi       │              │ Since your preview:                  │
│ 1 change since your preview.  │              │ · Week 1: 42 → 40 mi (Sat long run   │
│ [ Review and approve ]        │              │   was 9 of 12 mi)                    │
└───────────────────────────────┘              │ · Your Nov 7–9 limits are kept.      │
                                               │ [ Approve ] [ Make it lighter ]      │
                                               └──────────────────────────────────────┘
```

Visual notes: banner = `Panel` with accent `--type-threshold` and a dashed border (a new
`panel-provisional` modifier) so it reads "not active". Days changed by an exception get a ⏱ or
"off" `KindPill` and the existing `adjustment_note` line. The tabs are a segmented control matching
`Segmented` in `session-controls.tsx`.

---

## 9. Existing vs new

### Backend

| Area | Exists | New / changed |
|---|---|---|
| Generator | `generate_training_plan` | `projected` path (§4.2); `scope="next"` allowed during the last 3 days only when `provisional=True`; reads `schedule_exceptions` and pins; adds `provisional`, `projected_days`, `since_preview` to the payload. |
| Draft model | `Plan.preview_state`, `preview_data`, `preview_context` | New column `Plan.preview_scope` (`current` / `next`) and `Plan.provisional` (bool). Supersede only drafts of the **same scope**. |
| `GET /draft` | Newest draft | `?scope=current` (default, so the Plan page keeps showing the current block) and `?scope=next`. |
| Approve | `approve_draft` | Refuse a `provisional` draft (409 "Preview only; confirm after Nov 1"). Unchanged otherwise. |
| Eligibility | `nextBlockAvailable` (frontend) | `next_preview` on `/current` (§3). The frontend helper is removed. |
| Date inputs | Weekday `day_time_budgets`, `rest_date_overrides` | `schedule_exceptions` table; `GET/POST/DELETE /plans/{uid}/schedule-exceptions`; per-date limits in `fit_availability`; off-dates as rest in `generate_plan`. |
| Switch in a draft | `switch-targets`, `_resolve_switch`, `switch_token` (active plan only) | Optional `?plan_id=` for a next-scope draft: it resolves on the draft rows and records a pin instead of writing a change log. `_resolve_switch` is reused as is. |
| Safety | `validate_plan`, `enforce_no_back_to_back_hard`, `change_guard` | Run `validate_plan` on the next block **plus the projected last 3 days of the current block**. A preview with violations is shown with the violation, never silently fixed. |
| AI | Coach perspective on drafts | None for provisional drafts (`CoachingReview` gets `planId` only for non-provisional ones). |

### Frontend

| Area | Exists | New / changed |
|---|---|---|
| Plan page | Draft-or-active view, Review this block panel, Plan options | "This block / Next block" tabs; provisional banner; sticky confirm bar on phone; `next_preview` drives the button. |
| `lib/plan-state.ts` | `loadPlanState`, `nextBlockAvailable` | Load `draft?scope=current` and `draft?scope=next` separately. |
| `plan-options-dialog.tsx` | "Preview next block" after end | Keep as a second entry point, driven by `next_preview`. |
| Day detail | `PlanDayDetail readOnly` | In a next-block preview: show **Switch** and **Day off / limit** only. |
| New components | — | `next-block-banner.tsx`, `adjust-dates-sheet.tsx`, `date-changes-list.tsx`, Today `next-block-card.tsx`. |
| Settings | `time-availability.tsx` | Unchanged. "From now on" links to it. |

### API sketch (all under `/api/plans/{user_id}`)

```
POST /preview                  {scope:"next", provisional:true}       → provisional draft (409 outside window)
GET  /draft?scope=next                                                → provisional/final next draft or null
GET  /current                  … + next_preview {state, opens_on, next_start, draft_id, stale, reason}
GET  /schedule-exceptions?from=YYYY-MM-DD                             → [{id,date,kind,minutes,note}]
POST /schedule-exceptions      {dates:[…] | from,to, kind, minutes?, note?}  → rebuilds next draft if one exists
DELETE /schedule-exceptions/{id}
GET  /sessions/{date}/switch-targets?plan_id=…                        → targets on a next draft
POST /drafts/{id}/pins         {source_date, target_date, switch_token}
POST /drafts/{id}/approve      (refuses provisional)
POST /drafts/{id}/discard      {keep_exceptions: true}
```

---

## 10. Safety rules (non-negotiable)

1. **No back-to-back hard days, across the block boundary.** The provisional build counts the
   current block's remaining planned long run or workout as prior hard days. Validation runs on
   the joined window `[end_date - 2, next_end]`. Exceptions and pins must pass `validate_plan`
   (the only allowed pair is a flagged ultra back-to-back). A violation is refused with its reason,
   never silently downgraded, so the athlete sees exactly what will be saved.
2. **Mileage ramp.** Exceptions and pins can only keep or reduce weekly volume. Week budgets come
   from `load_policy` as now. A day off never moves its miles into other days beyond the existing
   budget. The final build re-runs `_assess_previous_block` and `deload_due` on real data, so a
   missed weekend can only make the block smaller, never bigger than the preview.
3. **The athlete approves each block.** Provisional drafts can't be approved. The final draft goes
   through the existing fingerprint and `_validate_schedule` checks. Nothing activates on its own
   (unless Jake picks the hybrid in Open question 1).
4. **Taper and race weeks are reduce-only.** Race day can't be switched, made off or limited.
5. **Long runs are protected.** A limit moves the long run to the nearest roomy day
   (`fit_availability`) or, if there's none, the long run becomes easy with a stated reason. It's
   never quietly shortened while keeping its title.
6. **No AI.** The deterministic engine does all of this. No paid calls on preview, rebuild or
   exception save.
7. **Disposable databases for tests.** Never `backend/stride.db`.

---

## 11. Tests to write (per PR)

- Eligibility: Thu → `upcoming`, Fri/Sat/Sun → `available`, Mon → `is_stale` flow. Timezone:
  11 pm Thu Pacific is still Thu when the server is in UTC Friday.
- Provisional build with an unrun Sunday long run never puts a workout on Monday.
- The baseline and deload in a Friday preview equal the Monday final build when every projected
  day is run exactly as planned (season sim helper: run the remaining days, then compare).
- Skipping the projected weekend → the final block is ≤ the preview each week; `since_preview`
  explains it.
- A next-scope draft doesn't supersede a current-scope draft, and the reverse.
- `GET /draft` default still returns the current-scope draft (Plan page unchanged).
- `approve` refuses a provisional draft.
- Off-day and time-limit exceptions survive the rebuild. Taper days only shrink. Race day refuses.
- Pins re-apply after a rebuild, or drop with a reason.
- Season matrix (`STRIDE_SEASON_FULL=1`): run every block via "preview Friday, then final build" and
  check the existing season-level rules still hold.
- Frontend: plan-state tests for split draft loading; banner copy for each `next_preview` state.

---

## 12. Suggested build order (small PRs)

1. **Draft scopes** (backend only). `Plan.preview_scope` column, supersede by scope,
   `GET /draft?scope=`, frontend loads `scope=current`. No visible change. Fixes a real bug class
   up front (a draft silently superseding another).
2. **`next_preview` eligibility** on `/current` with tests, replacing `nextBlockAvailable`. Show the
   button disabled with "Coming soon" behind a flag, or just the "opens Fri" line.
3. **Projected provisional build.** `provisional=True` path in `generate_training_plan` (projection
   of remaining days, cross-boundary validation), `approve` refuses provisional. Tests from §11.
4. **Next block tab and provisional banner** (frontend). Read-only preview, Discard, auto-rebuild
   when stale, Make it lighter. **This alone is usable** (see your next two weeks early).
5. **Final build with `since_preview`** and the Today "Next block ready" card.
6. **Date exceptions.** Table, endpoints, per-date `fit_availability`, off-days in the generator,
   Adjust dates sheet, date changes list, "Just these dates / From now on".
7. **Switch pins in the preview.** `switch-targets?plan_id=`, pins re-applied on rebuild.
8. **Docs.** Update ARCHITECTURE.md (the "only offered after completion" line), CLAUDE.md core-loop
   wording, README beta notes.

PRs 1–4 are about a week. 5–7 can follow one at a time.

---

## 13. Open questions for Jake

1. **Provisional vs early approval.** Recommended: provisional preview, confirm on Monday. Do you
   want the hybrid instead (approve Friday, auto-activate Monday if nothing material changed,
   ask again if it did)?
2. **When it opens.** Friday of the last week (3 days early) as described, or Thursday, or only
   Saturday (after fewer unknowns, but less time to plan)?
3. **Tune-up races.** Should "Race on Nov 8 (10K tune-up)" be an input in Adjust dates? It's a
   real need for scheduling, but there's no non-goal race model today, so it would be its own
   feature (race-week taper for a B race, post-race rest).
4. **Confirm on Sunday night?** The block ends Sunday. If Sunday's run has synced, should the final
   build be allowed Sunday evening instead of waiting for Monday?
5. **Day off: move or drop?** When a day off lands on a workout, move it to the next safe easy day
   (current `fit_availability` behaviour), or always drop it for that week and keep the plan simpler?
6. **Exceptions scope.** Are date exceptions per date (global, also used if you revise the current
   block) as proposed, or only for the next block?
7. **Travel notes like altitude or heat.** Notes only for now, or should they affect pace guidance
   later (weather and altitude are Phase 2)?
8. **Should the preview show the coach perspective** (an AI call) once it's final, or only after
   approval like today?
