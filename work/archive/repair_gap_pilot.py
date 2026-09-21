"""One demand gap: collect a local certificate, rerun its checker, answer in scope.

Questions remain questions. Never promote Q-0100#q1 into a factual claim.
"""
import json
from pathlib import Path
from mvp_store import init_db,_now,_uid
from knowledge_policy import claim_usable
from verify_pilot import check_auction,SCOPES
from answer_service import answer


def run():
    db=init_db()
    gap=db.execute("SELECT gap_id,state,attempts,max_attempts FROM gap WHERE anchor_claim='Q-0100#q1'").fetchone()
    if not gap: raise RuntimeError('Pinned demand gap missing')
    previous=db.execute("SELECT payload FROM event WHERE event_type='scoped_gap_answered' AND entity_ref=? ORDER BY occurred_at DESC LIMIT 1",(gap[0],)).fetchone()
    if (previous and claim_usable(db,'S-0100#c1')
            and json.loads(previous[0]).get('scope_added_from_explicit_model')==SCOPES['S-0100#c1']):
        print('Already resolved; no repeat work')
        return json.loads(previous[0])
    if gap[2]>=gap[3]: raise RuntimeError('Gap retry budget exhausted')
    db.execute('UPDATE gap SET attempts=attempts+1,updated_at=? WHERE gap_id=?',(_now(),gap[0])); db.commit()
    original=db.execute("SELECT statement FROM claim WHERE claim_id='Q-0100#q1'").fetchone()[0]
    before=answer(original,db=db)
    cid='S-0100#c1'
    collected=db.execute('SELECT report FROM claim_validation WHERE claim_id=? ORDER BY id DESC LIMIT 1',(cid,)).fetchone()
    checked=bool(collected and claim_usable(db,cid) and check_auction()['passed'])
    if not checked:
        result={'gap_id':gap[0],'state':'needs_review','reason':'current_certificate_unavailable','before':before}
    else:
        question='単一財・2人・私的価値・準線形効用・評価額と入札額{0,1,2}・同額時順位固定の第二価格封印入札で、相手の入札を固定したまま正直入札から自分だけ変えて効用を増やせるか？'
        after=answer(question,selector=lambda p:json.dumps({'answerable':True,'claim_ids':[cid]}),db=db)
        result={'gap_id':gap[0],'state':'resolved' if after['status']=='answered' else 'needs_review',
                'resolution_kind':'scoped_question_answer','original_question':original,
                'scope_added_from_explicit_model':SCOPES[cid], 'scope_was_not_assumed_universally':True,
                'before':before,'after':after,'collected_evidence':list(json.loads(collected[0])['evidence_fingerprints']),
                'fresh_exhaustive_check':checked,'question_claim_promoted':False,'external_api_calls':0}
    db.execute('UPDATE gap SET state=?,result=?,updated_at=? WHERE gap_id=?',
               (result['state'],json.dumps(result,ensure_ascii=False),_now(),gap[0]))
    db.execute('INSERT INTO event VALUES (?,?,?,?,?,?)',(_uid('ev-'),'scoped_gap_answered',gap[0],json.dumps(result,ensure_ascii=False),_now(),'gap_pilot'))
    db.commit(); db.close()
    Path('work/verification_pilot/gap_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('before','after')},ensure_ascii=False))
    return result


if __name__=='__main__': run()
