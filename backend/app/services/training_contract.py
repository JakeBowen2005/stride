"""Plain-language commitments derived from the approved numeric plan."""
from app.core.time_budget import estimated_minutes


def expectations(weeks,easy=600):
    result=[]
    for week in weeks:
        days=[d for d in week['days'] if d.get('prescribed',True) and d['type']!='rest' and not d.get('moved_to')]
        priority=[d for d in days if d['type'] in {'workout','long_run','race'}]
        result.append({'week_number':week['week_number'],'run_days':len(days),
            'planned_miles':round(sum(d['distance_miles'] for d in days),1),
            'priority_sessions':[{'date':d['date'],'title':d['title'],'purpose':d.get('purpose'),
                'estimated_minutes':round(estimated_minutes(d,easy))} for d in priority],
            'expectation':'Complete the scheduled frequency, keep easy days conversational, and execute the priority sessions at the prescribed effort.',
            'advance_when':'Complete full primary doses with controlled effort and recover well. Progression follows demonstrated consistency; a reduced session does not earn a higher workout level.',
            'hold_when':'Repeat the dose when execution is incomplete or recovery is uncertain. Missing laps or a missing rating call for clarification, not an invented failure.',
            'reduce_when':'Repeated poor recovery, pain, or excessive effort warrants a lighter session and reassessment.',
            'next_step':'Your block review explains what was earned and whether the next change is volume, work duration, or pace.'})
    return result
