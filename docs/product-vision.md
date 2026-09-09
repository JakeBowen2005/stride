# Stride — Product Vision

> Where this is ultimately going. Written 2026-09-09 from Jake's description.
> Read this before adding anything user-facing.

---

## The whole product, in four steps

```
Sign up  ->  Sync (Garmin or Strava)  ->  Set goal (distance + time)  ->  Plan builds
```

That is the entire onboarding. Nothing else. No questionnaire about how many
years you have been running, no manual PR entry, no preference wizard.

**Everything the app needs, it should infer from the synced data:**

| Thing | Where it comes from |
|---|---|
| Current weekly mileage | last 4 weeks of activities |
| Peak weekly mileage | all-time weekly max |
| Experience level | peak mileage + length of history |
| Easy pace | median pace of 3-8mi runs |
| Threshold / interval paces | parsed from workout descriptions and splits |
| PRs | best efforts detected across all activities |
| Workout ladder starting level | most demanding recent session |
| Injury risk | acute:chronic workload ratio |

The only things the athlete has to type are **goal distance, goal time, and
race date.** Anything else we ask for is a failure of inference.

---

## Design rules that follow from that

1. **Onboarding is three screens, not nine.** The current multi-step
   onboarding flow collects data the analyzer already derives. It should
   shrink to: sign up → connect → set goal.
2. **The plan appears immediately after the goal is set.** No "generate"
   button on first run. Setting a goal *is* the request for a plan.
3. **The data does the work.** If a field can be inferred from Strava/Garmin
   with reasonable confidence, infer it and let the athlete correct it in
   settings. Never block onboarding on it.
4. **Preferences have sane defaults.** Rest day, long run day, days per week,
   units — all defaulted, all editable later, none asked up front.
5. **It has to be honest about what it doesn't know.** A brand-new Strava
   account with three runs cannot support a marathon plan. Say so plainly and
   build the base first rather than inventing a plan from nothing.

---

## Phasing

### Phase A — single user (now)
Jake only. No auth, `user_id` hardcoded to 1. The point of this phase is to
prove the **coaching** is right: that the plans are ones a real competitive
runner would actually run, that the progression responds correctly to real
performance, and that the analysis is worth reading.

Do not build auth, multi-tenancy, or billing during this phase. Getting the
training logic right is the entire product; everything else is plumbing.

### Phase B — friends
- Email/password or OAuth sign-in
- Replace hardcoded `user_id` with the session user
- `athlete-profile-jake.md` becomes a per-user DB record generated from data
  rather than a checked-in file (the science docs stay static — training
  physiology is universal)
- Garmin Connect integration alongside Strava (Garmin wins if both connected)

### Phase C — open
Whatever Phase B teaches us. Not planned yet.

---

## What must be true before Phase B

These are the things that are Jake-specific today and would break for a second
user. Tracked so nobody has to rediscover them:

- [ ] `user_id` is hardcoded to `1` in six frontend files
- [ ] `docs/athlete-profile-jake.md` is loaded by name in `services/coach.py`
- [ ] "Good morning, Jake" is hardcoded in the dashboard
- [ ] No auth anywhere; every endpoint takes `user_id` as a path param and
      trusts it
- [ ] SQLite single-file DB; needs Postgres for concurrent users
- [ ] The Strava rate limiter is process-local, so it only holds with a single
      worker. Multi-user means moving those counters into Redis or the DB.

---

## Non-goals

- Not a general fitness app. **Running only.** No cycling, swimming, gym
  tracking. Jake lifts and trains jiu jitsu daily and the app should not care,
  beyond understanding that a "rest" day is not necessarily restful.
- Not a social network. No feed, no kudos, no following.
- Not a watch replacement. Strava/Garmin own the recording; Stride owns the
  coaching.
