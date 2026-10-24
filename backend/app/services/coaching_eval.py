"""Offline audit of saved reviews. Structural checks never substitute for coach grading."""
CRITERIA=('evidence_supported','challenge_appropriate','action_clear','respects_schedule','no_unsupported_physiology')


def evaluate(case):
    context=case['context']
    review=case['review']
    errors=[]
    candidates={c['id'] for c in context.get('candidates',[])}
    insights={i['id'] for i in context.get('historical_profile',{}).get('insights',[])}
    for suggestion in review.get('suggestions',[]):
        if suggestion.get('candidate_id') not in candidates:errors.append('unknown_candidate')
    for insight in review.get('history_insight_ids',[]):
        if insight not in insights:errors.append('unknown_historical_evidence')
    labels=case.get('coach_labels',{})
    missing=[key for key in CRITERIA if key not in labels]
    failed=[key for key in CRITERIA if labels.get(key) is False]
    return {'case_id':case['case_id'],'status':'fail' if errors or failed else 'needs_coach_review' if missing else 'pass',
            'structural_errors':errors,'failed_criteria':failed,'ungraded_criteria':missing}


def main():
    import argparse,json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('saved_reviews',help='Local JSONL; no model or provider calls')
    args=parser.parse_args()
    with open(args.saved_reviews) as source:
        results=[evaluate(json.loads(line)) for line in source if line.strip()]
    print(json.dumps({'results':results,'passed':sum(r['status']=='pass' for r in results),
                     'failed':sum(r['status']=='fail' for r in results),'needs_coach_review':sum(r['status']=='needs_coach_review' for r in results)},indent=2))


if __name__=='__main__':main()
