"""gap detector: 知識グラフの穴を自動検出し、amplifierで充填する自律ループ

検出する穴:
  G1: unsupported_claim — claimにevidenceがない
  G2: missing_instance  — science/universeノードにHAS_SCOPED_INSTANCEがない
  G3: unverified_edge   — 構造エッジに根拠（derivation_ref or claim支持）がない

Usage:
    python gap_detector.py detect              # 穴を検出して表示
    python gap_detector.py cycle --budget 3     # 検出→充填→再検出を1サイクル
    python gap_detector.py cycle --dry-run      # DB変更なしで試行
    python gap_detector.py status               # gap台帳の状態表示
"""

import argparse
import hashlib
import json
import sqlite3
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import config  # noqa: F401

from mvp_store import init_db, DB_PATH


# ════════════════════════════════════════════
# Gap台帳スキーマ
# ════════════════════════════════════════════

def init_gap_table(db: sqlite3.Connection):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS gap (
            gap_id TEXT PRIMARY KEY,
            fingerprint TEXT UNIQUE,
            gap_type TEXT NOT NULL,
            anchor_node TEXT,
            anchor_revision INTEGER,
            anchor_claim TEXT,
            scope TEXT NOT NULL DEFAULT '{}',
            topic TEXT,
            state TEXT NOT NULL DEFAULT 'open'
                CHECK(state IN ('open','running','candidate_ready','resolved',
                                'retry_wait','exhausted','needs_review','superseded')),
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            result TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    db.commit()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(gap_type: str, anchor_node: str, anchor_claim: str = "") -> str:
    raw = f"{gap_type}:{anchor_node}:{anchor_claim}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ════════════════════════════════════════════
# G1: unsupported_claim — 根拠なしclaim検出
# ════════════════════════════════════════════

def detect_unsupported_claims(db: sqlite3.Connection) -> list[dict]:
    """evidenceが紐付いていないclaimを検出。定義(definition)とHYPは除外。"""
    rows = db.execute("""
        SELECT c.claim_id, c.node_id, c.node_revision, c.statement, c.kind,
               n.layer, n.status, n.subtype
        FROM claim c
        JOIN node n ON c.node_id = n.id AND c.node_revision = n.revision
        LEFT JOIN support_assessment sa ON sa.target_claim = c.claim_id
        WHERE sa.assessment_id IS NULL
          AND n.subtype != 'HYP'
          AND n.status NOT IN ('superseded', 'stale')
          AND c.kind != 'definition'
          AND n.type != 'Question'
    """).fetchall()

    gaps = []
    for r in rows:
        gaps.append({
            "gap_type": "unsupported_claim",
            "anchor_node": r[1],
            "anchor_revision": r[2],
            "anchor_claim": r[0],
            "statement": r[3],
            "kind": r[4],
            "layer": r[5],
            "node_status": r[6],
        })
    return gaps


# ════════════════════════════════════════════
# G2: missing_instance — インスタンスなしクラス検出
# ════════════════════════════════════════════

def detect_missing_instances(db: sqlite3.Connection) -> list[dict]:
    """science/universe層のapprovedノードでHAS_SCOPED_INSTANCEが0本のものを検出"""
    rows = db.execute("""
        SELECT n.id, n.revision, n.layer, n.type,
               json_extract(n.data, '$.title') as title
        FROM node n
        WHERE n.layer IN ('science', 'universe')
          AND n.status = 'approved'
          AND NOT EXISTS (
              SELECT 1 FROM edge e
              WHERE e.type = 'HAS_SCOPED_INSTANCE'
                AND e.from_node = n.id
          )
    """).fetchall()

    gaps = []
    for r in rows:
        gaps.append({
            "gap_type": "missing_instance",
            "anchor_node": r[0],
            "anchor_revision": r[1],
            "layer": r[2],
            "node_type": r[3],
            "title": r[4] or r[0],
        })
    return gaps


# ════════════════════════════════════════════
# G3: unverified_edge — 根拠なしエッジ検出
# ════════════════════════════════════════════

# 根拠を要求する構造エッジ（evidence-backed原則をエッジにも適用）
EVIDENCE_REQUIRED_EDGE_TYPES = (
    "ABSTRACTS_FROM", "DERIVES_FROM", "FORMALIZED_BY", "HAS_SCOPED_INSTANCE",
)
# ワークフロー/参照エッジは組織構造であり根拠不要
WORKFLOW_EDGE_TYPES = (
    "PLANS", "EXECUTES_ON", "PRODUCES", "ANSWERS", "ABOUT", "GUIDES_TEST_DESIGN",
)


def detect_unverified_edges(db: sqlite3.Connection) -> list[dict]:
    """構造エッジで根拠がないものを検出。

    根拠ありの条件（いずれか1つを満たせばOK）:
      1. derivation_ref が設定されている（証明や根拠文書への参照）
      2. from_claim または to_claim が設定されている（claim-levelの根拠）
      3. エッジのfrom_node/to_nodeの組に対し、両ノードを支持する共通evidenceがある
    """
    placeholders = ",".join("?" for _ in EVIDENCE_REQUIRED_EDGE_TYPES)
    rows = db.execute(f"""
        SELECT e.edge_id, e.type, e.from_node, e.from_revision,
               e.to_node, e.to_revision, e.rationale, e.derivation_ref,
               e.from_claim, e.to_claim
        FROM edge e
        WHERE e.type IN ({placeholders})
    """, EVIDENCE_REQUIRED_EDGE_TYPES).fetchall()

    gaps = []
    for r in rows:
        edge_id = r[0]
        edge_type = r[1]
        from_node, from_rev = r[2], r[3]
        to_node, to_rev = r[4], r[5]
        rationale = r[6]
        derivation_ref = r[7]
        from_claim = r[8]
        to_claim = r[9]

        # 条件1: derivation_refがあればOK
        if derivation_ref:
            continue

        # 条件2: claim-levelの根拠があればOK
        if from_claim or to_claim:
            continue

        # 条件3: 両ノードを支持する共通evidenceがあればOK
        co_evidence = db.execute("""
            SELECT COUNT(DISTINCT sa1.evidence_id) FROM support_assessment sa1
            JOIN support_assessment sa2 ON sa1.evidence_id = sa2.evidence_id
            WHERE sa1.target_node = ? AND sa1.target_revision = ?
              AND sa2.target_node = ? AND sa2.target_revision = ?
        """, (from_node, from_rev, to_node, to_rev)).fetchone()[0]
        if co_evidence > 0:
            continue

        gaps.append({
            "gap_type": "unverified_edge",
            "anchor_node": from_node,  # エッジのfrom側をanchorに使う
            "anchor_revision": from_rev,
            "anchor_claim": edge_id,   # edge_idをanchor_claimフィールドに格納（fingerprintの一意性確保）
            "edge_id": edge_id,
            "edge_type": edge_type,
            "from_node": from_node,
            "to_node": to_node,
            "rationale": rationale or "",
        })
    return gaps


# ════════════════════════════════════════════
# Gap台帳操作
# ════════════════════════════════════════════

def upsert_gaps(db: sqlite3.Connection, gaps: list[dict]) -> int:
    """検出したgapを台帳にupsert。既存のものはスキップ。新規のみ追加。"""
    new_count = 0
    now = _now()
    for g in gaps:
        fp = _fingerprint(g["gap_type"], g["anchor_node"], g.get("anchor_claim", ""))
        existing = db.execute("SELECT state FROM gap WHERE fingerprint=?", (fp,)).fetchone()
        if existing:
            continue  # 既知のgap

        gap_id = f"gap-{fp[:8]}"
        db.execute(
            "INSERT INTO gap VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (gap_id, fp, g["gap_type"],
             g["anchor_node"], g.get("anchor_revision"), g.get("anchor_claim"),
             json.dumps(g, ensure_ascii=False), None,
             "open", 0, 3, "{}", now, now)
        )
        new_count += 1
    db.commit()
    return new_count


def select_open_gaps(db: sqlite3.Connection, limit: int = 3) -> list[dict]:
    """open状態のgapを優先度順に取得"""
    rows = db.execute("""
        SELECT gap_id, fingerprint, gap_type, anchor_node, anchor_revision,
               anchor_claim, scope, state, attempts
        FROM gap
        WHERE state = 'open'
        ORDER BY
            CASE gap_type
                WHEN 'unsupported_claim' THEN 1
                WHEN 'unverified_edge' THEN 2
                WHEN 'missing_instance' THEN 3
                ELSE 4
            END,
            created_at ASC
        LIMIT ?
    """, (limit,)).fetchall()

    return [{
        "gap_id": r[0], "fingerprint": r[1], "gap_type": r[2],
        "anchor_node": r[3], "anchor_revision": r[4],
        "anchor_claim": r[5], "scope": json.loads(r[6]),
        "state": r[7], "attempts": r[8],
    } for r in rows]


def update_gap_state(db: sqlite3.Connection, gap_id: str, state: str, result: dict = None):
    now = _now()
    if result:
        db.execute("UPDATE gap SET state=?, result=?, attempts=attempts+1, updated_at=? WHERE gap_id=?",
                    (state, json.dumps(result, ensure_ascii=False), now, gap_id))
    else:
        db.execute("UPDATE gap SET state=?, updated_at=? WHERE gap_id=?",
                    (state, now, gap_id))
    db.commit()


# ════════════════════════════════════════════
# トピック生成: gap → amplifier入力
# ════════════════════════════════════════════

def generate_topic(gap: dict) -> str:
    """gap情報からamplifierに渡すトピック文字列を生成"""
    scope = gap.get("scope", {})

    if gap["gap_type"] == "unsupported_claim":
        statement = scope.get("statement", gap.get("anchor_claim", ""))
        kind = scope.get("kind", "claim")
        return f"academic evidence for: {statement} — find primary sources with DOI that directly support or refute this {kind}"

    elif gap["gap_type"] == "missing_instance":
        title = scope.get("title", gap.get("anchor_node", ""))
        return f"concrete examples and case studies of: {title} — find documented instances with empirical data, parameters, and citable sources"

    elif gap["gap_type"] == "unverified_edge":
        edge_type = scope.get("edge_type", "UNKNOWN")
        from_n = scope.get("from_node", "?")
        to_n = scope.get("to_node", "?")
        rationale = scope.get("rationale", "")
        return f"evidence justifying the {edge_type} relationship from {from_n} to {to_n}: {rationale}"

    return f"knowledge about {gap.get('anchor_node', 'unknown topic')}"


# ════════════════════════════════════════════
# 充填: amplifier呼び出し + 自動紐付け
# ════════════════════════════════════════════

def _auto_link_evidence(db, gap: dict) -> int:
    """amplifierが登録したevidenceのうち、gapのclaimに関連するものをsupport_assessmentで紐付け"""
    if gap["gap_type"] != "unsupported_claim" or not gap.get("anchor_claim"):
        return 0

    from mvp_store import add_support

    # amplifierが登録した未紐付きevidence（origin_group='llm_amplified'）を取得
    unlinked = db.execute("""
        SELECT e.evidence_id, e.source_uri, e.locator, e.reliability_grade
        FROM evidence e
        WHERE e.origin_group = 'llm_amplified'
          AND NOT EXISTS (
              SELECT 1 FROM support_assessment sa
              WHERE sa.evidence_id = e.evidence_id
                AND sa.target_claim = ?
          )
    """, (gap["anchor_claim"],)).fetchall()

    if not unlinked:
        return 0

    # claimのstatementを取得
    claim_row = db.execute(
        "SELECT statement FROM claim WHERE claim_id=?", (gap["anchor_claim"],)
    ).fetchone()
    claim_text = claim_row[0] if claim_row else ""

    linked = 0
    for eid, uri, locator, grade in unlinked:
        # Grade D以下はスキップ（低品質）
        if grade not in ("A", "B", "C"):
            continue

        # Semantic Scholarのabstractで関連性を簡易判定
        relevance = _check_relevance(uri, claim_text)
        if relevance == "irrelevant":
            continue

        # support_assessment自動生成
        role = "premise"  # デフォルト。将来はLLMで判定
        rationale = f"gap_detector auto-linked: {relevance}"
        try:
            add_support(db, eid,
                gap["anchor_node"], gap["anchor_revision"],
                target_claim=gap["anchor_claim"],
                support_role=role,
                rationale=rationale,
                assessor="gap_detector")
            linked += 1
            print(f"      Linked: {eid} → {gap['anchor_claim']} ({relevance})")
        except sqlite3.Error as e:
            print(f"      WARN: Failed to link {eid}: {e}")

    return linked


def _check_relevance(source_uri: str, claim_text: str) -> str:
    """evidenceのURIからabstractを取得し、claimとの関連性を判定"""
    if not source_uri or not source_uri.startswith("doi:"):
        return "unknown"

    doi = source_uri[4:]

    # Semantic Scholarからabstract取得（キャッシュ的にDB内のデータも活用）
    try:
        from knowledge_amplifier import verify_semantic_scholar
        ss = verify_semantic_scholar(doi, claim_text)
        if ss and ss.get("verified"):
            rel = ss.get("claim_relevance", "unknown")
            if rel in ("likely_relevant", "possibly_relevant"):
                return rel
            elif rel == "low_relevance":
                return "irrelevant"
        return "unknown"  # abstractなしでも紐付け（unknown = 弱い支持）
    except (ImportError, OSError, urllib.error.URLError, TimeoutError):
        return "unknown"


def fill_gap(gap: dict, dry_run: bool = False) -> dict:
    """1件のgapに対してamplifierを呼び出し、claimに自動紐付けする"""
    topic = generate_topic(gap)
    print(f"    Topic: {topic[:80]}...")

    if dry_run:
        return {"status": "dry_run", "topic": topic}

    # G3: unverified_edgeはrelation_engineが実装されるまで自動充填しない
    if gap["gap_type"] == "unverified_edge":
        return {"status": "needs_review", "topic": topic,
                "reason": "G3 edges require relation_engine for validation (not yet implemented)"}

    from knowledge_amplifier import amplify
    results = amplify(topic, depth=0, dry_run=False, verbose=False)

    if not results:
        return {"status": "no_results", "topic": topic}

    r = results[0]
    stats = r.get("stats", {})
    accepted = stats.get("A", 0) + stats.get("B", 0) + stats.get("C", 0)

    # 自動紐付け
    linked = 0
    if accepted > 0:
        db = init_db()
        print(f"    Auto-linking evidence to claim...")
        linked = _auto_link_evidence(db, gap)
        print(f"    Linked: {linked} evidence → {gap.get('anchor_claim', 'N/A')}")

    return {
        "status": "completed",
        "topic": topic,
        "dois_checked": r.get("dois_checked", 0),
        "stats": stats,
        "linked": linked,
    }


# ════════════════════════════════════════════
# 1サイクル実行
# ════════════════════════════════════════════

def run_cycle(budget: int = 3, dry_run: bool = False) -> dict:
    db = init_db()
    init_gap_table(db)

    print("=" * 60)
    print("GAP DETECTOR — Cycle Start")
    print("=" * 60)

    # Step 1: 検出
    print("\n[1] Detecting gaps...")
    g1 = detect_unsupported_claims(db)
    g2 = detect_missing_instances(db)
    g3 = detect_unverified_edges(db)
    all_gaps = g1 + g2 + g3
    print(f"  Found: {len(g1)} G1 unsupported, {len(g2)} G2 missing_instance, {len(g3)} G3 unverified_edge")

    # Step 2: 台帳にupsert
    new_count = upsert_gaps(db, all_gaps)
    print(f"  New gaps registered: {new_count}")

    # Step 3: open gapを選択
    selected = select_open_gaps(db, limit=budget)
    print(f"\n[2] Selected {len(selected)} gaps to fill (budget={budget}):")

    results = []
    for gap in selected:
        print(f"\n  Gap: {gap['gap_id']} [{gap['gap_type']}]")
        print(f"    Node: {gap['anchor_node']}, Claim: {gap.get('anchor_claim', 'N/A')}")

        # anchor存在確認（revision固定）
        anchor_exists = db.execute(
            "SELECT status FROM node WHERE id=? AND revision=?",
            (gap["anchor_node"], gap["anchor_revision"])
        ).fetchone()
        if not anchor_exists:
            print(f"    → SUPERSEDED (anchor no longer exists)")
            update_gap_state(db, gap["gap_id"], "superseded")
            continue

        # 充填
        update_gap_state(db, gap["gap_id"], "running")
        result = fill_gap(gap, dry_run=dry_run)
        results.append({"gap_id": gap["gap_id"], **result})

        # 結果判定
        if result.get("status") == "dry_run":
            update_gap_state(db, gap["gap_id"], "open", result)
            print(f"    → [DRY RUN] Would fill")
        elif result.get("status") == "needs_review":
            update_gap_state(db, gap["gap_id"], "needs_review", result)
            print(f"    → NEEDS REVIEW ({result.get('reason', '')})")
        elif result.get("status") == "completed":
            stats = result.get("stats", {})
            accepted = stats.get("A", 0) + stats.get("B", 0) + stats.get("C", 0)
            rejected = stats.get("REJECTED", 0)
            linked = result.get("linked", 0)
            if linked > 0:
                # evidenceがclaimに紐付いた → 穴が閉じた
                update_gap_state(db, gap["gap_id"], "resolved", result)
                print(f"    → RESOLVED ({linked} evidence linked, {rejected} rejected)")
            elif accepted > 0:
                update_gap_state(db, gap["gap_id"], "candidate_ready", result)
                print(f"    → CANDIDATE READY ({accepted} evidence found but none linked)")
            else:
                attempts = gap["attempts"] + 1
                if attempts >= gap.get("max_attempts", 3):
                    update_gap_state(db, gap["gap_id"], "exhausted", result)
                    print(f"    → EXHAUSTED (no results after {attempts} attempts)")
                else:
                    update_gap_state(db, gap["gap_id"], "retry_wait", result)
                    print(f"    → RETRY WAIT (attempt {attempts})")
        else:
            update_gap_state(db, gap["gap_id"], "retry_wait", result)
            print(f"    → RETRY WAIT")

    # Step 4: 再検出
    print(f"\n[3] Re-detecting gaps...")
    g1_after = detect_unsupported_claims(db)
    g2_after = detect_missing_instances(db)
    g3_after = detect_unverified_edges(db)
    new_after = upsert_gaps(db, g1_after + g2_after + g3_after)

    # サマリー
    print(f"\n{'='*60}")
    print("CYCLE SUMMARY")
    print(f"{'='*60}")
    print(f"Gaps before: {len(all_gaps)} ({len(g1)} G1 + {len(g2)} G2 + {len(g3)} G3)")
    print(f"Gaps after:  {len(g1_after)+len(g2_after)+len(g3_after)} ({len(g1_after)} G1 + {len(g2_after)} G2 + {len(g3_after)} G3)")
    print(f"New gaps discovered: {new_after}")
    print(f"Gaps processed: {len(selected)}")
    for r in results:
        print(f"  {r['gap_id']}: {r.get('status', '?')}")

    # イベントログ
    from mvp_store import _uid
    db.execute("INSERT INTO event VALUES (?,?,?,?,?,?)", (
        _uid("ev-"), "gap_cycle_completed", None,
        json.dumps({
            "before": {"G1": len(g1), "G2": len(g2), "G3": len(g3)},
            "after": {"G1": len(g1_after), "G2": len(g2_after), "G3": len(g3_after)},
            "processed": len(selected),
            "results": [r.get("status") for r in results],
        }, ensure_ascii=False),
        _now(), "gap_detector"
    ))
    db.commit()

    return {
        "before": {"G1": len(g1), "G2": len(g2), "G3": len(g3)},
        "after": {"G1": len(g1_after), "G2": len(g2_after), "G3": len(g3_after)},
        "processed": results,
    }


# ════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════

def cmd_detect():
    db = init_db()
    init_gap_table(db)
    g1 = detect_unsupported_claims(db)
    g2 = detect_missing_instances(db)
    g3 = detect_unverified_edges(db)

    print(f"=== Unsupported Claims (G1): {len(g1)} ===")
    for g in g1:
        print(f"  {g['anchor_claim']} [{g['kind']}] → {g['statement'][:80]}")

    print(f"\n=== Missing Instances (G2): {len(g2)} ===")
    for g in g2:
        print(f"  {g['anchor_node']} [{g['layer']}/{g['node_type']}] → {g.get('title', '?')}")

    print(f"\n=== Unverified Edges (G3): {len(g3)} ===")
    for g in g3:
        print(f"  {g['edge_id']}: {g['from_node']} --{g['edge_type']}--> {g['to_node']}  rationale={g.get('rationale', '')[:50]}")


def cmd_status():
    db = init_db()
    init_gap_table(db)
    rows = db.execute("""
        SELECT state, COUNT(*) FROM gap GROUP BY state ORDER BY state
    """).fetchall()

    print("=== Gap Ledger Status ===")
    total = 0
    for state, count in rows:
        print(f"  {state}: {count}")
        total += count
    print(f"  TOTAL: {total}")

    print("\n=== Open Gaps ===")
    for r in db.execute("SELECT gap_id, gap_type, anchor_node, anchor_claim FROM gap WHERE state='open'"):
        print(f"  {r[0]} [{r[1]}] node={r[2]} claim={r[3] or 'N/A'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gap Detector — 知識グラフの穴検出・充填")
    cmds = parser.add_subparsers(dest="command", required=True)

    cmds.add_parser("detect", help="穴を検出して表示")

    c = cmds.add_parser("cycle", help="検出→充填→再検出を1サイクル実行")
    c.add_argument("--budget", type=int, default=3, help="1サイクルで処理するgap数")
    c.add_argument("--dry-run", action="store_true")

    cmds.add_parser("status", help="gap台帳の状態表示")

    args = parser.parse_args()

    if args.command == "detect":
        cmd_detect()
    elif args.command == "cycle":
        run_cycle(budget=args.budget, dry_run=args.dry_run)
    elif args.command == "status":
        cmd_status()
