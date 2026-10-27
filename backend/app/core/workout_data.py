"""Versioned numeric workout contracts. Legacy prose is an explicit fallback.

Work segments omit warmup/recovery/cooldown. Distances are meters, durations
seconds and paces seconds/mile. Confidence describes evidence, not fitness.
"""
import json
import math
from statistics import mean

from app.core.pacing import format_pace

VERSION = 1
MI = 1609.34


def segment(reps=1, *, meters=None, seconds=None, fast=None, slow=None, recovery_seconds=None, recovery_meters=None, category=None):
    return {"reps": reps, "distance_meters": meters, "duration_seconds": seconds,
            "pace_range_sec_per_mile": {"fast": fast, "slow": slow} if fast else None,
            "recovery_seconds": recovery_seconds, "recovery_meters": recovery_meters, "category": category}


def prescription(category, fmt, segments, *, program=None, phase=None, level=None, note=None, source="template"):
    return {"schema_version": VERSION, "category": category, "format": fmt, "segments": segments,
            "program_key": program, "phase": phase, "level": level, "evidence_source": source,
            "confidence": "high" if source == "template" else "low", "matched_activity_ids": [], "note": note}


def render(data):
    """Display is a projection of the numeric prescription, never its input."""
    if data.get('format')=='run_walk':
        s=data['segments'][0]
        reps=s['reps'];run=s['duration_seconds']/60;walk=(s.get('recovery_seconds') or 0)/60
        warm=(data.get('warmup') or {}).get('duration_seconds',0)/60
        total=warm+reps*run+max(0,reps-1)*walk+(data.get('cooldown') or {}).get('duration_seconds',0)/60
        return f'{warm:g}min brisk walk, then {reps} x ({run:g}min easy run + {walk:g}min walk). About {total:g} minutes. Run slowly enough to talk; walk briskly.'
    pieces = []
    for s in data['segments']:
        reps = s['reps']
        meters, seconds = s.get('distance_meters'), s.get('duration_seconds')
        if seconds:
            length = f"{seconds / 60:g}min" if seconds % 60 == 0 else f"{seconds:g}sec"
        elif meters:
            length = f"{meters / MI:g}mi" if abs(meters / MI - round(meters / MI, 1)) < 0.0001 else f"{meters:g}m"
        else:
            continue
        label = f"{reps}x{length}" if reps > 1 else length
        pace = s.get('pace_range_sec_per_mile')
        if s.get('effort'):
            label += f" at {s['effort']}"
        if pace:
            rng = format_pace(pace['fast'])
            if pace['slow'] != pace['fast']:
                rng += f"-{format_pace(pace['slow'])}"
            if meters and reps > 1 and abs(meters - MI) > 1:  # a 1mi rep's time IS its pace
                times = format_pace(round(pace['fast'] * meters / MI))
                if pace['slow'] != pace['fast']:
                    times += f"-{format_pace(round(pace['slow'] * meters / MI))}"
                label += f" in {times} ({rng}/mi)"
            else:
                label += f" at {rng}/mi"
        if s.get('recovery_seconds'):
            rest = int(s['recovery_seconds'])
            label += f" with {rest // 60}min jog rest" if rest % 60 == 0 else f" with {rest // 60}:{rest % 60:02d} jog rest"
        elif s.get('recovery_meters'):
            label += f" with {s['recovery_meters']:g}m jog rest"
        pieces.append(label + '.')
    text = ' Then '.join(pieces)
    # The effort note is guidance, not another step of the workout.
    if data.get('note'):
        text = f"{text} {data['note']}" if text else data['note']
    return text


def long_run_prescription(parts, note, easy_pace=None):
    """A structured long run as numbers, so its hard part can be verified like a workout.

    ``parts`` run in order: ("easy", miles) or (category, miles, pace_sec_per_mile | None),
    e.g. [("easy", 10), ("race_pace", 10, 410)]. Leading/trailing easy miles are the
    warmup/cooldown; easy miles between two hard parts are the recovery between them.
    A pace of None means effort-based (e.g. ultra race effort): distance is still checked.
    ``easy_pace`` lets plain Garmin auto-laps be read (the hard laps stand out from it).
    """
    parts = list(parts)
    warmup = parts.pop(0)[1] if parts and parts[0][0] == "easy" else 0
    cooldown = parts.pop()[1] if parts and parts[-1][0] == "easy" else 0
    segments = []
    for part in parts:
        if part[0] == "easy":
            if segments:
                segments[-1]["recovery_meters"] = round(part[1] * MI, 2)
            continue
        category, miles, pace = part
        last = segments[-1] if segments else None
        if (last and last["category"] == category and last["distance_meters"] == round(miles * MI, 2)
                and last.get("recovery_meters")):
            last["reps"] += 1  # repeated blocks (3x3mi at MP with float) are one segment
            continue
        segments.append(segment(meters=round(miles * MI, 2), fast=pace - 5 if pace else None, slow=pace + 5 if pace else None,
                                category=category))
    data = prescription("long_run", "continuous" if len(segments) == 1 and segments[0]["reps"] == 1 else "distance_intervals",
                        segments, note=note)
    data.update(warmup=segment(meters=round(warmup * MI, 2)) if warmup else None,
                cooldown=segment(meters=round(cooldown * MI, 2)) if cooldown else None,
                easy_pace_sec_per_mile=easy_pace)
    return data


def race_pace_miles(day):
    """Miles at race pace in a structured long run (0 for anything else)."""
    data = loads(day.get('prescription')) if day.get('type') == 'long_run' else None
    return round(sum(s.get('reps', 1) * (s.get('distance_meters') or 0) for s in (data or {}).get('segments') or []
                     if s.get('category') == 'race_pace') / MI, 1)


def day_prescription(day):
    """New non-ladder days retain their effort/fueling guidance as an authored note."""
    existing=loads(day.get('prescription'))
    if existing and (day['type'] in ('workout', 'long_run') or existing.get('format')=='run_walk'):
        return existing
    return prescription(day['type'], 'continuous', [segment(meters=round(day.get('distance_miles', 0) * MI, 2))] if day.get('distance_miles') else [],
                        note=day.get('description'), source='effort_guidance')


def loads(raw):
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, dict) and data.get('schema_version') == VERSION else None
    except (ValueError, TypeError):
        return None


def execution_from_activities(activities, prescribed):
    """Match labeled Garmin work to every segment. Unlabeled laps stay uncertain.

    Matching tolerances (8% distance, 10% duration) follow existing lap detection
    defaults. They accommodate GPS/lap-button noise, not substitute workouts.
    """
    result = {"schema_version": VERSION, "category": prescribed['category'], "format": prescribed['format'],
              "evidence_source": "none", "confidence": "low", "matched_activity_ids": [a.id for a in activities],
              "segments": [], "completion": None, "rep_paces_sec_per_mile": [], "target_paces_sec_per_mile": []}
    candidates = []
    from app.services.lap_analyzer import _find_work_laps
    for activity in activities:
        try:
            laps = json.loads(activity.splits or '[]')
        except (ValueError, TypeError):
            laps = []
        if not isinstance(laps, list):
            continue
        work = [lap for lap in laps if isinstance(lap, dict) and str(lap.get('intensity', '')).upper() in ('ACTIVE', 'INTERVAL')]
        # Garmin sometimes calls every auto-lap INTERVAL. Require explicit non-work labels.
        labeled = any(isinstance(lap, dict) and str(lap.get('intensity', '')).upper() in ('WARMUP', 'COOLDOWN', 'RECOVERY', 'REST') for lap in laps)
        valid = [lap for lap in work if all(isinstance(lap.get(k), (int, float)) and math.isfinite(lap[k]) and lap[k] > 0 for k in ('distance_m', 'duration_s'))]
        if labeled and valid:
            indices = [i for i, lap in enumerate(laps) if lap in valid]
            continuous = all(b == a + 1 for a, b in zip(indices, indices[1:]))
            if prescribed['format'] == 'continuous' and not continuous:
                result['evidence_source'] = 'interrupted_continuous_work'
                return result
            candidates.append((valid, "garmin_labeled_laps", "high", activity.id))
        elif prescribed.get('easy_pace_sec_per_mile') and all(isinstance(lap, dict) for lap in laps):
            # Existing deterministic lap detector uses the athlete's easy reference,
            # not the run average. A guessed work set still must match every rep.
            inferred = [laps[i] for i in _find_work_laps(laps, prescribed['easy_pace_sec_per_mile'])]
            if inferred and all(all(isinstance(lap.get(k), (int, float)) and math.isfinite(lap[k]) and lap[k] > 0 for k in ('distance_m', 'duration_s')) for lap in inferred):
                indices = [i for i, lap in enumerate(laps) if lap in inferred]
                if prescribed['format'] == 'continuous' and not all(b == a + 1 for a, b in zip(indices, indices[1:])):
                    result['evidence_source'] = 'interrupted_continuous_work'
                    return result
                candidates.append((inferred, "garmin_inferred_work_laps", "medium", activity.id))
    if len(candidates) != 1:
        return result
    work, source, confidence, activity_id = candidates[0]
    result["matched_activity_ids"] = [activity_id]
    result['work_lap_paces_sec_per_mile'] = [lap['duration_s'] * MI / lap['distance_m'] for lap in work]
    if prescribed['format'] == 'continuous' and len(prescribed['segments']) == 1:
        work = [{'distance_m': sum(lap['distance_m'] for lap in work), 'duration_s': sum(lap['duration_s'] for lap in work)}]
    result['evidence_source'], result['confidence'] = source, confidence
    expected = sum(s['reps'] for s in prescribed['segments'])
    index = 0
    matched = 0
    for spec in prescribed['segments']:
        for _ in range(spec['reps']):
            if index >= len(work):
                break
            lap = work[index]
            index += 1
            meters, seconds = spec.get('distance_meters'), spec.get('duration_seconds')
            fits = (not meters or abs(lap['distance_m'] - meters) / meters <= .08) and (not seconds or abs(lap['duration_s'] - seconds) / seconds <= .10)
            pace = lap['duration_s'] * MI / lap['distance_m']
            target = spec.get('pace_range_sec_per_mile')
            result['segments'].append({**segment(meters=lap['distance_m'], seconds=lap['duration_s'], fast=pace, slow=pace), 'matched': fits})
            if fits:
                matched += 1
                result['rep_paces_sec_per_mile'].append(pace)
                result['target_paces_sec_per_mile'].append(mean(target.values()) if target else None)
    result['completion'] = matched / expected if expected else None
    # Extra work is not the prescribed session and cannot prove controlled execution.
    if index < len(work):
        result['confidence'] = 'low'
    return result


def demanding_long_run(row):
    """A long run with prescribed quality cannot be verified by distance alone."""
    kind = row.get('type') if isinstance(row, dict) else row.type
    if kind != 'long_run':
        return False
    value = lambda key: row.get(key) if isinstance(row, dict) else getattr(row, key, None)
    data = loads(value('prescription')) or {}
    if any(s.get('category') in {'threshold', 'intervals', 'race_pace', 'steady', 'race_effort'} for s in data.get('segments', [])):
        return True
    title = (value('title') or '').lower()
    return any(term in title for term in ('mp ', 'marathon pace', 'marathon-pace', 'race-effort', 'steady', 'sandwich', 'progressive', 'progression'))
