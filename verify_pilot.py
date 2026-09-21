"""Ten existing claims: reproducible formal checks or explicit deferral.

No natural-language proof sketch or LLM vote is a proof certificate.
The two implemented checkers have intentionally narrow, pinned statements.
"""
import hashlib
import itertools
import json
from pathlib import Path
import sys

from mvp_store import init_db, add_evidence, add_support, _now, _uid
from knowledge_policy import POLICY, ROOT, claim_fingerprint, digest, claim_usable

IDS = ['K-0003#c1','K-0010#c1','B-0200#c1','S-0200#c1',
       'B-0100#c1','S-0100#c1','U-0100#c1','U-0200#c1',
       'E-AUTO-10_1145-1566374_1566402#factory-1',
       'E-AUTO-10_1145-1566374_1566402#factory-2']
STATEMENTS = {
 'B-0100#c1': '有限非空集合Dと a* in D に対し、C(f,a*,D)=0 ⟺ a* in argmax_{a in D} f(a)',
 'S-0100#c1': '入札者2人・評価額{0,1,2}の有限第二価格封印入札（同額時順位事前固定）では、正直入札が弱支配戦略であり、正直入札プロファイルがナッシュ均衡になる',
}
SCOPES = {
 'B-0100#c1': '有限非空集合D、実数値関数f、a*∈D。C=max(f(a)-f(a*))。最大値の存在とargmaxの定義を前提とする。',
 'S-0100#c1': '単一財、入札者2人、私的価値、準線形効用、評価額と入札額はいずれも{0,1,2}、同額時は事前固定順位。人間行動や連続入札への一般化なし。',
}


def check_maximum():
    from sympy import symbols, And, Eq, Ge, Le, Gt
    from sympy.logic.inference import satisfiable
    m, fs, fx = symbols('m fs fx', real=True)
    # Finite nonempty D supplies attained maximum m. a* in D gives fs<=m.
    # Forward: m-fs=0 and fx<=m entail fx<=fs for arbitrary x in D.
    forward = satisfiable(And(Eq(m-fs, 0), Le(fx,m), Gt(fx,fs)), use_lra_theory=True)
    # Reverse: maximality of a* applies in particular to the maximizer: m<=fs.
    reverse = satisfiable(And(Ge(m,fs), Le(m,fs), Gt(m-fs,0)), use_lra_theory=True)
    negative = satisfiable(And(Eq(m-fs, 1), Le(fx,m), Gt(fx,fs)), use_lra_theory=True)
    return {'passed': forward is False and reverse is False and negative is not False,
            'method': 'symbolic_real_linear_arithmetic',
            'obligations': {'forward_counterexample': str(forward), 'reverse_counterexample': str(reverse)},
            'negative_control_satisfiable': negative is not False,
            'axioms': ['Finite nonempty real-valued functions attain a maximum.',
                       'max(f-f(a*)) = max(f)-f(a*) by order-preserving translation.',
                       'argmax membership means f(x)<=f(a*) for all x in D.'],
            'limit': 'Checker verifies linear obligations under the explicit maximum/argmax encoding; not arbitrary Japanese theorem understanding.'}


def utility(player, value, bids, tie_winner, first_price=False):
    winner = tie_winner if bids[0] == bids[1] else (0 if bids[0] > bids[1] else 1)
    if player != winner:
        return 0
    price = bids[winner] if first_price else bids[1-winner]
    return value-price


def check_auction(first_price=False):
    failures, checked, ne_failures, ne_checked = [], 0, [], 0
    for tie, i, v, other, alternative in itertools.product(range(2),range(2),range(3),range(3),range(3)):
        truthful = [other, other]; truthful[i] = v
        deviation = truthful.copy(); deviation[i] = alternative
        gain = utility(i,v,deviation,tie,first_price)-utility(i,v,truthful,tie,first_price)
        checked += 1
        if gain > 0:
            failures.append([tie,i,v,other,alternative,gain])
    for tie,v0,v1,i,alternative in itertools.product(range(2),range(3),range(3),range(2),range(3)):
        bids=[v0,v1]; changed=bids.copy(); changed[i]=alternative
        gain=utility(i,bids[i],changed,tie,first_price)-utility(i,bids[i],bids,tie,first_price)
        ne_checked += 1
        if gain > 0:
            ne_failures.append([tie,v0,v1,i,alternative,gain])
    return {'passed': not failures and not ne_failures,
            'method': 'exhaustive_finite_model_check', 'dominance_cases': checked,
            'nash_cases': ne_checked, 'counterexamples': failures,
            'nash_counterexamples': ne_failures, 'domain': [0,1,2],
            'ties': 'both fixed priority orders', 'first_price': first_price}


def asset(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def run_pilot():
    db = init_db()
    directory = ROOT / 'work/verification_pilot'; directory.mkdir(exist_ok=True)
    results = []
    for cid in IDS:
        row = db.execute('SELECT node_id,node_revision,statement,epistemic_status FROM claim WHERE claim_id=?', (cid,)).fetchone()
        if not row:
            raise RuntimeError('Missing pinned pilot claim: '+cid)
        source_digest=digest([list(r) for r in db.execute('''SELECT e.*,sa.rationale FROM support_assessment sa
          JOIN evidence e ON e.evidence_id=sa.evidence_id WHERE sa.target_claim=?
          AND e.evidence_id NOT LIKE 'E-CHECK-%' ORDER BY e.evidence_id,sa.assessment_id''',(cid,))])
        checker_hash=asset(Path(__file__).resolve())['sha256']
        prior=db.execute('SELECT report,fingerprint FROM claim_validation WHERE claim_id=? ORDER BY id DESC LIMIT 1',(cid,)).fetchone()
        if prior:
            old=json.loads(prior[0])
            if (old.get('checker_sha256')==checker_hash and old.get('input_evidence_digest')==source_digest
                    and prior[1]==claim_fingerprint(db,cid)
                    and (old['decision']=='defer' or claim_usable(db,cid))):
                results.append({**old,'reused':True,'newly_usable':False})
                continue
        existing = claim_usable(db,cid)
        report = {'claim_id': cid, 'previous_state': row[3], 'scope': SCOPES.get(cid),
                  'decision': 'defer', 'assets': [], 'evidence_fingerprints': {},
                  'checker_sha256':checker_hash,'input_evidence_digest':source_digest}
        if cid in STATEMENTS and row[2] == STATEMENTS[cid]:
            if cid.startswith('S-0100'):
                node = json.loads(db.execute('SELECT data FROM node WHERE id=? AND revision=?', row[:2]).fetchone()[0])
                if node.get('domain_of_validity') != '単一財、私的価値、入札者2人、準線形効用、評価額・入札額 in {0,1,2}、同額時の順位は事前固定':
                    raise RuntimeError('Auction model scope changed; checker must be reviewed')
                check = check_auction()
                check['negative_control_failed'] = not check_auction(first_price=True)['passed']
                check['passed'] = check['passed'] and check['negative_control_failed']
            else:
                check = check_maximum()
            if not check['passed']:
                raise RuntimeError('Checker failed: '+cid)
            cert = directory / (cid.replace('#','_')+'.json')
            cert.write_text(json.dumps({'claim_id':cid,'statement':row[2], 'scope':SCOPES[cid], 'check':check}, ensure_ascii=False, indent=2), encoding='utf-8')
            eid = 'E-CHECK-'+cid.replace('#','-')
            if not db.execute('SELECT 1 FROM evidence WHERE evidence_id=?',(eid,)).fetchone():
                add_evidence(db,eid,'proof_certificate', source_uri=None,
                    source_version=POLICY,locator=str(cert.relative_to(ROOT)),
                    content_hash=asset(cert)['sha256'],origin_group='formal-check:'+cid,
                    reliability_grade='A',limitations=[SCOPES[cid]])
                add_support(db,eid,row[0],row[1],target_claim=cid,support_role='derivation',
                            rationale='Reproducible checker with stated finite/symbolic scope',assessor='formal_checker_v1')
            else:
                db.execute('UPDATE evidence SET content_hash=? WHERE evidence_id=?',(asset(cert)['sha256'],eid))
            db.execute("UPDATE claim SET epistemic_status='formally_verified' WHERE claim_id=?",(cid,))
            report.update(decision='passed', validated_state='formally_verified', reason='checker_passed',
                          assets=[asset(cert),asset(Path(__file__).resolve())],
                          evidence_fingerprints={eid:digest(list(db.execute('SELECT * FROM evidence WHERE evidence_id=?',(eid,)).fetchone()))},
                          check=check)
        else:
            if cid in ('B-0200#c1','S-0200#c1'):
                reason='proof_sketch_is_not_machine_checked; source_hash_pending; scope_requires_review'
            elif cid in ('K-0003#c1','K-0010#c1'):
                reason='source_hash_pending; source_entailment_uncalibrated; definition_scope_requires_review'
            elif cid.startswith('U-'):
                reason='scope_or_definition_not_formally_encoded'
            elif cid in STATEMENTS:
                reason='pinned_statement_changed'
            else:
                reason='single_source_extraction; independent_entailment_not_validated'
            report['reason'] = reason
        db.execute('''INSERT INTO claim_validation(claim_id,decision,validated_state,fingerprint,policy,report)
                      VALUES (?,?,?,?,?,?)''',
                   (cid,report['decision'],report.get('validated_state'),claim_fingerprint(db,cid),POLICY,json.dumps(report,ensure_ascii=False)))
        db.execute('INSERT INTO event VALUES (?,?,?,?,?,?)',
                   (_uid('ev-'),'claim_validation_recorded',cid,json.dumps(report,ensure_ascii=False),_now(),'verification_pilot'))
        db.commit()
        report['newly_usable'] = not existing and claim_usable(db,cid)
        results.append(report)
    output = {'policy':POLICY,'selected':len(results),'passed':sum(r['decision']=='passed' for r in results),
              'deferred':sum(r['decision']=='defer' for r in results),
              'results':results,'note':'Historical states retained; deferred records block ordinary use.'}
    (directory/'results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k!='results'},ensure_ascii=False))
    db.close()
    return output


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    run_pilot()
