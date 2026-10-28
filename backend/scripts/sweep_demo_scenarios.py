"""Hammer every demo athlete with settings and plan changes; report any 5xx or exception.

For each scenario: seed a fresh synthetic DB, then for each clock offset (days from today, so
plans are tested mid-block, a week in and after the block ended) run every case from a fresh
copy of that DB. A case changes settings or the goal, redrafts the block for the new schedule,
approves it, rebuilds, previews the next block, and reads every page's API. Session actions
(skip, replace, switch) and every switch-target preview (each valid one applied) run on the seeded plan.

Refusals (409/422) are expected and counted; only server errors fail the sweep. Uses temporary
databases with Garmin and AI disabled; never opens backend/stride.db. Takes a few minutes.

    venv/bin/python scripts/sweep_demo_scenarios.py                       # all scenarios
    venv/bin/python scripts/sweep_demo_scenarios.py trail-100k --offsets 8
    venv/bin/python scripts/sweep_demo_scenarios.py --database ../.demo/trail-100k/stride.db  # a played demo (copied)
"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = sorted(p.stem for p in (ROOT / "demo/scenarios").glob("*.json"))
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
READS = ["/api/plans/1/current", "/api/plans/1/outlook", "/api/plans/1/goal", "/api/plans/1/draft", "/api/users/1",
         "/api/analysis/1/weekly-mileage", "/api/analysis/1/mileage", "/api/analysis/1/mileage?include=walks",
         "/api/analysis/1/history", "/api/analysis/1/trends", "/api/analysis/1/activities",
         "/api/coaching/1/status", "/api/wellness/1", "/api/analysis/1/calibrated-paces"]


def cases():
    out = []
    for n in range(3, 8):
        for rest in ([], ["friday"], ["monday", "friday"]):
            if 7 - len(rest) >= n:
                out.append((f"days={n} rest={rest}", {"days_per_week": n, "rest_days": rest}))
    for day in DAYS:
        out.append((f"long run {day}", {"long_run_day": day}))
        out.append((f"7 days, long run {day}", {"days_per_week": 7, "rest_days": [], "long_run_day": day}))
        out.append((f"rest on long-run day {day}", {"rest_days": [day], "long_run_day": day}))
    out += [("time format", {"workout_format": "time"}), ("distance format", {"workout_format": "distance"}),
            ("km", {"units": "km"}), ("beginner", {"experience_level": "beginner"}), ("expert", {"experience_level": "expert"}),
            ("2 days", {"days_per_week": 2, "rest_days": ["monday", "wednesday", "friday", "sunday"]}),
            ("1 day", {"days_per_week": 1}), ("time limits", {"day_time_budgets": {"tuesday": 30, "saturday": 60}}),
            ("time limits, 7 days, Sunday long run", {"days_per_week": 7, "rest_days": [], "long_run_day": "sunday",
                                                      "day_time_budgets": {"tuesday": 30, "thursday": 30}}),
            ("time limits, time format", {"workout_format": "time", "day_time_budgets": {d: 40 for d in DAYS}})]
    for minutes in (15, 25, 45, 90):
        out.append((f"all days {minutes}min", {"day_time_budgets": {d: minutes for d in DAYS}}))
        out.append((f"weekdays {minutes}min", {"day_time_budgets": {d: minutes for d in DAYS[:5]}}))
    ahead = lambda days: (date.today() + timedelta(days=days)).isoformat()
    for goal in [{"goal_type": "race", "race_distance": "5k", "target_time_seconds": 1500, "race_date": ahead(60)},
                 {"goal_type": "race", "race_distance": "half", "target_time_seconds": 6000, "race_date": ahead(10)},
                 {"goal_type": "race", "race_distance": "marathon", "target_time_seconds": 14400, "race_date": ahead(200)},
                 {"goal_type": "race", "race_distance": "100k", "target_time_seconds": 50000, "race_date": ahead(200),
                  "terrain": "trail", "elevation_gain_ft": 8000, "override_readiness": True},
                 {"goal_type": "race", "race_distance": "100mi", "race_date": ahead(200), "terrain": "mountain", "override_readiness": True},
                 {"goal_type": "mileage", "target_weekly_mileage": 50}, {"goal_type": "general"}, {"goal_type": "comeback"}]:
        out.append((f"goal {goal['goal_type']} {goal.get('race_distance', '')}".strip(), {"_goal": goal}))
    return out


def worker(seed: Path, work: Path, offsets: list[int]) -> dict:
    """Runs inside a process whose DATABASE_URL points at `work`."""
    import time_machine
    from fastapi.testclient import TestClient
    sys.path.insert(0, str(ROOT / "backend"))
    from app.athlete_clock import today as athlete_today
    from app.database import engine
    from app.main import app

    failures, stats = [], Counter()

    def reset():
        engine.dispose()
        for suffix in ("", "-wal", "-shm"):
            Path(f"{work}{suffix}").unlink(missing_ok=True)
        shutil.copy(seed, work)

    def call(c, case, method, url, **kw):
        r = getattr(c, method)(url, **kw)
        stats[f"{method.upper()} {r.status_code}"] += 1
        if r.status_code >= 500:
            failures.append(f"{case}: {method.upper()} {url} {kw.get('json', '')} -> {r.status_code} {r.text[:300]}")
        return r

    def reads(c, case):
        for url in READS:
            call(c, case, "get", url)

    def approve(c, case, r):
        if r.status_code == 200:
            call(c, case, "post", f"/api/plans/1/drafts/{r.json()['id']}/approve")

    def settings_case(c, case, profile):
        goal = profile.pop("_goal", None)
        if goal:
            call(c, case, "post", "/api/users/1/goal/check", json=goal)
            call(c, case, "post", "/api/users/1/goal", json=goal)
        call(c, case, "put", "/api/users/1/profile", json=profile)
        approve(c, case, call(c, case, "post", "/api/plans/1/preview", json={"scope": "current", "mode": "schedule"}))
        reads(c, case)
        approve(c, case, call(c, case, "post", "/api/plans/1/preview", json={}))
        call(c, case, "post", "/api/plans/1/preview", json={"scope": "next"})
        call(c, case, "post", "/api/plans/1/preview", json={"lighter": True})
        reads(c, case)

    def upcoming(c):
        today = athlete_today().isoformat()
        return [d for w in c.get("/api/plans/1/current").json().get("weeks", []) for d in w["days"] if d["date"] >= today][:10]

    def session_case(c, prefix):
        for d in upcoming(c):
            case = f"{prefix} {d['date']} {d['type']}"
            for category in ("threshold", "intervals", "long_run"):
                call(c, case, "get", f"/api/plans/1/sessions/{d['date']}/options?category={category}")
            later = (date.fromisoformat(d["date"]) + timedelta(days=1)).isoformat()
            for body in [{"action": "skip"}, {"action": "replace", "replacement": "easy"}, {"action": "replace", "replacement": "rest"},
                         {"action": "replace", "replacement": "long_run"}, {"action": "switch", "target_date": later}]:
                call(c, case, "post", f"/api/plans/1/sessions/{d['date']}", json=body)
            reads(c, case)

    def switch_case(c, prefix):
        for d in upcoming(c):
            case = f"{prefix} {d['date']} {d['type']}"
            r = call(c, case, "get", f"/api/plans/1/sessions/{d['date']}/switch-targets")
            if r.status_code != 200:
                continue
            ok = [t for t in r.json()["targets"] if t["ok"]]
            stats["switch targets ok"] += len(ok)
            stats["switch targets refused"] += len(r.json()["targets"]) - len(ok)
            if ok:
                done = call(c, case, "post", f"/api/plans/1/sessions/{d['date']}", json={"action": "switch", "target_date": ok[0]["date"], "switch_token": ok[0]['token']})
                if done.status_code != 200:  # the preview said yes, so the switch itself must succeed
                    failures.append(f"{case}: previewed switch to {ok[0]['date']} refused: {done.text[:200]}")
                elif done.json()['changes'] != ok[0]['changes']:
                    failures.append(f"{case}: applied switch differed from its approved preview")
                else:
                    # A valid switch must leave ordinary edits usable, including after a rest-day override.
                    candidates = [day for day in upcoming(c) if day['type'] == 'easy' and not day.get('actual')
                                  and day.get('prescribed') is not False and not day.get('session_status')]
                    if candidates:
                        day = candidates[0]['date']
                        skipped = call(c, case, 'post', f'/api/plans/1/sessions/{day}', json={'action': 'skip'})
                        if skipped.status_code != 200:
                            failures.append(f"{case}: unrelated skip after switch refused: {skipped.text[:200]}")
            reads(c, case)

    def guarded(name, body):
        reset()
        try:
            with TestClient(app) as c:
                body(c)
        except Exception:
            failures.append(f"{name}: EXCEPTION {traceback.format_exc()[-800:]}")

    for offset in offsets:
        with time_machine.travel(datetime.now() + timedelta(days=offset), tick=True):
            for name, profile in cases():
                name = f"+{offset}d {name}"
                guarded(name, lambda c: settings_case(c, name, dict(profile)))
            guarded(f"+{offset}d session actions", lambda c: session_case(c, f"+{offset}d session"))
            guarded(f"+{offset}d switches", lambda c: switch_case(c, f"+{offset}d switch"))
    return {"failures": failures, "stats": dict(sorted(stats.items()))}


def run_one(label: str, seed: Path, folder: Path, offsets: list[int]) -> dict:
    work = folder / f"{label}.work.db"
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{work}", GARMIN_POLL_MINUTES="0", GARMIN_API_KEY="", OPENAI_API_KEY="",
               ANTHROPIC_API_KEY="", OPENAI_AUTO_REVIEWS="false", ATHLETE_PROFILE_DOC="", STRIDE_BACKUP_DIR=str(folder / f"backups-{label}"))
    out = subprocess.run([sys.executable, __file__, "--worker", str(seed), str(work), "--offsets", ",".join(map(str, offsets))],
                         cwd=ROOT / "backend", env=env, capture_output=True, text=True)
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"failures": [f"worker crashed: {out.stderr[-1500:]}"], "stats": {}}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("scenarios", nargs="*", help=f"default: all ({', '.join(SCENARIOS)}), or none when --database is given")
    parser.add_argument("--offsets", default="0,3,8,15", help="comma-separated clock offsets in days")
    parser.add_argument("--database", type=Path, action="append", default=[], help="also sweep a COPY of this demo DB")
    parser.add_argument("--worker", nargs=2, type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    offsets = [int(x) for x in args.offsets.split(",")]
    if args.worker:
        print(json.dumps(worker(*args.worker, offsets)))
        return

    unknown = set(args.scenarios) - set(SCENARIOS)
    if unknown:
        parser.error(f"unknown scenario(s): {', '.join(sorted(unknown))}")
    folder = Path(tempfile.mkdtemp(prefix="stride-sweep-"))
    seeds = {}
    for scenario in args.scenarios or ([] if args.database else SCENARIOS):
        seeds[scenario] = folder / f"{scenario}.seed.db"
        subprocess.run([sys.executable, str(ROOT / "demo/seed.py"), "--scenario", scenario, "--database", str(seeds[scenario])],
                       check=True, capture_output=True)
    for path in args.database:
        if path.resolve() == (ROOT / "backend/stride.db").resolve():
            raise SystemExit("Refusing to sweep the personal database.")
        label = f"copy-{path.parent.name}"
        seeds[label] = folder / f"{label}.seed.db"
        with sqlite3.connect(path) as source, sqlite3.connect(seeds[label]) as copy:
            source.backup(copy)

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(6, len(seeds))) as pool:
        results = dict(zip(seeds, pool.map(lambda item: run_one(item[0], item[1], folder, offsets), seeds.items())))
    failed = 0
    for label, result in results.items():
        failed += len(result["failures"])
        print(f"{label}: {len(result['failures'])} failures · {result['stats']}")
        for line in result["failures"][:10]:
            print("   ", line)
    shutil.rmtree(folder, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
