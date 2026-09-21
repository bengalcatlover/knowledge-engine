"""Export every claim/edge's current ordinary-use decision and phase evidence."""
import json
import sqlite3
from pathlib import Path
from mvp_store import init_db
from knowledge_policy import claim_usable, edge_usable, independence_metrics


def run():
    db=init_db()
    claims=[]
    for cid,state,node in db.execute('SELECT claim_id,epistemic_status,node_id FROM claim'):
        audit=db.execute('SELECT decision,report FROM claim_validation WHERE claim_id=? ORDER BY id DESC LIMIT 1',(cid,)).fetchone()
        reason=json.loads(audit[1]).get('reason') if audit else 'no_current_validation_record'
        claims.append({'claim_id':cid,'node_id':node,'historical_status':state,
                       'usable':claim_usable(db,cid),'reason':reason})
    edges=[{'edge_id':eid,'type':typ,'usable':edge_usable(db,eid),
            'status':(db.execute('SELECT status FROM edge_review WHERE edge_id=?',(eid,)).fetchone() or ['candidate'])[0]}
           for eid,typ in db.execute('SELECT edge_id,type FROM edge')]
    old=sqlite3.connect('work/mvp_before_policy_implementation.sqlite3')
    old_states=dict(old.execute('SELECT claim_id,epistemic_status FROM claim')); old.close()
    changes=[{'claim_id':c['claim_id'],'before':old_states.get(c['claim_id']),
              'after':c['historical_status']} for c in claims if old_states.get(c['claim_id'])!=c['historical_status']]
    report={'claims':claims,'edges':edges,'claim_count':len(claims),
            'usable_claim_count':sum(c['usable'] for c in claims),
            'usable_edge_count':sum(e['usable'] for e in edges),
            'status_changes':changes,'confirmed_independent_support_claims':independence_metrics(db),
            'integrity':db.execute('PRAGMA integrity_check').fetchone()[0],
            'foreign_key_violations':db.execute('PRAGMA foreign_key_check').fetchall()}
    Path('work/verification_pilot/boundary_inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('claims','edges')},ensure_ascii=False))
    db.close()


if __name__=='__main__': run()
