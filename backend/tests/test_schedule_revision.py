"""Schedule-only changes keep the approved block and change as little as possible."""
from datetime import date, timedelta

from app.core.change_guard import review_change, summarize_change
from app.database import SessionLocal
from app.core.schedule_revision import SchedulePrefs, revise_for_schedule
from app.core.schedule_revision import WEEKDAYS

EASY = "Conversational effort."


def week(number, sessions, monday=date(2026, 10, 19), editable_from=None):
    """sessions: 7 (type, title, miles) tuples, Monday first."""
    start = monday + timedelta(weeks=number - 1)
    days = []
    for i, (kind, title, miles) in enumerate(sessions):
        day = start + timedelta(days=i)
        days.append({"date": day.isoformat(), "day": WEEKDAYS[i], "type": kind, "title": title,
                     "distance_miles": miles, "editable": editable_from is None or day >= editable_from})
    return {"week_number": number, "days": days}


REST = ("rest", "Rest Day", 0)


def prefs(days, rest=(), long_day="saturday"):
    return SchedulePrefs(days, sorted(rest), long_day)


def total(w):
    return sum(d["distance_miles"] for d in w["days"])


def quality(w):
    return sorted(d["title"] for d in w["days"] if d["type"] == "workout")


def by_day(w):
    return {d["day"]: d for d in w["days"]}


def jake_block():
    """Jake's block from the screenshot, revised on Wed Oct 21 (Mon-Wed already run)."""
    w1 = week(1, [("easy", "Run", 5), ("workout", "3x8min Threshold", 7), ("easy", "Easy Run", 5),
                  ("workout", "6x400m Relaxed Repetitions", 5), ("easy", "Easy Run", 6),
                  ("long_run", "Easy Long Run", 11), REST], editable_from=date(2026, 10, 22))
    w2 = week(2, [("easy", "Easy Run + Strides", 5), ("workout", "3mi Tempo Run", 6), ("easy", "Easy Run", 6),
                  ("workout", "3x1200m Intervals", 6), ("easy", "Easy Run", 6), ("long_run", "Easy Long Run", 11), REST],
              editable_from=date(2026, 10, 22))
    return [w1, w2]


def test_six_to_seven_days_adds_a_short_recovery_run_and_keeps_every_workout():
    before = jake_block()
    rev = revise_for_schedule(before, prefs(6, ["sunday"]), prefs(7), experience="advanced", easy_desc=EASY)
    for old, new in zip(before, rev.weeks):
        assert quality(new) == quality(old)  # 3mi tempo and 3x1200m stay exactly as approved
        sunday = by_day(new)["sunday"]
        assert sunday["type"] == "easy" and sunday["title"] == "Recovery Run" and 2 <= sunday["distance_miles"] <= 4
        assert by_day(new)["saturday"]["distance_miles"] == 11
        assert total(new) - total(old) <= 3  # "a little bit more", never a new block's worth
    assert [d for d in rev.weeks[0]["days"] if not d["editable"]] == [d for d in before[0]["days"] if not d["editable"]]
    assert review_change(before, rev.weeks, prefs(7), kind="schedule") == []
    changed = {c["date"]: c for c in rev.changes}
    assert {"2026-10-25", "2026-11-01"} <= set(changed)
    # Any other change only trims an easy run by a half mile to fund the new day.
    assert all(c["reason"].startswith("Shortened") for d, c in changed.items() if d not in {"2026-10-25", "2026-11-01"})
    assert "same workouts" in summarize_change(before, rev.weeks)[1]


def test_beginner_more_days_splits_miles_instead_of_adding_them():
    # 20 mi over 4 days → 5 days: same 20 mi, the new day is made from the two easy runs.
    before = [week(1, [REST, ("workout", "Easy Fartlek", 4), ("easy", "Easy Run", 5), REST,
                       ("easy", "Easy Run", 5), ("long_run", "Long Run", 6), REST])]
    rev = revise_for_schedule(before, prefs(4, ["monday", "thursday", "sunday"]), prefs(5), experience="beginner", easy_desc=EASY)
    new = rev.weeks[0]
    assert total(new) == total(before[0]) == 20
    assert sum(d["type"] != "rest" for d in new["days"]) == 5 and quality(new) == ["Easy Fartlek"]
    assert by_day(new)["sunday"]["type"] == "easy"  # the day after the long run
    assert review_change(before, rev.weeks, prefs(5), kind="schedule") == []


def test_low_volume_beginner_three_to_five_days_waits_for_the_next_block():
    # 10 mi over 3 days has no easy miles to split: never jump to 20 mi or a second workout.
    before = [week(1, [REST, ("workout", "Easy Fartlek", 3), REST, ("easy", "Easy Run", 3), REST, ("long_run", "Long Run", 4), REST])]
    rev = revise_for_schedule(before, prefs(3, ["monday", "wednesday", "friday", "sunday"]), prefs(5),
                              experience="beginner", easy_desc=EASY)
    assert total(rev.weeks[0]) == 10 and quality(rev.weeks[0]) == ["Easy Fartlek"]
    assert any("next block" in note for note in rev.notes)
    assert review_change(before, rev.weeks, prefs(5), kind="schedule") == []


def test_fewer_days_drops_easy_runs_first_and_keeps_their_miles():
    before = [week(1, [("easy", "Easy Run", 5), ("workout", "Threshold", 7), ("easy", "Easy Run", 5),
                       ("workout", "Intervals", 6), ("easy", "Easy Run", 4), ("long_run", "Long Run", 11), ("easy", "Recovery Run", 3)])]
    rev = revise_for_schedule(before, prefs(7), prefs(5, ["monday", "friday"]), experience="advanced", easy_desc=EASY)
    new = by_day(rev.weeks[0])
    assert new["monday"]["type"] == new["friday"]["type"] == "rest"
    assert quality(rev.weeks[0]) == ["Intervals", "Threshold"] and new["saturday"]["distance_miles"] == 11
    assert total(rev.weeks[0]) == total(before[0])  # 9 freed miles moved onto Wed and Sun
    assert review_change(before, rev.weeks, prefs(5, ["monday", "friday"]), kind="schedule") == []


def test_workout_on_a_new_rest_day_moves_to_a_safe_easy_day():
    before = [week(1, [("easy", "Easy Run", 5), ("workout", "Threshold", 7), ("easy", "Easy Run", 5),
                       ("easy", "Easy Run", 5), ("workout", "Intervals", 6), ("long_run", "Long Run", 11), REST])]
    rev = revise_for_schedule(before, prefs(6, ["sunday"]), prefs(5, ["friday", "sunday"]), experience="advanced", easy_desc=EASY)
    new = by_day(rev.weeks[0])
    assert new["friday"]["type"] == "rest" and quality(rev.weeks[0]) == ["Intervals", "Threshold"]
    # Mon and Wed touch Tuesday's threshold; Thursday sits between an easy day and the new rest day.
    assert new["thursday"]["title"] == "Intervals"
    assert review_change(before, rev.weeks, prefs(5, ["friday", "sunday"]), kind="schedule") == []


def test_long_run_follows_a_new_long_run_day():
    before = jake_block()
    rev = revise_for_schedule(before, prefs(6, ["sunday"]), prefs(6, ["saturday"], "sunday"), experience="advanced", easy_desc=EASY)
    for new in rev.weeks:
        assert by_day(new)["sunday"]["type"] == "long_run" and by_day(new)["saturday"]["type"] == "rest"
    assert review_change(before, rev.weeks, prefs(6, ["saturday"], "sunday"), kind="schedule") == []


def test_guard_rejects_added_quality_back_to_back_and_big_jumps():
    before = jake_block()
    after = jake_block()
    by_day(after[1])["sunday"].update(type="workout", title="Bonus Intervals", distance_miles=8)
    problems = review_change(before, after, prefs(7), kind="schedule")
    assert any("must not add quality" in p for p in problems)
    assert any("straight after another hard day" in p for p in problems)
    assert any("more added volume" in p for p in problems)


def _approved_block(experience='advanced'):
    from fastapi.testclient import TestClient
    from app.main import app
    from tests.test_plan_preview import seed
    client = TestClient(app)
    seed()
    assert client.put('/api/users/1/profile', json={'experience_level': experience}).status_code == 200
    draft = client.post('/api/plans/1/preview').json()
    assert client.post(f"/api/plans/1/drafts/{draft['id']}/approve").status_code == 200
    return client, client.get('/api/plans/1/current').json()


def test_api_schedule_change_keeps_the_approved_workouts_and_is_approvable():
    client, active = _approved_block()  # the seeded athlete runs 6 days with Friday rest
    assert client.put('/api/users/1/profile', json={'days_per_week': 7, 'rest_days': []}).status_code == 200
    r = client.post('/api/plans/1/preview', json={'scope': 'current', 'mode': 'schedule'})
    assert r.status_code == 200, r.text
    draft = r.json()
    assert draft['revision'] == 'schedule' and draft['athlete']['schedule_preferences']['days_per_week'] == 7
    titles = lambda w, kind: [d['title'] for d in w['days'] if d['type'] == kind]
    added = 0
    for old_week, new_week in zip(active['weeks'], draft['weeks']):
        assert titles(new_week, 'workout') == titles(old_week, 'workout')
        assert titles(new_week, 'long_run') == titles(old_week, 'long_run')
        assert -0.5 <= new_week['target_mileage'] - old_week['target_mileage'] <= 3  # a little more, never a new block
        for old_day, new_day in zip(old_week['days'], new_week['days']):
            if old_day['type'] == 'rest' and new_day['type'] != 'rest':
                assert new_day['day'] == 'friday' and new_day['type'] == 'easy' and new_day['distance_miles'] <= 4
                assert new_day['adjustment_note']
                added += 1
    assert added >= 1 and draft['change_summary'] and draft['changes']
    # The stored draft matches what the guard checked: every changed date is saved.
    with SessionLocal() as db:
        from app.models.plan import PlannedWorkout
        rows = {r.date: r for r in db.query(PlannedWorkout).filter_by(plan_id=draft['id'])}
        for change in draft['changes']:
            assert rows[change['date']].adjustment_note == change['reason']
    assert client.post(f"/api/plans/1/drafts/{draft['id']}/approve").status_code == 200
    assert client.get('/api/plans/1/current').json()['id'] == draft['id']


def test_api_schedule_mode_without_a_change_says_so_and_full_rebuild_explains_itself():
    client, _ = _approved_block()
    r = client.post('/api/plans/1/preview', json={'scope': 'current', 'mode': 'schedule'})
    assert r.status_code == 409 and 'already uses your run days' in r.json()['detail']
    rebuilt = client.post('/api/plans/1/preview').json()
    assert rebuilt['change_summary'] and rebuilt['change_summary'][0].startswith('Week 1:')


def test_every_day_that_moves_miles_is_recorded_so_the_draft_matches_the_check():
    before = [week(1, [REST, ("workout", "Easy Fartlek", 4), ("easy", "Easy Run", 5), REST,
                       ("easy", "Easy Run", 5), ("long_run", "Long Run", 6), REST])]
    rev = revise_for_schedule(before, prefs(4, ["monday", "thursday", "sunday"]), prefs(5), experience="beginner", easy_desc=EASY)
    changed = {c["date"]: c for c in rev.changes}
    revised = {d["date"]: d for d in rev.weeks[0]["days"]}
    original = {d["date"]: d for d in before[0]["days"]}
    assert {d for d in revised if revised[d] != original[d]} == set(changed)  # donors included
    assert any(c["reason"].startswith("Shortened") for c in rev.changes)


def test_guard_judges_a_schedule_change_only_by_what_it_touched():
    # A race-week shakeout under 2 mi that the change never touched must not block it.
    before = jake_block()
    by_day(before[1])["monday"].update(title="Shakeout", distance_miles=1.5)
    rev = revise_for_schedule(before, prefs(6, ["sunday"]), prefs(7), experience="advanced", easy_desc=EASY)
    assert review_change(before, rev.weeks, prefs(7), kind="schedule") == []
    assert any("isn't worth the trip" in p for p in review_change(before, rev.weeks, prefs(7), kind="rebuild"))


def test_api_schedule_change_after_a_week_is_locked_still_drafts():
    # Week 1 has nothing left to edit (the trail-100k demo hit this mid-block): its budget comes from its days.
    client, active = _approved_block()
    with SessionLocal() as db:
        from app.models.plan import PlannedWorkout
        db.query(PlannedWorkout).filter_by(plan_id=active['id'], week_number=1).update({'session_status': 'skipped'})
        db.commit()
    assert client.put('/api/users/1/profile', json={'days_per_week': 7, 'rest_days': [], 'long_run_day': 'sunday'}).status_code == 200
    r = client.post('/api/plans/1/preview', json={'scope': 'current', 'mode': 'schedule'})
    assert r.status_code in (200, 409), r.text


def test_api_time_limits_redraft_stores_the_fitted_prescription_as_json():
    # fit_availability rewrites a capped day's prescription as a dict; the draft row must still save.
    client, active = _approved_block()
    limits = {d: 25 for d in WEEKDAYS[:5]}  # weekdays only: a schedule change may not shorten the long run
    assert client.put('/api/users/1/profile', json={'day_time_budgets': limits}).status_code == 200
    r = client.post('/api/plans/1/preview', json={'scope': 'current', 'mode': 'schedule'})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        from app.models.plan import PlannedWorkout
        fitted = [w for w in db.query(PlannedWorkout).filter_by(plan_id=r.json()['id']) if w.adjustment_note == 'Fit the saved daily availability.']
        assert fitted and all(isinstance(w.prescription, str) for w in fitted)
