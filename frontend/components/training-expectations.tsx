"use client";
import {useUnits} from '@/components/unit-preferences';
import {distanceInUnits,unitLabel} from '@/lib/units';
import {formatDateShort} from '@/lib/format';
export interface WeekExpectation{week_number:number;run_days:number;planned_miles:number;completed_days?:number;ran_miles?:number;priority_sessions:{date:string;title:string;purpose?:string|null;estimated_minutes:number;completed?:boolean;planned_title?:string|null;swapped_with?:string|null;ran_miles?:number}[];expectation:string;advance_when:string;hold_when:string;reduce_when:string;next_step:string}
/** Each week's key sessions; the progression rules are the same every week, so they're shown once. */
export function TrainingExpectations({weeks}:{weeks:WeekExpectation[]}){
  const units=useUnits();
  if(!weeks.length)return null;
  const rules=weeks[0];
  return <section aria-label="What this block asks of you" className="glass space-y-3 p-4 sm:p-5">
    <h2 className="text-[13px] font-bold">What this block asks of you</h2>
    <p className="text-sm">{rules.expectation}</p>
    {weeks.map(w=><details key={w.week_number} open={w.week_number===1} className="glass-tile px-3.5 py-1">
      <summary className="flex min-h-11 cursor-pointer items-center text-sm font-semibold">Week {w.week_number}: {w.run_days} run days · {distanceInUnits(w.planned_miles,units)} {unitLabel(units)}{w.completed_days?<span className="ml-1 font-normal text-muted-foreground">· ran {distanceInUnits(w.ran_miles??0,units)} on {w.completed_days} of {w.run_days} days</span>:null}</summary>
      {w.priority_sessions.length
        ? <ul className="my-2 space-y-2">{w.priority_sessions.map(s=><li key={s.date} className="text-sm">{s.completed&&<span aria-label="done" style={{color:"var(--accent-warm)"}}>✓ </span>}<strong>{s.title}</strong> · {formatDateShort(s.date)} · {s.completed?<>{distanceInUnits(s.ran_miles??0,units)} {unitLabel(units)} in {s.estimated_minutes} min</>:<>about {s.estimated_minutes} min</>}
          {(s.planned_title||s.swapped_with)&&<span className="text-muted-foreground">{s.swapped_with?` · swapped with ${new Date(`${s.swapped_with}T12:00:00`).toLocaleDateString("en-US",{weekday:"short"})}`:""}{s.planned_title?<> · planned <span className="line-through">{s.planned_title}</span></>:null}</span>}
          {s.purpose&&<p className="text-muted-foreground">{s.purpose}</p>}</li>)}</ul>
        : <p className="my-2 text-sm text-muted-foreground">Easy running only this week.</p>}
    </details>)}
    <div className="space-y-2 border-t border-[var(--glass-border)] pt-3 text-sm">
      <p><strong>Earn the next step:</strong> {rules.advance_when}</p>
      <p><strong>When we hold:</strong> {rules.hold_when}</p>
      <p><strong>When we reduce:</strong> {rules.reduce_when}</p>
      <p className="text-xs text-muted-foreground">Prescribed sessions only; days completed before this block are excluded.</p>
    </div>
  </section>;
}
