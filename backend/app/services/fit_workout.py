"""Planned workout -> Garmin FIT workout file (no Garmin approval needed).

The athlete copies the file to the watch's GARMIN/NewFiles folder over USB and it
appears under Training > Workouts. The step list built here is the same one the
Training API push will send once Business access exists; only the encoding differs.

Encoding follows the FIT protocol (file_id, workout, workout_step messages). Units:
time steps in ms, distance steps in cm, speed targets in mm/s.
"""
import re
import struct
import time

from app.core.pacing import format_pace
from app.core.workout_data import MI, day_prescription, loads

# FIT enums (Profile.xlsx)
DURATION_TIME, DURATION_DISTANCE, DURATION_OPEN, DURATION_REPEAT = 0, 1, 5, 6
TARGET_SPEED, TARGET_OPEN = 0, 2
ACTIVE, REST, WARMUP, COOLDOWN, RECOVERY = 0, 1, 2, 3, 4
SPORT_RUNNING = 1
FIT_EPOCH = 631065600  # 1989-12-31T00:00:00Z
# Narrower pace ranges make the watch beep at every GPS wobble.
MIN_RANGE_SEC_PER_MILE = 10
NAME_BYTES, NOTES_BYTES = 24, 64


def _step(name, duration_type, duration_value=None, *, intensity=ACTIVE, pace=None, notes=None):
    return {"name": name, "duration_type": duration_type, "duration_value": duration_value,
            "intensity": intensity, "pace": pace, "notes": notes}


def _length(meters=None, seconds=None):
    if seconds:
        return (f"{seconds / 60:g}min" if seconds % 60 == 0 else f"{seconds:g}s"), DURATION_TIME, round(seconds * 1000)
    if meters:
        miles = meters / MI
        label = f"{miles:g}mi" if abs(miles - round(miles, 2)) < 0.001 and miles >= 1 else f"{meters:g}m"
        return label, DURATION_DISTANCE, round(meters * 100)
    return None


def _bookend(spec, text, intensity, name):
    """Warmup/cooldown from the numeric prescription, else the display text, else lap button."""
    if isinstance(spec, dict):
        length = _length(spec.get("distance_meters"), spec.get("duration_seconds"))
        if length:
            return _step(name, length[1], length[2], intensity=intensity, notes=text)
    if text:
        m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(mi|km|min)\b", text)
        if m:
            value, unit = float(m.group(1)), m.group(2)
            length = _length(seconds=value * 60) if unit == "min" else _length(meters=value * (MI if unit == "mi" else 1000))
            return _step(name, length[1], length[2], intensity=intensity, notes=text)
        return _step(name, DURATION_OPEN, intensity=intensity, notes=f"{text}. Press lap when done.")
    return None


def _pace_target(pace, easy):
    if not pace or easy:
        return None
    fast, slow = pace["fast"], pace["slow"]
    if slow - fast < MIN_RANGE_SEC_PER_MILE:
        mid = (fast + slow) / 2
        fast, slow = mid - MIN_RANGE_SEC_PER_MILE / 2, mid + MIN_RANGE_SEC_PER_MILE / 2
    return {"fast": fast, "slow": slow}


def _pace_note(pace):
    if not pace:
        return None
    text = format_pace(pace["fast"])
    if pace["slow"] != pace["fast"]:
        text += f"-{format_pace(pace['slow'])}"
    return f"{text}/mi"


def build_steps(row):
    """Ordered workout steps for a PlannedWorkout (or the dict shape plans use)."""
    get = (lambda k: row.get(k)) if isinstance(row, dict) else (lambda k: getattr(row, k, None))
    if get("type") in ("rest", None) or not (get("distance_miles") or get("prescription")):
        raise ValueError("Rest day: there is no workout to send to the watch.")
    if get("type") == "workout" and not loads(get("prescription")):
        # Legacy prose-only sessions would export as one long run, misstating the reps.
        raise ValueError("This older workout has no step structure to send to the watch.")
    data = day_prescription({"type": get("type"), "distance_miles": get("distance_miles") or 0,
                             "prescription": get("prescription"), "description": get("description")})
    run_walk = data.get("format") == "run_walk"
    easy_day = get("type") in ("easy", "recovery") or data.get("category") in ("easy", "recovery")
    steps = []
    warm = _bookend(data.get("warmup"), get("warmup"), WARMUP, "Warm up")
    if warm:
        steps.append(warm)
    for seg in data.get("segments") or []:
        length = _length(seg.get("distance_meters"), seg.get("duration_seconds"))
        if not length:
            continue
        label, duration_type, value = length
        # Easy running and plain long-run miles stay untargeted: "conversational", not a pace alarm.
        easy = easy_day or (get("type") == "long_run" and not seg.get("category"))
        pace = _pace_target(seg.get("pace_range_sec_per_mile"), easy)
        note = seg.get("effort") or _pace_note(seg.get("pace_range_sec_per_mile"))
        work = _step("Run" if run_walk else label, duration_type, value, pace=pace, notes=note)
        recovery = None
        rest_len = _length(seg.get("recovery_meters"), seg.get("recovery_seconds"))
        if rest_len:
            recovery = _step("Walk" if run_walk else "Jog", rest_len[1], rest_len[2],
                             intensity=REST if run_walk else RECOVERY)
        reps = int(seg.get("reps") or 1)
        if reps > 1:
            first = len(steps)
            steps.append(work)
            if recovery:
                steps.append(recovery)
            steps.append({"repeat_from": first, "reps": reps})
        else:
            steps.append(work)
            if recovery:
                steps.append(recovery)
    cool = _bookend(data.get("cooldown"), get("cooldown"), COOLDOWN, "Cool down")
    if cool:
        steps.append(cool)
    if not any("repeat_from" not in s for s in steps):
        raise ValueError("This session has no structured steps to send to the watch.")
    return steps


# --- FIT encoding -----------------------------------------------------------------

_CRC_TABLE = (0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
              0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400)


def _crc(data, crc=0):
    for byte in data:
        for nibble in (byte & 0x0F, byte >> 4):
            tmp = _CRC_TABLE[crc & 0x0F]
            crc = (crc >> 4) & 0x0FFF
            crc = crc ^ tmp ^ _CRC_TABLE[nibble]
    return crc


ENUM, UINT16, UINT32, UINT32Z, STRING = 0x00, 0x84, 0x86, 0x8C, 0x07
_FORMAT = {ENUM: "B", UINT16: "H", UINT32: "I", UINT32Z: "I"}
_INVALID = {ENUM: 0xFF, UINT16: 0xFFFF, UINT32: 0xFFFFFFFF, UINT32Z: 0}


def _string(value, size):
    raw = (value or "").encode("utf-8")[:size - 1]
    while raw:  # never split a multi-byte character
        try:
            raw.decode("utf-8")
            break
        except UnicodeDecodeError:
            raw = raw[:-1]
    return raw.ljust(size, b"\0")


class _Writer:
    def __init__(self):
        self.body = bytearray()

    def define(self, local, global_num, fields):
        self.body += struct.pack("<BBBHB", 0x40 | local, 0, 0, global_num, len(fields))
        for num, base, size in fields:
            self.body += struct.pack("<BBB", num, size, base)

    def data(self, local, fields, values):
        self.body.append(local)
        for (num, base, size), value in zip(fields, values):
            if base == STRING:
                self.body += _string(value, size)
            else:
                self.body += struct.pack("<" + _FORMAT[base], _INVALID[base] if value is None else value)

    def file(self):
        header = struct.pack("<BBHI4s", 14, 0x10, 2132, len(self.body), b".FIT")
        header += struct.pack("<H", _crc(header))
        out = header + bytes(self.body)
        return out + struct.pack("<H", _crc(out))


FILE_ID = [(0, ENUM, 1), (1, UINT16, 2), (2, UINT16, 2), (3, UINT32Z, 4), (4, UINT32, 4)]
WORKOUT = [(4, ENUM, 1), (6, UINT16, 2), (8, STRING, NAME_BYTES)]
STEP = [(254, UINT16, 2), (0, STRING, NAME_BYTES), (1, ENUM, 1), (2, UINT32, 4), (3, ENUM, 1), (4, UINT32, 4),
        (5, UINT32, 4), (6, UINT32, 4), (7, ENUM, 1), (8, STRING, NOTES_BYTES)]


def encode(name, steps, *, created=None):
    created = int(created if created is not None else time.time())
    w = _Writer()
    w.define(0, 0, FILE_ID)
    # type=workout, manufacturer=development, serial is the creation time so re-exports stay distinct
    w.data(0, FILE_ID, [5, 255, 0, created & 0xFFFFFFFF or 1, created - FIT_EPOCH])
    w.define(1, 26, WORKOUT)
    w.data(1, WORKOUT, [SPORT_RUNNING, len(steps), name])
    w.define(2, 27, STEP)
    for index, s in enumerate(steps):
        if "repeat_from" in s:
            w.data(2, STEP, [index, None, DURATION_REPEAT, s["repeat_from"], None, s["reps"], None, None, None, None])
            continue
        pace = s["pace"]
        if pace:  # slower pace = lower speed bound
            low, high = round(MI / pace["slow"] * 1000), round(MI / pace["fast"] * 1000)
            target = [TARGET_SPEED, 0, low, high]
        else:
            target = [TARGET_OPEN, None, None, None]
        w.data(2, STEP, [index, s["name"], s["duration_type"], s["duration_value"], *target, s["intensity"], s["notes"]])
    return w.file()


def workout_fit(row, *, created=None):
    """(filename, bytes) for one planned day."""
    get = (lambda k: row.get(k)) if isinstance(row, dict) else (lambda k: getattr(row, k, None))
    steps = build_steps(row)
    day = str(get("date") or "")
    short = f"{day[5:7]}/{day[8:10]} " if len(day) == 10 else ""
    name = f"{short}{get('title') or 'Stride run'}"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", get("title") or "run").strip("-").lower()[:40] or "run"
    return f"stride-{day}-{slug}.fit", encode(name, steps, created=created)
