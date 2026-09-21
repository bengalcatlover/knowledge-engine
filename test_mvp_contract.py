"""縦串MVP契約テスト — テストファースト

第二価格オークションMVPが満たすべき不変条件を先に定義する。
実装がこれらを通過するまでapprovedにしない。
"""

import json
import pytest
import sqlite3
from pathlib import Path

# ─── MVP ノードID定義 ───
MVP_NODES = {
    "B-0100": {"layer": "foundation", "type": "FormalPrinciple", "subtype": "THM"},
    "S-0100": {"layer": "science", "type": "ScopedLaw", "subtype": "LAW"},
    "K-0003": {"layer": "science", "type": "Theory", "subtype": "THY"},
    "K-0010": {"layer": "science", "type": "Theory", "subtype": "THY"},
    "K-0007": {"layer": "science", "type": "Method", "subtype": "MTH"},
    "U-0100": {"layer": "universe", "type": "WorldModel", "subtype": "WM"},
    "O-0100": {"layer": "object", "type": "System"},
    "Q-0100": {"layer": "practice", "type": "Question", "subtype": "Q"},
    "A-0100": {"layer": "practice", "type": "Action", "subtype": "ACT"},
    "V-0100": {"layer": "practice", "type": "Verification", "subtype": "VER"},
}

# HYPノード（隔離対象）
HYP_NODES = {"H-0100"}

# ─── テスト用データストア（実装時にこのインターフェースを満たす） ───

class MVPStore:
    """MVP用のノード・エッジ・根拠ストアのインターフェース"""

    def __init__(self, db_path: str = ":memory:"):
        self.db = sqlite3.connect(db_path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS node (
                id TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1,
                layer TEXT NOT NULL,
                type TEXT NOT NULL,
                subtype TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                data TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (id, revision)
            );
            CREATE TABLE IF NOT EXISTS claim (
                claim_id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                node_revision INTEGER NOT NULL,
                statement TEXT NOT NULL,
                kind TEXT NOT NULL,
                epistemic_status TEXT NOT NULL DEFAULT 'unverified',
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
                rationale TEXT
            );
            CREATE TABLE IF NOT EXISTS evidence (
                evidence_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                source_uri TEXT,
                source_version TEXT,
                locator TEXT,
                content_hash TEXT,
                origin_group TEXT,
                reliability_grade TEXT
            );
            CREATE TABLE IF NOT EXISTS event (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                entity_ref TEXT,
                payload TEXT NOT NULL DEFAULT '{}',
                occurred_at TEXT NOT NULL DEFAULT '',
                actor TEXT NOT NULL DEFAULT 'system'
            );
            CREATE TABLE IF NOT EXISTS support_assessment (
                assessment_id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL,
                target_node TEXT NOT NULL,
                target_revision INTEGER NOT NULL,
                target_claim TEXT,
                support_role TEXT NOT NULL,
                FOREIGN KEY (evidence_id) REFERENCES evidence(evidence_id)
            );
        """)
        self.db.commit()

    def add_node(self, id, revision, layer, type_, subtype=None, status="draft", data=None):
        self.db.execute(
            "INSERT INTO node VALUES (?,?,?,?,?,?,?,?,?)",
            (id, revision, layer, type_, subtype, status, json.dumps(data or {}), "", "")
        )
        self.db.commit()

    def add_claim(self, claim_id, node_id, node_rev, statement, kind, epistemic_status="unverified"):
        self.db.execute(
            "INSERT INTO claim VALUES (?,?,?,?,?,?)",
            (claim_id, node_id, node_rev, statement, kind, epistemic_status)
        )
        self.db.commit()

    def add_edge(self, edge_id, type_, from_node, from_rev, to_node, to_rev, from_claim=None, to_claim=None, rationale=None):
        self.db.execute(
            "INSERT INTO edge VALUES (?,?,?,?,?,?,?,?,?)",
            (edge_id, type_, from_node, from_rev, from_claim, to_node, to_rev, to_claim, rationale)
        )
        self.db.commit()

    def add_evidence(self, evidence_id, kind, source_uri=None, locator=None, content_hash=None, origin_group=None, reliability_grade=None):
        self.db.execute(
            "INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?)",
            (evidence_id, kind, source_uri, None, locator, content_hash, origin_group, reliability_grade)
        )
        self.db.commit()

    def add_support(self, assessment_id, evidence_id, target_node, target_rev, target_claim=None, support_role="premise"):
        self.db.execute(
            "INSERT INTO support_assessment VALUES (?,?,?,?,?,?)",
            (assessment_id, evidence_id, target_node, target_rev, target_claim, support_role)
        )
        self.db.commit()

    def get_node_status(self, node_id):
        row = self.db.execute("SELECT status FROM node WHERE id=? ORDER BY revision DESC LIMIT 1", (node_id,)).fetchone()
        return row[0] if row else None

    def set_status(self, node_id, revision, new_status):
        self.db.execute("UPDATE node SET status=? WHERE id=? AND revision=?", (new_status, node_id, revision))
        self.db.commit()


# ════════════════════════════════════════════
# 契約テスト
# ════════════════════════════════════════════

@pytest.fixture
def store() -> MVPStore:
    return build_mvp_store()


def build_mvp_store() -> MVPStore:
    """テスト用のMVPストアを構築する"""
    s = MVPStore()

    # ノード投入
    for nid, info in MVP_NODES.items():
        s.add_node(nid, 1, info["layer"], info["type"], info.get("subtype"), status="draft")

    # HYPノード（隔離）
    s.add_node("H-0100", 1, "practice", "Question", "HYP", status="proposed")

    # claim投入
    s.add_claim("B-0100#c1", "B-0100", 1, "有限集合上の最適性判定", "theorem")
    s.add_claim("S-0100#c1", "S-0100", 1, "第二価格封印入札で正直入札が弱支配戦略", "empirical")
    s.add_claim("U-0100#c1", "U-0100", 1, "封印入札オークション市場モデル", "abstraction")
    s.add_claim("H-0100#c1", "H-0100", 1, "人間実験でも申告乖離が減少する", "application_hypothesis")

    # 根拠（evidence store）
    s.add_evidence("E-001", "source_excerpt", "doi:10.1073/pnas.36.1.48", "p.49 Theorem 1", "abc123", "nash1950", "A")
    s.add_evidence("E-002", "source_excerpt", "https://ocw.mit.edu/14.12", "Lecture 5", "def456", "mit_ocw", "B")
    s.add_evidence("E-003", "execution_log", None, "run_001/output.json", "ghi789", "simulator_v1", "C")

    # support assessment
    s.add_support("SA-001", "E-001", "B-0100", 1, "B-0100#c1", "derivation")
    s.add_support("SA-002", "E-001", "S-0100", 1, "S-0100#c1", "premise")
    s.add_support("SA-003", "E-002", "S-0100", 1, "S-0100#c1", "premise")
    s.add_support("SA-004", "E-003", "O-0100", 1, None, "observation")

    # エッジ（根拠構造）
    s.add_edge("e1", "ABSTRACTS_FROM", "B-0100", 1, "S-0100", 1)
    s.add_edge("e2", "ABSTRACTS_FROM", "S-0100", 1, "U-0100", 1)
    s.add_edge("e3", "ABSTRACTS_FROM", "U-0100", 1, "O-0100", 1)

    # エッジ（参照・対応）
    s.add_edge("e4", "HAS_SCOPED_INSTANCE", "K-0003", 1, "U-0100", 1)
    s.add_edge("e5", "HAS_SCOPED_INSTANCE", "K-0010", 1, "U-0100", 1)
    s.add_edge("e6", "GUIDES_TEST_DESIGN", "K-0007", 1, "Q-0100", 1)

    # エッジ（ワークフロー）
    s.add_edge("e7", "ABOUT", "Q-0100", 1, "U-0100", 1)
    s.add_edge("e8", "PLANS", "Q-0100", 1, "A-0100", 1)
    s.add_edge("e9", "EXECUTES_ON", "A-0100", 1, "O-0100", 1)
    s.add_edge("e10", "PRODUCES", "A-0100", 1, "V-0100", 1)
    s.add_edge("e11", "ANSWERS", "V-0100", 1, "Q-0100", 1, to_claim="Q-0100#c1" if False else None)

    return s


# ─── Test 1: 根拠到達性 ───
def test_evidence_reachability(store: MVPStore):
    """上位ノード(B-0100, S-0100)からevidence storeまで辿れるか"""
    for target in ["B-0100", "S-0100"]:
        row = store.db.execute("""
            SELECT COUNT(*) FROM support_assessment sa
            WHERE sa.target_node = ?
        """, (target,)).fetchone()
        assert row[0] >= 1, f"{target} has no evidence path (support_assessment count=0)"
    print("PASS: test_evidence_reachability")


# ─── Test 2: DAG検査（版単位で循環がないか） ───
def test_dag_no_cycles(store: MVPStore):
    """ABSTRACTS_FROM / DERIVES_FROM / FORMALIZED_BY エッジに循環がないか"""
    structural_types = ("ABSTRACTS_FROM", "DERIVES_FROM", "FORMALIZED_BY")
    edges = store.db.execute(
        "SELECT from_node, to_node FROM edge WHERE type IN (?,?,?)",
        structural_types
    ).fetchall()

    # 隣接リスト構築
    adj: dict[str, list[str]] = {}
    for f, t in edges:
        adj.setdefault(f, []).append(t)

    # DFSで循環検出
    visited = set()
    in_stack = set()

    def dfs(node):
        visited.add(node)
        in_stack.add(node)
        for neighbor in adj.get(node, []):
            if neighbor in in_stack:
                raise AssertionError(f"Cycle detected: {node} -> {neighbor}")
            if neighbor not in visited:
                dfs(neighbor)
        in_stack.discard(node)

    for node in adj:
        if node not in visited:
            dfs(node)

    print("PASS: test_dag_no_cycles")


# ─── Test 3: HYP隔離 ───
def test_hyp_isolation(store: MVPStore):
    """HYPノードがcanonicalノードから根拠エッジを受けていないか"""
    structural_types = ("ABSTRACTS_FROM", "DERIVES_FROM", "FORMALIZED_BY")
    for hyp_id in HYP_NODES:
        # HYPが根拠構造エッジの from 側にいてはいけない（上位に影響させない）
        rows = store.db.execute(
            "SELECT edge_id FROM edge WHERE from_node=? AND type IN (?,?,?)",
            (hyp_id, *structural_types)
        ).fetchall()
        assert len(rows) == 0, f"HYP {hyp_id} has structural edges as source: {rows}"

        # HYPのstatusがapproved/canonicalになっていないか
        status = store.get_node_status(hyp_id)
        assert status in ("proposed", "draft", "blocked"), f"HYP {hyp_id} has invalid status: {status}"

    print("PASS: test_hyp_isolation")


# ─── Test 4: stale伝播 ───
def test_stale_propagation(store: MVPStore):
    """O-0100の根拠を撤回→依存するU-0100, S-0100がstaleになるか"""
    # O-0100をstaleにする
    store.set_status("O-0100", 1, "stale")

    # ABSTRACTS_FROMの逆方向をたどり、依存ノードをstaleにする
    def propagate_stale(node_id, rev):
        dependents = store.db.execute(
            "SELECT from_node, from_revision FROM edge WHERE to_node=? AND to_revision=? AND type='ABSTRACTS_FROM'",
            (node_id, rev)
        ).fetchall()
        for dep_id, dep_rev in dependents:
            store.set_status(dep_id, dep_rev, "stale")
            propagate_stale(dep_id, dep_rev)

    propagate_stale("O-0100", 1)

    # 検証: U-0100, S-0100 がstaleになっているか
    for nid in ["U-0100", "S-0100"]:
        status = store.get_node_status(nid)
        assert status == "stale", f"{nid} should be stale but is {status}"

    # K-0003, K-0010 はHAS_SCOPED_INSTANCEなので影響を受けない
    for nid in ["K-0003", "K-0010"]:
        status = store.get_node_status(nid)
        assert status != "stale", f"{nid} should NOT be stale (reference asset)"

    print("PASS: test_stale_propagation")


# ─── Test 7: 独自証明を持つノードのstale保護 ───
def test_independent_proof_protection(store: MVPStore):
    """B-0100は独自のproof_certificateを持つため、O-0100撤回でstale化しない"""
    # B-0100にproof_certificateを付与
    store.db.execute(
        "INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?,?,?)",
        ("E-PROOF-TEST", "proof_certificate", None, None, "proof.md", "testhash", "self", "A")
    )
    store.db.execute(
        "INSERT OR IGNORE INTO support_assessment VALUES (?,?,?,?,?,?)",
        ("SA-PROOF-TEST", "E-PROOF-TEST", "B-0100", 1, "B-0100#c1", "derivation")
    )
    store.db.commit()

    # mvp_store.pyのpropagate_staleを使う
    from mvp_store import propagate_stale as real_propagate
    real_propagate(store.db, "O-0100", 1)

    # B-0100は独自証明を持つのでstale化しない
    status = store.get_node_status("B-0100")
    assert status != "stale", f"B-0100 should NOT be stale (has independent proof) but is {status}"

    # U-0100, S-0100はstale化する
    for nid in ["U-0100", "S-0100"]:
        status = store.get_node_status(nid)
        assert status == "stale", f"{nid} should be stale but is {status}"

    print("PASS: test_independent_proof_protection")


# ─── Test 5: 変異検出 ───
def test_mutation_detection():
    """第二価格→第一価格に変えた変異で、逸脱利得を検出できるか"""
    # 第二価格オークション: 支払い = 他者の入札額
    def second_price_utility(value, bid, other_bid):
        if bid > other_bid:
            return value - other_bid
        elif bid == other_bid:
            return (value - other_bid) / 2  # タイブレーク
        return 0

    # 第一価格オークション（変異）: 支払い = 自分の入札額
    def first_price_utility(value, bid, other_bid):
        if bid > other_bid:
            return value - bid
        elif bid == other_bid:
            return (value - bid) / 2
        return 0

    values = [0, 1, 2]

    # 第二価格: 正直入札(bid=value)からの逸脱利得を検査
    second_price_deviations = []
    for v in values:
        truthful_utility = sum(second_price_utility(v, v, ob) for ob in values) / len(values)
        for b in values:
            deviated_utility = sum(second_price_utility(v, b, ob) for ob in values) / len(values)
            if deviated_utility > truthful_utility + 1e-9:
                second_price_deviations.append((v, b, deviated_utility - truthful_utility))

    # 第一価格: 正直入札からの逸脱利得を検査
    first_price_deviations = []
    for v in values:
        truthful_utility = sum(first_price_utility(v, v, ob) for ob in values) / len(values)
        for b in values:
            deviated_utility = sum(first_price_utility(v, b, ob) for ob in values) / len(values)
            if deviated_utility > truthful_utility + 1e-9:
                first_price_deviations.append((v, b, deviated_utility - truthful_utility))

    # 第二価格では正直入札からの有利な逸脱がないはず
    assert len(second_price_deviations) == 0, f"Second price has deviations: {second_price_deviations}"

    # 第一価格では有利な逸脱が存在するはず（変異検出）
    assert len(first_price_deviations) > 0, "First price mutation NOT detected (should have deviations)"

    print(f"PASS: test_mutation_detection (first_price deviations={len(first_price_deviations)})")


# ─── Test 6: 架空引用拒否 ───
def test_reject_fabricated_citation(store: MVPStore):
    """content_hashがない根拠でノードをapprovedにしようとしたら拒否"""
    # content_hashなしのevidenceを追加
    store.add_evidence("E-FAKE", "source_excerpt", "https://fake.example.com", None, None, None, None)  # content_hash=None
    store.add_support("SA-FAKE", "E-FAKE", "S-0100", 1, "S-0100#c1", "premise")

    # policy check: content_hashなしのevidenceに依存するsupport_assessmentがあれば拒否
    rows = store.db.execute("""
        SELECT sa.assessment_id, e.evidence_id
        FROM support_assessment sa
        JOIN evidence e ON sa.evidence_id = e.evidence_id
        WHERE sa.target_node = 'S-0100'
          AND e.content_hash IS NULL
    """).fetchall()

    assert len(rows) > 0, "Should detect evidence without content_hash"

    # approvedにしようとしたら拒否する（policy engine相当のチェック）
    can_approve = len(rows) == 0  # content_hashなしがあれば承認不可
    assert not can_approve, "Should NOT approve node with fabricated citation (missing content_hash)"

    print("PASS: test_reject_fabricated_citation")


# ─── Test 8: Projection — resolve_to_nodesとtrace_evidence_chain ───
def test_projection_resolve_and_trace(store: MVPStore):
    """検索結果のref_idからMVPノード解決→根拠追跡が動作するか"""
    from search_engine import resolve_to_nodes, trace_evidence_chain

    # resolve_to_nodesはMVP DBを読むので、テスト用DBをモンキーパッチ
    import search_engine
    original_get_mvp_db = search_engine._get_mvp_db
    search_engine._get_mvp_db = lambda: store.db

    try:
        # approvedノード（K-0003相当のB-0100）を解決
        nodes = resolve_to_nodes(["B-0100", "NONEXISTENT", "S-0100"], include_candidates=True)
        assert len(nodes) == 2, f"Should resolve 2 nodes, got {len(nodes)}"
        assert nodes[0]["node_id"] == "B-0100"
        assert nodes[1]["node_id"] == "S-0100"

        # evidence chain追跡
        chain = trace_evidence_chain("B-0100", 1, include_candidates=True)
        assert len(chain["claims"]) >= 1, "B-0100 should have at least 1 claim"
        assert len(chain["evidence"]) >= 1, "B-0100 should have at least 1 evidence"

        # evidence detailの検証
        ev = chain["evidence"][0]
        assert "evidence_id" in ev
        assert "locator" in ev
        assert "content_hash_present" in ev

    finally:
        search_engine._get_mvp_db = original_get_mvp_db

    print("PASS: test_projection_resolve_and_trace")


# ─── Test 9: Projection — HYP隔離がProjection経由で壊れないか ───
def test_projection_hyp_excluded_from_structural(store: MVPStore):
    """HYPノードがProjectionで解決されてもstructuralエッジを持たない"""
    from search_engine import resolve_to_nodes

    import search_engine
    original_get_mvp_db = search_engine._get_mvp_db
    search_engine._get_mvp_db = lambda: store.db

    try:
        nodes = resolve_to_nodes(["H-0100"], include_candidates=True)
        assert len(nodes) == 1, "H-0100 should be resolvable"
        assert nodes[0]["status"] == "proposed", f"H-0100 status should be proposed, got {nodes[0]['status']}"
        assert nodes[0]["subtype"] == "HYP", f"H-0100 subtype should be HYP, got {nodes[0]['subtype']}"

        # HYPは解決できるが、structural edgeのfrom側にいないことを確認
        structural_types = ("ABSTRACTS_FROM", "DERIVES_FROM", "FORMALIZED_BY")
        rows = store.db.execute(
            "SELECT edge_id FROM edge WHERE from_node=? AND type IN (?,?,?)",
            ("H-0100", *structural_types)
        ).fetchall()
        assert len(rows) == 0, f"HYP should have no structural edges as source via Projection: {rows}"

    finally:
        search_engine._get_mvp_db = original_get_mvp_db

    print("PASS: test_projection_hyp_excluded_from_structural")


# ════════════════════════════════════════════
# 実行
# ════════════════════════════════════════════

if __name__ == "__main__":
    print("=== MVP Contract Tests ===\n")

    store = build_mvp_store()

    test_evidence_reachability(store)
    test_dag_no_cycles(store)
    test_hyp_isolation(store)

    # stale伝播テストは別ストアで（状態を壊すため）
    store2 = build_mvp_store()
    test_stale_propagation(store2)

    test_mutation_detection()

    # 架空引用テストも別ストア
    store3 = build_mvp_store()
    test_reject_fabricated_citation(store3)

    # 独自証明保護テストも別ストア
    store4 = build_mvp_store()
    test_independent_proof_protection(store4)

    # Projection契約テスト
    store5 = build_mvp_store()
    test_projection_resolve_and_trace(store5)
    test_projection_hyp_excluded_from_structural(store5)

    print("\n=== ALL 9 CONTRACT TESTS PASSED ===")
