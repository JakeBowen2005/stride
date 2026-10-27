"""Bounded original-FIT import, no provider calls or paid historical reviews."""
import hashlib
import io
import json
import math
from datetime import timezone
from zoneinfo import ZoneInfo
import fitdecode
from app.models.activity import Activity
from app.models.user import User
from app.models.history import ActivitySource
from app.services.garmin_api import laps_from_fit
from app.services.history_evidence import source_for,capture,PARSER_VERSION

MAX_BYTES=10*1024**2


def read_summary(blob):
    sessions=[]
    with fitdecode.FitReader(io.BytesIO(blob),check_crc=fitdecode.CrcCheck.RAISE) as reader:
        for frame in reader:
            if isinstance(frame,fitdecode.FitDataMessage) and frame.name=='session':
                sessions.append({k:frame.get_value(k,fallback=None) for k in ('sport','start_time','total_distance','total_timer_time','total_elapsed_time','avg_heart_rate','max_heart_rate')})
    if len(sessions)!=1 or str(sessions[0]['sport']).lower()!='running':
        raise ValueError('Import one running session per FIT file.')
    data=sessions[0]
    seconds=data['total_timer_time'] or data['total_elapsed_time']
    distance=data['total_distance']
    if not data['start_time'] or not all(isinstance(v,(float,int)) and math.isfinite(v) and v>0 for v in (seconds,distance)):
        raise ValueError('The FIT file needs a start time, distance and duration.')
    data['seconds']=seconds
    return data


def import_fit(user_id,blob,db):
    if not blob or len(blob)>MAX_BYTES:
        raise ValueError('Choose a FIT file no larger than 10 MiB.')
    digest=hashlib.sha256(blob).hexdigest()
    alias=db.query(ActivitySource).filter_by(user_id=user_id,provider='fit_upload',external_id=digest).first()
    existing=db.get(Activity,alias.activity_id) if alias else db.query(Activity).filter_by(user_id=user_id,source='manual',external_id='fit-'+digest).first()
    if existing:return {'activity_id':existing.id,'duplicate':True}
    data=read_summary(blob)
    user=db.get(User,user_id)
    if not user:raise ValueError('Athlete not found.')
    stamp=data['start_time']
    if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
    local=stamp.astimezone(ZoneInfo(user.timezone or 'America/Los_Angeles')).replace(tzinfo=None)
    laps=laps_from_fit(blob)
    activity=Activity(user_id=user_id,source='manual',external_id='fit-'+digest,name='Imported FIT run',date=local,
                      distance_meters=data['total_distance'],duration_seconds=data['seconds'],elapsed_seconds=data['total_elapsed_time'],
                      average_pace_per_km=data['seconds']/data['total_distance']*1000,average_heartrate=data['avg_heart_rate'],
                      max_heartrate=data['max_heart_rate'],splits=json.dumps(laps),workout_type='easy')
    # Parse and externalize before claiming a SQL writer. Recheck identity under
    # the lock so concurrent uploads cannot create duplicate recordings.
    from app.config import settings
    blob_reference=None
    db.rollback()
    if settings.fit_blob_bucket:
        from app.services.blob_store import put_fit
        blob_reference=put_fit(user_id,blob)
    from app.api.plans import _begin_schedule_write
    _begin_schedule_write(db)
    alias=db.query(ActivitySource).filter_by(user_id=user_id,provider='fit_upload',external_id=digest).first()
    existing=db.get(Activity,alias.activity_id) if alias else db.query(Activity).filter_by(user_id=user_id,source='manual',external_id='fit-'+digest).first()
    if existing:
        return {'activity_id':existing.id,'duplicate':True}
    db.add(activity);db.flush()
    source=source_for(activity,'fit_upload',digest,db)
    capture(source,'fit',db,blob=blob,blob_reference=blob_reference)
    source.enrichment_status,source.parser_version='complete',PARSER_VERSION
    from app.services.garmin import reanalyze_laps
    reanalyze_laps(user_id,db)
    db.commit()
    return {'activity_id':activity.id,'duplicate':False,'laps':len(laps),'message':'Original evidence retained. Historical imports do not queue paid reviews.'}
