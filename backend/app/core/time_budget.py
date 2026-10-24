"""Fit a session to actual availability without inventing faster training paces."""
from copy import deepcopy
import math
from app.core.workout_data import MI,loads,render,day_prescription


def contract_size(data,easy):
    seconds,meters=0.,0.
    if not data:return seconds,meters
    def part(s,pace):
        duration=s.get('duration_seconds')
        distance=s.get('distance_meters')
        if duration is not None:return duration,(distance if distance is not None else duration/pace*MI)
        return (distance or 0)/MI*pace,distance or 0
    for name in ('warmup','cooldown'):
        if data.get(name):
            time,distance=part(data[name],easy);seconds+=time;meters+=distance
    for s in data.get('segments',[]):
        pace=(s.get('pace_range_sec_per_mile') or {}).get('slow') or data.get('estimated_work_pace_sec_per_mile') or easy
        time,distance=part(s,pace)
        reps=s.get('reps',1)
        rest=s.get('recovery_seconds') or (s.get('recovery_meters') or 0)/MI*easy
        seconds+=reps*time+max(0,reps-1)*rest
        meters+=reps*distance+max(0,reps-1)*(s.get('recovery_meters') or rest/easy*MI)
    return seconds,meters


def estimated_minutes(day,easy):
    data=loads(day.get('prescription'))
    seconds,meters=contract_size(data,easy)
    if not data:return (day.get('distance_miles') or 0)*easy/60
    return (seconds+max(0,(day.get('distance_miles') or 0)-meters/MI)*easy)/60


def _easy(day,miles,easy,long=False):
    day.update(type='rest' if miles<=0 else 'long_run' if long else 'easy',title='Easy Long Run' if long else 'Easy Run',distance_miles=miles,
               description=f'{miles:g}mi at conversational effort, within your available time.',
               purpose='Build aerobic endurance within your schedule.',warmup=None,cooldown=None,b2b=False)
    day['prescription']=day_prescription(day|{'prescription':None})


def fit_availability(weeks,limits,easy,*,developing=False,prior_hard_dates=None):
    notes=[]
    if not limits:return notes
    from datetime import date
    all_days=[d for w in weeks for d in w['days']]
    fields=('type','title','description','purpose','distance_miles','warmup','cooldown','prescription','b2b')
    for week in weeks:
        # Preserve the full main dose by placing it on a roomier easy day first.
        # Completed days, long runs and adjacent hard sessions are never displaced.
        for source in list(week['days']):
            limit=limits.get(source.get('day','').lower())
            spec=loads(source.get('prescription'))
            if source['type']!='workout' or source.get('prescribed') is False or source.get('editable') is False or limit is None or not spec or contract_size(spec,easy)[0]<=limit*60:
                continue
            candidates=[]
            for target in week['days']:
                if target['type'] not in {'easy','recovery'} or target.get('prescribed') is False or target.get('editable') is False:continue
                available=limits.get(target.get('day','').lower(),float('inf'))
                if available*60<contract_size(spec,easy)[0]:continue
                stamp=date.fromisoformat(target['date'])
                neighbours=[d for d in all_days if d is not source and d is not target and d['type'] in {'workout','long_run','race'} and abs((date.fromisoformat(d['date'])-stamp).days)<=1]
                if neighbours or any(abs((date.fromisoformat(d)-stamp).days)<=1 for d in prior_hard_dates or []):continue
                candidates.append(target)
            if candidates:
                target=min(candidates,key=lambda d:d['date'])
                old_source={k:deepcopy(source.get(k)) for k in fields}
                old_target={k:deepcopy(target.get(k)) for k in fields}
                source.update(old_target);target.update(old_source)
                notes.append(f"Moved the full quality dose from {source['date']} to {target['date']} to fit available time and retain progression.")
        for day in week['days']:
            limit=limits.get(day.get('day',day.get('day_name','')).lower())
            if limit is None or day.get('prescribed') is False or day.get('editable') is False:continue
            if day['type']=='race':
                if estimated_minutes(day,easy)>limit:
                    notes.append(f"{day['date']}: race duration exceeds normal availability; reserve separate event time.")
                continue
            if day['type']=='rest' or estimated_minutes(day,easy)<=limit:continue
            original=day['title']
            data=deepcopy(loads(day.get('prescription')))
            if data and data.get('segments') and (day['type']=='workout' or data.get('format')=='run_walk'):
                # Remove unstructured easy padding first; preserve all bookends.
                dose_changed=False
                while contract_size(data,easy)[0]>limit*60:
                    dose_changed=True
                    segment=max(data['segments'],key=lambda s:s.get('reps',1)*(s.get('duration_seconds') or (s.get('distance_meters') or 0)/MI*easy))
                    if segment.get('reps',1)>1:
                        segment['reps']-=1
                    elif segment.get('duration_seconds',0)>180:
                        segment['duration_seconds']-=60
                    else:
                        data=None;break
                if data:
                    seconds,meters=contract_size(data,easy)
                    data.update(progression_eligible=False if dose_changed else data.get('progression_eligible',True),
                                evidence_source='schedule_adjusted' if dose_changed else data.get('evidence_source','template'),total_distance_meters=round(meters,2))
                    day.update(prescription=data,distance_miles=round(meters/MI,2),description=render(data),title=('Run/Walk · time fitted' if data.get('format')=='run_walk' else 'Controlled session · time fitted') if dose_changed else f'{original} · time fitted')
                else:
                    _easy(day,math.floor(limit*60/easy*10)/10,easy)
            else:
                _easy(day,math.floor(limit*60/easy*10)/10,easy,long=day['type']=='long_run')
            day['schedule_note']=f"Adapted to {limit} available minutes. Full-dose progression requires the original work prescription."
            notes.append(f"{day['date']}: {original} fitted to {limit} available minutes; unused mileage is not crammed into other days.")
        if developing:
            longs=[d for d in week['days'] if d['type']=='long_run' and d.get('prescribed',True)]
            if longs and not longs[0]['title'].startswith('Run/Walk'):
                long=longs[0]
                for day in week['days']:
                    if day['type'] in {'easy','recovery'} and day.get('prescribed',True):
                        cap=math.floor(long['distance_miles']/1.2*10)/10
                        if day['distance_miles']>cap:_easy(day,cap,easy)
                from datetime import date,timedelta
                after=(date.fromisoformat(long['date'])+timedelta(days=1)).isoformat()
                follow=next((d for d in week['days'] if d['date']==after and d['type'] in {'easy','recovery'} and d.get('prescribed',True)),None)
                if follow:
                    others=[d['distance_miles'] for d in week['days'] if d is not follow and d['type']!='rest' and d['distance_miles']>0]
                    cap=min([sum(d['distance_miles'] for d in week['days'])*.18]+others)
                    if follow['distance_miles']>cap:_easy(follow,math.floor(cap*10)/10,easy)
        week['target_mileage']=round(sum(d['distance_miles'] for d in week['days']),1)
    return notes
