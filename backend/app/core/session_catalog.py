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

- Pfitzinger & Douglas, *Advanced Marathoning*: marathon-pace runs and medium-long
  runs as the marathon-specific sessions of build/peak; Daniels: goal-pace reps
  for 5K/10K peaks.
- Koop, *Training Essentials for Ultrarunning*: power-hiking steep climbs and
  downhill running as trainable ultra skills (vertical and eccentric durability).

Experience floors and ceilings are Stride coaching heuristics chosen so a trained
runner never sees a beginner dose; they are not validated safety thresholds.
Goal-pace templates (`goals` set) appear only for their goal and phases and step
toward goal pace from demonstrated pace (core/goal_pace.py).
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
    goals: frozenset = field(default_factory=frozenset)    # empty = every goal (generic shape)
    phases: frozenset = field(default_factory=frozenset)   # with goals: phases that open it
    dose: str | None = None       # dose-band key when it differs from category
    bookends: tuple | None = None  # (warmup, cooldown) easy miles, e.g. medium-long runs
    vert_m: int | None = None      # climbing target for vertical sessions

    @property
    def dose_key(self):
        return self.dose or self.category

    @property
    def specific(self):
        return bool(self.goals)

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
    _t('t_4x5', 'cruise_time', '4x5min Cruise Intervals', [Rep(4, 300, None, 60)], THRESHOLD_CRUISE, T_CUE),
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

# ── Goal-specific templates (peak/build specificity) ─────────────────────────
ULTRA_GOALS = frozenset({'50k', '50mi', '100k', '100mi'})
TRAIL = frozenset({'trail', 'mountain'})
GP_CUE = 'Goal-pace rhythm: relaxed, even and on target; faster than prescribed is not better.'
GOAL_5K = 'Goal-pace reps: rehearse 5K race rhythm so goal pace feels familiar on race day.'
GOAL_10K = 'Goal-pace reps: long, even reps at 10K rhythm build the specific endurance to hold it for 6.2 miles.'
MP_CUE = 'Marathon rhythm: smooth and patient, breathing controlled. Take a gel if it runs past 60 minutes.'
MP_BLOCK = 'Marathon-pace blocks: race rhythm in sizeable pieces, with short floats to keep the pace honest.'
MP_STEADY = 'Continuous marathon pace: locks in race rhythm and fueling the way race day demands.'
MLR = 'Medium-long run with a marathon-pace segment (Pfitzinger): midweek endurance plus race rhythm on tired legs.'
POWER_HIKE = 'Power-hike climbs: steep vertical at sustainable ultra effort, a skill you will use for hours on race day.'
HIKE_CUE = 'Hands on quads on the steepest grades, short quick steps, breathing controlled. Walk or jog down easy.'
DOWNHILL = 'Downhill durability: controlled fast descending builds the eccentric quad strength ultras demand.'
DOWNHILL_CUE = 'Climb at steady effort, then descend quick and light: short steps, eyes ahead, never braking hard.'
# Climb-rate heuristics for the vertical target (Stride estimates, not measured):
# ~700 m/h power-hiking a steep grade, ~500 m/h running a moderate climb.
HIKE_M_PER_HR, CLIMB_M_PER_HR = 700, 500


def _gp(key, family, name, goal, work, purpose):
    return Template(key, 'intervals', family, name, tuple(work), 'specific_pace', purpose, GP_CUE,
                    goals=frozenset({goal}), phases=frozenset({'peak'}), dose='race_pace')


def _mp(key, family, name, work, purpose, bookends=None):
    return Template(key, 'threshold', family, name, tuple(work), 'specific_pace', purpose, MP_CUE,
                    goals=frozenset({'marathon'}), phases=frozenset({'build', 'peak'}), dose='marathon_pace',
                    bookends=bookends)


def _vert(key, family, name, reps, seconds, recovery, climb_seconds, rate, purpose, cue, phases):
    return Template(key, 'hills', family, name, (Rep(reps, seconds, None, recovery),), None, purpose, cue,
                    terrain=TRAIL, goals=ULTRA_GOALS, phases=frozenset(phases), dose='vert',
                    vert_m=int(round(reps * climb_seconds / 3600 * rate, -1)))


SPECIFIC_CATALOG: tuple[Template, ...] = (
    # 5K peak: goal-pace reps
    _gp('gp5_5x1k', 'goal_pace_short', '5x1K at 5K Goal Pace', '5k', [Rep(5, None, 1000, 120)], GOAL_5K),
    _gp('gp5_6x1k', 'goal_pace_short', '6x1K at 5K Goal Pace', '5k', [Rep(6, None, 1000, 90)], GOAL_5K),
    _gp('gp5_8x800', 'goal_pace_short', '8x800m at 5K Goal Pace', '5k', [Rep(8, None, 800, 75)], GOAL_5K),
    _gp('gp5_3x1mi', 'goal_pace_mile', '3x1mi at 5K Goal Pace', '5k', [Rep(3, None, MI, 120)], GOAL_5K),
    _gp('gp5_4x1mi', 'goal_pace_mile', '4x1mi at 5K Goal Pace', '5k', [Rep(4, None, MI, 120)], GOAL_5K),
    _gp('gp5_3x2k', 'goal_pace_long', '3x2K at 5K Goal Pace', '5k', [Rep(3, None, 2000, 150)], GOAL_5K),
    _gp('gp5_2x3k', 'goal_pace_long', '2x3K at 5K Goal Pace', '5k', [Rep(2, None, 3000, 180)], GOAL_5K),
    # 10K peak: goal-pace reps
    _gp('gp10_6x1k', 'goal_pace_short', '6x1K at 10K Goal Pace', '10k', [Rep(6, None, 1000, 60)], GOAL_10K),
    _gp('gp10_8x1k', 'goal_pace_short', '8x1K at 10K Goal Pace', '10k', [Rep(8, None, 1000, 60)], GOAL_10K),
    _gp('gp10_4x1mi', 'goal_pace_mile', '4x1mi at 10K Goal Pace', '10k', [Rep(4, None, MI, 75)], GOAL_10K),
    _gp('gp10_5x1mi', 'goal_pace_mile', '5x1mi at 10K Goal Pace', '10k', [Rep(5, None, MI, 75)], GOAL_10K),
    _gp('gp10_3x2k', 'goal_pace_long', '3x2K at 10K Goal Pace', '10k', [Rep(3, None, 2000, 90)], GOAL_10K),
    _gp('gp10_4x2k', 'goal_pace_long', '4x2K at 10K Goal Pace', '10k', [Rep(4, None, 2000, 90)], GOAL_10K),
    _gp('gp10_3x3k', 'goal_pace_long', '3x3K at 10K Goal Pace', '10k', [Rep(3, None, 3000, 120)], GOAL_10K),
    # Marathon build/peak: MP blocks, continuous MP and medium-long runs
    _mp('mp_3x2mi', 'mp_block', '3x2mi at Marathon Pace', [Rep(3, None, 2 * MI, 120)], MP_BLOCK),
    _mp('mp_2x3mi', 'mp_block', '2x3mi at Marathon Pace', [Rep(2, None, 3 * MI, 180)], MP_BLOCK),
    _mp('mp_3x3mi', 'mp_block', '3x3mi at Marathon Pace', [Rep(3, None, 3 * MI, 180)], MP_BLOCK),
    _mp('mp_2x4mi', 'mp_block', '2x4mi at Marathon Pace', [Rep(2, None, 4 * MI, 180)], MP_BLOCK),
    _mp('mp_4mi', 'mp_continuous', '4mi at Marathon Pace', [Rep(1, None, 4 * MI)], MP_STEADY),
    _mp('mp_5mi', 'mp_continuous', '5mi at Marathon Pace', [Rep(1, None, 5 * MI)], MP_STEADY),
    _mp('mp_6mi', 'mp_continuous', '6mi at Marathon Pace', [Rep(1, None, 6 * MI)], MP_STEADY),
    _mp('mp_8mi', 'mp_continuous', '8mi at Marathon Pace', [Rep(1, None, 8 * MI)], MP_STEADY),
    _mp('mlr_10', 'medium_long', '10mi Medium-Long with 3mi at MP', [Rep(1, None, 3 * MI)], MLR, (6, 1)),
    _mp('mlr_12', 'medium_long', '12mi Medium-Long with 4mi at MP', [Rep(1, None, 4 * MI)], MLR, (7, 1)),
    _mp('mlr_14', 'medium_long', '14mi Medium-Long with 5mi at MP', [Rep(1, None, 5 * MI)], MLR, (8, 1)),
    _mp('mlr_15', 'medium_long', '15mi Medium-Long with 6mi at MP', [Rep(1, None, 6 * MI)], MLR, (8, 1)),
    # Trail ultras: power-hike vertical and downhill durability (effort-based)
    _vert('ph_6x4', 'power_hike', '6x4min Power-Hike Climbs', 6, 240, 180, 240, HIKE_M_PER_HR, POWER_HIKE, HIKE_CUE, {'base', 'build', 'peak'}),
    _vert('ph_5x6', 'power_hike', '5x6min Power-Hike Climbs', 5, 360, 240, 360, HIKE_M_PER_HR, POWER_HIKE, HIKE_CUE, {'base', 'build', 'peak'}),
    _vert('ph_4x8', 'power_hike', '4x8min Run-Hike Climbs', 4, 480, 300, 480, HIKE_M_PER_HR, POWER_HIKE, HIKE_CUE, {'build', 'peak'}),
    _vert('ph_4x10', 'power_hike', '4x10min Run-Hike Climbs', 4, 600, 300, 600, HIKE_M_PER_HR, POWER_HIKE, HIKE_CUE, {'build', 'peak'}),
    _vert('ph_3x12', 'power_hike', '3x12min Sustained Climbs', 3, 720, 360, 720, HIKE_M_PER_HR, POWER_HIKE, HIKE_CUE, {'build', 'peak'}),
    _vert('dh_5x5', 'downhill', '5x(3min Climb + 2min Fast Descent)', 5, 300, 60, 180, CLIMB_M_PER_HR, DOWNHILL, DOWNHILL_CUE, {'build', 'peak'}),
    _vert('dh_6x5', 'downhill', '6x(3min Climb + 2min Fast Descent)', 6, 300, 60, 180, CLIMB_M_PER_HR, DOWNHILL, DOWNHILL_CUE, {'build', 'peak'}),
    _vert('dh_4x8', 'downhill', '4x(5min Climb + 3min Fast Descent)', 4, 480, 90, 300, CLIMB_M_PER_HR, DOWNHILL, DOWNHILL_CUE, {'build', 'peak'}),
    _vert('dh_5x8', 'downhill', '5x(5min Climb + 3min Fast Descent)', 5, 480, 90, 300, CLIMB_M_PER_HR, DOWNHILL, DOWNHILL_CUE, {'peak'}),
)
CATALOG = CATALOG + SPECIFIC_CATALOG
# The menu leads with at most this many goal-specific shapes so a general shape
# (threshold/VO2/hills) stays available alongside them.
MAX_SPECIFIC_FAMILIES = 2
# A medium-long run stays well under the long run: at most this share of the
# week's volume (Stride heuristic in the spirit of Pfitzinger's 11-15mi MLRs at 55-70 mpw).
MEDIUM_LONG_SHARE = 0.25

# Minutes of hard work per session (excluding warmup, recovery, cooldown).
# race_pace / marathon_pace / vert are Stride heuristics placed between Daniels'
# T and I caps (goal-pace reps), near Pfitzinger's midweek MP runs (marathon pace)
# and as climbing time (vert); they are not literature limits.
EXPERIENCE_FLOOR = {
    'threshold': {'beginner': 10, 'intermediate': 15, 'advanced': 20, 'expert': 24},
    'intervals': {'beginner': 8, 'intermediate': 12, 'advanced': 15, 'expert': 18},
    'race_pace': {'beginner': 8, 'intermediate': 12, 'advanced': 16, 'expert': 20},
    'marathon_pace': {'beginner': 15, 'intermediate': 20, 'advanced': 25, 'expert': 30},
    'vert': {'beginner': 12, 'intermediate': 18, 'advanced': 24, 'expert': 30},
}
EXPERIENCE_CEILING = {
    'threshold': {'beginner': 16, 'intermediate': 30, 'advanced': 40, 'expert': 50},
    'intervals': {'beginner': 12, 'intermediate': 18, 'advanced': 24, 'expert': 30},
    'race_pace': {'beginner': 12, 'intermediate': 20, 'advanced': 28, 'expert': 34},
    'marathon_pace': {'beginner': 25, 'intermediate': 40, 'advanced': 55, 'expert': 70},
    'vert': {'beginner': 20, 'intermediate': 32, 'advanced': 45, 'expert': 60},
}
# Daniels' per-session volume guidance (share of weekly mileage).
DANIELS_SHARE = {'threshold': 0.10, 'intervals': 0.08}
VOLUME_SHARE = {**DANIELS_SHARE, 'race_pace': 0.09, 'marathon_pace': 0.15, 'vert': 0.12}
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
    by_volume = VOLUME_SHARE[category] * max(weekly_miles, 0) * pace / 60
    floor = min(floor, max(by_volume, EXPERIENCE_FLOOR[category]['beginner']))
    high = min(ceiling, max(by_volume, floor + 5))
    if phase == 'taper' or deload:
        high = max(8, floor * 0.75)
        floor = high * 0.6
    elif phase == 'base' and category == 'intervals':
        high = floor
        floor = floor * 0.7
    return DoseBand(round(floor, 1), round(high, 1), round(floor + 0.6 * (high - floor), 1))


def specific_bands(program, experience, weekly_miles, paces, phase, *, deload=False, terrain=None):
    """Dose bands for the goal-specific categories this goal and phase allow.

    Goal pace opens only in the phases goal_pace.SPECIFIC_PHASES lists and never in
    a deload; trail-ultra vertical work needs trail/mountain terrain and is left out
    of taper, race and recovery weeks. Empty dict = generic menu only.
    """
    from app.core.goal_pace import allows_goal_pace
    bands = {}
    if paces.get('specific_pace') and allows_goal_pace(program, phase, deload=deload):
        key = 'marathon_pace' if program == 'marathon' else 'race_pace'
        bands[key] = dose_band(key, experience, weekly_miles, paces['specific_pace'], phase)
    if program in ULTRA_GOALS and terrain in TRAIL and phase in {'base', 'build', 'peak'} and not deload:
        bands['vert'] = dose_band('vert', experience, weekly_miles, paces['long_run_pace'], phase)
    return bands


def _menu(template):
    return 'threshold' if template.category == 'threshold' else 'intervals'


def _minutes(template, paces):
    pace = paces.get(template.pace_key) if template.pace_key else paces.get('interval_pace', 420) * 1.15
    return template.work_minutes(pace) if pace else None


def ranked_templates(category, band, paces, *, phase='general', terrain=None, prefer_time=False, week_index=0,
                     program=None, specific=None, weekly_miles=None):
    """Candidates ordered for the menu: one family at a time, closest dose first.

    The caller validates each against the week's budget and spacing and keeps the
    first passing template per family, up to MAX_OPTIONS. Family order puts the
    athlete's preferred format first and then rotates by calendar week so the menu
    has variety from one week to the next without randomness. Goal-specific
    families (`specific`: dose bands from specific_bands) lead, at most
    MAX_SPECIFIC_FAMILIES of them, so one general shape still fits in the menu.
    """
    specific = specific or {}
    pool = []
    for template in CATALOG:
        if _menu(template) != category or (template.terrain and terrain not in template.terrain):
            continue
        if template.specific:
            if program not in template.goals or phase not in template.phases or template.dose_key not in specific:
                continue
            fits = specific[template.dose_key]
            if template.bookends and sum(template.bookends) + sum(r.reps * (r.meters or 0) for r in template.work) / MI \
                    > MEDIUM_LONG_SHARE * (weekly_miles or 0):
                continue
        else:
            if category == 'intervals' and phase in {'base', 'taper'} and template.family not in SHARP_INTERVAL_FAMILIES:
                continue
            fits = band
        minutes = _minutes(template, paces)
        if minutes is not None and fits.contains(minutes):
            pool.append((template, minutes, fits))
    families = sorted({t.family for t, _, _ in pool})
    if families:
        shift = week_index % len(families)
        families = families[shift:] + families[:shift]
    # Trail athletes get hills first; everyone else gets their preferred format first.
    def family_rank(family):
        has_preferred = any(t.is_time_based == prefer_time for t, _, _ in pool if t.family == family)
        return (family != 'hills', not has_preferred)
    families.sort(key=family_rank)
    goal_families = [f for f in families if any(t.specific for t, _, _ in pool if t.family == f)]
    general = [f for f in families if f not in goal_families]
    families = goal_families[:MAX_SPECIFIC_FAMILIES] + general + goal_families[MAX_SPECIFIC_FAMILIES:]
    ordered = []
    for family in families:
        members = sorted((p for p in pool if p[0].family == family),
                         key=lambda p: (p[0].is_time_based != prefer_time, abs(p[1] - p[2].target), p[1]))
        ordered.extend(t for t, _, _ in members)
    return ordered


def at_floor(families, band, paces, program=None):
    """Smallest template that reaches the band floor (a controlled dose), trying
    each family in order; else the largest one below it. Secondary sessions use
    this so they share the menu's dose floors instead of a separate table."""
    largest = None
    for family in families:
        sized = sorted((m, t.key, t) for t in CATALOG if t.family == family and (not t.goals or program in t.goals)
                       for m in [_minutes(t, paces)] if m is not None)
        above = [t for m, _, t in sized if m >= band.low - 0.5]
        if above:
            return above[0]
        if sized and (largest is None or sized[-1][0] > largest[0]):
            largest = sized[-1]
    return largest[2] if largest else None


def pick_specific(family, band, paces, program=None, phase=None):
    """Template of a family closest to the band target (plan-engine placement)."""
    sized = [(abs(m - band.target), m, t.key, t) for t in CATALOG
             if t.family == family and (not t.goals or program in t.goals) and (not t.phases or phase in t.phases)
             for m in [_minutes(t, paces)] if m is not None and band.contains(m)]
    return min(sized)[3] if sized else None


def ultra_vert_session(phase, program, terrain, paces, experience, weekly_miles, week_start, deload=False):
    """Trail-ultra quality day for the plan engine. Base keeps the short hill
    repeats (strength first); build and peak alternate power-hike climbs and
    downhill durability by calendar week. None = use the existing hill session."""
    if phase not in {'build', 'peak'}:
        return None
    band = specific_bands(program, experience, weekly_miles, paces, phase, deload=deload, terrain=terrain).get('vert')
    if not band:
        return None
    families = ('power_hike', 'downhill') if week_start.isocalendar()[1] % 2 else ('downhill', 'power_hike')
    template = next((t for f in families for t in [pick_specific(f, band, paces, program, phase)] if t), None)
    if not template:
        return None
    from app.core.workout_ladders import program_key
    return build_workout(template, paces, program=program_key(program), phase=phase)


def build_workout(template, paces, *, program=None, phase=None, bookend_miles=1.5, why=''):
    """Numeric prescription first; title, text and mileage are projections of it."""
    easy = paces['long_run_pace']
    pace = paces.get(template.pace_key) if template.pace_key else None
    fast = paces.get('interval_pace_fast', pace) if template.pace_key == 'interval_pace' else pace
    goal_pace = template.pace_key == 'specific_pace'
    segments = [segment(r.reps, seconds=r.seconds, meters=r.meters, fast=fast, slow=pace,
                        recovery_seconds=r.recovery_seconds or None,
                        category='race_pace' if goal_pace else None) for r in template.work]
    fmt = ('continuous' if template.family in {'continuous', 'mp_continuous', 'medium_long'}
           else 'time_intervals' if template.is_time_based else 'track_intervals')
    note = template.cue
    if template.vert_m:
        note += f' Aim for about {template.vert_m} m ({round(template.vert_m * 3.281, -1):,.0f} ft) of climbing in the work.'
    elif template.category == 'hills':
        note += ' Jog down the hill as recovery.'
    data = prescription(template.category, fmt, segments, program=program, phase=phase, note=note)
    data.update(progression_eligible=False, easy_pace_sec_per_mile=easy, template_id=template.key,
                stimulus=template.family)
    if goal_pace:
        data['goal_pace'] = True
    if template.vert_m:
        data['vert_target_m'] = template.vert_m
    warm, cool = template.bookends or (bookend_miles, bookend_miles)
    data['warmup'] = segment(meters=warm * MI)
    data['cooldown'] = segment(meters=cool * MI)
    # Effort-based work: mileage estimate only (climbing/hiking covers less ground).
    work_pace = pace or easy * (1.3 if template.vert_m else 0.85)
    work_miles = sum(r.reps * (r.meters / MI if r.meters else r.seconds / work_pace) for r in template.work)
    recovery_miles = sum((r.reps - 1 if len(template.work) == 1 else r.reps) * r.recovery_seconds / easy
                         for r in template.work)
    total = warm + cool + work_miles + recovery_miles
    data['total_distance_meters'] = round(total * MI, 2)
    return {'name': template.name, 'structure': render(data), 'prescription': data, 'total_miles': math.ceil(total * 2) / 2,
            'warmup': f'{warm:g}mi easy', 'cooldown': f'{cool:g}mi easy',
            'purpose': f'{template.purpose} {why}'.strip()}
