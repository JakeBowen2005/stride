"""Personalized, deterministic menus. The athlete/model selects a concrete option.

Dose limits below are transparent Stride defaults, not universal safe thresholds.
All proposed sessions and companion easy-day cuts pass the shared schedule validator.
"""
import copy
import hashlib
import json
import math
from datetime import date, datetime, timedelta

from fastapi import HTTPException

from app.core.workout_data import MI, day_prescription, loads, prescription, render, segment
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.models.progression import WorkoutProgression
from app.models.user import Goal, User
from app.services.coaching_options import snapshot

VERSION = 'session-menu-v1'


def _json(raw, fallback=None):
    try: return json.loads(raw) if raw else fallback
    except (ValueError, TypeError): return fallback


def context_for(plan, db):
    from app.services.analyzer import analyze_athlete, compute_weekly_mileage
    from app.services.quality_history import quality_history
    from app.core.quality_policy import select_quality_policy
    from app.core.plan_engine import _build_current_paces, effective_paces
    from app.services.pace_calibrator import calibrate_paces
    from app.api.plans import _parse_pace
    user = db.get(User, plan.user_id)
    goal = db.query(Goal).filter_by(user_id=plan.user_id, active=True).first()
    analysis = analyze_athlete(plan.user_id, db)
    experience = user.experience_level or analysis.get('overview', {}).get('experience_level', 'beginner')
    today = date.today(); monday = today-timedelta(days=today.weekday())
    weeks = {w['week_start']: w['actual'] for w in compute_weekly_mileage(plan.user_id, db, 10)}
    full = [weeks.get((monday-timedelta(weeks=i)).isoformat(), 0) for i in range(8,0,-1)]
    evidence = quality_history(plan.user_id, db)
    acts = db.query(Activity).filter(Activity.user_id==plan.user_id,
        Activity.date>=datetime.combine(today-timedelta(days=56),datetime.min.time()),
        Activity.date<datetime.combine(today+timedelta(days=1),datetime.min.time())).order_by(Activity.id).all()
    long = max((a.distance_meters/MI for a in acts if a.date.date()>=today-timedelta(days=28)), default=0)
    assessment = (_json(plan.assessment, {}) or {}).get('decision')
    quality = select_quality_policy(goal.goal_type if goal else 'general',experience,user.days_per_week,
        full,evidence['weekly_run_days'],long,assessment=assessment,evidence=evidence)
    recent_pace = analysis.get('paces',{}).get('recent_easy_pace') or analysis.get('paces',{}).get('easy_pace')
    easy = _parse_pace(recent_pace) if recent_pace else 0
    calibrated = calibrate_paces(plan.user_id,db)
    stored = _json(plan.training_paces,{}) or {}
    paces = _build_current_paces(easy or stored.get('long_run_pace',570),calibrated)
    rows = db.query(PlannedWorkout).filter_by(plan_id=plan.id).order_by(PlannedWorkout.date).all()
    # No new category evidence: retain the approved numeric pace, never infer a
    # faster threshold from a label change or an easy-run estimate.
    for category, key in (('threshold','threshold_pace'),('intervals','interval_pace')):
        if key not in calibrated:
            contracts = [loads(r.prescription) for r in rows if (loads(r.prescription) or {}).get('category')==category]
            targets = [seg['pace_range_sec_per_mile'] for data in contracts for seg in data['segments'] if seg.get('pace_range_sec_per_mile')]
            if category=='threshold' and targets:
                paces['broken_threshold_pace']=max(t['slow'] for t in targets)
                paces['tempo_pace']=paces['broken_threshold_pace']+10
            elif category=='intervals' and targets:
                paces['interval_pace']=max(t['slow'] for t in targets);paces['interval_pace_fast']=max(t['fast'] for t in targets)
            elif stored:
                keys=('threshold_pace','tempo_pace','broken_threshold_pace') if category=='threshold' else ('interval_pace','interval_pace_fast')
                for name in keys:
                    if name in stored:paces[name]=stored[name]
    from app.core.workout_ladders import program_key
    program = goal.race_distance or goal.goal_type if goal else 'general'
    progression = db.query(WorkoutProgression).filter_by(user_id=plan.user_id, program_key=program_key(program)).order_by(WorkoutProgression.id).all()
    paces = effective_paces(paces,{p.category:{'current_pace_sec':p.current_pace_sec} for p in progression if p.current_pace_sec})
    rows = db.query(PlannedWorkout).filter_by(plan_id=plan.id).order_by(PlannedWorkout.date).all()
    completed_dates={a.date.date().isoformat() for a in acts}
    data = {'version':VERSION,'today':today.isoformat(),'plan_id':plan.id,'active':plan.is_active,
        'load':plan.load,'snapshot':plan.athlete_snapshot,'phases':plan.phases,'goal_snapshot':plan.goal_snapshot,
        'athlete':{k:getattr(user,k) for k in ('experience_level','rest_days','days_per_week','long_run_day','workout_format')},
        'goal':{k:getattr(goal,k) for k in ('id','goal_type','race_distance','target_time_seconds','race_date','terrain')} if goal else None,
        'sessions':[{**snapshot(r),'id':r.id,'date':r.date,'status':'completed' if r.date in completed_dates else r.session_status,'moved_to':r.moved_to,'moved_from':r.moved_from,'feedback':r.feel_rating,'notes':r.feel_notes,'original':r.original_prescription} for r in rows],
        'activities':[{k:getattr(a,k) for k in ('id','date','distance_meters','duration_seconds','feel_rating','feel_notes','description','splits')} for a in acts],
        'quality':quality.to_dict(),'paces':paces,'levels':[(p.category,p.current_level,p.current_pace_sec) for p in progression]}
    token=hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest()
    return {'user':user,'goal':goal,'experience':experience,'baseline':sum(full[-4:])/4,'recent_long':long,
        'evidence':evidence,'quality':quality,'paces':paces,'rows':rows,'token':token,'program':program}


def _workout(category, reps, length, paces, program, phase, fmt):
    pace=paces.get('broken_threshold_pace',paces['tempo_pace']-10) if category=='threshold' else paces['interval_pace']
    fast=pace if category=='threshold' else paces.get('interval_pace_fast',pace)
    work=segment(reps,seconds=length if category=='threshold' else None,meters=length if category=='intervals' else None,
        fast=fast,slow=pace,recovery_seconds=120)
    data=prescription(category,'time_intervals' if category=='threshold' else 'track_intervals',[work],program=program,phase=phase,
        note='Controlled and repeatable. Athlete-selected dose; complete it before considering progression.')
    data.update(progression_eligible=False,easy_pace_sec_per_mile=paces['long_run_pace'])
    data['warmup']=segment(meters=1.5*MI);data['cooldown']=segment(meters=1.5*MI)
    total=3+reps*(length/pace if category=='threshold' else length/MI)+(reps-1)*120/paces['long_run_pace']
    data['total_distance_meters']=round(total*MI,2)
    from app.core.quality_policy import format_bookends
    title=f'{reps}x{length//60}min Threshold' if category=='threshold' else f'{reps}x{length:g}m Intervals'
    return format_bookends({'name':title,'structure':render(data),'prescription':data,'total_miles':math.ceil(total*2)/2,
        'warmup':'1.5mi easy','cooldown':'1.5mi easy','purpose':f'Current-fitness {category} work inside your goal, recovery and weekly load limits.'},paces,fmt)


def _as_patch(workout):
    return {'type':'workout','title':workout['name'],'description':workout['structure'],'purpose':workout['purpose'],
        'distance_miles':workout['total_miles'],'warmup':workout.get('warmup'),'cooldown':workout.get('cooldown'),
        'prescription':json.dumps(workout['prescription']),'b2b':False}


def build_session_options(plan, row, category, db, context=None):
    from app.api.plans import _get_activities_for_date, _fits_week_budget, _validate_schedule
    if not plan.is_active or row.date<max(date.today().isoformat(),plan.prescribed_from or plan.start_date) or row.type=='race' or row.activity_id or row.moved_to or row.session_status=='skipped' or _get_activities_for_date(row.date,plan.user_id,db):
        raise HTTPException(409,'Only an unrun current or future session in the approved plan can be changed')
    ctx=context or context_for(plan,db)
    saved_goal=_json(plan.goal_snapshot,{}) or {}
    if ctx['goal'] and saved_goal and (saved_goal.get('type')!=ctx['goal'].goal_type or saved_goal.get('distance')!=ctx['goal'].race_distance):
        raise HTTPException(409,'Your goal changed. Review a revised block before selecting workouts for the new goal.')
    phases=_json(plan.phases,[]) or []
    phase=phases[row.week_number-1].get('phase','general') if row.week_number<=len(phases) else 'general'
    others=[r for r in ctx['rows'] if r.week_number==row.week_number and r.id!=row.id]
    substantial=lambda r:r.type=='workout' and (loads(r.prescription) or {}).get('category')!='speed_support'
    hard_long=lambda r:r.type=='long_run' and any(t in r.title.lower() for t in ('mp ','race-effort','steady','sandwich'))
    actual_quality=lambda r:any(a.workout_type in {'workout','threshold','intervals','tempo','fartlek','hill_repeats','race'} for a in _get_activities_for_date(r.date,plan.user_id,db))
    hard_count=sum(substantial(r) or hard_long(r) or actual_quality(r) for r in others)
    capacity=2 if ctx['quality'].stage=='dual' else 1
    info=phases[row.week_number-1] if row.week_number<=len(phases) else {}
    phase_cap=info.get('max_workouts')
    if phase_cap is None and phase=='taper':phase_cap=1
    if phase=='recovery':phase_cap=0
    if phase=='base' and ctx['experience'] not in {'advanced','expert'}:phase_cap=1
    load=_json(plan.load,{}) or {}
    deload=plan.is_deload and ('deload_week' not in load or load['deload_week']==row.week_number-1)
    b2b=bool(info.get('back_to_back')) or sum(bool(r.b2b) and r.type=='long_run' for r in ctx['rows'] if r.week_number==row.week_number)>=2
    if phase_cap is not None:capacity=min(capacity,phase_cap)
    if deload or b2b:capacity=min(capacity,1)
    candidates=[];reasons=[]
    poor=ctx['evidence']['recent_low_feel'] or ctx['evidence']['recent_failure']
    if category in {'threshold','intervals'}:
        if poor or phase in {'race_week','recovery'}:
            reasons.append('Recent recovery or race/recovery phase calls for easy running or rest instead of another hard session.')
        elif hard_count<capacity:
            caps={'beginner':12,'intermediate':20,'advanced':24,'expert':30}
            cap=caps.get(ctx['experience'],12)
            if ctx['baseline']<25:cap=min(cap,12)
            if ctx['baseline']>=50 and ctx['evidence']['primary_successes']>=2:cap+=6
            if phase in {'base','taper'}:cap=min(cap,12 if phase=='base' else 8)
            if deload:cap=min(cap,12)
            if category=='threshold':
                doses=[(2,180),(2,240),(2,360),(3,300),(3,360),(2,600),(3,480),(4,360),(3,600)]
                doses=[d for d in doses if d[0]*d[1]<=cap*60]
            else:
                minutes=min(cap,{'beginner':8,'intermediate':12,'advanced':16,'expert':20}.get(ctx['experience'],8))
                doses=[(4,400),(6,400),(8,400),(5,600),(4,800),(5,800),(4,1000),(3,1200),(4,1609.34)]
                doses=[d for d in doses if d[0]*d[1]/MI*ctx['paces']['interval_pace']/60<=minutes
                       and (phase not in {'base','taper'} or d[1]<=600)]
            for reps,length in doses:
                candidates.append(_as_patch(_workout(category,reps,length,ctx['paces'],ctx['program'],phase,ctx['user'].workout_format)))
            reasons.append(f"{ctx['experience'].title()} background, {ctx['baseline']:.1f} recent mi/week, {phase} phase; current demonstrated paces and earned quality slots set this menu.")
        else:
            reasons.append('This week already uses its substantial quality slots. Replace another quality session or earn the two-workout stage first.')
        if category=='intervals' and not poor and phase not in {'taper','race_week','recovery'} and not deload and not b2b and (phase_cap is None or phase_cap>=2) and ctx['quality'].stage=='support' and hard_count==1 and not any(r.type=='workout' and not substantial(r) for r in others):
            from app.core.quality_policy import light_speed_support
            for i in range(6):
                candidates.append(_as_patch(light_speed_support(ctx['paces'],ctx['user'].workout_format,
                    week_start=date.fromisoformat(row.date)+timedelta(weeks=i),terrain=ctx['goal'].terrain if ctx['goal'] else None)))
            reasons.append('A light second stimulus is available; full intervals need the two-substantial-workout stage.')
    elif category=='long_run':
        if poor:
            reasons.append('Recovery feedback does not support prescribing a long run right now. Choose easy running or rest.')
        elif row.b2b or any(r.type=='long_run' for r in others):
            reasons.append('Keep one main long run per week. Planned ultra back-to-backs need their coordinated structure.')
        else:
            budgets=(_json(plan.load,{}) or {}).get('weekly_budgets',[])
            budget=budgets[row.week_number-1] if row.week_number<=len(budgets) else sum(r.distance_miles for r in others)+row.distance_miles
            cap=min(budget*.35,max(6,ctx['recent_long']*1.1))
            if phase=='taper':cap=min(cap,10)
            if phase in {'recovery','race_week'}:cap=min(cap,6)
            lengths=sorted(set([2,3,4,5,6,8,10,12,14,16,18,20,math.floor(cap*2)/2]))
            for miles in lengths:
                if miles>cap+.01 or miles<max(2,cap*.5):continue
                from app.core.plan_engine import _long_run_structure
                patch={'type':'long_run','distance_miles':miles,'warmup':None,'cooldown':None,'b2b':False,**_long_run_structure(miles,'easy',ctx['paces'])}
                if ctx['program'] in {'50k','50mi','100k','100mi'}:
                    from app.core.periodization import week_phase
                    from app.core.special_weeks import ultra_long_run
                    info=week_phase(date.fromisoformat(row.date), 'race',ctx['program'],date.fromisoformat(ctx['goal'].race_date) if ctx['goal'].race_date else None)
                    patch.update({k:v for k,v in ultra_long_run(date.fromisoformat(row.date),ctx['program'],miles/.35,info,ctx['paces'],ctx['goal'].terrain).items() if k in patch})
                if patch['distance_miles']>cap+.001:continue  # helper minimum duration must not override the athlete's dose cap
                patch['prescription']=json.dumps(day_prescription(patch));candidates.append(patch)
                if ctx['program'] in {'marathon','half'} and phase in {'build','peak'} and ctx['quality'].stage=='dual' and hard_count<1 and ctx['baseline']>=40 and miles>=12 and not poor:
                    steady=copy.deepcopy(patch);steady.update(_long_run_structure(miles,'steady_finish',ctx['paces']));steady['prescription']=json.dumps(day_prescription(steady));candidates.append(steady)
            reasons.append('Long-run length is bounded by recent completed endurance, phase and 35% of this week’s budget; this share is a Stride heuristic.')
    before={r.id:snapshot(r) for r in ctx['rows']}
    options=[];seen=set()
    for patch in candidates:
        signature=json.dumps(patch,sort_keys=True)
        if signature in seen:continue
        seen.add(signature)
        with db.begin_nested() as trial:
            try:
                if not _fits_week_budget(plan,row,patch['distance_miles'],db):continue
                for key,value in patch.items():setattr(row,key,value)
                db.flush();_validate_schedule(plan,db)
                changes=[{'session_id':r.id,'date':r.date,'before':before[r.id],'replacement':snapshot(r)} for r in ctx['rows'] if snapshot(r)!=before[r.id]]
                if not changes:continue
                option_id=hashlib.sha256((ctx['token']+json.dumps(changes,sort_keys=True)).encode()).hexdigest()
                options.append({'id':option_id,'date':row.date,'title':patch['title'],'description':patch['description'],
                    'distance_miles':patch['distance_miles'],'warmup':patch['warmup'],'cooldown':patch['cooldown'],
                    'prescription':_json(patch['prescription']), 'changes':changes})
            except HTTPException:pass
            finally:trial.rollback()
    if not options:reasons.append('No matching option fits the remaining budget, rest preferences and hard-day spacing. Try another date or an easier category.')
    return {'category':category,'options':options,'reasons':reasons,'quality_stage':ctx['quality'].stage,'context':ctx['token']}


def apply_option(plan,row,category,option_id,reason,db):
    from app.api.plans import _mark_changed,_validate_schedule
    menu=build_session_options(plan,row,category,db)
    choice=next((o for o in menu['options'] if o['id']==option_id),None)
    if not choice:raise HTTPException(409,'This option is no longer available. Reload the options using your latest training.')
    for change in choice['changes']:
        target=db.get(PlannedWorkout,change['session_id'])
        _mark_changed(target,f'{reason}. Athlete selected {choice["title"]}; weekly budget rebalanced where needed.')
        for key,value in change['replacement'].items():setattr(target,key,value)
        if target.id==row.id:target.session_status='replaced'
    db.flush();_validate_schedule(plan,db)
    return choice
