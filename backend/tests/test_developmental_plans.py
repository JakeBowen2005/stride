"""User-facing progression: purposeful early quality without changing advanced programs."""
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.core import developmental
from app.core.load_policy import plan_load
from app.core.plan_engine import generate_plan
from app.core.workout_data import MI, execution_from_activities
from app.core.workout_evaluator import evaluate_workout, gate_progression

ROOT = Path(__file__).resolve().parents[2]
MONDAY = date(2026, 10, 19)


def plan(**overrides):
    args = dict(goal_type='race', goal_distance='5k', target_time_seconds=1800,
                current_weekly_mileage=8, peak_weekly_mileage=8, experience_level='beginner',
                days_per_week=3, rest_days=['monday', 'wednesday', 'friday', 'sunday'],
                long_run_day='saturday', easy_pace_seconds=720, start_date=MONDAY,
                first_prescribe_date=MONDAY, num_weeks=2, completed_weeks=[8]*4,
                weekly_run_days=[3]*4, deload_is_due=True)
    return generate_plan(**(args | overrides))


def test_stable_easy_history_does_not_force_a_second_week_deload():
    p = plan()
    assert not p['is_deload']
    assert all(w['quality_sessions'] == 1 for w in p['weeks'])
    assert p['weeks'][0]['target_mileage'] == 8
    assert 8 < p['weeks'][1]['target_mileage'] <= 8.8
    assert p['violations'] == []


def test_fatigue_overrides_introductory_workout_and_mileage_growth():
    p = plan(assessment='recovery', fatigue_recovery=True)
    assert all(w['quality_sessions'] == 0 for w in p['weeks'])
    assert max(w['target_mileage'] for w in p['weeks']) <= 8*.7


@pytest.mark.parametrize('history,days', [([0]*4, [0]*4), ([8,8,0,8], [3,3,0,3])])
def test_true_start_or_missed_week_cannot_earn_quality(history, days):
    p = plan(completed_weeks=history, weekly_run_days=days)
    assert all(w['quality_sessions'] == 0 for w in p['weeks'])


def test_low_volume_start_never_invents_a_ten_mile_baseline():
    assert plan_load(0,0,'beginner','race',2,developmental=True).weekly_budgets == [3,3]
    assert plan_load(2,2,'beginner','race',2,developmental=True).weekly_budgets == [2.2,2.4]


def test_short_runs_preserve_four_day_consistency_in_a_down_week():
    dates = [(MONDAY-timedelta(days=i)).isoformat() for i in (3,10,17)]
    p = plan(days_per_week=4, rest_days=['monday','wednesday','friday'],
             quality_evidence={'development_dates':dates})
    assert p['is_deload']
    for w in p['weeks']:
        assert sum(d['distance_miles']>0 for d in w['days']) == 4
        assert w['target_mileage'] <= w['budget_miles']+.01
        assert sum(d['distance_miles'] for d in w['days'] if d['type']=='workout') < w['budget_miles']*.5


def test_introducing_a_new_dose_holds_first_week_then_repeats_while_miles_build():
    p = plan(progression_state={'development':{'current_level':3,'last_completed_level':2}})
    assert p['weeks'][0]['target_mileage'] == 8
    assert p['weeks'][1]['target_mileage'] > 8
    specs = [d['prescription'] for w in p['weeks'] for d in w['days'] if d['type']=='workout']
    assert specs[0]['segments'] == specs[1]['segments']


def test_repeatable_recent_volume_grows_but_spikes_and_breaks_do_not_become_anchors():
    p=plan_load(9.25,11,'beginner','race',2,completed_weeks=[8,8,10,11],developmental=True)
    assert p.planning_anchor == 11 and p.weekly_budgets == [12.1,13.3]
    for history in ([8,8,8,30],[8,8,0,20]):
        baseline=sum(history)/4
        p=plan_load(baseline,30,'beginner','race',2,completed_weeks=history,developmental=True)
        assert p.planning_anchor == baseline


def test_intro_contract_matches_ten_easy_ten_controlled_ten_easy():
    wo=developmental.workout(1,660,12)
    spec=wo['prescription']
    assert spec['warmup']['duration_seconds'] == spec['cooldown']['duration_seconds'] == 600
    assert spec['segments'][0]['duration_seconds'] == 600
    assert spec['segments'][0]['pace_range_sec_per_mile'] is None
    assert 'controlled medium-to-hard effort' in wo['structure']
    assert spec['category']=='development'


def test_ladder_includes_continuous_short_and_long_reps_with_small_dose_steps():
    specs=[developmental.workout(level,660,35)['prescription'] for level in range(1,13)]
    doses=[sum(s['reps']*s['duration_seconds']/60 for s in p['segments']) for p in specs]
    assert all(a<=b<=a+3 for a,b in zip(doses,doses[1:]))
    assert any(s['reps']>1 and s['duration_seconds']<=120 for p in specs for s in p['segments'])
    assert any(s['reps']>1 and s['duration_seconds']>=300 for p in specs for s in p['segments'])
    assert doses[-1] == 20


def evaluation(feel=7, pace=594, fraction=1, labeled=True):
    from app.models.activity import Activity
    spec=developmental.workout(1,660,12)['prescription']
    laps=[{'intensity':'WARMUP','distance_m':600/660*MI,'duration_s':600},
          {'intensity':'ACTIVE','distance_m':600*fraction/pace*MI,'duration_s':600*fraction},
          {'intensity':'COOLDOWN','distance_m':600/660*MI,'duration_s':600}]
    act=Activity(id=1,splits=json.dumps(laps if labeled else []))
    execution=execution_from_activities([act],spec)
    return spec,evaluate_workout(None,None,None,'workout',None,'Controlled Effort',feel,spec,execution)


def test_duration_and_recovery_earn_exposure_without_calibrating_pace():
    spec,ev=evaluation()
    assert ev.decision=='advance' and ev.new_pace_sec is None
    assert gate_progression(ev,spec,1).decision=='advance'  # base is a legitimate introductory phase


@pytest.mark.parametrize('kwargs,decision', [({'feel':None},'hold'),({'feel':3},'regress'),
    ({'fraction':.5},'hold'),({'labeled':False},'insufficient')])
def test_missing_or_poor_evidence_does_not_earn_progression(kwargs,decision):
    assert evaluation(**kwargs)[1].decision==decision


def test_budget_adapted_or_race_week_work_cannot_advance():
    spec,ev=evaluation()
    spec['progression_eligible']=False
    assert gate_progression(ev,spec,1).decision=='hold'


def test_effort_work_has_no_guessed_pace_target_or_athlete_facing_threshold_pace():
    assert evaluation(pace=660)[1].decision=='advance'
    assert set(plan()['pacing_guide'])=={'easy','goal_race_pace'}


@pytest.mark.parametrize('experience,exposures', [('beginner',4),('intermediate',2)])
def test_progression_requires_distinct_successful_exposures(experience,exposures):
    from app.database import SessionLocal
    from app.models.user import User
    from app.models.progression import WorkoutProgression
    from app.api.plans import _load_progression_state,_update_progression_from_evaluation
    with SessionLocal() as db:
        db.get(User,1).experience_level=experience
        _load_progression_state(1,db,'5k')
        state=db.query(WorkoutProgression).filter_by(category='development').one()
        for i in range(exposures):
            _update_progression_from_evaluation(1,'development','advance','Controlled Effort',
                (MONDAY+timedelta(weeks=i)).isoformat(),300,db,program=state.program_key)
        assert state.current_level==2 and state.current_pace_sec is None


def test_race_week_sharpener_and_shakeout_are_smaller_than_the_training_week():
    p=plan(race_date=MONDAY+timedelta(days=6))
    week=p['weeks'][0]
    training=[d for d in week['days'] if d['type']!='race']
    assert sum(d['distance_miles'] for d in training) <= week['budget_miles']+.01
    assert sum(d['distance_miles']>0 for d in week['days'])<=3
    assert max(d['distance_miles'] for d in training)<=2.5
    for d in training:
        if d['type']=='workout':
            assert d['prescription']['phase']=='race_week'
            assert not d['prescription']['progression_eligible']


@pytest.mark.parametrize('scenario,experience,min_peak', [('beginner-5k',None,10),('beginner-mileage',None,20),
    ('beginner-marathon',None,28),('beginner-mileage','intermediate',18)])
def test_entire_program_builds_with_early_quality_and_no_immediate_deload(tmp_path,scenario,experience,min_peak):
    out=tmp_path/'program.md'
    cmd=[sys.executable,str(ROOT/'backend/scripts/simulate_demo_program.py'),scenario,'--start-date','2026-10-21','--out',str(out)]
    if experience:cmd+=['--experience',experience]
    done=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=120)
    assert done.returncode==0,done.stderr[-2500:]
    text=out.read_text()
    rows=[line.split('|')[1:-1] for line in text.splitlines() if line.startswith('| ') and line.split('|')[1].strip().isdigit()]
    assert max(float(row[3]) for row in rows if row[2].strip()!='Race Week')>=min_peak
    assert float(rows[1][3])>=float(rows[0][3])
    assert any('Controlled' in row[-1] for row in rows[:3])
    assert all('**hold**' not in line for line in text.splitlines() if line.startswith('- **Block'))
    assert 'at controlled medium-to-hard effort' in text


def test_returning_from_a_deload_is_not_a_new_spike():
    history=[19.1,21.1,15.8,21.1]
    p=plan_load(sum(history)/4,21.1,'beginner','race',2,completed_weeks=history,developmental=True)
    assert p.planning_anchor==21.1


def test_established_intermediate_keeps_full_quality_instead_of_restarting_intro():
    p=plan(experience_level='intermediate',current_weekly_mileage=35,peak_weekly_mileage=35,
           completed_weeks=[35]*4,weekly_run_days=[5]*4,days_per_week=5,
           rest_days=['friday','sunday'],quality_evidence={'primary_successes':4},deload_is_due=False)
    assert not p['load'].get('developmental')
    assert all(d.get('prescription',{}).get('category')!='development' for w in p['weeks'] for d in w['days'])


@pytest.mark.parametrize('perturbation,decision', [('--miss-week','reduce'),('--poor-week','recovery')])
def test_whole_program_responds_to_interruption_and_bad_recovery(tmp_path,perturbation,decision):
    out=tmp_path/'stress.md'
    done=subprocess.run([sys.executable,str(ROOT/'backend/scripts/simulate_demo_program.py'),
        'beginner-mileage','--start-date','2026-10-21','--weeks','8',perturbation,'4','--out',str(out)],
        cwd=ROOT,capture_output=True,text=True,timeout=120)
    assert done.returncode==0,done.stderr[-2500:]
    assert f'**{decision}**' in out.read_text()


@pytest.mark.parametrize('experience',['beginner','intermediate'])
@pytest.mark.parametrize('days',[3,4,6])
@pytest.mark.parametrize('miles',[2,8,15,30])
@pytest.mark.parametrize('distance',['5k','marathon'])
@pytest.mark.parametrize('weeks_out',[0,8])
def test_developmental_schedule_matrix_respects_frequency_budget_and_spacing(experience,days,miles,distance,weeks_out):
    names=['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
    allowed={3:{1,3,5},4:{1,3,5,6},6:set(range(6))}[days]
    p=plan(experience_level=experience,days_per_week=days,rest_days=[names[i] for i in range(7) if i not in allowed],
           current_weekly_mileage=miles,peak_weekly_mileage=miles,completed_weeks=[miles]*4,
           weekly_run_days=[days]*4,goal_distance=distance,race_date=MONDAY+timedelta(weeks=weeks_out,days=6))
    assert p['violations']==[]
    for w in p['weeks']:
        assert sum(d['distance_miles']>0 for d in w['days'])<=days
        assert sum(d['distance_miles'] for d in w['days'] if d['type']!='race')<=w['budget_miles']+.1


def test_midweek_intro_fills_the_budget_without_shrinking_the_only_long_run():
    p=plan(first_prescribe_date=MONDAY+timedelta(days=2),completed_by_date={(MONDAY+timedelta(days=1)).isoformat():2.5})
    assert p['weeks'][0]['target_mileage']==8
    assert sum(d['distance_miles'] for d in p['weeks'][0]['days'] if d['type']=='long_run')>=2.5


def test_intro_replacement_menu_preserves_effort_track_and_budget():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import SessionLocal
    from app.models.user import Goal,User
    from app.models.plan import Plan,PlannedWorkout
    from app.services.demo_seed import seed_demo
    profile=json.loads((ROOT/'demo/scenarios/beginner-5k.json').read_text())
    with SessionLocal() as db:
        db.query(Goal).delete();db.query(User).delete();db.commit()
        seed_demo(db,profile)
        active=db.query(Plan).filter_by(is_active=True).one()
        day=db.query(PlannedWorkout).filter(PlannedWorkout.plan_id==active.id,PlannedWorkout.type=='workout',
            PlannedWorkout.date>=date.today().isoformat()).order_by(PlannedWorkout.date).first().date
    client=TestClient(app)
    menu=client.get(f'/api/plans/1/sessions/{day}/options?category=intervals')
    assert menu.status_code==200,menu.text
    options=menu.json()['options']
    assert len(options)>=2,menu.text
    for option in options:
        spec=option['prescription']
        assert spec['category']=='development' and spec['progression_eligible'] is False
        assert all(s['pace_range_sec_per_mile'] is None for s in spec['segments'])
    applied=client.post(f'/api/plans/1/sessions/{day}',json={'action':'replace','replacement':'intervals','option_id':options[0]['id']})
    assert applied.status_code==200,applied.text


@pytest.mark.parametrize('scenario',['sub17-5k','sub3-marathon','trail-100k'])
def test_advanced_whole_program_matches_existing_golden_document(tmp_path,scenario):
    out=tmp_path/'advanced.md'
    done=subprocess.run([sys.executable,str(ROOT/'backend/scripts/simulate_demo_program.py'),scenario,
        '--start-date','2026-10-21','--out',str(out)],cwd=ROOT,capture_output=True,text=True,timeout=120)
    assert done.returncode==0,done.stderr[-2500:]
    assert out.read_text()==(ROOT/'docs/demo-programs'/f'{scenario}.md').read_text()
