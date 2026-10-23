"""Play a demo athlete's whole program forward and write it as a readable Markdown doc.

The runner completes every prescribed run exactly: the prescribed distance, workouts at
the middle of their pace range with matching Garmin-style laps, and a 7/10 feel rating
after workouts, long runs and races. Every time a block ends, the real engine builds the
next block from what was run, and it is approved. Race goals run to race day; other goals
run for --weeks weeks.

Uses a temporary database and frozen clock; never touches backend/stride.db, Garmin or AI.

    venv/bin/python scripts/simulate_demo_program.py beginner-marathon --out ../docs/demo-programs/beginner-marathon.md
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FEEL = 7  # "good": a normal, successful session
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def first_sentence(text, limit=170):
    text = " ".join((text or "").split())
    if not text:
        return ""
    cut = text.find(". ")
    sentence = text if cut == -1 else text[:cut + 1]
    return sentence if len(sentence) <= limit else sentence[:limit - 1].rstrip(" ,;") + "…"


def laps_for(day, easy_pace, mi):
    """Garmin-style laps that execute a structured session (workout or long run) exactly."""
    spec = day.get("prescription") or {}
    segments = spec.get("segments") or []
    work = []
    for index, seg in enumerate(segments):
        pace_range = seg.get("pace_range_sec_per_mile") or {}
        pace = ((pace_range.get("fast") or 0) + (pace_range.get("slow") or 0)) / 2 or spec.get('estimated_work_pace_sec_per_mile') or easy_pace
        reps = seg.get("reps") or 1
        for rep in range(reps):
            seconds = seg.get("duration_seconds") or (seg.get("distance_meters") or 0) / mi * pace
            meters = seg.get("distance_meters") or (seg.get("duration_seconds") or 0) / pace * mi
            if not meters:
                continue
            work.append({"intensity": "ACTIVE", "distance_m": meters, "duration_s": seconds})
            last = index == len(segments) - 1 and rep == reps - 1
            if not last and (seg.get("recovery_seconds") or seg.get("recovery_meters")):
                rest_s = seg.get("recovery_seconds") or seg["recovery_meters"] / mi * easy_pace
                work.append({"intensity": "RECOVERY", "distance_m": rest_s / easy_pace * mi, "duration_s": rest_s})
    if not work:
        return []
    remaining = max(0.0, day["distance_miles"] * mi - sum(lap["distance_m"] for lap in work))
    warm = (spec.get("warmup") or {}).get("distance_meters")
    cool = (spec.get("cooldown") or {}).get("distance_meters")
    if (spec.get('warmup') or {}).get('duration_seconds'):
        warm = spec['warmup']['duration_seconds'] / easy_pace * mi
    if (spec.get('cooldown') or {}).get('duration_seconds'):
        cool = spec['cooldown']['duration_seconds'] / easy_pace * mi
    if warm is None and cool is None:
        warm = cool = remaining / 2
    else:
        warm, cool = warm or 0, cool or 0
    easy_lap = lambda kind, meters: {"intensity": kind, "distance_m": meters, "duration_s": meters / mi * easy_pace}
    laps = [easy_lap("WARMUP", warm)] + work + [easy_lap("COOLDOWN", cool)]
    return [lap for lap in laps if lap["distance_m"] > 1]


def describe(day):
    if day["type"] == "rest" or not day["distance_miles"]:
        return "Rest"
    spec = day.get("prescription") or {}
    # Easy and long runs keep their guidance in the prescription note ("6mi easy at 8:05-8:55/mi. Conversational...").
    what = first_sentence(spec.get("note") if spec.get("evidence_source") == "effort_guidance" or not spec.get("segments") else None) \
        or first_sentence(day.get("description"))
    if day["type"] == "long_run":
        # Long runs explain their structure over up to three sentences ("4h50 on trail... Run the middle third at race effort.")
        text = " ".join((day.get("description") or "").split())
        sentences = [x for x in text.split(". ") if x][:3]
        what = ". ".join(sentences) or what
    what = what.rstrip(".")
    if day["type"] == "workout" and day.get("warmup"):
        what += f" (warm up {day['warmup']}, cool down {day.get('cooldown') or day['warmup']})"
    why = first_sentence(day.get("purpose"), 130) if day["type"] in ("workout", "long_run", "race") else ""
    return f"{what}. *Why:* {why}" if why else f"{what}."


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--weeks", type=int, default=16, help="length for goals without a race date")
    parser.add_argument("--keep-db", type=Path, help="copy the simulated database here for inspection")
    parser.add_argument('--start-date', type=date.fromisoformat, default=date.today(), help='freeze seeding and the whole program to this date')
    parser.add_argument('--experience', choices=['beginner', 'intermediate'], help='inspect the same starting history with another developmental tier')
    parser.add_argument('--miss-week', type=int, help='stress test: miss every run in this 1-based calendar week')
    parser.add_argument('--poor-week', type=int, help='stress test: rate hard days 3/10 in this calendar week')
    parser.add_argument('--no-laps', action='store_true', help='realistic: no lap data; the runner self-reports completion and effort')
    parser.add_argument('--hard-from-week', type=int, help='realistic: workouts feel harder than intended (effort 8/10) from this week')
    parser.add_argument('--skip-every', type=int, help='realistic: inconsistent schedule, skip every Nth scheduled run')
    parser.add_argument('--goal-change-week', type=int, help='realistic: switch goal at the start of this week (see --goal-change-to)')
    parser.add_argument('--goal-change-to', default='10k', help='race distance for --goal-change-week (race 16 weeks later)')
    args = parser.parse_args()
    if any(w is not None and w < 1 for w in (args.miss_week, args.poor_week, args.hard_from_week, args.skip_every, args.goal_change_week)):
        parser.error('Stress-test week numbers must be positive.')
    import time_machine
    with time_machine.travel(datetime.combine(args.start_date, time(12)), tick=False):
        simulate(args)


def simulate(args):

    profile = json.loads((ROOT / "demo/scenarios" / f"{args.scenario}.json").read_text())
    deviations = [f'missed week {args.miss_week}' if args.miss_week else None,
                  f'poor-recovery week {args.poor_week}' if args.poor_week else None,
                  'no lap data (self-reported completion)' if args.no_laps else None,
                  f'workouts harder than intended from week {args.hard_from_week}' if args.hard_from_week else None,
                  f'skips every {args.skip_every}th run' if args.skip_every else None,
                  f'goal changes to {args.goal_change_to} in week {args.goal_change_week}' if args.goal_change_week else None]
    deviations = [d for d in deviations if d]
    if deviations:
        text = '; '.join(deviations)
        profile = {**profile, 'simulation_deviation': text[0].upper() + text[1:] + '.',
                   'description': profile['description'] + f' Stress test: {text}.'}
    if args.experience:
        profile = {**profile, 'experience': args.experience,
                   'name': profile['name'] + f' ({args.experience})',
                   'description': f"{args.experience.title()} progression comparison using the {args.scenario} starting history."}
    workdir = Path(tempfile.mkdtemp(prefix="stride-sim-"))
    os.environ.update(DATABASE_URL=f"sqlite:///{workdir / 'sim.db'}", GARMIN_POLL_MINUTES="0",
                      GARMIN_API_KEY="", OPENAI_API_KEY="", OPENAI_AUTO_REVIEWS="false",
                      STRIDE_BACKUP_DIR=str(workdir / "backups"))
    sys.path.insert(0, str(ROOT / "backend"))
    import time_machine
    from fastapi.testclient import TestClient

    from app.core.workout_data import MI
    from app.database import SessionLocal
    from app.main import app
    from app.models.activity import Activity
    from app.models.wellness import DailyWellness
    from app.services.demo_seed import seed_demo

    client = TestClient(app)
    start = date.today()
    with SessionLocal() as db:
        seeded = seed_demo(db, profile)
    race_day = date.fromisoformat(seeded["race_date"]) if seeded.get("race_date") else None
    monday = start - timedelta(days=start.weekday())
    end = race_day or monday + timedelta(weeks=args.weeks, days=-1)
    easy_pace = profile["easy_pace"]

    days, blocks, history = {}, [], {}
    first = client.get("/api/plans/1/current").json()
    blocks.append({"start": first["start_date"], "end": first["end_date"], "assessment": first.get("assessment"),
                   "load": first.get("load"), "notes": first.get("notes", [])})
    for week in first["weeks"]:
        for day in week["days"]:
            if day["date"] < start.isoformat():
                history[day["date"]] = day  # lived before the simulation began

    current = start
    scheduled_runs = 0
    try:
        while current <= end:
            week_number = (current - monday).days // 7 + 1
            missed = week_number == args.miss_week
            with time_machine.travel(datetime.combine(current, time(12)), tick=False):
                if args.goal_change_week and week_number == args.goal_change_week and current.weekday() == 0:
                    changed = client.post("/api/users/1/goal", json={
                        "goal_type": "race", "race_distance": args.goal_change_to, "override_readiness": True,
                        "race_date": (current + timedelta(weeks=16)).isoformat()})
                    if changed.status_code != 200:
                        raise SystemExit(f"{current}: goal change failed: {changed.text}")
                    end = max(end, current + timedelta(weeks=4))
                plan = client.get("/api/plans/1/current").json()
                if current.isoformat() > plan["end_date"]:
                    draft = client.post("/api/plans/1/preview", json={"scope": "next"})
                    if draft.status_code != 200:
                        raise SystemExit(f"{current}: next block failed: {draft.text}")
                    draft = draft.json()
                    approved = client.post(f"/api/plans/1/drafts/{draft['id']}/approve")
                    if approved.status_code != 200:
                        raise SystemExit(f"{current}: approval failed: {approved.text}")
                    plan = client.get("/api/plans/1/current").json()
                    blocks.append({"start": plan["start_date"], "end": plan["end_date"], "assessment": plan.get("assessment"),
                                   "load": plan.get("load"), "notes": plan.get("notes", [])})
                phase_by_date = {d["date"]: (w.get("phase") or {}) for w in plan["weeks"] for d in w["days"]}
                day = next((d for w in plan["weeks"] for d in w["days"] if d["date"] == current.isoformat()), None)
                if day:
                    days[day["date"]] = {**day, "phase": phase_by_date.get(day["date"], {})}
                if day and not missed and day["type"] != "rest" and day["distance_miles"] and day.get("prescribed", True):
                    scheduled_runs += 1
                    if args.skip_every and scheduled_runs % args.skip_every == 0 and day["type"] != "race":
                        missed = True  # life happens: this run doesn't
                with SessionLocal() as db:
                    if day and not missed and day["type"] != "rest" and day["distance_miles"]:
                        # Any session with paced work (workouts, marathon-pace long runs) gets matching laps.
                        spec = day.get("prescription") or {}
                        structured = any(seg.get("category") for seg in spec.get("segments") or [])  # MP / steady / race effort
                        laps = laps_for(day, easy_pace, MI) if (day["type"] == "workout" or structured) and not args.no_laps else []
                        seconds = sum(l["duration_s"] for l in laps) if laps else day["distance_miles"] * easy_pace
                        category = (day.get("prescription") or {}).get("category")
                        db.add(Activity(user_id=1, source="manual", external_id=f"sim-{current}", name=f"Simulated {day['title']}",
                                        date=datetime.combine(current, time(7)), distance_meters=day["distance_miles"] * MI,
                                        duration_seconds=seconds, average_pace_per_km=seconds / (day["distance_miles"] * 1.60934),
                                        average_heartrate=155 if laps else 135, description=day.get("description"),
                                        splits=json.dumps(laps), workout_type=category if laps else day["type"]))
                    if not db.query(DailyWellness).filter_by(user_id=1, date=current.isoformat()).first():
                        db.add(DailyWellness(user_id=1, date=current.isoformat(), sleep_seconds=8 * 3600, sleep_score=85,
                                             hrv_last_night=70, hrv_baseline_low=60, hrv_baseline_high=80, resting_hr=48,
                                             readiness_score=80, acwr=1.0))
                    db.commit()
                if day and not missed and day["type"] in ("workout", "long_run", "race") and day["distance_miles"]:
                    body = {"feel_rating": 3 if week_number == args.poor_week else FEEL}
                    if day["type"] == "workout":
                        hard = args.hard_from_week and week_number >= args.hard_from_week
                        body["effort_rating"] = 8 if hard else 6
                        if args.no_laps:
                            body["completion"] = "full"
                    feedback = client.post(f"/api/plans/1/feedback/{current.isoformat()}", json=body)
                    if feedback.status_code != 200:
                        raise SystemExit(f"{current}: feedback failed: {feedback.text}")
            current += timedelta(days=1)
    finally:
        if args.keep_db:
            import sqlite3
            with sqlite3.connect(workdir / "sim.db") as source, sqlite3.connect(args.keep_db) as target:
                source.backup(target)  # includes WAL contents, unlike a file copy
        shutil.rmtree(workdir, ignore_errors=True)

    write_doc(args.out, profile, seeded, start, end, race_day, history, days, blocks)


def write_doc(out, profile, seeded, start, end, race_day, history, days, blocks):
    every = {**history, **days}
    weeks = {}
    for iso in sorted(every):
        d = date.fromisoformat(iso)
        weeks.setdefault(d - timedelta(days=d.weekday()), []).append(every[iso])
    rows, sections = [], []
    for number, (week_start, week_days) in enumerate(sorted(weeks.items()), start=1):
        total = sum(d["distance_miles"] for d in week_days)
        phase = next((d["phase"].get("phase") for d in week_days if isinstance(d.get("phase"), dict) and d["phase"].get("phase")), "")
        longs = [d for d in week_days if d["type"] == "long_run" and d["distance_miles"]]
        quality = [d["title"] for d in week_days if d["type"] in ("workout", "race") and d["distance_miles"]]
        rows.append(f"| {number} | {week_start:%b %d} | {phase.replace('_', ' ').title() or '—'} | {total:.1f} | "
                    f"{' + '.join(f'{d['distance_miles']:g}' for d in longs) or '—'} | {', '.join(quality) or 'easy running only'} |")
        lines = [f"### Week {number} · {week_start:%b %d}–{week_start + timedelta(days=6):%b %d} · "
                 f"{phase.replace('_', ' ').title() or 'Plan'} · {total:.1f} mi"]
        for d in week_days:
            day_date = date.fromisoformat(d["date"])
            label = f"**{DOW[day_date.weekday()]} {day_date:%b %d}**"
            if d["date"] in history:
                miles = d.get("actual", {}).get("total_distance_miles") if d.get("actual") else d["distance_miles"]
                lines.append(f"- {label} · already run before this program ({miles or 0:g} mi)" if miles else f"- {label} · Rest")
            elif d["type"] == "rest" or not d["distance_miles"]:
                lines.append(f"- {label} · Rest")
            else:
                lines.append(f"- {label} · {d['title']} · {d['distance_miles']:g} mi — {describe(d)}")
        sections.append("\n".join(lines))

    athlete = profile
    goal = (f"{athlete.get('distance', '').upper()} race on {race_day:%a %b %d, %Y}" if race_day
            else f"build to {athlete.get('target_weekly_mileage')} mi/week (no race)")
    block_lines = []
    for i, block in enumerate(blocks, start=1):
        decision = (block.get("assessment") or {}).get("decision") or "first block"
        mode = (block.get("load") or {}).get("mode", "")
        reasons = (block.get("load") or {}).get("reasons") or []
        why = [r for r in (block.get("assessment") or {}).get("reasons") or [] if r][:3]
        block_lines.append(f"- **Block {i}** ({date.fromisoformat(block['start']):%b %d}–{date.fromisoformat(block['end']):%b %d}): "
                           f"**{decision}** → {mode}. {' '.join(reasons[-1:])}" + (f" Why: {' '.join(why)}" if why else ""))
    extra = ''
    if profile['experience'] in {'beginner', 'intermediate'}:
        checks = list(dict.fromkeys(note for b in blocks for note in b.get('notes', []) if note.startswith('Endurance preparation gap:')))
        extra = ('\n\n## Coaching checks\n\n'
                 'Controlled efforts use easy warmup and cooldown bookends, with medium-to-hard work at about 6/10 effort. '
                 'The 7/10 post-run feel rating means recovery felt good; it is a different scale. '
                 'Effort-session pace is an estimate for simulation and budgeting, not a measured threshold pace. '
                 'Reduced deload/taper doses do not earn progression.\n\n'
                 + ('\n'.join('- ' + note for note in checks) if checks else 'No near-race endurance gap was flagged in this simulation.') + '\n')
    execution_note = ('Every prescribed run is completed exactly (distance, and workouts at the middle of their pace range) with a 7/10 feel after hard days.'
                      if not profile.get('simulation_deviation') else 'Stress simulation: ' + profile['simulation_deviation'] + ' The schedule below shows prescriptions, including missed runs.')
    body = f"""# {athlete['name']}: the whole program, run exactly as prescribed

{athlete['description']}

- **Athlete:** {athlete['experience']}, {athlete.get('days_per_week', 6)} run days/week, rest on {', '.join(d.title() for d in athlete.get('rest_days', ['sunday'])) or 'no fixed day'}, long run on {athlete.get('long_run_day', 'saturday').title()}
- **Goal:** {goal}
- **Simulated:** {start:%b %d, %Y} → {end:%b %d, %Y}. {execution_note} Every two weeks Stride builds the next block from what was run and it is approved.
- Generated by `backend/scripts/simulate_demo_program.py` on today's engine; regenerate after plan-engine changes.

## How each block was decided

{chr(10).join(block_lines)}

## At a glance

| Week | Starts | Phase | Miles | Long run | Quality |
|---|---|---|---|---|---|
{chr(10).join(rows)}{extra}

## Week by week

{chr(10).join(chr(10) + s for s in sections).strip()}
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body)
    print(f"Wrote {out} ({len(rows)} weeks, {len(blocks)} blocks)")


if __name__ == "__main__":
    main()
