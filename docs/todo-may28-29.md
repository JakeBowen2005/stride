# Stride TODO — Evening May 28 / Day May 29

## 1. Multi-Activity Day Aggregation in Plan View

**Problem**: Tuesday May 26 shows 3.9mi in the plan, but actual was 5.9mi (warmup + workout + cooldown as separate Strava activities).

**Root Cause**: `_match_activity` in `plans.py` picks a single activity per planned workout day by closest distance. It ignores other activities on the same date.

**Fix**:
- In `get_current_plan()` (`backend/app/api/plans.py`), change `_match_activity` to return ALL activities on that date (not just the closest one)
- The `actual` field on each plan day should aggregate: sum distance, sum duration, show combined pace
- New `_build_actual` logic:
  ```
  activities = query all activities for user on this date
  if none: actual = null
  if one: same as current
  if multiple:
    total_distance = sum(a.distance_meters)
    total_duration = sum(a.duration_seconds)
    avg_pace = total_duration / (total_distance / 1609.34) → format as mm:ss
    avg_hr = weighted avg by duration
    actual = { distance_miles: total, avg_pace, duration_seconds: total, ... }
    actual["activities"] = [list of individual activities for detail view]
  ```
- `_build_comparison` already works off the actual dict, so it'll auto-correct once actual distance is right
- **Frontend**: no changes needed for the plan page (it already renders `actual.distance_miles`). Later we can add an expandable view to see individual activities.

**Files**: `backend/app/api/plans.py` — `_match_activity`, `get_current_plan`, `_build_actual`

---

## 2. Post-Run Feedback System

**Problem**: No way to log how a run felt, whether you hit pace targets, or if you swapped the day's workout.

### 2a. Backend: Feedback API

**New endpoint**: `POST /api/feedback/{user_id}/day/{date}`

Request body:
```json
{
  "feel_rating": 7,           // 1-10 scale (required)
  "feel_notes": "Legs tired from yesterday, kept it easy",  // free text (optional)
  "pace_assessment": "on_target",  // "above", "on_target", "below", "skipped" (optional)
  "swapped": false,            // did they swap today's workout? (optional)
  "swap_reason": null,         // why they swapped (optional)
  "actual_workout": null       // what they did instead, e.g. "easy run" (optional)
}
```

Logic:
- Find the PlannedWorkout for this date
- Find the matched Activity (or aggregated activities from fix #1)
- Save feel_rating and feel_notes to the Activity record (fields already exist)
- Save pace_assessment, swapped, swap_reason to PlannedWorkout (new fields needed)
- Return the updated plan day with feedback

**New PlannedWorkout fields**:
- `feel_rating: int | None` (mirror from activity for quick access)
- `pace_assessment: str | None` — "above", "on_target", "below", "skipped"
- `swapped: bool` — default False
- `swap_reason: str | None`
- `actual_workout_type: str | None` — what they actually did if swapped

**Migration**: Add columns to `planned_workouts` table.

**Files**:
- `backend/app/models/plan.py` — add fields to PlannedWorkout
- `backend/app/api/plans.py` — new POST endpoint
- DB migration (alembic or manual ALTER TABLE)

### 2b. Frontend: Feedback UI

**Where**: On the Plan page, past days that have an actual activity show a feedback prompt.

**Design**:
- Below each completed day in the plan, show a small "How'd it go?" prompt if no feedback yet
- Tap to expand: feel rating (1-10 emoji/number row), optional notes textarea, pace assessment (3 buttons: above/on/below target)
- If the user swapped the workout (e.g., did easy instead of threshold): toggle "I swapped this" → shows dropdown for what they did + reason
- After submitting, show a brief coach response (see #3)

**Files**:
- `frontend/app/plan/page.tsx` or a new `FeedbackForm` component
- `frontend/components/feedback-form.tsx` (new)

---

## 3. Science-Backed Coach Feedback (RAG over training docs)

**Problem**: Don't want generic LLM advice. Want responses grounded in the actual training science docs and athlete profile.

### Architecture: Structured Context Injection (not vector RAG)

For a single-user app targeting Jake specifically, full vector search is overkill. Instead:

**Approach**: Build a context assembler that selects the RIGHT science doc sections based on the situation, then passes them as system prompt context to the LLM.

**Context Assembly Logic** (`backend/app/services/coach.py`):

```python
def build_coach_context(user, plan_day, feedback, recent_history):
    """Assemble relevant training science for the LLM prompt."""

    context_sections = []

    # 1. Always include: athlete profile (current fitness, PRs, preferences)
    context_sections.append(load_doc("athlete-profile-jake.md"))

    # 2. Always include: core training principles
    context_sections.append(load_doc("training-principles.md"))

    # 3. Goal-specific science (select based on active goal)
    goal = get_active_goal(user)
    if goal.race_distance == "5k":
        context_sections.append(load_doc("5k-training-science.md"))
    elif goal.race_distance == "10k":
        context_sections.append(load_doc("10k-training-science.md"))
    elif goal.race_distance == "half":
        context_sections.append(load_doc("half-marathon-training-science.md"))
    elif goal.race_distance == "marathon":
        context_sections.append(load_doc("marathon-training-science.md"))

    # 4. Recent training context (last 7-14 days of runs)
    #    - weekly mileage trend
    #    - workout results (paces hit vs prescribed)
    #    - feel ratings trend
    #    - acute:chronic ratio

    # 5. Today's specific context
    #    - what was prescribed
    #    - what was actually done
    #    - how it felt (feedback)
    #    - comparison data

    return "\n---\n".join(context_sections)
```

**LLM Prompt Structure**:
```
SYSTEM: You are a running coach for {athlete_name}. You have deep knowledge
of training science and this specific athlete's history.

{assembled_context — training principles + distance-specific science + athlete profile}

RECENT TRAINING (last 14 days):
{formatted recent runs with paces, distances, feel ratings}

TODAY'S RUN:
Prescribed: {planned workout details}
Actual: {what they did — distance, pace, HR}
Feel: {rating}/10 — "{notes}"
Pace vs target: {assessment}

Respond as a knowledgeable coach. Reference specific training principles when relevant.
Keep it concise (2-4 sentences). Be honest — if they need to slow down, say so.
If they crushed it, acknowledge it. If they're fatigued, suggest adjustments.
```

**Key Design Decisions**:
- **No vector DB needed** — we have 5 science docs + 1 athlete profile. Just load the right ones.
- **Context is deterministic** — same situation always gets same docs. No retrieval randomness.
- **LLM budget**: Use Claude Haiku for quick feedback (~$0.001/response). Reserve Sonnet for weekly summaries.
- **Fallback**: If LLM budget exceeded, fall back to template-based responses using the same logic (if feel < 4 and pace below target → "Sounds like a tough day. Consider an extra easy day.")

### When Coach Feedback Triggers

1. **After submitting feel rating** on a completed run → immediate 2-4 sentence response
2. **Plan adjustment suggestion** — if 3+ days of low feel ratings or pace consistently below target, suggest modifications to remaining plan days
3. **Weekly summary** (future) — end of week recap with science-backed insights

### Plan Adjustment from Feedback

When user says "legs are tired, swapping workout for easy":
- Mark today's PlannedWorkout as `swapped = True`
- User picks what they actually did
- Coach acknowledges: "Good call. Fresh legs tomorrow will make Thursday's workout more productive. The science backs this — quality over quantity for VO2max sessions."
- **Optional**: offer to swap Thursday's workout to account for the change (e.g., move Tuesday's threshold to Thursday, make Friday the lighter day)
- This is NOT auto-adjusting the plan — it's offering a suggestion the user confirms

**Files**:
- `backend/app/services/coach.py` (new) — context assembly + LLM call
- `backend/app/api/feedback.py` (new) — feedback endpoints that trigger coach
- `backend/app/config.py` — add `anthropic_api_key` or `ollama_url`

---

## 4. Generalization Plan (Future — After Jake-First)

Once the system works for Jake:
1. **Athlete profile becomes a DB model** — store per-user training preferences, known patterns, current fitness assessment
2. **Science docs stay static** — they're universal training science, not per-user
3. **Context assembly becomes per-user** — reads athlete profile from DB instead of a static markdown file
4. **LLM learns athlete over time** — each feedback entry builds a richer picture. Store coach observations as structured data (e.g., "responds well to threshold work", "tends to go too fast on easy days")

---

## Execution Order

### Evening May 28
1. **Fix #1**: Multi-activity day aggregation (backend only, ~30 min)
2. **Fix #2a**: Feedback API + model changes (backend, ~45 min)
3. DB migration for new PlannedWorkout fields

### May 29
4. **Fix #2b**: Feedback UI on plan page (frontend, ~1 hr)
5. **Fix #3**: Coach service with context assembly (backend, ~1-2 hrs)
6. Wire coach response into feedback UI
7. Test end-to-end: complete a run → submit feedback → get science-backed response
8. Test plan swap flow: mark a day as swapped → get adjustment suggestion

---

## Open Questions
- For coach LLM: Claude API (Haiku for quick, Sonnet for summaries) or local Ollama? Budget says start with Claude Haiku, switch to Ollama if costs creep up.
- Should the coach be able to actually modify the remaining plan days, or just suggest? Start with suggest-only — user confirms any changes.
- Weekly summary: generate automatically on Sunday night, or on-demand? Start with on-demand.
