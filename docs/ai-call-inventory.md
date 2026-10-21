# AI call inventory (coach v6, Oct 21 2026)

Stride makes one kind of AI call: an OpenAI structured-output review. Training decisions are made in
code first. The model explains them and may only pick from server-built, pre-validated candidates.
The old Anthropic free-text path was removed in v5. Without an OpenAI key, feedback uses
`_template_feedback` in `backend/app/services/coach.py`.

To see exactly what is sent for any run or plan, without a provider call and against a copy of the DB:

```bash
cd backend && venv/bin/python scripts/dump_coach_context.py --db /path/to/copy.db            # weekly (active plan)
cd backend && venv/bin/python scripts/dump_coach_context.py --db /path/to/copy.db --activity 574 --full
```

## Call path

| | |
|---|---|
| Transport | `services/openai_coach.py` `request_advice` → `client.responses.parse` |
| Model | `settings.openai_coach_model` (`gpt-5.4-mini`), reasoning effort low, `max_output_tokens=3000`, `store=False`, 35s timeout, no retries |
| System prompt | `openai_coach.INSTRUCTIONS` (~5k chars) |
| User input | `model_payload(context, research)`: research first (stable, so it gets prompt-cache hits), then context. Refused over 120k chars |
| Output | `CoachAdvice`: summary ≤480, plan_fit, ≤3 observations, ≤2 uncertainties, ≤5 research_ids, ≤2 suggestions `{candidate_id, reason}` |
| Validation | candidate ids must exist and be one per date; research ids must be supplied ones. Any failure → stored `fallback`, nothing applied |
| Cache | `coaching_reviews`, unique on a sha256 of context + research + instructions + key version. The context includes `today`, so a cached review lasts at most a day |
| Budget | `openai_coach_daily_limit` (12) attempts per UTC day |

## Triggers

| Trigger | Scope | Code |
|---|---|---|
| Garmin sync of a run dated in the last 2 days (background worker) | `run` | `coaching_jobs.process_one` |
| Feedback submitted for a planned day | `run` | `api/plans.py` feedback → `coach.get_coach_feedback` |
| Run detail sheet / Today card "Refresh" | `run` | `POST /api/coaching/{uid}/review {activity_id}` |
| Plan page "Coach perspective" (and "what isn't working" requests) | `week` | `POST /api/coaching/{uid}/review {plan_id, athlete_concern?}` |

Page loads never start a paid call. `GET /latest` only rebuilds the context to mark a review stale.

## What goes into the context (`services/coaching.build_context`)

Typical size from Jake's data: ~62k chars ≈ 15.5k input tokens per review.

| Section | What it holds | Typical chars |
|---|---|---|
| research (5-6 docs) | Excerpts: quality policy, personal dossier, decision engine, training principles, support variety, goal-distance science | ~28,000 |
| `plan` | Plan meta, load, phases, assessment, every session (snapshot, status, feel, notes, evaluation), quality authority, weekly structure | ~18,000 |
| `candidates` | The validated change menu, trimmed to id/date/before/replacement/other_changes | ~3,500 |
| `week_view` (new) | This week and next, day by day: planned type/title/miles, done miles, feel, key sessions, remaining planned miles | ~2,900 |
| `recent_runs` | One line per run from the last **28** days (was 56 days, up to 60 runs) | ~2,500 |
| `recovery` | 7 days of Garmin wellness (sleep, HRV and baseline, RHR, readiness, ACWR) | ~1,200 |
| `workload` | `completed_week_load`: 12 completed weeks, ratio, label | ~1,100 |
| `training_summary` | Last 6 full weeks, this week done vs planned, last 6 quality sessions with rep paces | ~1,000 |
| `policy_interpretation` | Fixed rules about weekly quality counting, HR, risk labels, matching | ~800 |
| `run` (run scope only) | Distance, time, pace, HR, elevation, training effect, ≤60 laps, detected session, athlete feedback | ~700-4,000 |
| `run_vs_plan`, `matched_prescription`, `execution`, `deterministic_evaluation` | How the run compares with what was prescribed, and Stride's decision | 0-2,000 |
| `progression`, `quality_evidence`, `current_paces`, `goal`, `athlete` | Ladder levels, verified quality history, calibrated paces, goal and profile | ~1,500 |
| `prior_reviews` (new, v6) | The coach's own completed notes from the last 14 days, newest first: latest note per run or weekly review, max 6, excluding the subject under review. Read from `coaching_reviews`; added after the fingerprint so it never makes another review stale | ~3,000 |
| `review_scope` (new) | `run` or `week`; tells the prompt which shape the summary takes | — |
| `athlete_request` | The athlete's own concern, treated as data | ≤500 |

## Prompt shape by scope

- **week** (Coach perspective): (1) how this week is going, done vs planned; (2) the purpose of next
  week's key sessions; (3) the one thing to protect or watch.
- **run**: what was run with real numbers, what it means, what to do next, ending with what it means
  for the rest of the week.

## Known follow-ups

- `plan` is the biggest section. `week_view` now covers the near term, so older completed sessions
  could be summarised instead of listed.

## Coach memory (v6)

Ready reviews were already stored permanently in `coaching_reviews`; v6 reads them back as
`prior_reviews` (`services/coaching.prior_reviews`, `MEMORY_DAYS = 14`, `MEMORY_LIMIT = 6`).
The prompt tells the model to stay consistent with its earlier notes and follow up on what it
flagged, but current data always wins, and notes are never evidence of training. Memory is excluded
from the context fingerprint, so a new note never stales or blocks another review's suggestions.
