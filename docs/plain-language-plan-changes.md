# Plain-language plan changes (design)

> **Removed Oct 28 2026.** In use the AI turned "move my back-to-back to Sat-Sun" into a single
> easy-day swap that left the weekend broken, and the quick picker dropped workouts instead of
> rearranging them. Both are gone from the app (services, API, UI, tests). The `plan_change_requests`
> table and model stay for history and this month's AI spend. Rearranging is now by hand with
> **Switch** (`_resolve_switch` in `api/plans.py`): swap two days in a week, back-to-back weekends
> move as a pair, and a switch that breaks hard-day spacing tries the smallest same-week
> rearrangement that keeps every session. The notes below are kept as the design history.

> Status: phases 0–1 implemented Oct 27 2026 (`core/request_ops.py`, `services/plan_changes.py`,
> `services/plan_change_ai.py`, `api/plan_changes.py`, `components/plan-change-request.tsx`).
> Open questions in §6 were defaulted to the doc's recommendations: reduce/rearrange only, no
> rest-day override, the later workout of the week is dropped first, a 14-day window, the old
> "Ask coach" review kept under a disclosure, a separate 10/day cap, gpt-5.4-mini
> (`OPENAI_PLAN_CHANGE_MODEL` to switch), clarify at most twice, undo until a changed day is run.
> Not built yet: the eval set (§5 Phase 1) and phases 2–3.

Jake's idea: the athlete writes what's coming up in their own words, for example *"It's Halloween
weekend. I'm going out Friday and Saturday night and I don't want to do my long run hungover.
Can we restructure the week?"* The AI suggests a rearranged week. Stride's deterministic rules
check that it follows the training philosophy. The athlete reviews the updated week and approves
it or says no.

This fits how Stride already works: **the AI advises, the rules decide, and the athlete approves.**
This design makes the AI's part smaller than it is in run reviews. Here it only *translates* language
into constraints and a small set of edit operations. Stride's own code applies every edit and
checks every rule.

---

## 1. What already exists

| Building block | Where | What it gives us | Gap for this feature |
|---|---|---|---|
| Plan options dialog | `frontend/components/plan-options-dialog.tsx` | The single entry point for changing the block: reason chips, a 500-char "Details" box, "Ask coach to adjust", "Move a session", and rebuilds | The free text only feeds a review. It can't produce a rearranged week. |
| Athlete concern | `ReviewRequest.athlete_concern` (`api/coaching.py`), `normalize_concern` and `context['athlete_request']` (`services/coaching.py`), `CoachingReview.athlete_concern` | The athlete's words already reach the model as **data, not instructions** ("It never widens what you may change") | The model can only pick from the candidate menu below. That menu changes one workout day at a time, so it can't move a long run. |
| Suggestion candidates | `services/coaching_options.build_options` | Each candidate is dry-run in `read_only_trial` through the **same** `_validate_schedule` used on accept: easier variants, easy, rest, and earned quality options (≤24 total) | Only replaces `type == 'workout'` days in place. It never moves, swaps or shortens a long run, and it changes one day per suggestion. |
| Accept | `POST /api/coaching/{uid}/reviews/{id}/accept` | Takes the write lock (`_begin_schedule_write`), rejects stale context (fingerprint), rejects past or run days, records the change with `_mark_changed`, re-validates and rolls back on failure | Applies one candidate. Allows one applied suggestion per review. |
| Session actions | `POST /api/plans/{uid}/sessions/{date}` (`change_session`), `session-controls.tsx` | `skip`, `replace` (easy, rest, or a policy-validated quality option), `move` | `move` only goes to a **later** unrun easy or rest day, and the destination's easy run is lost. There's no swap and no move to an earlier day, and those are exactly what Halloween needs. Each action is one day and one commit, so there's no multi-day atomic change. |
| Schedule validator | `api/plans._validate_schedule` → `core/plan_validator.validate_plan` | Weekly mileage budget (+0.5 mi tolerance; extra miles already run never block), runs on rest days, **hard after hard** (across weeks and against real hard runs before the plan; only flagged ultra b2b pairs are exempt), per-weekday time limits (`day_time_budgets`, which only judge *added* minutes) | No long-run spacing rule. No taper or race-week rule. |
| Silent safety net | `enforce_no_back_to_back_hard` | Downgrades a stacked workout to easy | It fixes things quietly. A request must **fail validation**, not get silently rewritten, so the diff the athlete approves is exactly what is saved. |
| Change guard | `core/change_guard.review_change(kind='schedule')`, `summarize_change` | For schedule-only changes: no added quality sessions, long-run distance unchanged, week growth ≤10% and ≤ the added-miles allowance, run-day count, locked days untouched. Also writes plain "Week 1: 42 → 40 mi, 6 run days, same workouts" lines | Built for revised blocks (`schedule_revision`), but it is almost exactly the policy this feature needs. |
| Draft and approve | `POST /plans/{uid}/preview`, `/drafts/{id}/approve`, `/discard` | A whole-block draft the athlete approves | Too heavy for "change Thu–Sun". A proposal should be a list of edits to the active plan, not a new plan. |
| OpenAI transport | `services/openai_coach.py` | Responses API, `responses.parse` with a Pydantic `text_format` (Structured Outputs), `reasoning={'effort':'low'}`, `store=False`, no SDK retries, input-size ceiling, usage recorded | A new schema and instructions are needed. The transport can be reused as is. |
| Quota | `services/coaching._check_ai_budget` | Per-athlete 30/day resetting at the athlete's midnight, an app-wide 100/UTC day, and consent checks | It counts `CoachingReview.attempts` only, so a new table needs its own count (see §3). |

**Bottom line:** the validators, trial sessions, write lock, audit field (`_mark_changed` →
`original_prescription` and `adjustment_note`), consent check and Structured Outputs transport all
exist. What's missing is (a) **multi-day atomic edits that include swaps and moves to earlier days**,
(b) **long-run spacing and taper rules**, and (c) the request → proposal → approve record.

---

## 2. The flow

```
athlete text ─▶ safety screen ─▶ AI: constraints + ops ─▶ apply in read_only_trial ─▶ rules
   (≤500)        (deterministic)   (Structured Outputs)                                │
                                                                    pass ◀─────────────┤
                                     fail: reasons ─▶ AI retry (once) ─▶ rules ─────────┤
                                     fail again ─▶ rules-only solver(constraints) ─▶ rules
                                     still fail ─▶ "no safe rearrangement" + manual moves
pass ─▶ before/after diff ─▶ athlete Approve / Discard ─▶ re-validate under write lock ─▶ save + audit ─▶ Undo
```

### 2.1 Worked example: Halloween 2026

Today is **Mon Oct 26**. Halloween is **Sat Oct 31**. Jake's default week: Mon easy, Tue intervals,
Wed easy, Thu threshold, Fri rest (preferred rest day), Sat long run, Sun easy.

The AI should restate what it understood (shown to the athlete so they can catch a misunderstanding)
and give one proposal:

- Constraints: Sat Oct 31 morning and Sun Nov 1 morning should be **no hard running**, and it's fine
  to make them short or rest.
- Ops: `swap(Thu Oct 29 ↔ Sat Oct 31)` puts the long run on Thursday. That would leave Thursday's
  threshold on Saturday, so `easy(Sat Oct 31)` turns it into an easy day and `shorten(Sat Oct 31,
  3 mi)` makes it short. Sunday stays easy.

Result: Tue intervals, Wed easy, **Thu long run**, Fri rest, Sat short easy, Sun easy. The rules
pass: Wed→Thu is easy→hard and Thu→Fri is hard→rest, so there are no back-to-back hard days. Week
mileage goes down, never up. Quality sessions go from 2 to 1 (allowed, because removing work is fail
safe). The long run keeps its distance. Long-run spacing is 5 days since last Saturday's.

The alternative that keeps both workouts (Mon threshold, Wed intervals, long run Fri morning
before going out) runs on Jake's preferred rest day. The rules correctly reject that today. Whether
a one-week rest-day override should be allowed is an open question (§6).

### 2.2 The AI's job and its output schema

The AI gets a **slim context** (§3.1) and returns a Pydantic model through `responses.parse`.
Field limits are hard backstops, as in `CoachAdvice`:

```python
class Constraint(BaseModel):          # what the athlete said, made checkable
    date: str                         # ISO, must be inside the editable window
    kind: Literal['no_run', 'no_hard', 'max_minutes', 'prefer_rest']
    minutes: int | None

class Op(BaseModel):                  # the ONLY edits the model may propose
    op: Literal['move', 'swap', 'shorten', 'easy', 'skip']
    date: str
    target_date: str | None           # move / swap
    miles: float | None               # shorten: must be lower than the current miles

class PlanChangeProposal(BaseModel):
    kind: Literal['proposal', 'clarify', 'no_change', 'out_of_scope']
    understood: str = Field(max_length=300)        # restated in plain words, shown to the athlete
    constraints: list[Constraint] = Field(max_length=8)
    ops: list[Op] = Field(max_length=6)
    question: str | None = Field(max_length=200)   # kind == 'clarify'
    choices: list[str] = Field(max_length=3)       # quick replies for the question
    safety: Literal['none', 'illness', 'injury', 'red_flag']
    explanation: str = Field(max_length=500)       # coach-tone "why", no numbers it didn't get
```

Op semantics are deterministic and live in Stride. The model never writes a prescription.

| Op | Effect | Allowed when |
|---|---|---|
| `move(a → b)` | Session `a` goes to day `b`. `a` becomes rest. `b`'s easy run is dropped. | `a`, `b` unrun, ≥ today, in the window; `b` is easy or rest. Earlier **or** later, unlike `change_session` today. |
| `swap(a ↔ b)` | Exchanges the two days' contents (prescription, warmup and cooldown move with them; paces never change) | Both unrun, ≥ today, in the window, neither is a race |
| `shorten(d, mi)` | Lowers the distance (easy: never below `MIN_EASY_FLOOR`; long run: never below `MIN_LONG_SHARE` of the week; workouts: easy-ify instead) | `mi` < current |
| `easy(d)` | Hard day becomes easy, `min(miles, 6)` (same as `build_options`) | Day is a workout or long run |
| `skip(d)` | Becomes rest | Any unrun, non-race day |

There is deliberately **no op that adds miles or quality**, changes paces, or touches past, run or
race days. Requests like "add a workout Thursday" come back as `out_of_scope`, pointing to "Want
more speed" and the next-block preview.

### 2.3 Validation (all deterministic, all in one trial)

1. **Shape checks:** dates inside the window (today … today+13 and inside the active plan), ops
   reference real unrun rows, no day touched twice except `swap` followed by a shorten or easy on
   the same day, ≤6 ops.
2. **Apply** all ops to a `read_only_trial` copy. This is the same isolation `build_options` uses, so
   the request never takes a writer lock.
3. **`_validate_schedule(trial_plan, trial, changed=all touched rows)`:** weekly budget, rest days,
   hard after hard (including real hard runs before the plan), per-weekday time limits.
   **Do not** run `enforce_no_back_to_back_hard` here. A conflict is a rejection with a reason, not a
   silent rewrite.
4. **`review_change(kind='schedule')`**, loosened in one place: the long run may shrink, never grow.
   It covers no added quality sessions, no run-day growth and locked days untouched.
5. **New rules this feature needs:**
   - *Volume never rises:* each week's planned total after the change ≤ before. This is stricter than
     the guard's 10%, because a life-event change shouldn't add load. Moving a session across a week
     boundary is refused in the MVP, which also guarantees no cramming missed volume.
   - *Long-run spacing:* ≥5 days between long runs, counting the last completed long run. This is
     missing from `plan_validator` today and worth adding there for everyone.
   - *Taper and race week:* during `taper` or `race_week`, only reducing ops are allowed (`skip`,
     `easy`, `shorten`). The sharpener stays ≥3 days before race day, and the race day is locked.
   - *Constraint satisfaction:* the result meets **every constraint the AI extracted** (e.g. no hard
     day on Sat or Sun). This catches a proposal that passes the rules but ignores the request.
6. Rejections return as short `{code, date, message}` reasons, the same shape `validate_plan` uses.

### 2.4 Retry and fallback

- **One retry:** the model sees its previous ops plus the rejection reasons ("2026-10-30: Long Run
  comes straight after another hard day") and the same context. The retry counts as an attempt.
- **Rules-only solver** (also the no-AI path): given the constraints, place the unrun sessions of the
  affected week(s) by brute force. A week has ≤3 hard sessions over ≤7 days, so there are at most a
  few hundred placements. It keeps every rule and scores by (1) the long run kept at full distance,
  (2) fewest changed days, (3) workouts kept on their original weekday order (Jake's preference:
  intervals early in the week, threshold later), and (4) fewest quality sessions dropped. If nothing
  fits, it drops the lowest-priority quality session and tries again. That is fail safe: it never stacks.
- **Still nothing:** say so plainly, list the rejection reasons, and offer the existing manual
  controls (move or skip a session).

### 2.5 Clarifying questions

`kind='clarify'` returns one question plus up to 3 quick replies (e.g. *"Which morning do you want
the long run: Thursday or Friday?"*). The answer is appended to the request and resent, at most **2
rounds**. If the model asks a third time, the solver runs on the constraints it already has. Ask
only when the answer changes the plan. When a conservative default exists, use it and say so in
`understood`.

### 2.6 Safety

- **Deterministic pre-screen, before any model call:** a word list (pain, injured, sprain, stress
  fracture, sick, fever, flu, covid, chest, dizzy, faint, …).
  - *Illness or injury:* the proposal may only reduce (`skip`, `easy`, `shorten`). The UI suggests rest
    and points to the existing "Feeling run down" path. Never "push through".
  - *Red flags* (chest pain, fainting, shortness of breath at rest): no plan proposal. Show a short
    "stop and get checked by a medical professional" note and offer to skip the next days.
- The model's `safety` field can only **tighten** the screen's result (e.g. "my shin's been barking"),
  never loosen it.
- **No diagnosis:** the existing instructions already forbid it. Keep that sentence.
- **Prompt injection:** the request is data. Ops are an enum, validators are authoritative, and no
  tools or database access are available (the same posture as `openai_coach.py`).

### 2.7 Approve, persist, undo

New table `plan_change_requests`:

| Column | Notes |
|---|---|
| `id, user_id, plan_id, created_at` | |
| `request_text` | normalized like `normalize_concern`, ≤500 chars |
| `thread` | JSON list of clarifying Q/A turns |
| `status` | `clarifying`, `proposed`, `no_safe_change`, `applied`, `declined`, `undone`, `stale` |
| `source` | `ai`, `ai_retry`, `solver` (who produced the applied ops) |
| `proposal` | the structured output and the final ops |
| `rejections` | JSON reasons from failed attempts, which feed eval cases |
| `before_rows, after_rows` | snapshots (`_snapshot` fields) of every touched row |
| `plan_fingerprint` | refuse apply if the plan, runs or prefs changed since proposing |
| `model, attempts, input_tokens, output_tokens` | same accounting as `coaching_reviews` |
| `applied_at, undone_at` | |

- **Apply** (`POST /api/plans/{uid}/requests/{id}/apply`): `_begin_schedule_write`, recheck the
  fingerprint, **re-run the full validation**, write the rows, and `_mark_changed(row, "Athlete
  request #N: <understood>")` on each so the existing "adjusted" badges and `original_prescription`
  keep working. Commit once. Any failure rolls back everything.
- **Undo** (`POST …/undo`): restore `before_rows` only if every touched row still equals
  `after_rows`, none has a run yet, and none is in the past. Otherwise explain what blocks it. Undo
  re-validates too.
- **Expiry:** a proposal goes `stale` on any plan change or at the athlete's midnight (the context
  holds `today`). Re-proposing with an identical request and fingerprint reuses the stored result for free.

---

## 3. Cost

### 3.1 Context: slim, not the review payload

A run review sends ~30k input tokens (measured over seven real reviews; see
`docs/openai-coaching.md`): laps, history dossier, research excerpts and prior reviews. None of
that is needed to rearrange a week. Proposed context:

| Part | Estimate | Cacheable |
|---|---|---|
| Instructions (role, op semantics, rules summary, safety, "request is data") | ~1,200 tok | yes, static |
| JSON schema of `PlanChangeProposal` (counted as input) | ~500 tok | yes, static |
| Editable window: 14 days × `{date, dow, type, title, miles, minutes, locked, run_miles}` | ~650 tok | no |
| Athlete rules: rest days, days/week, per-weekday minute limits, week budgets, phase per week, race date | ~150 tok | no |
| Last 7 days actually run (date, type, miles, watch feel) | ~200 tok | no |
| Request text, plus clarifying thread | ~100–250 tok | no |
| **Total** | **≈3,000 input** | ~1,700 static |

Output: structured JSON ~250–400 tokens, plus low-effort reasoning. Budget **~1,000 output tokens**
and cap `max_output_tokens` at 2,000. Measure real usage in Phase 1. These are estimates.

### 3.2 Prices (standard tier, per 1M tokens, checked Oct 26 2026)

From OpenAI's [pricing page](https://developers.openai.com/api/docs/pricing) and model pages
([gpt-5.4-mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini),
[gpt-6-luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[gpt-6.1-terra](https://developers.openai.com/api/docs/models/gpt-6.1-terra)). All of these support Structured Outputs.

| Model | Input | Cached input | Output | One request (3k in / 1k out) | + retry (worst case) |
|---|---|---|---|---|---|
| **gpt-5.4-mini** (Stride today) | $0.75 | $0.075 | $4.50 | **$0.0068** | $0.014 |
| gpt-6-luna | $0.10 | $0.01 | $0.50 | $0.0008 | $0.0017 |
| gpt-5.4-nano | $0.20 | $0.02 | $1.25 | $0.0019 | $0.004 |
| gpt-6.1-terra | $1.00 | $0.05 | $5.00 | $0.008 | $0.016 |
| gpt-6-sol | $2.00 | $0.20 | $10.00 | $0.016 | $0.032 |
| gpt-5.5 | $5.00 | $0.50 | $30.00 | $0.045 | $0.09 |
| *gpt-5.4-mini with the full ~30k review context* | | | | *$0.027* | *$0.054* |

The slim context is about **4× cheaper** than reusing the review context, and it's faster. Flex and
Batch are half price but slow and best-effort, so they're the wrong fit for an interactive "propose
my week".

**Caching:** put the ~1,700 static tokens first, like `model_payload` does with research. That's above
the 1,024-token caching minimum, and cache reads cost 0.1× input
([prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)). On
gpt-5.4-mini this saves ~$0.001 per request (to ≈$0.0056). That's worth doing because it's free,
but output dominates the cost. The bigger saving is the **result cache**: an identical request with
an identical plan fingerprint returns the stored proposal without a call.

### 3.3 Recommendation

- **Model:** ship on **gpt-5.4-mini** (already configured, consented and tested in Stride). In
  parallel, run the Phase 1 eval set (§5) against **gpt-6-luna**. It's ~8× cheaper, newer, and built
  for focused high-volume tasks. Switch if it scores as well on understanding the request (the
  validators protect safety on either model). Make it a separate setting, e.g.
  `OPENAI_PLAN_CHANGE_MODEL`, so reviews and requests can differ.
- **Cap:** **10 attempts per athlete per day** (clarify rounds and the retry count), resetting at the
  athlete's midnight, counted separately from the 30 reviews so a busy sync day never blocks "I'm
  sick, fix my week". Both share the app-wide daily cap. Worst case: 10 × $0.014 ≈ **$0.14 per
  athlete per day**. Realistic use is a few requests a month, which is **cents per month** and fits
  the ~$15/month budget easily.
- **Rules-only comparison:** the solver (§2.4) plus a structured picker ("This week I can't run hard
  on: Sat Sun", "No time on: …", "Feeling: sick/sore") costs $0 and handles most real cases (busy
  days, travel, nights out). What it can't do is read *"going out Fri and Sat, don't want the long
  run hungover"* and work out that this means *no hard Sat/Sun mornings*, and it can't explain its
  choice in coach language. So build the solver as the fallback and the no-AI path, and let the AI
  sit on top as the language layer. The AI is a convenience. The rules are the safety.

---

## 4. UI

**Where:** the Plan options dialog, which is already the single "change the block" entry point.
Its top section becomes **"What's coming up?"**, a text box with a placeholder like *"Halloween
weekend: out Fri and Sat night, don't want my long run hungover."* The current reason chips stay as
quick starters, plus *Busy weekend*, *Traveling* and *Feeling sick*. This **replaces** the "Ask coach
to adjust" concern review. One box doing both jobs would confuse athletes, and the new flow covers
the concern use case with real edits. (The coach review panel itself, which PR #51 is changing, is
left alone.)

It works like a chat but without open-ended conversation. Each turn is request → (question) →
proposal, which keeps cost and scope bounded.

| State | What the athlete sees |
|---|---|
| Idle | Text box (500 chars, counter), chips, "Suggest changes" button, "N of 10 left today" |
| Working | Spinner, "Reading your week…" (~3–8 s). Cancel. |
| Clarifying | The coach's one question, up to 3 reply buttons, and an optional free answer |
| Proposal | **"Here's what I understood"** (constraints in plain words) → a **before/after week**: each day as a row, changed rows highlighted, old session struck through → new. `summarize_change` lines ("Week 1: 44 → 41 mi, same run days, workouts: Intervals, Threshold → Intervals"). A "Checks passed" disclosure (no back-to-back hard days, mileage not increased, long run spacing). Coach's why. **Approve** / **Discard** / "Try different wording" |
| No safe change | "I couldn't fit that without breaking a rule": the reasons, plus buttons for Move / Skip a session |
| Safety | Illness/injury: a reduce-only proposal with a rest note. Red flag: a medical note, no plan proposal, offer to skip days |
| Out of scope | "This tool rearranges or lightens your week. For more training, use Want more speed or preview the next block." |
| Applied | Toast "Week updated" with **Undo**. Changed days show the existing adjusted badge with the request note |
| Stale | "Your plan changed since this was suggested." Re-run (free if the text is unchanged and it isn't a new day) |
| Limit / AI off / no consent | Same messages as reviews today, plus the **structured picker** (rules-only solver) so the feature still works |

**Mobile:** the dialog becomes a full-height bottom sheet. The diff is a vertical day list (one line
each: `Thu · Threshold 7 mi → Long run 14 mi`). Approve and Discard sit in a sticky footer above the
safe area. 16px gutters, tap targets ≥40px (matching the `h-10` buttons), and the text box uses
`enterKeyHint="send"`. No horizontal scrolling for the week: rows stack.

---

## 5. Phased plan

**Phase 0: deterministic foundations (no AI, useful immediately)**
- `core/request_ops.py`: `move` (earlier or later), `swap`, `shorten`, `easy`, `skip` on a trial plan,
  applied atomically.
- Add **long-run spacing** and **taper/race-week reduce-only** checks to `plan_validator`, with tests.
- Volume-never-rises and constraint-satisfaction checks.
- Rules-only solver plus tests built on Jake-shaped weeks (Halloween, travel Tue–Thu, sick Mon–Wed,
  race week).

**Phase 1: MVP**
- `plan_change_requests` table plus migration. Endpoints: create, answer, apply, undo, list.
- `services/plan_change_ai.py`: slim context, `PlanChangeProposal` schema, instructions, one retry,
  solver fallback. Reuse the `openai_coach` transport and consent and quota patterns (a separate
  10/day count).
- Plan options UI: text box, proposal diff, approve, undo, and every state in §4 including mobile.
- Eval set (`docs/evaluation/`): ~20 written requests with expected constraints and "must not" rules,
  run against gpt-5.4-mini and gpt-6-luna. Record tokens to confirm §3.1.
- Scope: current week plus the next 7 days, reduce or rearrange only, no cross-week moves.

**Phase 2**
- Clarifying rounds (if Phase 1 shows they're needed), the structured picker for no-AI use, and
  result caching across identical requests.
- Show the request history on the Plan page ("Changed for: Halloween weekend").

**Phase 3**
- One-week rest-day overrides (if Jake wants them), cross-week moves with a budget check, and
  multi-week events (vacation, a work trip) that feed the next block's generation as constraints.

---

## 6. Open questions for Jake

1. **Never add training?** The MVP only rearranges or lightens. Should "I've got extra time Thursday,
   add a run" ever be allowed, or should it always go to the next block?
2. **One-week rest-day override:** for Halloween, a long run Friday morning keeps both workouts but
   uses your Friday rest day. Allow it for one week with an explicit "yes, run on my rest day" tap?
3. **Drop versus squeeze:** when there's no safe slot, the solver drops the lowest-priority quality
   session (fail safe). Which goes first, intervals or threshold, and does that change by phase?
4. **Window:** this week plus 7 days, or the whole 2-week block?
5. **Replace "Ask coach to adjust"** with this, or keep both?
6. **Cap:** a separate 10/day, or share the existing 30?
7. **Model:** stay on gpt-5.4-mini, or switch to gpt-6-luna if the evals match?
8. **Clarify or assume:** ask a question, or always pick the most conservative reading and say so?
9. **Undo window:** until the first changed day starts, or longer?
