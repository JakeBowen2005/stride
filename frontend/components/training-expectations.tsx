"use client";
import {useUnits} from '@/components/unit-preferences';
import {distanceInUnits,unitLabel} from '@/lib/units';
export interface WeekExpectation{week_number:number;run_days:number;planned_miles:number;priority_sessions:{date:string;title:string;purpose?:string;estimated_minutes:number}[];expectation:string;advance_when:string;hold_when:string;reduce_when:string;next_step:string}
/** Each week's key sessions; the progression rules are the same every week, so they're shown once. */
export function TrainingExpectations({weeks}:{weeks:WeekExpectation[]}){
  const units=useUnits();
  if(!weeks.length)return null;
  const rules=weeks[0];
  return <section aria-label="What this block asks of you" className="space-y-3 rounded border p-3">
    <h2 className="font-medium">What this block asks of you</h2>
    <p className="text-sm">{rules.expectation}</p>
    {weeks.map(w=><details key={w.week_number} open={w.week_number===1}>
      <summary className="min-h-11 cursor-pointer text-sm">Week {w.week_number}: {w.run_days} run days · {distanceInUnits(w.planned_miles,units)} {unitLabel(units)}</summary>
      {w.priority_sessions.length
        ? <ul className="my-2 space-y-2">{w.priority_sessions.map(s=><li key={s.date} className="text-sm"><strong>{s.title}</strong> · {s.date} · about {s.estimated_minutes} min{s.purpose&&<p className="text-muted-foreground">{s.purpose}</p>}</li>)}</ul>
        : <p className="my-2 text-sm text-muted-foreground">Easy running only this week.</p>}
    </details>)}
    <div className="space-y-2 border-t pt-2 text-sm">
      <p><strong>Earn the next step:</strong> {rules.advance_when}</p>
      <p><strong>When we hold:</strong> {rules.hold_when}</p>
      <p><strong>When we reduce:</strong> {rules.reduce_when}</p>
      <p className="text-xs text-muted-foreground">Prescribed sessions only; days completed before this block are excluded.</p>
    </div>
  </section>;
}
