import json
import sqlite3
import hashlib
from pathlib import Path
import pytest
import knowledge_policy as policy
import mvp_store


@pytest.fixture
def store(tmp_path,monkeypatch):
    monkeypatch.setattr(mvp_store,'DB_PATH',tmp_path/'mvp.db')
    monkeypatch.setattr(policy,'ROOT',tmp_path)
    db=mvp_store.init_db()
    mvp_store.add_node(db,'N',1,'science','Theory',status='approved')
    mvp_store.add_claim(db,'N#1','N',1,'A bounded test statement','theorem','formally_verified')
    cert=tmp_path/'cert.txt'; cert.write_text('proof',encoding='utf-8')
    h=hashlib.sha256(cert.read_bytes()).hexdigest()
    mvp_store.add_evidence(db,'E','proof_certificate',locator='cert.txt',content_hash=h)
    mvp_store.add_support(db,'E','N',1,target_claim='N#1')
    report={'scope':'bounded fixture', 'assets':[{'path':'cert.txt','sha256':h}],
            'evidence_fingerprints':{'E':policy.digest(list(db.execute('SELECT * FROM evidence').fetchone()))}}
    db.execute('INSERT INTO claim_validation(claim_id,decision,validated_state,fingerprint,policy,report) VALUES (?,?,?,?,?,?)',
               ('N#1','passed','formally_verified',policy.claim_fingerprint(db,'N#1'),policy.POLICY,json.dumps(report)))
    db.commit()
    yield db
    db.close()


def test_node_approval_does_not_validate_all_claims(store,monkeypatch):
    import search_engine
    monkeypatch.setattr(search_engine,'_get_mvp_db',lambda:store)
    mvp_store.add_claim(store,'N#2','N',1,'Unverified leak marker','theorem')
    assert policy.claim_usable(store,'N#1')
    assert not policy.claim_usable(store,'N#2')
    assert [c['claim_id'] for c in search_engine.trace_evidence_chain('N',1)['claims']]==['N#1']
    assert len(search_engine.trace_evidence_chain('N',1,True)['claims'])==2


@pytest.mark.parametrize('status',['proposed','blocked','stale','draft'])
def test_nonapproved_nodes_excluded(store,status):
    store.execute('UPDATE node SET status=?',(status,))
    assert not policy.node_usable(store,'N',1)


def test_hyp_excluded(store):
    store.execute("UPDATE node SET subtype='HYP'")
    assert not policy.claim_usable(store,'N#1')


def test_statement_or_asset_changes_invalidate(store,tmp_path):
    assert policy.claim_usable(store,'N#1')
    (tmp_path/'cert.txt').write_text('altered',encoding='utf-8')
    assert not policy.claim_usable(store,'N#1')
    (tmp_path/'cert.txt').write_text('proof',encoding='utf-8')
    store.execute("UPDATE claim SET statement='stronger claim'")
    assert not policy.claim_usable(store,'N#1')


def test_evidence_change_invalidates(store):
    store.execute("UPDATE evidence SET content_hash='pending_verification'")
    assert not policy.claim_usable(store,'N#1')


def test_legacy_and_hyp_edges_not_usable(store):
    mvp_store.add_edge(store,'DEPENDS_ON','N',1,'N',1,rationale='[HYP_EDGE] example')
    eid=store.execute('SELECT edge_id FROM edge').fetchone()[0]
    assert not policy.edge_usable(store,eid)
    policy.init_policy(store)
    assert store.execute('SELECT status FROM edge_review').fetchone()[0]=='candidate'


def test_old_inbox_index_and_rebuild(tmp_path,monkeypatch,capsys):
    import brain_rag
    monkeypatch.setattr(brain_rag,'ROOT',tmp_path)
    monkeypatch.setattr(brain_rag,'DATABASE',tmp_path/'brain.db')
    inbox=tmp_path/'concepts/_inbox'; inbox.mkdir(parents=True)
    (inbox/'K-1.md').write_text('---\nstatus: approved\n---\nsecretmarker',encoding='utf-8')
    brain_rag.build(include_inbox=True); capsys.readouterr()
    brain_rag.search('secretmarker',6,None)
    assert 'secretmarker' not in capsys.readouterr().out
    brain_rag.build(); capsys.readouterr()
    assert brain_rag.connection().execute('SELECT count(*) FROM notes').fetchone()[0]==0


def test_old_vector_index_filtered(tmp_path,monkeypatch):
    import search_engine as se
    import numpy as np
    monkeypatch.setattr(se,'ROOT',tmp_path)
    monkeypatch.setattr(se,'DATABASE',tmp_path/'search.db')
    monkeypatch.setattr(se,'EMBED_FILE',tmp_path/'embeddings.npz')
    monkeypatch.setattr(se,'embed_batch',lambda x:[[1.0,0.0]])
    db=se.get_db()
    db.execute('INSERT INTO docs VALUES (?,?,?,?,?,?,?,?)',('leak','','','','','K-X','concepts','concepts/_inbox/K-X.md')); db.commit()
    np.savez(se.EMBED_FILE,ref_ids=np.array(['K-X']),embeddings=np.array([[1.,0.]]))
    assert se.bm25_search(db,'leak')==[]
    assert se.vector_search('leak')==[]
    assert se.resolve_to_nodes(['NONEXISTENT'])==[]


def test_graph_direct_candidate_rejected():
    import graph
    card={'id':'K-X','title':'leak','definition':'leak','path':'concepts/_inbox/K-X.md','status':'approved'}
    assert graph.traverse({'K-X':card},'K-X')==[]
    assert graph.resolve(card)['definition']==''


def test_answer_cannot_invent_id_or_text(store):
    from answer_service import answer
    from unittest.mock import patch
    # This fixture tests rendering/injected IDs independently of domain routing.
    with patch('answer_service.scope_gate', return_value=True):
        return _check_answer_rendering(store,answer)


def _check_answer_rendering(store,answer):
    denied=answer('query',selector=lambda p:'{"answerable":true,"claim_ids":["fake"]}',db=store)
    assert denied['status']=='abstain'
    allowed=answer('query',selector=lambda p:'{"answerable":true,"claim_ids":["N#1"],"answer":"invented"}',db=store)
    assert allowed['status']=='answered'
    assert 'invented' not in allowed['answer']


@pytest.mark.parametrize('q',[
    '第二価格オークションなら常に正直が最適？',
    '3人で連続入札する第二価格オークションで正直が最適？',
    'For a finite empty set D, is an argmax guaranteed?',
    '無限非空集合Dで最大値は存在するか？',
    '単一財・2人・私的価値・準線形効用・評価額と入札額{0,1,2}・同額時順位固定でも、人間は必ず正直入札するか？',
])
def test_holdout_scope_rejections(q):
    from answer_service import scope_gate
    assert not scope_gate(q,'S-0100#c1')
    assert not scope_gate(q,'B-0100#c1')


def test_nonempty_scope_is_not_empty():
    from answer_service import scope_gate
    assert scope_gate('有限非空集合Dで最大改善量は0か？','B-0100#c1')


def test_doi_variants_are_not_independent():
    assert policy.canonical_work('DOI:10.1000/ABC')==policy.canonical_work('https://doi.org/10.1000/abc')
    assert policy.canonical_work('unknown') is None


def test_no_independence_from_assessor_names(store):
    mvp_store.add_support(store,'E','N',1,target_claim='N#1',assessor='a_different_model')
    policy.init_policy(store)
    assert policy.independence_metrics(store)==0


def test_candidate_edges_cannot_resolve_gaps(store):
    from gap_detector import init_gap_table
    from relation_engine import resolve_g3_gaps
    init_gap_table(store)
    eid=mvp_store.add_edge(store,'DEPENDS_ON','N',1,'N',1,rationale='candidate')
    store.execute('INSERT INTO gap(gap_id,fingerprint,gap_type,anchor_claim,scope,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
        ('g','f','unverified_edge',eid,json.dumps({'from_node':'N','to_node':'N'}),'now','now'))
    assert resolve_g3_gaps(store,verbose=False)['resolved']==0
    assert store.execute('SELECT state FROM gap').fetchone()[0]=='open'


def test_promotion_requires_audited_claims(store):
    from node_factory import check_promotion
    mvp_store.add_claim(store,'N#2','N',1,'unverified','theorem')
    assert not check_promotion(store,'N')['eligible']


def test_formal_checkers_and_negative_controls():
    from verify_pilot import check_auction,check_maximum
    assert check_maximum()['passed']
    assert check_auction()['passed']
    assert not check_auction(first_price=True)['passed']
