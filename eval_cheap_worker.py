"""Small, inspectable preflight. Synthetic checks are never inserted in the graph."""
import json
from pathlib import Path
from cheap_llm import configure, complete
from evidence_miner import extract_claims_from_abstract
from node_factory import CLASSIFY_PROMPT
from relation_engine import VERIFY_PROMPT, VALID_EDGE_TYPES
from mvp_store import get_db


def main():
    worker = configure(max_calls=5, max_seconds=180, max_reserved_usd=0.02)
    results = {}
    results['negation_and_scope'] = extract_claims_from_abstract(
        'Synthetic evaluation: observational study', 'test fixture', 2026,
        'In an observational sample of 120 adults, X was correlated with Y. '
        'This study does not establish that X causes Y. No statistically significant '
        'association was found among children. The results apply only to the sampled population.')
    results['hypothesis'] = extract_claims_from_abstract(
        'Synthetic evaluation: untested proposal', 'test fixture', 2026,
        'We hypothesize that adding a memory module may improve task completion. '
        'No experiment has been performed. The proposed benefit has not been measured or demonstrated.')
    results['classification'] = json.loads(complete(CLASSIFY_PROMPT.format(
        nodes_list='K-0017 (science/Theory): Information theory and entropy',
        claim_text='Shannon entropy quantifies the uncertainty of a discrete probability distribution.',
        subjects='entropy', evidence_id='TEST-ONLY', claim_type='definitional'),
        task='node_factory', max_tokens=1024))
    results['unrelated_nodes'] = json.loads(complete(VERIFY_PROMPT.format(
        node_a_id='TEST-A', node_a_title='Huffman coding',
        node_a_claims='A1: Huffman coding constructs a prefix code.',
        node_b_id='TEST-B', node_b_title='Plant growth',
        node_b_claims='B1: The study measured plant height in centimeters.',
        co_evidence='(none)', candidate_reason='random test pair',
        edge_types=', '.join(VALID_EDGE_TYPES)), task='relation_engine', max_tokens=1024))
    db = get_db()
    row = db.execute("SELECT evidence_id, abstract_text FROM evidence_mining_log "
                     "WHERE state='mined' AND length(abstract_text)>150 ORDER BY evidence_id LIMIT 1").fetchone()
    if row:
        results['real_source'] = {'evidence_id': row[0], 'source_excerpt': row[1],
            'claims': extract_claims_from_abstract('', '', None, row[1])}
    db.close()
    results['usage'] = worker.summary()
    path = Path('work/cheap_worker_evaluation.json')
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
