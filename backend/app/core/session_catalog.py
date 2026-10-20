"""Workout catalog for athlete-initiated replacements.

The replace menu offers THREE sessions of a similar, experience-appropriate dose
in DIFFERENT shapes (time reps, distance reps, continuous, ladders, hills), so the
athlete chooses how to train, not whether to do a token 2x3min.

Sources for the session shapes (coaching literature, not controlled trials):
- Jack Daniels, *Daniels' Running Formula* (3rd ed.): cruise intervals and tempo
  runs at T pace with short recoveries; I-pace reps of 2-5 minutes. His volume
  guidance caps one session's T work near 10% of weekly mileage and I work near
  8% — the only numeric volume rule used below.
- Pete Pfitzinger & Scott Douglas, *Advanced Marathoning*: LT intervals and tempo
  runs of 20-40 minutes for experienced marathoners; VO2 reps of 600m-1600m.
- Greg McMillan training-plan guide: hill repeats and fartlek as strength/speed
  work, ladders as rhythm variety.
- docs/research/the-long-game-coaching-dossier.md ch. 4-5 and 17: Jake's
  reported 3x2mi / 4x1.5mi threshold and 6x800 / 5x1200 / 4x1mi sessions, and a
  25-minute (5x5min) threshold restart for an advanced athlete.

Experience floors and ceilings are Stride coaching heuristics chosen so a trained
runner never sees a beginner dose; they are not validated safety thresholds.
"""
import math
from dataclasses import dataclass, field

from app.core.workout_data import MI, prescription, render, segment

MAX_OPTIONS = 3


@dataclass(frozen=True)
class Rep:
    reps: int
    seconds: int | None = None
    meters: float | None = None
    recovery_seconds: int = 0


@dataclass(frozen=True)
class Template:
    key: str
    category: str          # threshold | intervals | hills
    family: str            # shape; the menu shows at most one per family
    name: str
    work: tuple[Rep, ...]
    pace_key: str | None   # None = effort-based (hills)
    purpose: str
    cue: str
    terrain: frozenset = field(default_factory=frozenset)  # empty = any terrain

    @property
    def is_time_based(self):
        return all(r.seconds for r in self.work)

    def work_minutes(self, pace_sec_per_mile):
        return sum(r.reps * (r.seconds or r.meters / MI * pace_sec_per_mile) for r in self.work) / 60


def _t(key, family, name, work, purpose, cue, pace_key='broken_threshold_pace'):
    return Template(key, 'threshold', family, name, tuple(work), pace_key, purpose, cue)


def _i(key, family, name, work, purpose, cue):
    return Template(key, 'intervals', family, name, tuple(work), 'interval_pace', purpose, cue)


THRESHOLD_CRUISE = 'Cruise intervals: short jog rests let you stack more threshold time than one continuous run.'
THRESHOLD_MILE = 'Measured threshold reps: a clear pace target per rep and easy to compare week to week.'
TEMPO = 'Continuous tempo: holding one steady, comfortably hard rhythm without breaks.'
LADDER_T = 'Descending threshold ladder: shorter reps as fatigue builds keep the pace controlled.'
T_CUE = 'Comfortably hard and controlled; you could keep going when it ends.'
TEMPO_CUE = 'Settle in during the first mile; stay smooth and even, never racing.'

VO2_SHORT = 'Short fast reps: quick turnover and VO2 stimulus with frequent recoveries.'
VO2_MIDDLE = 'Classic 800m-1K reps: the backbone of 5K/10K aerobic power.'
VO2_LONG = 'Long reps: sustained hard running that builds 5K/10K race toughness.'
VO2_TIME = 'Time-based VO2 reps: same stimulus without a track; run by effort and watch.'
PYRAMID = 'Pyramid: changing rep lengths practice pace judgment while the total stays a full session.'
HILLS = 'Hill repeats: running strength and power with less impact than flat speed.'
I_CUE = 'Hard but even; the last rep should match the first.'
HILL_CUE = 'Strong, tall uphill effort near 5K effort; jog or walk down fully recovered.'

CATALOG: tuple[Template, ...] = (
    # Threshold: cruise intervals by time
    _t('t_3x5', 'cruise_time', '3x5min Cruise Intervals', [Rep(3, 300, None, 60)], THRESHOLD_CRUISE, T_CUE),
    _t('t_4x4', 'cruise_time', '4x4min Cruise Intervals', [Rep(4, 240, None, 60)], THRESHOLD_CRUISE, T_CUE),
    _t('t_3x6', 'cruise_time', '3x6min Cruise Intervals', [Rep(3, 360, None, 60)], THRESHOLD_CRUISE, T_CUE),
    _t('t_5x5', 'cruise_time', '5x5min Cruise Intervals', [Rep(5, 300, None, 60)], THRESHOLD_CRUISE, T_CUE),
    _t('t_3x8', 'cruise_time', '3x8min Cruise Intervals', [Rep(3, 480, None, 90)], THRESHOLD_CRUISE, T_CUE),
    _t('t_3x10', 'cruise_time', '3x10min Cruise Intervals', [Rep(3, 600, None, 120)], THRESHOLD_CRUISE, T_CUE),
    _t('t_4x8', 'cruise_time', '4x8min Cruise Intervals', [Rep(4, 480, None, 90)], THRESHOLD_CRUISE, T_CUE),
    _t('t_3x12', 'cruise_time', '3x12min Cruise Intervals', [Rep(3, 720, None, 120)], THRESHOLD_CRUISE, T_CUE),
    _t('t_4x10', 'cruise_time', '4x10min Cruise Intervals', [Rep(4, 600, None, 120)], THRESHOLD_CRUISE, T_CUE),
    # Threshold: measured reps by distance
    _t('t_3x1k', 'cruise_distance', '3x1K Threshold', [Rep(3, None, 1000, 60)], THRESHOLD_MILE, T_CUE),
    _t('t_3x1mi', 'cruise_distance', '3x1mi Threshold', [Rep(3, None, MI, 60)], THRESHOLD_MILE, T_CUE),
    _t('t_4x1mi', 'cruise_distance', '4x1mi Threshold', [Rep(4, None, MI, 60)], THRESHOLD_MILE, T_CUE),
    _t('t_3x1.5mi', 'cruise_distance', '3x1.5mi Threshold', [Rep(3, None, 1.5 * MI, 90)], THRESHOLD_MILE, T_CUE),
    _t('t_5x1mi', 'cruise_distance', '5x1mi Threshold', [Rep(5, None, MI, 60)], THRESHOLD_MILE, T_CUE),
    _t('t_3x2mi', 'cruise_distance', '3x2mi Threshold', [Rep(3, None, 2 * MI, 120)], THRESHOLD_MILE, T_CUE),
    _t('t_4x1.5mi', 'cruise_distance', '4x1.5mi Threshold', [Rep(4, None, 1.5 * MI, 90)], THRESHOLD_MILE, T_CUE),
    # Continuous tempo (tempo_pace: the deliberate slower continuous anchor)
    _t('tempo_15', 'continuous', '15min Tempo Run', [Rep(1, 900)], TEMPO, TEMPO_CUE, 'tempo_pace'),
    _t('tempo_2mi', 'continuous', '2mi Tempo Run', [Rep(1, None, 2 * MI)], TEMPO, TEMPO_CUE, 'tempo_pace'),
    _t('tempo_20', 'continuous', '20min Tempo Run', [Rep(1, 1200)], TEMPO, TEMPO_CUE, 'tempo_pace'),
    _t('tempo_3mi', 'continuous', '3mi Tempo Run', [Rep(1, None, 3 * MI)], TEMPO, TEMPO_CUE, 'tempo_pace'),
    _t('tempo_25', 'continuous', '25min Tempo Run', [Rep(1, 1500)], TEMPO, TEMPO_CUE, 'tempo_pace'),
    _t('tempo_4mi', 'continuous', '4mi Tempo Run', [Rep(1, None, 4 * MI)], TEMPO, TEMPO_CUE, 'tempo_pace'),
    _t('tempo_30', 'continuous', '30min Tempo Run', [Rep(1, 1800)], TEMPO, TEMPO_CUE, 'tempo_pace'),
    _t('tempo_5mi', 'continuous', '5mi Tempo Run', [Rep(1, None, 5 * MI)], TEMPO, TEMPO_CUE, 'tempo_pace'),
    # Threshold ladders
    _t('t_ladder_6_4_2', 'ladder', '6-4-2min Threshold Ladder', [Rep(1, 360, None, 60), Rep(1, 240, None, 60), Rep(1, 120)], LADDER_T, T_CUE),
    _t('t_ladder_8_6_4', 'ladder', '8-6-4min Threshold Ladder', [Rep(1, 480, None, 90), Rep(1, 360, None, 60), Rep(1, 240)], LADDER_T, T_CUE),
    _t('t_ladder_10_8_6', 'ladder', '10-8-6min Threshold Ladder', [Rep(1, 600, None, 120), Rep(1, 480, None, 90), Rep(1, 360)], LADDER_T, T_CUE),
    _t('t_ladder_12_10_8', 'ladder', '12-10-8min Threshold Ladder', [Rep(1, 720, None, 120), Rep(1, 600, None, 90), Rep(1, 480)], LADDER_T, T_CUE),
    _t('t_ladder_15_10_5', 'ladder', '15-10-5min Threshold Ladder', [Rep(1, 900, None, 120), Rep(1, 600, None, 90), Rep(1, 300)], LADDER_T, T_CUE),
    # Intervals: short reps
    _i('i_6x400', 'short_reps', '6x400m Intervals', [Rep(6, None, 400, 75)], VO2_SHORT, I_CUE),
    _i('i_8x400', 'short_reps', '8x400m Intervals', [Rep(8, None, 400, 75)], VO2_SHORT, I_CUE),
    _i('i_6x600', 'short_reps', '6x600m Intervals', [Rep(6, None, 600, 90)], VO2_SHORT, I_CUE),
    _i('i_10x400', 'short_reps', '10x400m Intervals', [Rep(10, None, 400, 75)], VO2_SHORT, I_CUE),
    _i('i_12x400', 'short_reps', '12x400m Intervals', [Rep(12, None, 400, 60)], VO2_SHORT, I_CUE),
    _i('i_8x600', 'short_reps', '8x600m Intervals', [Rep(8, None, 600, 90)], VO2_SHORT, I_CUE),
    # Intervals: 800m-1K
    _i('i_3x1k', 'middle_reps', '3x1K Intervals', [Rep(3, None, 1000, 150)], VO2_MIDDLE, I_CUE),
    _i('i_5x800', 'middle_reps', '5x800m Intervals', [Rep(5, None, 800, 120)], VO2_MIDDLE, I_CUE),
    _i('i_4x1k', 'middle_reps', '4x1K Intervals', [Rep(4, None, 1000, 150)], VO2_MIDDLE, I_CUE),
    _i('i_6x800', 'middle_reps', '6x800m Intervals', [Rep(6, None, 800, 120)], VO2_MIDDLE, I_CUE),
    _i('i_5x1k', 'middle_reps', '5x1K Intervals', [Rep(5, None, 1000, 150)], VO2_MIDDLE, I_CUE),
    _i('i_8x800', 'middle_reps', '8x800m Intervals', [Rep(8, None, 800, 120)], VO2_MIDDLE, I_CUE),
    _i('i_6x1k', 'middle_reps', '6x1K Intervals', [Rep(6, None, 1000, 150)], VO2_MIDDLE, I_CUE),
    # Intervals: 1200m-mile
    _i('i_3x1200', 'long_reps', '3x1200m Intervals', [Rep(3, None, 1200, 180)], VO2_LONG, I_CUE),
    _i('i_3x1mi', 'long_reps', '3x1mi Intervals', [Rep(3, None, MI, 180)], VO2_LONG, I_CUE),
    _i('i_4x1200', 'long_reps', '4x1200m Intervals', [Rep(4, None, 1200, 180)], VO2_LONG, I_CUE),
    _i('i_5x1200', 'long_reps', '5x1200m Intervals', [Rep(5, None, 1200, 180)], VO2_LONG, I_CUE),
    _i('i_4x1mi', 'long_reps', '4x1mi Intervals', [Rep(4, None, MI, 180)], VO2_LONG, I_CUE),
    # Intervals: time-based
    _i('i_8x1', 'time_reps', '8x1min On / 1min Off', [Rep(8, 60, None, 60)], VO2_TIME, I_CUE),
    _i('i_5x2', 'time_reps', '5x2min Hard', [Rep(5, 120, None, 60)], VO2_TIME, I_CUE),
    _i('i_6x2', 'time_reps', '6x2min Hard', [Rep(6, 120, None, 60)], VO2_TIME, I_CUE),
    _i('i_5x3', 'time_reps', '5x3min Hard', [Rep(5, 180, None, 120)], VO2_TIME, I_CUE),
    _i('i_4x4', 'time_reps', '4x4min Hard', [Rep(4, 240, None, 180)], VO2_TIME, I_CUE),
    _i('i_6x3', 'time_reps', '6x3min Hard', [Rep(6, 180, None, 120)], VO2_TIME, I_CUE),
    _i('i_5x4', 'time_reps', '5x4min Hard', [Rep(5, 240, None, 180)], VO2_TIME, I_CUE),
    # Intervals: pyramids
    _i('i_pyr_short', 'pyramid', '400-800-1200-800-400m Pyramid',
       [Rep(1, None, 400, 90), Rep(1, None, 800, 120), Rep(1, None, 1200, 150), Rep(1, None, 800, 120), Rep(1, None, 400)], PYRAMID, I_CUE),
    _i('i_ladder_down', 'pyramid', '1200-1000-800-600-400m Ladder',
       [Rep(1, None, 1200, 150), Rep(1, None, 1000, 120), Rep(1, None, 800, 120), Rep(1, None, 600, 90), Rep(1, None, 400)], PYRAMID, I_CUE),
    _i('i_pyr_long', 'pyramid', '800-1200-1600-1200-800m Pyramid',
       [Rep(1, None, 800, 120), Rep(1, None, 1200, 150), Rep(1, None, 1600, 180), Rep(1, None, 1200, 150), Rep(1, None, 800)], PYRAMID, I_CUE),
) + tuple(
    # Hills (trail/mountain goals): effort-based, own category so lap paces on a
    # hill never calibrate flat interval pace.
    Template(key, 'hills', 'hills', name, (Rep(reps, seconds, None, int(seconds * 1.5)),), None, HILLS, HILL_CUE,
             frozenset({'trail', 'mountain'}))
    for key, name, reps, seconds in (
        ('h_8x60', '8x60sec Hill Repeats', 8, 60), ('h_8x90', '8x90sec Hill Repeats', 8, 90),
        ('h_6x2', '6x2min Hill Repeats', 6, 120), ('h_10x90', '10x90sec Hill Repeats', 10, 90),
        ('h_6x3', '6x3min Hill Repeats', 6, 180),
    )
)

# Minutes of hard work per session (excluding warmup, recovery, cooldown).
EXPERIENCE_FLOOR = {
    'threshold': {'beginner': 10, 'intermediate': 15, 'advanced': 20, 'expert': 24},
    'intervals': {'beginner': 8, 'intermediate': 12, 'advanced': 15, 'expert': 18},
}
EXPERIENCE_CEILING = {
    'threshold': {'beginner': 16, 'intermediate': 30, 'advanced': 40, 'expert': 50},
    'intervals': {'beginner': 12, 'intermediate': 18, 'advanced': 24, 'expert': 30},
}
# Daniels' per-session volume guidance (share of weekly mileage).
DANIELS_SHARE = {'threshold': 0.10, 'intervals': 0.08}
# Families allowed in phases where the menu should stay short and sharp.
SHARP_INTERVAL_FAMILIES = {'short_reps', 'time_reps', 'hills'}


@dataclass(frozen=True)
class DoseBand:
    low: float
    high: float
    target: float

    def contains(self, minutes):
        return self.low - 0.5 <= minutes <= self.high + 0.5


def dose_band(category, experience, weekly_miles, pace, phase='general', deload=False):
    """Minutes of quality work that fit this athlete this week.

    The floor keeps a trained runner out of token doses; Daniels' share of weekly
    volume (converted to minutes at the work pace) scales the top of the band.
    Low current volume pulls the floor down so a comeback is not overloaded.
    Taper and deload keep intensity but cut the dose (Pfitzinger/Daniels taper
    practice); base keeps threshold whole and keeps intervals short.
    """
    level = experience if experience in EXPERIENCE_FLOOR['threshold'] else 'beginner'
    floor = EXPERIENCE_FLOOR[category][level]
    ceiling = EXPERIENCE_CEILING[category][level]
    by_volume = DANIELS_SHARE[category] * max(weekly_miles, 0) * pace / 60
    floor = min(floor, max(by_volume, EXPERIENCE_FLOOR[category]['beginner']))
    high = min(ceiling, max(by_volume, floor + 5))
    if phase == 'taper' or deload:
        high = max(8, floor * 0.75)
        floor = high * 0.6
    elif phase == 'base' and category == 'intervals':
        high = floor
        floor = floor * 0.7
    return DoseBand(round(floor, 1), round(high, 1), round(floor + 0.6 * (high - floor), 1))


def ranked_templates(category, band, paces, *, phase='general', terrain=None, prefer_time=False, week_index=0):
    """Candidates ordered for the menu: one family at a time, closest dose first.

    The caller validates each against the week's budget and spacing and keeps the
    first passing template per family, up to MAX_OPTIONS. Family order puts the
    athlete's preferred format first and then rotates by calendar week so the menu
    has variety from one week to the next without randomness.
    """
    pool = []
    for template in CATALOG:
        if template.terrain and terrain not in template.terrain:
            continue
        if category == 'threshold' and template.category != 'threshold':
            continue
        if category == 'intervals':
            if template.category not in {'intervals', 'hills'}:
                continue
            if phase in {'base', 'taper'} and template.family not in SHARP_INTERVAL_FAMILIES:
                continue
        pace = paces.get(template.pace_key) if template.pace_key else paces.get('interval_pace', 420) * 1.15
        if not pace:
            continue
        minutes = template.work_minutes(pace)
        if band.contains(minutes):
            pool.append((template, minutes))
    families = sorted({t.family for t, _ in pool})
    if families:
        shift = week_index % len(families)
        families = families[shift:] + families[:shift]
    # Trail athletes get hills first; everyone else gets their preferred format first.
    def family_rank(family):
        has_preferred = any(t.is_time_based == prefer_time for t, _ in pool if t.family == family)
        return (family != 'hills', not has_preferred)
    families.sort(key=family_rank)
    ordered = []
    for family in families:
        members = sorted((p for p in pool if p[0].family == family),
                         key=lambda p: (p[0].is_time_based != prefer_time, abs(p[1] - band.target), p[1]))
        ordered.extend(t for t, _ in members)
    return ordered


def build_workout(template, paces, *, program=None, phase=None, bookend_miles=1.5):
    """Numeric prescription first; title, text and mileage are projections of it."""
    easy = paces['long_run_pace']
    pace = paces.get(template.pace_key) if template.pace_key else None
    fast = paces.get('interval_pace_fast', pace) if template.pace_key == 'interval_pace' else pace
    segments = [segment(r.reps, seconds=r.seconds, meters=r.meters, fast=fast, slow=pace,
                        recovery_seconds=r.recovery_seconds or None) for r in template.work]
    fmt = ('continuous' if template.family == 'continuous'
           else 'time_intervals' if template.is_time_based else 'track_intervals')
    data = prescription(template.category, fmt, segments, program=program, phase=phase,
                        note=template.cue + (' Jog down the hill as recovery.' if template.category == 'hills' else ''))
    data.update(progression_eligible=False, easy_pace_sec_per_mile=easy, template_id=template.key,
                stimulus=template.family)
    data['warmup'] = segment(meters=bookend_miles * MI)
    data['cooldown'] = segment(meters=bookend_miles * MI)
    work_pace = pace or easy * 0.85  # hills: effort-based; estimate for mileage only
    work_miles = sum(r.reps * (r.meters / MI if r.meters else r.seconds / work_pace) for r in template.work)
    recovery_miles = sum((r.reps - 1 if len(template.work) == 1 else r.reps) * r.recovery_seconds / easy
                         for r in template.work)
    total = 2 * bookend_miles + work_miles + recovery_miles
    data['total_distance_meters'] = round(total * MI, 2)
    bookend = f'{bookend_miles:g}mi easy'
    return {'name': template.name, 'structure': render(data), 'prescription': data, 'total_miles': math.ceil(total * 2) / 2,
            'warmup': bookend, 'cooldown': bookend, 'purpose': template.purpose}
