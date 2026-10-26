"""Plain-language commitments derived from the approved numeric plan."""
from app.core.time_budget import estimated_minutes


PRIORITY={'workout','long_run','race'}


def _ran(day):
    """What was actually run that day (plan payload's actual.session), or None if not yet run."""
    return (day.get('actual') or {}).get('session')


def _priority_session(day,by_date,easy):
    ran=_ran(day)
    if not ran:
        return {'date':day['date'],'title':day['title'],'purpose':day.get('purpose'),'completed':False,
                'estimated_minutes':round(estimated_minutes(day,easy))}
    # Done: describe the run itself. A swapped long run carries the long-run day's purpose.
    partner=by_date.get(ran['swapped_with']) if ran['swapped_with'] else None
    purpose=(partner or {}).get('purpose') if ran['off_plan'] else day.get('purpose')
    actual=day['actual']
    return {'date':day['date'],'title':ran['title'],'purpose':purpose,'completed':True,
            'planned_title':ran['planned_title'] if ran['off_plan'] else None,'swapped_with':ran['swapped_with'],
            'ran_miles':actual['distance_miles'],'estimated_minutes':round((actual.get('duration_seconds') or 0)/60)}


def expectations(weeks,easy=600):
    result=[]
    for week in weeks:
        days=[d for d in week['days'] if d.get('prescribed',True) and d['type']!='rest' and not d.get('moved_to')]
        by_date={d['date']:d for d in days}
        # Priority follows what was run once a day is done (a long run swapped onto Sunday counts there)
        priority=[d for d in days if (_ran(d) or d)['type'] in PRIORITY]
        done=[d for d in days if d.get('actual')]
        result.append({'week_number':week['week_number'],'run_days':len(days),
            'planned_miles':round(sum(d['distance_miles'] for d in days),1),
            'completed_days':len(done),'ran_miles':round(sum(d['actual']['total_distance_miles'] for d in done),1),
            'priority_sessions':[_priority_session(d,by_date,easy) for d in priority],
            'expectation':'Complete the scheduled frequency, keep easy days conversational, and execute the priority sessions at the prescribed effort.',
            'advance_when':'Complete full primary doses with controlled effort and recover well. Progression follows demonstrated consistency; a reduced session does not earn a higher workout level.',
            'hold_when':'Repeat the dose when execution is incomplete or recovery is uncertain. Missing laps or a missing rating call for clarification, not an invented failure.',
            'reduce_when':'Repeated poor recovery, pain, or excessive effort warrants a lighter session and reassessment.',
            'next_step':'Your block review explains what was earned and whether the next change is volume, work duration, or pace.'})
    return result
