import json
from pathlib import Path
from cheap_llm import configure
from answer_service import answer


def run():
    cases=json.loads(Path('work/reuse_cases.json').read_text(encoding='utf-8'))
    worker=configure(max_calls=10,max_seconds=180,max_reserved_usd=0.02)
    results=[]
    for case in cases:
        result=answer(case['query'])
        passed=result['status']==case['expected']
        if case.get('claim'): passed=passed and case['claim'] in result['claim_ids']
        results.append({'case':case,'passed':passed,'result':result})
        print(case['id'],result['status'],'PASS' if passed else 'FAIL',flush=True)
    report={'passed':sum(r['passed'] for r in results),'total':len(results),
            'answered_expected':sum(r['passed'] for r in results if r['case']['expected']=='answered'),
            'abstained_expected':sum(r['passed'] for r in results if r['case']['expected']=='abstain'),
            'usage':worker.summary(),'results':results,
            'limit':'Two narrowly checked claims, five supported queries and five out-of-scope queries; not open-domain QA accuracy.'}
    Path('work/verification_pilot/reuse_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False))
    return report


if __name__=='__main__':
    run()
