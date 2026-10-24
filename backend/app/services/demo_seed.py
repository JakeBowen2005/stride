from app.athlete_clock import today as athlete_today
"""Entirely synthetic, reproducible athlete fixtures. Requires an empty demo DB."""
import json
import math
from datetime import date, datetime, timedelta

from app.core.workout_data import MI, day_prescription, prescription, render, segment
from app.models.activity import Activity, PersonalRecord
from app.models.plan import Plan, PlannedWorkout
from app.models.progression import WorkoutProgression
from app.models.user import Goal, User
from app.models.wellness import DailyWellness

DAYS=['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
PRS=[('5K',3.10686,'5k'),('10K',6.21371,'10k'),('Half',13.1094,'half'),('Marathon',26.2188,'marathon')]


def easy_week(profile,target,run_days,long_day):
    """Easy-only beginner week: long run ~30% (never shorter than the others), the rest spread evenly, strides once."""
    long=round(min(profile['long_miles'],target*max(.3,1.2/len(run_days))),1)
    easy=round((target-long)/max(1,len(run_days)-1),1)
    strides=profile.get('strides') and next((d for d in run_days if d!=long_day),None)
    return {d:(long,'long_run','Easy Long Run') if d==long_day else (easy,'easy','Easy Run + Strides' if d==strides else 'Easy Run') for d in run_days}


def seed_demo(db, profile):
    if db.query(User).count():raise ValueError('Refusing to overwrite a populated database')
    today=athlete_today();monday=today-timedelta(days=today.weekday())
    goal_type=profile.get('goal_type','race');workouts=profile.get('workouts',True)
    rest_days=profile.get('rest_days',['sunday']);days_per_week=profile.get('days_per_week',6);long_run_day=profile.get('long_run_day','saturday')
    race=monday+timedelta(weeks=profile['weeks_to_race'],days=6) if goal_type=='race' else None
    distance=profile.get('distance')
    user=User(id=1,name=profile['name'],age=profile['age'],units='miles',workout_format='time' if distance=='100k' else 'distance',
        years_running=profile.get('years_running',8),experience_level=profile['experience'],days_per_week=days_per_week,rest_days=','.join(rest_days),long_run_day=long_run_day,
        current_weekly_mileage=sum(profile['weekly_miles'][-4:])/4,peak_weekly_mileage=max(profile['weekly_miles']),
        **{'pr_'+k:v for k,v in profile['prs'].items()})
    db.add(user);db.flush()
    db.add(Goal(user_id=1,goal_type=goal_type,race_distance=distance,target_time_seconds=profile.get('target_seconds'),
        race_date=race.isoformat() if race else None,terrain=profile.get('terrain'),elevation_gain_ft=profile.get('elevation_gain_ft'),
        target_weekly_mileage=profile.get('target_weekly_mileage'),description=profile['description']))
    from app.core.workout_ladders import program_key
    # No ladder level: the plan API seeds level 1 with no pace on first generation.
    for cat in ('threshold','intervals') if profile.get('ladder_level') is not None else ():
        db.add(WorkoutProgression(user_id=1,category=cat,program_key=program_key(distance),current_level=profile['ladder_level'],
            current_pace_sec=profile['threshold_pace']+10 if cat=='threshold' else profile['interval_pace'],sessions_at_level=2,format_rotation=0))
    if goal_type=='race':
        goal_snapshot={'type':'race','distance':distance,'race_date':race.isoformat(),'target_time':profile['target_seconds'],'terrain':profile.get('terrain')}
    else:
        goal_snapshot={'type':goal_type,'target_weekly_mileage':profile.get('target_weekly_mileage')}
    run_days=[i for i,name in enumerate(DAYS) if name not in rest_days][:days_per_week]
    long_day=DAYS.index(long_run_day)
    plan=None
    for week,target in enumerate(profile['weekly_miles']):
        start=monday-timedelta(weeks=12-week)
        if week%2==0:
            plan=Plan(user_id=1,start_date=start.isoformat(),end_date=(start+timedelta(days=13)).isoformat(),prescribed_from=start.isoformat(),is_active=week==10,
                goal_snapshot=json.dumps(goal_snapshot),athlete_snapshot=json.dumps({'synthetic':True,'schedule_preferences':{'rest_days':rest_days,'days_per_week':days_per_week}}),
                load=json.dumps({'weekly_budgets':profile['weekly_miles'][week:week+2]}))
            db.add(plan);db.flush()
        if not workouts:
            _easy_history_week(db,profile,plan,week,start,easy_week(profile,target,run_days,long_day))
            continue
        threshold=prescription('threshold','time_intervals',[segment(3,seconds=480,fast=profile['threshold_pace'],slow=profile['threshold_pace'],recovery_seconds=120)])
        threshold.update(warmup=segment(meters=1.5*MI),cooldown=segment(meters=1.5*MI))
        intervals=prescription('intervals','track_intervals',[segment(5,meters=1000,fast=profile['interval_pace'],slow=profile['interval_pace'],recovery_seconds=120)])
        intervals.update(warmup=segment(meters=1.5*MI),cooldown=segment(meters=1.5*MI))
        def session_miles(data):
            s=data['segments'][0];pace=s['pace_range_sec_per_mile']['slow']
            return math.ceil((3+s['reps']*((s.get('duration_seconds') or 0)/pace+(s.get('distance_meters') or 0)/MI)+(s['reps']-1)*120/profile['easy_pace'])*2)/2
        t_miles,i_miles=session_miles(threshold),session_miles(intervals)
        long=min(profile['long_miles'],target*.34)
        easy=(target-t_miles-i_miles-long)/3
        for day in range(7):
            d=start+timedelta(days=day);data=threshold if day==1 else intervals if day==3 else None
            typ='rest' if day==6 else 'workout' if data else 'long_run' if day==5 else 'easy'
            miles=0 if typ=='rest' else t_miles if day==1 else i_miles if day==3 else long if day==5 else easy
            title='3x8min Threshold' if day==1 else '5x1000m Intervals' if day==3 else 'Trail Long Run' if day==5 and profile['terrain']=='trail' else 'Easy Long Run' if day==5 else 'Rest Day' if day==6 else 'Easy Run'
            notes='SYNTHETIC fixture. Controlled, recovered well.'
            if day==5 and profile['terrain']=='trail':notes+=' Practiced hiking climbs and 60g carbohydrate/hour.'
            description=render(data) if data else notes
            pw=PlannedWorkout(plan_id=plan.id,date=d.isoformat(),day_name=d.strftime('%A').lower(),week_number=week%2+1,type=typ,title=title,
                description=description,distance_miles=miles,prescription=json.dumps(data or day_prescription({'type':typ,'distance_miles':miles,'description':description})),
                feel_rating=8 if miles else None,feel_notes=notes,session_status='completed' if miles else 'not_logged')
            db.add(pw)
            if miles:
                laps=[]
                if data:
                    laps.append({'intensity':'WARMUP','distance_m':1.5*MI,'duration_s':1.5*profile['easy_pace']})
                    s=data['segments'][0];pace=s['pace_range_sec_per_mile']['slow']
                    for rep in range(s['reps']):
                        meters=s.get('distance_meters') or s['duration_seconds']/pace*MI
                        seconds=s.get('duration_seconds') or meters/MI*pace
                        laps.append({'intensity':'ACTIVE','distance_m':meters,'duration_s':seconds})
                        if rep<s['reps']-1:laps.append({'intensity':'RECOVERY','distance_m':120/profile['easy_pace']*MI,'duration_s':120})
                    laps.append({'intensity':'COOLDOWN','distance_m':1.5*MI,'duration_s':1.5*profile['easy_pace']})
                duration=sum(l['duration_s'] for l in laps) if laps else miles*profile['easy_pace']
                activity=Activity(user_id=1,source='manual',external_id=f'demo-{profile["id"]}-{d}',name=f'Synthetic {title}',date=datetime.combine(d,datetime.min.time()).replace(hour=7),
                    distance_meters=miles*MI,duration_seconds=duration,average_pace_per_km=duration/(miles*1.60934),average_heartrate=155 if data else 132,
                    max_heartrate=170 if data else 148,description=description,splits=json.dumps(laps),workout_type='threshold' if day==1 else 'intervals' if day==3 else typ,
                    feel_rating=8,feel_notes=notes,elevation_gain=miles*35 if profile['terrain']=='trail' else miles*5)
                db.add(activity);db.flush();pw.activity_id=activity.id
            db.add(DailyWellness(user_id=1,date=d.isoformat(),sleep_seconds=8*3600,sleep_score=88,hrv_last_night=75,hrv_baseline_low=60,hrv_baseline_high=85,resting_hr=44,readiness_score=82,acwr=1.05))
    for i in range(today.weekday()):
        d=monday+timedelta(days=i)
        if not workouts:
            # Repeat last week's easy-only pattern for the days already run.
            miles=easy_week(profile,profile['weekly_miles'][-1],run_days,long_day).get(i,(0,))[0]
            if miles:db.add(Activity(user_id=1,source='manual',name='Synthetic current-week easy run',date=datetime.combine(d,datetime.min.time()).replace(hour=7),distance_meters=miles*MI,duration_seconds=miles*profile['easy_pace'],average_pace_per_km=profile['easy_pace']/1.60934,workout_type='easy',feel_rating=8))
            continue
        db.add(Activity(user_id=1,source='manual',name='Synthetic current-week easy run',date=datetime.combine(d,datetime.min.time()).replace(hour=7),distance_meters=6*MI,duration_seconds=6*profile['easy_pace'],average_pace_per_km=profile['easy_pace']/1.60934,workout_type='easy',feel_rating=8))
    for i in range(today.weekday()+1):
        d=monday+timedelta(days=i)
        db.add(DailyWellness(user_id=1,date=d.isoformat(),sleep_seconds=8*3600,sleep_score=90,hrv_last_night=76,hrv_baseline_low=60,hrv_baseline_high=85,resting_hr=43,readiness_score=85,acwr=1.05))
    for label,miles,key in PRS:
        if key not in profile['prs']:continue
        db.add(PersonalRecord(user_id=1,distance_label=label,distance_miles=miles,time_seconds=profile['prs'][key],pace_per_mile=profile['prs'][key]/miles,date=datetime.combine(today-timedelta(days=100),datetime.min.time())))
    db.commit()
    from app.api.plans import generate_training_plan,approve_draft,PlanRequest
    preview=generate_training_plan(1,PlanRequest(),db)
    if preview.get('violations'):raise ValueError(f'Demo generation failed validation: {preview["violations"]}')
    approve_draft(1,preview['id'],db)
    return {'scenario':profile['id'],'anchor':today.isoformat(),'race_date':race.isoformat() if race else None,'preview_id':preview['id'],
            'quality_stage':preview['quality_policy']['stage'],'phases':[w['phase']['phase'] for w in preview['weeks']]}


def _easy_history_week(db,profile,plan,week,start,days):
    """One completed week of easy-only history (no workouts, no laps)."""
    for day in range(7):
        d=start+timedelta(days=day);miles,typ,title=days.get(day,(0,'rest','Rest Day'))
        notes='SYNTHETIC fixture. Conversational the whole way, felt good.'
        if 'Strides' in title:notes+=' Finished with 4x20sec relaxed strides.'
        pw=PlannedWorkout(plan_id=plan.id,date=d.isoformat(),day_name=d.strftime('%A').lower(),week_number=week%2+1,type=typ,title=title,
            description=notes,distance_miles=miles,prescription=json.dumps(day_prescription({'type':typ,'distance_miles':miles,'description':notes})),
            feel_rating=8 if miles else None,feel_notes=notes,session_status='completed' if miles else 'not_logged')
        db.add(pw)
        if miles:
            duration=miles*profile['easy_pace']
            activity=Activity(user_id=1,source='manual',external_id=f'demo-{profile["id"]}-{d}',name=f'Synthetic {title}',date=datetime.combine(d,datetime.min.time()).replace(hour=7),
                distance_meters=miles*MI,duration_seconds=duration,average_pace_per_km=duration/(miles*1.60934),average_heartrate=142,
                max_heartrate=158,description=notes,splits=json.dumps([]),workout_type=typ,feel_rating=8,feel_notes=notes,elevation_gain=miles*10)
            db.add(activity);db.flush();pw.activity_id=activity.id
        db.add(DailyWellness(user_id=1,date=d.isoformat(),sleep_seconds=7.5*3600,sleep_score=80,hrv_last_night=55,hrv_baseline_low=45,hrv_baseline_high=65,resting_hr=58,readiness_score=75,acwr=1.05))
