# Coaching evaluation

`coaching-cases.json` defines the initial 12 cases and desired behavior. Expand it
with real failures using consented or deidentified data. These are acceptance
criteria, not a claim that an independent coach has approved every output.

For each saved output, prepare a local JSONL record:

```json
{"case_id":"missing-laps","context":{"candidates":[],"historical_profile":{"insights":[]}},"review":{"suggestions":[],"history_insight_ids":[]},"coach_labels":{"evidence_supported":true,"challenge_appropriate":true,"action_clear":true,"respects_schedule":true,"no_unsupported_physiology":true}}
```

Run from backend: `venv/bin/python -m app.services.coaching_eval REVIEWS.jsonl`.
This makes no network/model calls. Unknown candidate/evidence IDs fail. Unlabeled
outputs remain `needs_coach_review`; passing unit tests alone cannot mark prose
quality approved. Grade the five criteria against the case expectation and
compare pass/fail counts across policy versions before changing models/prompts.
Track latency, tokens, queue failures and repeat athlete corrections alongside
these judgments. Keep raw health-data exports out of Git.

This follows the [official OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices): use representative cases, explicit criteria and human judgment to calibrate automated checks. It does not depend on a hosted evaluation product.
