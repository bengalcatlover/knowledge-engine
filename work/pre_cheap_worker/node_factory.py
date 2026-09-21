"""node_factory: provisionalノード自動生成

evidence_minerのunresolved claimから新ノードを生成する。
Fable 5 + GPT-6 Astra 統合設計に基づく実装。

原則:
  - 全ノードはprovisional（status="proposed"）で生成
  - 昇格条件: 独立evidence >= 2 + edge >= 2
  - 2サイクルevidence 0 → archive
  - エッジなしノード生成は拒否（自分でG2ギャップを作らない）
  - クラス生成より先にインスタンス生成（安全）

Usage:
    python node_factory.py generate                # unresolved claimからノード生成
    python node_factory.py generate --dry-run      # DB変更なし
    python node_factory.py promote                 # 昇格/archive判定
    python node_factory.py promote --dry-run
    python node_factory.py status                  # provisionalノードの状態
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from mvp_store import (
    init_db, get_db, add_node, add_claim, add_edge, add_support,
    _uid, _now, DB_PATH
)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
HAIKU_MODEL = "claude-haiku-4-5-20251001"


# ════════════════════════════════════════════
# ノードID採番
# ════════════════════════════════════════════

# layer → ID prefix
LAYER_PREFIX = {
    "foundation": "B",
    "science": "K",
    "universe": "U",
    "object": "O",
    "practice": "P",
}


def _next_node_id(db, prefix: str) -> str:
    """指定prefixの次のノードIDを生成"""
    rows = db.execute(
        "SELECT id FROM node WHERE id LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{prefix}-%",)
    ).fetchall()
    if not rows:
        return f"{prefix}-0300"  # 既存ノードが0200まであるので0300から

    last_id = rows[0][0]
    m = re.match(r'[A-Z]+-(\d+)', last_id)
    if m:
        next_num = int(m.group(1)) + 1
        return f"{prefix}-{next_num:04d}"
    return f"{prefix}-{_uid()[:4]}"


# ════════════════════════════════════════════
# LLM分類: unresolved claimからノード情報を推論
# ════════════════════════════════════════════

CLASSIFY_PROMPT = """You are a knowledge graph architect. Given an unresolved claim and the existing node list, decide how to place this claim in the graph.

EXISTING NODES:
{nodes_list}

UNRESOLVED CLAIM:
  Text: {claim_text}
  Subjects: {subjects}
  Source evidence: {evidence_id}
  Claim type: {claim_type}

TASK: Decide the best placement. Output ONLY valid JSON (no markdown fences):
{{
  "decision": "new_instance" | "new_class" | "absorb",
  "absorb_into": "existing_node_id or null",
  "absorb_reason": "why this claim fits the existing node, or null",
  "new_node": {{
    "title": "short descriptive title in English",
    "title_ja": "Japanese title",
    "layer": "foundation | science | universe | object | practice",
    "type": "Theory | Method | ScopedLaw | FormalPrinciple | System | WorldModel",
    "subtype": "THY | MTH | LAW | THM | WM | null",
    "parent_node_id": "existing node this is an instance/subtype of, or null",
    "edge_type": "HAS_SCOPED_INSTANCE | IS_A | DERIVES_FROM | null",
    "differentiation": "1-sentence explanation of how this differs from parent"
  }}
}}

Rules:
1. Prefer "absorb" if the claim clearly belongs to an existing node (just wasn't matched by keywords).
2. Prefer "new_instance" over "new_class" — instances are safer.
3. If "new_class", parent_node_id is REQUIRED (no orphan classes).
4. The new node MUST have at least one edge to an existing node.
5. layer must match the content: methods → science, models → universe, tools → object.
"""


def _call_anthropic(prompt: str, model: str = HAIKU_MODEL) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "max_tokens": 1024, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(url, json.dumps(payload).encode(), headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return "\n".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")


def _parse_json(raw: str) -> dict:
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw, re.DOTALL)
    text = match.group(1) if match else raw
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise ValueError(f"Could not parse JSON: {text[:300]}")


def _format_nodes_list(db) -> str:
    lines = []
    for r in db.execute("""
        SELECT n.id, n.layer, n.type, n.subtype, n.status,
               json_extract(n.data, '$.title') as title
        FROM node n ORDER BY n.id
    """):
        title = r[5] or r[0]
        lines.append(f"  - {r[0]} ({r[1]}/{r[2]}/{r[3] or '-'}) [{r[4]}]: {title}")
    return "\n".join(lines)


def classify_claim(claim_text: str, subjects: list[str],
                   evidence_id: str, claim_type: str, db) -> dict:
    """LLMでunresolved claimの配置を決定"""
    nodes_list = _format_nodes_list(db)
    prompt = CLASSIFY_PROMPT \
        .replace("{nodes_list}", nodes_list) \
        .replace("{claim_text}", claim_text) \
        .replace("{subjects}", ", ".join(subjects or ["unknown"])) \
        .replace("{evidence_id}", evidence_id) \
        .replace("{claim_type}", claim_type or "empirical")

    raw = _call_anthropic(prompt)
    return _parse_json(raw)


# ════════════════════════════════════════════
# unresolved claimの収集
# ════════════════════════════════════════════

def collect_unresolved_claims(db) -> list[dict]:
    """evidence_minerが処理したがノード帰属できなかったclaimを再収集。

    mining logのunresolved > 0のevidenceに対し、abstractを再取得して
    unresolvedだったclaimを特定する。

    効率のため、mining_logにunresolved claimの詳細を保存する方が良いが、
    現時点では再抽出で対応（LLMコスト vs 複雑性のトレードオフ）。
    """
    # evidence_mining_logからunresolved > 0のevidenceを取得
    rows = db.execute("""
        SELECT ml.evidence_id, ml.abstract_text, ml.claims_unresolved,
               e.source_uri
        FROM evidence_mining_log ml
        JOIN evidence e ON ml.evidence_id = e.evidence_id
        WHERE ml.claims_unresolved > 0
          AND ml.state = 'mined'
    """).fetchall()

    if not rows:
        return []

    # 既にnode_factoryで処理済みのevidence_idを除外
    processed = set()
    try:
        for r in db.execute("""
            SELECT DISTINCT json_extract(data, '$.node_factory_source')
            FROM node WHERE json_extract(data, '$.node_factory_source') IS NOT NULL
        """):
            if r[0]:
                processed.add(r[0])
    except Exception:
        pass

    unresolved = []
    for eid, abstract_text, count, source_uri in rows:
        if eid in processed:
            continue
        unresolved.append({
            "evidence_id": eid,
            "abstract_text": abstract_text or "",
            "claims_unresolved": count,
            "source_uri": source_uri,
        })

    return unresolved


# ════════════════════════════════════════════
# ノード生成パイプライン
# ════════════════════════════════════════════

def _validate_new_node(classification: dict, db) -> list[str]:
    """新ノードの事前検証。違反リストを返す。"""
    violations = []
    nn = classification.get("new_node", {})

    if not nn:
        violations.append("new_node is empty")
        return violations

    layer = nn.get("layer", "")
    if layer not in ("foundation", "science", "universe", "object", "practice"):
        violations.append(f"invalid layer: {layer}")

    parent_id = nn.get("parent_node_id")
    edge_type = nn.get("edge_type")

    # エッジなしノード生成は拒否（Fable設計: 自分でG2ギャップを作らない）
    if not parent_id or not edge_type:
        violations.append("no parent_node_id or edge_type (orphan node rejected)")

    # 親ノードの存在確認
    if parent_id:
        exists = db.execute(
            "SELECT 1 FROM node WHERE id=?", (parent_id,)
        ).fetchone()
        if not exists:
            violations.append(f"parent_node {parent_id} not found")

    # 差別化テスト（Fable設計）
    diff = nn.get("differentiation", "")
    if not diff or len(diff) < 10:
        violations.append("differentiation too short (must explain how this differs from parent)")

    return violations


def generate_nodes(dry_run: bool = False, verbose: bool = True) -> dict:
    """unresolved claimからprovisionalノードを生成"""
    db = get_db()
    init_db()

    unresolved = collect_unresolved_claims(db)
    if not unresolved:
        if verbose:
            print("No unresolved claims to process.")
        return {"generated": 0, "absorbed": 0, "rejected": 0}

    if verbose:
        print(f"=== Node Factory: {len(unresolved)} evidence with unresolved claims ===\n")

    # 既存claimとノード情報
    from evidence_miner import _load_nodes_with_claims, extract_claims_from_abstract, \
        fetch_abstract, _extract_doi, resolve_node_attribution, _load_existing_claims

    nodes_with_claims = _load_nodes_with_claims(db)
    existing_claims = _load_existing_claims(db)

    stats = {"generated": 0, "absorbed": 0, "rejected": 0, "details": []}

    # 1サイクル最大20ノード（Fable設計: new_nodes: 20/cycle）
    MAX_NEW_NODES = 20
    generated_this_cycle = 0

    for item in unresolved:
        if generated_this_cycle >= MAX_NEW_NODES:
            if verbose:
                print(f"\n[BUDGET] Max {MAX_NEW_NODES} nodes per cycle reached")
            break

        eid = item["evidence_id"]
        abstract = item["abstract_text"]
        doi = _extract_doi(item["source_uri"])

        if verbose:
            print(f"[{eid}] Processing {item['claims_unresolved']} unresolved claims")

        # abstractからclaim再抽出
        if not abstract or len(abstract) < 50:
            if doi:
                ad = fetch_abstract(doi)
                if ad.get("ok"):
                    abstract = ad["abstract"]
            if not abstract or len(abstract) < 50:
                if verbose:
                    print(f"  [SKIP] No abstract available")
                continue

        claims = extract_claims_from_abstract(
            "", "", None, abstract, nodes_with_claims=nodes_with_claims
        )
        if not claims:
            continue

        # unresolvedのclaimだけフィルタ
        for i, claim in enumerate(claims):
            if generated_this_cycle >= MAX_NEW_NODES:
                break

            attr = resolve_node_attribution(
                claim.get("subjects", []), claim["text"], nodes_with_claims
            )
            if attr["node_id"] is not None:
                continue  # 帰属先あり → skip

            # LLMで分類
            if verbose:
                print(f"  Classifying: {claim['text'][:70]}...")

            try:
                classification = classify_claim(
                    claim["text"],
                    claim.get("subjects", []),
                    eid,
                    claim.get("claim_type", "empirical"),
                    db
                )
            except Exception as e:
                if verbose:
                    print(f"  [ERROR] Classification failed: {e}")
                stats["rejected"] += 1
                continue

            decision = classification.get("decision", "")

            # absorb: 既存ノードに吸収
            if decision == "absorb":
                absorb_into = classification.get("absorb_into")
                if absorb_into and db.execute("SELECT 1 FROM node WHERE id=?", (absorb_into,)).fetchone():
                    if verbose:
                        reason = classification.get("absorb_reason", "")
                        print(f"  → ABSORB into {absorb_into}: {reason[:60]}")

                    if not dry_run:
                        # claimを既存ノードに追加
                        rev = db.execute(
                            "SELECT revision FROM node WHERE id=? ORDER BY revision DESC LIMIT 1",
                            (absorb_into,)
                        ).fetchone()[0]
                        cid = f"{eid}#factory-{i}"
                        kind_map = {"empirical": "empirical", "theoretical": "theorem",
                                    "methodological": "empirical", "definitional": "definition"}
                        kind = kind_map.get(claim.get("claim_type", ""), "empirical")
                        try:
                            add_claim(db, cid, absorb_into, rev, claim["text"], kind)
                            add_support(db, eid, absorb_into, rev,
                                        target_claim=cid, support_role="premise",
                                        rationale="node_factory absorbed claim",
                                        assessor="node_factory")
                        except Exception as e:
                            if verbose:
                                print(f"  [WARN] Absorb failed: {e}")
                    stats["absorbed"] += 1
                    stats["details"].append({
                        "action": "absorb", "evidence_id": eid,
                        "absorb_into": absorb_into, "claim": claim["text"][:60]
                    })
                    continue
                else:
                    if verbose:
                        print(f"  [WARN] absorb target {absorb_into} not found, trying new_instance")
                    decision = "new_instance"

            # new_instance / new_class
            if decision in ("new_instance", "new_class"):
                violations = _validate_new_node(classification, db)
                if violations:
                    if verbose:
                        print(f"  → REJECTED: {'; '.join(violations)}")
                    stats["rejected"] += 1
                    stats["details"].append({
                        "action": "rejected", "evidence_id": eid,
                        "reason": violations, "claim": claim["text"][:60]
                    })
                    continue

                nn = classification["new_node"]
                layer = nn["layer"]
                prefix = LAYER_PREFIX.get(layer, "X")
                node_id = _next_node_id(db, prefix)

                if verbose:
                    print(f"  → NEW [{decision}] {node_id}: {nn.get('title', '?')}")
                    print(f"    layer={layer}, type={nn.get('type')}, parent={nn.get('parent_node_id')}")
                    print(f"    diff: {nn.get('differentiation', '')[:60]}")

                if not dry_run:
                    # ノード生成（provisional = status "proposed"）
                    node_data = {
                        "title": nn.get("title", ""),
                        "title_ja": nn.get("title_ja", ""),
                        "differentiation": nn.get("differentiation", ""),
                        "node_factory_source": eid,
                        "decision": decision,
                    }
                    add_node(db, node_id, 1, layer,
                             nn.get("type", "Theory"),
                             nn.get("subtype"),
                             status="proposed",
                             data=node_data)

                    # claim追加
                    cid = f"{node_id}#c1"
                    kind_map = {"empirical": "empirical", "theoretical": "theorem",
                                "methodological": "empirical", "definitional": "definition"}
                    kind = kind_map.get(claim.get("claim_type", ""), "empirical")
                    add_claim(db, cid, node_id, 1, claim["text"], kind)

                    # support_assessment
                    add_support(db, eid, node_id, 1,
                                target_claim=cid, support_role="premise",
                                rationale="node_factory generated from unresolved claim",
                                assessor="node_factory")

                    # 親ノードへのエッジ
                    parent_id = nn.get("parent_node_id")
                    edge_type = nn.get("edge_type", "HAS_SCOPED_INSTANCE")
                    parent_rev = db.execute(
                        "SELECT revision FROM node WHERE id=? ORDER BY revision DESC LIMIT 1",
                        (parent_id,)
                    ).fetchone()
                    if parent_rev:
                        rationale = nn.get("differentiation", "node_factory auto-generated")
                        add_edge(db, edge_type,
                                 parent_id, parent_rev[0],
                                 node_id, 1,
                                 rationale=rationale)

                    # nodes_with_claimsを更新（後続claimの帰属判定に使う）
                    nodes_with_claims.append({
                        "node_id": node_id, "revision": 1, "layer": layer,
                        "type": nn.get("type", "Theory"), "subtype": nn.get("subtype"),
                        "status": "proposed",
                        "title": nn.get("title", ""),
                        "claims": [{"claim_id": cid, "statement": claim["text"]}]
                    })

                stats["generated"] += 1
                generated_this_cycle += 1
                stats["details"].append({
                    "action": "generated", "node_id": node_id,
                    "title": nn.get("title", ""), "layer": layer,
                    "parent": nn.get("parent_node_id"),
                    "evidence_id": eid
                })

    if verbose:
        print(f"\n=== Summary: {stats['generated']} generated, "
              f"{stats['absorbed']} absorbed, {stats['rejected']} rejected ===")

    return stats


# ════════════════════════════════════════════
# 昇格/archive判定
# ════════════════════════════════════════════

def check_promotion(db, node_id: str, revision: int = 1) -> dict:
    """provisionalノードの昇格条件を判定。

    昇格条件（Fable設計）:
      - 独立evidence >= 2（同一論文の2 claimは1カウント）
      - edge >= 2
      - contradiction claimなし or dispute resolved

    Returns:
        {"eligible": bool, "reason": str, "independent_evidence": int, "edges": int}
    """
    # 独立evidenceカウント（origin_group単位で重複排除）
    ev_rows = db.execute("""
        SELECT DISTINCT e.origin_group
        FROM support_assessment sa
        JOIN evidence e ON sa.evidence_id = e.evidence_id
        WHERE sa.target_node = ? AND sa.target_revision = ?
          AND e.origin_group IS NOT NULL
    """, (node_id, revision)).fetchall()
    independent_evidence = len(ev_rows)

    # エッジカウント（from/to両方向）
    edge_count = db.execute("""
        SELECT COUNT(*) FROM edge
        WHERE (from_node = ? AND from_revision = ?)
           OR (to_node = ? AND to_revision = ?)
    """, (node_id, revision, node_id, revision)).fetchone()[0]

    # contradiction確認
    contradictions = db.execute("""
        SELECT COUNT(*) FROM claim
        WHERE node_id = ? AND node_revision = ?
          AND epistemic_status = 'contradicted'
    """, (node_id, revision)).fetchone()[0]

    eligible = (independent_evidence >= 2 and edge_count >= 2 and contradictions == 0)
    reason_parts = []
    if independent_evidence < 2:
        reason_parts.append(f"evidence={independent_evidence}/2")
    if edge_count < 2:
        reason_parts.append(f"edges={edge_count}/2")
    if contradictions > 0:
        reason_parts.append(f"contradictions={contradictions}")

    return {
        "eligible": eligible,
        "reason": "ready" if eligible else "; ".join(reason_parts),
        "independent_evidence": independent_evidence,
        "edges": edge_count,
        "contradictions": contradictions,
    }


def run_promotion(dry_run: bool = False, verbose: bool = True) -> dict:
    """全provisionalノードの昇格/archive判定"""
    db = get_db()

    # provisionalノード（status="proposed"でnode_factory_source付き）
    rows = db.execute("""
        SELECT n.id, n.revision, n.status, n.layer, n.type,
               json_extract(n.data, '$.title') as title,
               json_extract(n.data, '$.node_factory_source') as source
        FROM node n
        WHERE n.status = 'proposed'
          AND json_extract(n.data, '$.node_factory_source') IS NOT NULL
        ORDER BY n.id
    """).fetchall()

    if verbose:
        print(f"=== Promotion Check: {len(rows)} provisional nodes ===\n")

    stats = {"promoted": 0, "archived": 0, "pending": 0}

    for nid, rev, status, layer, ntype, title, source in rows:
        check = check_promotion(db, nid, rev)

        if verbose:
            print(f"  {nid}: {title or nid}")
            print(f"    evidence={check['independent_evidence']}, edges={check['edges']}, "
                  f"contradictions={check['contradictions']}")

        if check["eligible"]:
            if verbose:
                print(f"    → PROMOTE to draft")
            if not dry_run:
                from mvp_store import set_status
                set_status(db, nid, rev, "draft")
            stats["promoted"] += 1

        else:
            # archive判定: node_factory_sourceのevidenceが古い（2サイクル以上）かつevidence=0
            if check["independent_evidence"] == 0:
                # TODO: サイクルカウントの追跡（現状は即archiveしない、警告のみ）
                if verbose:
                    print(f"    → PENDING (no evidence yet, {check['reason']})")
                stats["pending"] += 1
            else:
                if verbose:
                    print(f"    → PENDING ({check['reason']})")
                stats["pending"] += 1

    if verbose:
        print(f"\n=== Summary: {stats['promoted']} promoted, "
              f"{stats['archived']} archived, {stats['pending']} pending ===")

    return stats


# ════════════════════════════════════════════
# status表示
# ════════════════════════════════════════════

def show_status():
    db = get_db()
    rows = db.execute("""
        SELECT n.id, n.layer, n.type, n.status,
               json_extract(n.data, '$.title') as title,
               json_extract(n.data, '$.node_factory_source') as source,
               json_extract(n.data, '$.decision') as decision
        FROM node n
        WHERE json_extract(n.data, '$.node_factory_source') IS NOT NULL
        ORDER BY n.id
    """).fetchall()

    print(f"=== Node Factory Status: {len(rows)} factory-generated nodes ===\n")

    for nid, layer, ntype, status, title, source, decision in rows:
        check = check_promotion(db, nid, 1)
        print(f"  {nid} [{status}] ({layer}/{ntype}): {title or nid}")
        print(f"    source={source}, decision={decision}")
        print(f"    evidence={check['independent_evidence']}, edges={check['edges']}")
        # エッジ一覧
        edges = db.execute("""
            SELECT type, from_node, to_node FROM edge
            WHERE from_node = ? OR to_node = ?
        """, (nid, nid)).fetchall()
        for etype, fn, tn in edges:
            if fn == nid:
                print(f"    edge: {nid} --{etype}--> {tn}")
            else:
                print(f"    edge: {fn} --{etype}--> {nid}")
        print()


# ════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Node Factory: provisional node generation")
    sub = parser.add_subparsers(dest="cmd")

    p_gen = sub.add_parser("generate", help="Generate nodes from unresolved claims")
    p_gen.add_argument("--dry-run", action="store_true")

    p_promo = sub.add_parser("promote", help="Check and promote provisional nodes")
    p_promo.add_argument("--dry-run", action="store_true")

    p_status = sub.add_parser("status", help="Show factory-generated node status")

    args = parser.parse_args()

    if args.cmd == "generate":
        generate_nodes(dry_run=args.dry_run)
    elif args.cmd == "promote":
        run_promotion(dry_run=args.dry_run)
    elif args.cmd == "status":
        show_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
