"""Cached, descriptive training trends. Missing evidence is never a failed workout."""
from datetime import date,datetime,timedelta
from statistics import mean,pstdev
import json
from app.athlete_clock import today
from app.models.activity import Activity,runs_only
from app.models.wellness import DailyWellness
from app.services.history_cache import cached
from app.services.history_facts import historical_profile

VERSION='longitudinal-v1'
QUALITY={'workout','threshold','intervals','tempo','fartlek','hill_repeats'}


def _build(user_id,db,as_of,persist):
    profile=historical_profile(user_id,db,as_of,persist=persist)
    rows=db.query(Activity).filter(Activity.user_id==user_id,runs_only(),
        Activity.date>=datetime.combine(as_of-timedelta(days=84),datetime.min.time()),
        Activity.date<datetime.combine(as_of+timedelta(days=1),datetime.min.time())).order_by(Activity.date).all()
    windows=[]
    monday=as_of-timedelta(days=as_of.weekday())
    for count in (4,8,12):
        runs=[a for a in rows if monday-timedelta(weeks=count)<=a.date.date()<monday]
        windows.append({'weeks':count,'recorded_mpw':round(sum(a.distance_meters for a in runs)/1609.34/count,1),
                        'run_days_per_week':round(len({a.date.date() for a in runs})/count,1),'recorded_runs':len(runs),
                        'activity_ids':[a.id for a in runs][-20:], 'coverage':'Recorded training; missing days may be unrecorded, not rest.'})
    quality=[]
    for a in [r for r in rows if r.workout_type in QUALITY][-12:]:
        try:laps=json.loads(a.splits or '[]')
        except (TypeError,ValueError):laps=[]
        active=[l for l in laps if str(l.get('intensity','')).upper() in {'ACTIVE','INTERVAL'} and l.get('duration_s') and l.get('distance_m')]
        paces=[l['duration_s']/(l['distance_m']/1609.34) for l in active]
        quality.append({'activity_id':a.id,'date':a.date.date().isoformat(),'work_minutes':round(sum(l['duration_s'] for l in active)/60,1) if active else None,
                        'rep_pace_cv_percent':round(pstdev(paces)/mean(paces)*100,1) if len(paces)>=2 else None,
                        'effort':a.effort_rating if a.effort_rating is not None else a.watch_effort,
                        'feel':a.effective_feel,'completion':a.reported_completion,
                        'evidence':'measured active laps' if active else 'work dose unknown; recording or self-report is not lap verification'})
    # Compare similar-distance easy runs at similar heart rate and climbing.
    easy=[a for a in rows if a.workout_type in {'easy','recovery'} and a.average_heartrate and 3000<=a.distance_meters<=16000 and a.duration_seconds>0]
    recent=[a for a in easy if a.date.date()>=as_of-timedelta(days=28)]
    earlier=[a for a in easy if a.date.date()<as_of-timedelta(days=28)]
    comparison=None
    if len(recent)>=3:
        anchor=mean(a.average_heartrate for a in recent)
        distance=mean(a.distance_meters for a in recent)
        def similar(a):
            return abs(a.average_heartrate-anchor)<=5 and abs(a.distance_meters-distance)<=distance*.2 and a.elevation_gain is not None
        current=[a for a in recent if similar(a)]
        if len(current)>=3:
            grade=mean(a.elevation_gain/a.distance_meters for a in current)
            prior=[a for a in earlier if similar(a) and abs(a.elevation_gain/a.distance_meters-grade)<=.005]
            if len(prior)>=3:
                comparison={'recent_pace_sec_per_mile':round(mean(a.duration_seconds/(a.distance_meters/1609.34) for a in current)),
                            'prior_pace_sec_per_mile':round(mean(a.duration_seconds/(a.distance_meters/1609.34) for a in prior)),
                            'recent_activity_ids':[a.id for a in current],'prior_activity_ids':[a.id for a in prior],
                            'uncertainty':'Matched approximately on heart rate, distance and climbing; weather, surface and sensor differences remain unknown. This does not prove a fitness change.'}
    wellness=db.query(DailyWellness).filter(DailyWellness.user_id==user_id,DailyWellness.date>=(as_of-timedelta(days=84)).isoformat(),DailyWellness.date<=as_of.isoformat()).all()
    long_recovery=[]
    for a in [r for r in rows if r.workout_type=='long_run'][-6:]:
        following=[r for r in rows if 1<=(r.date.date()-a.date.date()).days<=2]
        sleep=[w.sleep_seconds for w in wellness if w.sleep_seconds is not None and 1<=(date.fromisoformat(w.date)-a.date.date()).days<=2]
        feels=[r.effective_feel for r in following if r.effective_feel is not None]
        long_recovery.append({'activity_id':a.id,'date':a.date.date().isoformat(),'next_two_days_run_ids':[r.id for r in following],
                              'reported_feel_mean':round(mean(feels),1) if feels else None,'sleep_hours_mean':round(mean(sleep)/3600,1) if sleep else None,
                              'note':'Descriptive follow-up only; absent recordings or feedback do not establish recovery.'})
    return {'version':VERSION,'as_of':as_of.isoformat(),'windows':windows,'quality_sessions':quality,
            'comparable_easy_runs':comparison,'long_run_follow_up':long_recovery,
            'historical_capacity':profile['historical_capacity'],'uncertainties':['No causal or injury-risk conclusions are inferred from these associations.']}


def analyze(user_id,db,as_of=None,*,persist=True):
    as_of=as_of or today()
    return cached(user_id,VERSION,as_of.isoformat(),db,lambda:_build(user_id,db,as_of,persist),persist=persist)
