"""縦串MVP用ノード・エッジ・根拠ストア

第二価格オークションで5層を1本貫通させる実装。
契約テスト(test_mvp_contract.py)のMVPStoreと同じスキーマを使い、
実データを投入する。
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "work" / "mvp.sqlite3"


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS node (
            id TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,
            layer TEXT NOT NULL CHECK(layer IN ('foundation','science','universe','object','practice')),
            type TEXT NOT NULL,
            subtype TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','ready','approved','blocked','stale','superseded','proposed')),
            data TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (id, revision)
        );

        CREATE TABLE IF NOT EXISTS claim (
            claim_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            node_revision INTEGER NOT NULL,
            statement TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('definition','theorem','empirical','abstraction','application_hypothesis')),
            epistemic_status TEXT NOT NULL DEFAULT 'unverified'
                CHECK(epistemic_status IN ('unverified','source_supported','formally_verified','empirically_supported','contradicted')),
            assumptions TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (node_id, node_revision) REFERENCES node(id, revision)
        );

        CREATE TABLE IF NOT EXISTS edge (
            edge_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            from_node TEXT NOT NULL,
            from_revision INTEGER NOT NULL,
            from_claim TEXT,
            to_node TEXT NOT NULL,
            to_revision INTEGER NOT NULL,
            to_claim TEXT,
            scope TEXT,
            rationale TEXT,
            derivation_ref TEXT
        );

        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK(kind IN ('source_excerpt','observation','execution_log','proof_certificate')),
            source_uri TEXT,
            source_version TEXT,
            locator TEXT,
            content_hash TEXT,
            origin_group TEXT,
            reliability_grade TEXT CHECK(reliability_grade IN ('A','B','C') OR reliability_grade IS NULL),
            limitations TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS support_assessment (
            assessment_id TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL,
            target_node TEXT NOT NULL,
            target_revision INTEGER NOT NULL,
            target_claim TEXT,
            support_role TEXT NOT NULL CHECK(support_role IN ('definition','premise','derivation','observation','counterexample')),
            rationale TEXT,
            assessor TEXT,
            assessed_at TEXT,
            FOREIGN KEY (evidence_id) REFERENCES evidence(evidence_id)
        );

        CREATE TABLE IF NOT EXISTS event (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            entity_ref TEXT,
            payload TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'system'
        );

        -- append-only保護
        CREATE TRIGGER IF NOT EXISTS mvp_event_no_update
            BEFORE UPDATE ON event BEGIN SELECT RAISE(ABORT, 'event is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS mvp_event_no_delete
            BEFORE DELETE ON event BEGIN SELECT RAISE(ABORT, 'event is append-only'); END;
    """)
    db.commit()
    from knowledge_policy import init_policy
    init_policy(db)
    return db


def _now():
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix=""):
    return f"{prefix}{uuid.uuid4().hex[:8]}"


# ════════════════════════════════════════════
# ノード操作
# ════════════════════════════════════════════

def add_node(db, id_, revision, layer, type_, subtype=None, status="draft", data=None):
    now = _now()
    db.execute(
        "INSERT INTO node VALUES (?,?,?,?,?,?,?,?,?)",
        (id_, revision, layer, type_, subtype, status, json.dumps(data or {}, ensure_ascii=False), now, now)
    )
    db.execute(
        "INSERT INTO event VALUES (?,?,?,?,?,?)",
        (_uid("ev-"), "node_created", id_, json.dumps({"revision": revision, "layer": layer, "type": type_}), now, "system")
    )
    db.commit()


def add_claim(db, claim_id, node_id, node_rev, statement, kind, epistemic_status="unverified", assumptions=None):
    db.execute(
        "INSERT INTO claim VALUES (?,?,?,?,?,?,?)",
        (claim_id, node_id, node_rev, statement, kind, epistemic_status, json.dumps(assumptions or []))
    )
    db.commit()


def add_edge(db, type_, from_node, from_rev, to_node, to_rev, from_claim=None, to_claim=None, rationale=None, derivation_ref=None, scope=None):
    eid = _uid("edge-")
    db.execute(
        "INSERT INTO edge VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (eid, type_, from_node, from_rev, from_claim, to_node, to_rev, to_claim, scope, rationale, derivation_ref)
    )
    db.commit()
    return eid


def add_evidence(db, evidence_id, kind, source_uri=None, source_version=None, locator=None, content_hash=None, origin_group=None, reliability_grade=None, limitations=None):
    db.execute(
        "INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?)",
        (evidence_id, kind, source_uri, source_version, locator, content_hash, origin_group, reliability_grade, json.dumps(limitations or []))
    )
    db.commit()


def add_support(db, evidence_id, target_node, target_rev, target_claim=None, support_role="premise", rationale=None, assessor="system"):
    aid = _uid("sa-")
    db.execute(
        "INSERT INTO support_assessment VALUES (?,?,?,?,?,?,?,?,?)",
        (aid, evidence_id, target_node, target_rev, target_claim, support_role, rationale, assessor, _now())
    )
    db.commit()
    return aid


def set_status(db, node_id, revision, new_status):
    now = _now()
    db.execute("UPDATE node SET status=?, updated_at=? WHERE id=? AND revision=?", (new_status, now, node_id, revision))
    db.execute(
        "INSERT INTO event VALUES (?,?,?,?,?,?)",
        (_uid("ev-"), "status_changed", node_id, json.dumps({"revision": revision, "new_status": new_status}), now, "system")
    )
    db.commit()


# ════════════════════════════════════════════
# Policy Engine: stale伝播
# ════════════════════════════════════════════

STRUCTURAL_EDGE_TYPES = ("ABSTRACTS_FROM", "DERIVES_FROM", "FORMALIZED_BY")

def _has_independent_proof(db, node_id, revision) -> bool:
    """ノードが独自のproof_certificateを持つか（下位変更の影響を受けない）"""
    count = db.execute("""
        SELECT COUNT(*) FROM support_assessment sa
        JOIN evidence e ON sa.evidence_id = e.evidence_id
        WHERE sa.target_node = ? AND sa.target_revision = ?
          AND e.kind = 'proof_certificate'
    """, (node_id, revision)).fetchone()[0]
    return count > 0


def propagate_stale(db, node_id, revision):
    """指定ノードをstaleにし、ABSTRACTS_FROM/DERIVES_FROM/FORMALIZED_BYの逆方向に伝播。
    独自のproof_certificateを持つノードには伝播しない（B-0100保護）。"""
    set_status(db, node_id, revision, "stale")
    dependents = db.execute(
        "SELECT from_node, from_revision FROM edge WHERE to_node=? AND to_revision=? AND type IN (?,?,?)",
        (node_id, revision, *STRUCTURAL_EDGE_TYPES)
    ).fetchall()
    for dep_id, dep_rev in dependents:
        current = db.execute("SELECT status FROM node WHERE id=? AND revision=?", (dep_id, dep_rev)).fetchone()
        if current and current[0] not in ("stale", "superseded"):
            if _has_independent_proof(db, dep_id, dep_rev):
                continue  # 独自証明を持つノードはstale伝播から保護
            propagate_stale(db, dep_id, dep_rev)


# ════════════════════════════════════════════
# Policy Engine: 承認前チェック
# ════════════════════════════════════════════

def check_approval_readiness(db, node_id, revision) -> list[str]:
    """承認前の不変条件チェック。違反リストを返す（空なら承認可能）"""
    violations = []
    from knowledge_policy import claim_usable
    ids = [r[0] for r in db.execute('SELECT claim_id FROM claim WHERE node_id=? AND node_revision=?', (node_id, revision))]
    if not ids or any(not claim_usable(db, cid, require_node=False) for cid in ids):
        violations.append('claims lack current validation records')

    # 1. content_hashなしの根拠がないか
    rows = db.execute("""
        SELECT e.evidence_id FROM support_assessment sa
        JOIN evidence e ON sa.evidence_id = e.evidence_id
        WHERE sa.target_node = ? AND sa.target_revision = ?
          AND e.content_hash IS NULL
    """, (node_id, revision)).fetchall()
    if rows:
        violations.append(f"evidence without content_hash: {[r[0] for r in rows]}")

    # 2. HYPノードがapprovedになろうとしていないか
    node = db.execute("SELECT subtype, status FROM node WHERE id=? AND revision=?", (node_id, revision)).fetchone()
    if node and node[0] == "HYP":
        violations.append("HYP nodes cannot be approved directly")

    # 3. 根拠経路が存在するか（L1/L2ノードのみ）
    layer = db.execute("SELECT layer FROM node WHERE id=? AND revision=?", (node_id, revision)).fetchone()
    if layer and layer[0] in ("foundation", "science"):
        support_count = db.execute(
            "SELECT COUNT(*) FROM support_assessment WHERE target_node=? AND target_revision=?",
            (node_id, revision)
        ).fetchone()[0]
        if support_count == 0:
            violations.append(f"no evidence path for {node_id}")

    return violations


# ════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════

def dump_graph(db):
    """グラフの概要を表示"""
    print("=== Nodes ===")
    for row in db.execute("SELECT id, revision, layer, type, subtype, status FROM node ORDER BY layer, id"):
        print(f"  {row[0]}@{row[1]}  [{row[2]}/{row[3]}] status={row[5]}")

    print("\n=== Edges ===")
    for row in db.execute("SELECT from_node, type, to_node FROM edge ORDER BY type"):
        print(f"  {row[0]} --{row[1]}--> {row[2]}")

    print("\n=== Evidence ===")
    for row in db.execute("SELECT evidence_id, kind, source_uri, locator, content_hash FROM evidence"):
        print(f"  {row[0]}: {row[1]} | {row[2]} | loc={row[3]} | hash={'OK' if row[4] else 'MISSING'}")

    print("\n=== Support Assessments ===")
    for row in db.execute("SELECT assessment_id, evidence_id, target_node, support_role FROM support_assessment"):
        print(f"  {row[0]}: {row[1]} -> {row[2]} ({row[3]})")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dump"
    db = init_db()
    if cmd == "init":
        print(f"Initialized MVP store: {DB_PATH}")
    elif cmd == "dump":
        dump_graph(db)
    elif cmd == "check":
        node_id = sys.argv[2]
        violations = check_approval_readiness(db, node_id, 1)
        if violations:
            print(f"BLOCKED: {node_id}")
            for v in violations:
                print(f"  - {v}")
        else:
            print(f"READY: {node_id} can be approved")
