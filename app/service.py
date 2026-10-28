"""Thursday scheduling and durable, reconciled delivery; caller holds worker lock."""
from datetime import datetime
import json
import uuid
from zoneinfo import ZoneInfo
from .domain import Blocked, Place, choose, slack_text
from .sources import collect, DisabledSlack, TemporaryFailure, RejectedDelivery


def due(settings, now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('An aware clock is required')
    local=now.astimezone(ZoneInfo(settings.timezone))
    return local, local.weekday()==3 and local.strftime('%H:%M')>=settings.send_time


def run(settings, store, source, now, slack=None, rng=None):
    local,is_due=due(settings,now)
    if not is_due:return {'status':'idle','detail':'Waiting for Thursday '+settings.send_time+' '+settings.timezone}
    day=local.date().isoformat();row=store.get(settings.mode,day)
    if row and row['status'] in ('sent','previewed'):
        return {'status':row['status'],'duplicate':True,'message_id':row['message_id']}
    if row and row['context']!=settings.context():
        raise Blocked('Pending weekly configuration changed; reconcile the saved choice before continuing')
    if row is None:
        place=choose(collect(settings,source),settings,rng)
        key=str(uuid.uuid5(uuid.NAMESPACE_URL,settings.mode+':'+settings.channel+':'+day))
        row=store.reserve(settings.mode,day,settings.context(),place,key)
    place=Place(**json.loads(row['place']));text=slack_text(place)
    if settings.mode=='preview':
        store.update(settings.mode,day,status='previewed',detail='Preview only; no Slack delivery')
        return {'status':'previewed','message':text,'sources':place.sources,'day':day}
    slack=slack or DisabledSlack()
    # Always reconcile before a write, including after a process crashed in post().
    try:found=slack.lookup(settings.channel,row['delivery_key'])
    except Exception as error:raise Blocked('Slack delivery lookup unavailable; no write attempted') from error
    if found.state=='present' and isinstance(found.message_id,str) and found.message_id.strip():
        store.update(settings.mode,day,status='sent',message_id=found.message_id,detail=None)
        return {'status':'sent','message_id':found.message_id,'reconciled':True}
    if found.state!='absent':raise Blocked('Slack delivery outcome unknown; authoritative lookup required')
    if row['status']=='failed' or row['attempts']>=3:
        store.update(settings.mode,day,status='failed',detail='Three-attempt delivery budget exhausted')
        raise Blocked('Weekly delivery stopped; attempt budget exhausted')
    if now.timestamp()<row['next_at']:return {'status':'retry_wait','attempts':row['attempts']}
    attempts=row['attempts']+1
    store.update(settings.mode,day,status='sending',attempts=attempts,next_at=now.timestamp()+600)
    try:
        ack=slack.post(settings.channel,text,row['delivery_key'])
        if not isinstance(ack,str) or not ack.strip():raise RuntimeError('Missing acknowledgement')
    except RejectedDelivery:
        store.update(settings.mode,day,status='failed',detail='Slack rejected delivery')
        raise Blocked('Slack rejected delivery; operator action required')
    except TemporaryFailure:
        store.update(settings.mode,day,status='failed' if attempts>=3 else 'pending',detail='Transient delivery failure')
        return {'status':'failed' if attempts>=3 else 'retry_wait','attempts':attempts}
    except Exception:
        store.update(settings.mode,day,status='uncertain',detail='Delivery outcome unknown; reconcile before retry')
        return {'status':'uncertain','attempts':attempts}
    store.update(settings.mode,day,status='sent',message_id=ack,detail=None)
    return {'status':'sent','message_id':ack}
