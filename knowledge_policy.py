"""Single fail-closed boundary for ordinary retrieval, reasoning and promotion.

Raw database and explicit include_candidates access are diagnostic only.
Scientific usability requires a current validation record, not just a node label.
"""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
POLICY = 'boundary-v1'
VALID_STATES = {'formally_verified', 'source_supported', 'empirically_supported'}


def init_policy(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS edge_review (
        edge_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'candidate'
        CHECK(status IN ('candidate','validated','rejected')), fingerprint TEXT, report TEXT);
      CREATE TABLE IF NOT EXISTS claim_validation (
        id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id TEXT NOT NULL,
        decision TEXT NOT NULL CHECK(decision IN ('passed','defer','rejected')),
        validated_state TEXT, fingerprint TEXT NOT NULL, policy TEXT NOT NULL,
        report TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
      CREATE TRIGGER IF NOT EXISTS validation_no_update BEFORE UPDATE ON claim_validation
        BEGIN SELECT RAISE(ABORT,'validation is append-only'); END;
      CREATE TRIGGER IF NOT EXISTS validation_no_delete BEFORE DELETE ON claim_validation
        BEGIN SELECT RAISE(ABORT,'validation is append-only'); END;
      INSERT OR IGNORE INTO edge_review(edge_id) SELECT edge_id FROM edge;
      CREATE TRIGGER IF NOT EXISTS edge_candidate_default AFTER INSERT ON edge
        BEGIN INSERT OR IGNORE INTO edge_review(edge_id) VALUES (NEW.edge_id); END;
      CREATE TABLE IF NOT EXISTS evidence_lineage (
        evidence_id TEXT PRIMARY KEY, canonical_work TEXT,
        independent_group TEXT, independence_review TEXT NOT NULL DEFAULT 'unreviewed',
        metadata_fingerprint TEXT NOT NULL);
    ''')
    for row in db.execute('SELECT * FROM evidence').fetchall():
        canonical = canonical_work(row[2])
        prior = db.execute('SELECT metadata_fingerprint FROM evidence_lineage WHERE evidence_id=?',(row[0],)).fetchone()
        if not prior or prior[0] != digest(list(row)):
            db.execute('INSERT OR REPLACE INTO evidence_lineage VALUES (?,?,NULL,?,?)',
                       (row[0],canonical,'unreviewed',digest(list(row))))
    db.commit()


def canonical_work(uri):
    if not uri:
        return None
    value=unquote(uri.strip()).lower()
    value=re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:)', '', value)
    if re.fullmatch(r'10\.\d{4,9}/\S+', value):
        return 'doi:'+value
    return None  # missing DOI is unknown, never a new independent evidence group


def independence_metrics(db):
    counts=[]
    try:
        for (cid,) in db.execute('SELECT claim_id FROM claim'):
            groups=set()
            for row in db.execute('''SELECT e.*,l.independent_group,l.metadata_fingerprint
              FROM support_assessment sa JOIN evidence e ON e.evidence_id=sa.evidence_id
              JOIN evidence_lineage l ON l.evidence_id=e.evidence_id
              WHERE sa.target_claim=? AND l.independence_review='confirmed' ''',(cid,)):
                if row[9] and row[10]==digest(list(row[:9])): groups.add(row[9])
            if len(groups)>=2: counts.append(cid)
    except sqlite3.OperationalError:
        return 0
    return len(counts)


def digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def claim_fingerprint(db, claim_id):
    row = db.execute('''SELECT c.claim_id,c.node_id,c.node_revision,c.statement,c.kind,c.assumptions,
          n.status,n.subtype,n.data FROM claim c JOIN node n ON n.id=c.node_id
          AND n.revision=c.node_revision WHERE c.claim_id=?''', (claim_id,)).fetchone()
    return digest(list(row)) if row else None


def asset_valid(asset):
    try:
        path = (ROOT / asset['path']).resolve()
        if not path.is_relative_to(ROOT) or 'mitocw-txt' in path.parts:
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == asset['sha256']
    except (OSError, KeyError, TypeError):
        return False


def claim_usable(db, claim_id, require_node=True):
    row = db.execute('''SELECT c.epistemic_status,c.kind,n.status,n.subtype FROM claim c
          JOIN node n ON n.id=c.node_id AND n.revision=c.node_revision WHERE c.claim_id=?''',
          (claim_id,)).fetchone()
    if not row or row[0] not in VALID_STATES or row[1] == 'application_hypothesis' or row[3] == 'HYP':
        return False
    if require_node and row[2] != 'approved':
        return False
    if row[2] in ('blocked','stale','superseded'):
        return False
    try:
        audit = db.execute('''SELECT decision,validated_state,fingerprint,policy,report
              FROM claim_validation WHERE claim_id=? ORDER BY id DESC LIMIT 1''', (claim_id,)).fetchone()
    except sqlite3.OperationalError:
        return False  # unmigrated databases are not implicitly trusted
    if not audit or audit[0] != 'passed' or audit[1] != row[0] or audit[3] != POLICY:
        return False
    if audit[2] != claim_fingerprint(db, claim_id):
        return False
    try:
        report = json.loads(audit[4])
        if not report.get('scope') or not report.get('assets') or not all(asset_valid(a) for a in report['assets']):
            return False
        for eid, expected in report.get('evidence_fingerprints', {}).items():
            ev = db.execute('SELECT * FROM evidence WHERE evidence_id=?', (eid,)).fetchone()
            if not ev or digest(list(ev)) != expected:
                return False
            if not db.execute('SELECT 1 FROM support_assessment WHERE evidence_id=? AND target_claim=?',
                              (eid, claim_id)).fetchone():
                return False
        return bool(report.get('evidence_fingerprints'))
    except (ValueError, TypeError, KeyError):
        return False


def node_usable(db, node_id, revision):
    return any(claim_usable(db, r[0]) for r in db.execute(
        'SELECT claim_id FROM claim WHERE node_id=? AND node_revision=?', (node_id, revision)))


def edge_usable(db, edge_id):
    row = db.execute('SELECT * FROM edge WHERE edge_id=?', (edge_id,)).fetchone()
    if not row or '[HYP_EDGE]' in (row[9] or ''):
        return False
    try:
        review = db.execute('SELECT status,fingerprint FROM edge_review WHERE edge_id=?', (edge_id,)).fetchone()
    except sqlite3.OperationalError:
        return False
    return bool(review and review[0] == 'validated' and review[1] == digest(list(row))
                and node_usable(db, row[2], row[3]) and node_usable(db, row[5], row[6])
                and row[4] and row[7] and claim_usable(db, row[4]) and claim_usable(db, row[7]))


def note_usable(role, path, root=ROOT):
    """Recheck current source, even when an old inbox/vector index still exists."""
    relative = Path(str(path).replace('\\', '/'))
    if role not in {'accepted','concepts','perspectives'} or '_inbox' in relative.parts:
        return False
    full = (root / relative).resolve()
    if not full.is_relative_to(root.resolve()) or not full.is_file():
        return False
    text = full.read_text(encoding='utf-8')
    if not text.startswith('---'):
        return False
    head = text.split('---', 2)[1]
    if role == 'perspectives':
        return bool(re.search(r'^user_confirmed:\s*true\s*$', head, re.M | re.I))
    return bool(re.search(r'^status:\s*[\"\']?(approved|accepted)[\"\']?\s*$', head, re.M))


def usable_claim_rows(db):
    names = ('claim_id','node_id','revision','statement','kind','epistemic_status','assumptions')
    return [dict(zip(names, r)) for r in db.execute(
        'SELECT claim_id,node_id,node_revision,statement,kind,epistemic_status,assumptions FROM claim')
        if claim_usable(db, r[0])]
