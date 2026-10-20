# OpenAI coaching in Stride

## Where the model helps

1. **After a run:** compare actual work segments, execution confidence, the athlete's feel/notes and recent recovery with the upcoming approved sessions. Explain a hard but successful effort differently from incomplete or ambiguous work.
2. **Before approving a block:** review the proposed volume, goal/phase, quality stage and missing evidence against the personal coaching sources. Preview review is advisory; approval remains the existing atomic activation flow.
3. **When a session could fit better:** select a server-authored alternative, show its full prescription and reason, then let the athlete apply it. The initial menu offers smaller same-category work, shorter threshold repetitions where the same work and full recoveries fit, easy running, or rest. It does not invent a new training program.

This intentionally puts language-model judgment around the deterministic coaching engine. More ambitious workout proposals can later be added to the authored menu with independent dose/phase tests. A model cannot infer verified fitness from a persuasive story, a prior PR or one whole-run average.

## Setup and model

Put `OPENAI_API_KEY` in **backend/.env**, never frontend environment variables or Git. The local file is ignored. Restart the backend after changing it.

```dotenv
OPENAI_API_KEY=your-key-here
OPENAI_COACH_MODEL=gpt-5.4-mini
OPENAI_COACH_DAILY_LIMIT=12
OPENAI_COACH_TIMEOUT_SECONDS=35
OPENAI_AUTO_REVIEWS=true
```

The default is GPT-5.4 mini with low reasoning effort and the Responses API's Pydantic Structured Outputs. The official model documentation lists $0.75/M input tokens and $4.50/M output tokens when checked October 19, 2026. A measured synthetic review used 7,277 input / 561 output tokens, roughly $0.008 at those rates; actual context/output varies. Twelve such calls/day would be about $3/month, but this is an illustration, **not a dollar budget guarantee**. Set a project budget/alerts in OpenAI as well.

Each call has a 120,000-character serialized input ceiling, 3,000 output-token ceiling, bounded network timeout, and no SDK retries. The local 12-attempt/day UTC limit includes failed requests and retried attempts; requests with identical evidence are cached and don't spend again. No paid calls on page load. Newly synced recent Garmin runs now enqueue an automatic background review (see [automatic review and session menus](adaptive-sessions-and-demos.md)). Saving planned-day run feedback requests one review after the deterministic effects have committed. There is no automatic historical backfill.

Official references: [model and pricing](https://developers.openai.com/api/docs/models/gpt-5.4-mini), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Data and research

The request contains selected numeric run/lap metrics, recent training, subjective feedback, age/experience/scheduling preferences, goal, current plan, deterministic execution/evaluation, recovery, progression state and permitted alternatives. Activity names, GPS routes, provider credentials and account identifiers are excluded; internal database IDs identify evidence. Free-text notes are included as athlete input, so avoid putting unrelated private information in them. No hand-written athlete profile is injected; the database is the current source of truth.

A bounded research pack includes the quality-stage policy, training principles, support-workout research, the two original personal coaching documents and relevant race-distance material. Long originals are excerpts, not full-document retrieval. The originals remain untouched. Personal ChatGPT retrospectives are explicitly labeled contextual claims rather than confirmed logs or independently validated science. Only supplied source IDs can be cited. OpenAI receives `store=False`; that does not imply zero provider retention under its separate data policies.

Local storage saves the structured advice, source paths, context fingerprint, permitted candidate snapshots, model, token usage and accepted option. It does not save the entire prompt or API key. Provider failures log exception **types only**, without payloads or exception messages. The previous Anthropic pathway remains available only when OpenAI is not configured; OpenAI failures use deterministic/template feedback rather than silently sending the same personal data to another provider.

## Enforced boundary

- `services/coaching_options.py` authors alternatives before the call. Legacy alternatives preserve quality slots, category, paces and bookends while reducing dose. Adaptive session-menu alternatives may reshape a session or use an earned quality slot; they are rebuilt and validated against phase, recovery, spacing and the weekly budget before acceptance. Neither pathway permits invented faster paces, rest-day changes, race changes or level advancement. Modified workouts carry `progression_eligible=False`.
- Every candidate is trialed in a rolled-back savepoint through `api/plans._validate_schedule`, the shared budget/rest/hard-spacing validator. Preview plans have no mutation candidates.
- `services/openai_coach.py` has no tools, database mutation or arbitrary URL capabilities. Structured output selects candidate IDs only. Unknown candidates/sources and conflicting same-day suggestions are rejected entirely.
- `api/coaching.accept` serializes acceptance, verifies ownership and exact context freshness, locks completed activities/history, records the original prescription and adjustment note, validates the full schedule again, and commits atomically. Duplicate acceptance is idempotent. One option per review; request a new review to consider another.
- A new activity, lap change, rating, goal, recovery update, schedule edit, day rollover, model/key change, policy/source update or plan activation invalidates old advice. Accepted options cannot activate a preview.
- Model prose is fallible advisory text, not a verified factual evaluator. The applied deterministic decision is separately included in run feedback. Output schema and validation prevent training mutations from prose; they cannot prove every sentence is true.

## APIs and UI

- `POST /api/coaching/{user_id}/review`: `{activity_id? , plan_id?}`; defaults to current approved block if neither supplied.
- `GET /api/coaching/{user_id}/latest?activity_id=...` or `?plan_id=...`: stored review plus freshness, no OpenAI call.
- `GET /api/coaching/{user_id}/status`: configured/model/local daily usage, never the key.
- `POST /api/coaching/{user_id}/reviews/{id}/accept`: `{candidate_id}`.

Today shows the review for today's latest recorded run; run details support any past run; Plan supports current or preview block review. Stale/fallback/pending states are explicit. An unavailable provider cannot undo saved feedback or deactivate a plan. A fallback can be retried after five minutes; identical successful advice is reused until context changes. A process interruption while a reservation is pending can require recovery (see below).

## Testing and remaining limits

Normal tests explicitly disable both provider keys before importing settings and use disposable databases. Regression coverage includes malicious/unknown candidate IDs, unknown sources, deduplication/concurrency, quotas, bounded transport, phase/category/pace preservation, rollback and stale context rejection. A separate small live connection test used synthetic metrics only. UI QA and migration verification use database copies with Garmin polling and tokens disabled.

Calls run in the synchronous worker request (not the event loop), with a 35-second network timeout; manual reviews still run within the request; automatic Garmin reviews use the local durable job worker. A killed process can leave a pending reservation; it expires to a safe fallback and can be retried after five minutes. The menu is deliberately conservative, not unrestricted AI plan generation. No OpenAI-powered pace calibration, automatic escalation, diagnostic triage or weekly-notification system was added. Garmin sync now schedules reviews through the local durable worker. Those need separate product decisions and evaluations.

### Live evaluation finding

The first real-history smoke review incorrectly counted threshold workouts in two separate weeks as a second weekly quality stimulus, and overinterpreted an average HR without zones. The v2 prompt/context now supplies explicit per-week quality dates, a clear distinction between introductory quality and earned progression, HR uncertainty and non-diagnostic risk semantics. A regression verifies this context. Live model checks supplement deterministic tests; a valid JSON response is not evidence that coaching prose is correct.
