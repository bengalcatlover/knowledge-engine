"""relation_engine: エッジ推論・検証エンジン（最小版）

Fable 5 + GPT-6 Astra 統合設計に基づく。

2段ロケット方式:
  Stage 1: 安い候補生成（co-evidence / claim keyword co-occurrence）
  Stage 2: LLM検証（Haiku）→ evidence-backed か HYP_EDGE 隔離

機能:
  1. generate_candidates() — co-evidenceペアから関係候補を生成
  2. verify_candidate()   — Haikuで候補を検証、エッジ型を決定
  3. resolve_g3()         — 既存G3 gapに対してco-evidence検索で解消試行
  4. run_relate()         — orchestratorから呼ばれる統合エントリポイント

Usage:
    python relation_engine.py candidates   # 候補一覧表示
    python relation_engine.py resolve      # G3解消
    python relation_engine.py run          # 候補生成+検証+G3解消
    python relation_engine.py run --dry-run
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.request
from dataclasses import dataclass

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from mvp_store import init_db, get_db, add_edge, add_support, _uid, _now

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# エッジ型の許可リスト（Fable/Astra設計準拠）
VALID_EDGE_TYPES = [
    "GENERALIZES",      # A generalizes B
    "SPECIALIZES",      # A is a special case of B
    "DEPENDS_ON",       # A requires B
    "DERIVES_FROM",     # A is derived from B
    "CONTRADICTS",      # A contradicts B
    "COMPLEMENTS",      # A and B complement each other
    "APPLIES_TO",       # A applies B's theory
    "EXTENDS",          # A extends B
    "IS_A",             # A is a kind of B
    "HAS_SCOPED_INSTANCE",  # existing type
    "ABSTRACTS_FROM",       # existing type
]

# ════════════════════════════════════════════
# LLM呼び出し
# ════════════════════════════════════════════

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


VERIFY_PROMPT = """You are a knowledge graph edge verifier. Given two nodes and their claims, decide if a directed relationship exists between them.

NODE A: {node_a_id}
Title: {node_a_title}
Claims:
{node_a_claims}

NODE B: {node_b_id}
Title: {node_b_title}
Claims:
{node_b_claims}

CO-EVIDENCE (papers that support both nodes):
{co_evidence}

CANDIDATE REASON: {candidate_reason}

TASK:
1. Is there a meaningful, specific relationship between Node A and Node B?
2. If yes, what is the edge type? Choose from: {edge_types}
3. What is the direction? A→B or B→A?
4. What is the justification? Cite specific claims or evidence.
5. Confidence: "verified" (clear evidence supports this) or "hypothesis" (plausible but not directly evidenced)

Reply in JSON:
```json
{{
  "exists": true/false,
  "edge_type": "TYPE",
  "direction": "A_to_B" or "B_to_A",
  "justification": "why this relationship holds",
  "confidence": "verified" or "hypothesis",
  "justification_claims": ["claim_id_1", "claim_id_2"]
}}
```

Rules:
- Do NOT invent relationships. If co-evidence is weak or claims don't connect, set exists=false.
- "verified" = at least one claim or evidence directly states or implies this relationship.
- "hypothesis" = plausible inference but no direct statement in the evidence.
- Be specific about the justification. Vague answers like "they are related" are NOT acceptable.
"""


# ════════════════════════════════════════════
# Stage 1: 候補生成
# ════════════════════════════════════════════

@dataclass
class EdgeCandidate:
    node_a: str
    node_b: str
    reason: str
    co_evidence_ids: list
    score: float  # co-evidence count or keyword overlap


def generate_candidates(db: sqlite3.Connection, max_candidates: int = 20) -> list[EdgeCandidate]:
    """co-evidenceペアからエッジ候補を生成。

    同じevidenceが2つの異なるノードをsupportしていれば、
    それらのノード間に関係がある可能性が高い。
    """
    # 既存エッジのペアを取得（重複生成を避ける）
    existing_pairs = set()
    for r in db.execute("SELECT from_node, to_node FROM edge"):
        existing_pairs.add((r[0], r[1]))
        existing_pairs.add((r[1], r[0]))

    # co-evidenceペアを検出
    rows = db.execute("""
        SELECT sa1.target_node, sa2.target_node,
               GROUP_CONCAT(DISTINCT sa1.evidence_id) as evidence_ids,
               COUNT(DISTINCT sa1.evidence_id) as co_count
        FROM support_assessment sa1
        JOIN support_assessment sa2
            ON sa1.evidence_id = sa2.evidence_id
            AND sa1.target_node < sa2.target_node
        WHERE sa1.target_node != sa2.target_node
        GROUP BY sa1.target_node, sa2.target_node
        HAVING co_count >= 1
        ORDER BY co_count DESC
    """).fetchall()

    candidates = []
    for r in rows:
        node_a, node_b = r[0], r[1]
        evidence_ids = r[2].split(",") if r[2] else []
        co_count = r[3]

        # 既存エッジがあればスキップ
        if (node_a, node_b) in existing_pairs:
            continue

        candidates.append(EdgeCandidate(
            node_a=node_a,
            node_b=node_b,
            reason=f"co-evidence: {co_count} shared evidence(s)",
            co_evidence_ids=evidence_ids,
            score=co_count,
        ))

        if len(candidates) >= max_candidates:
            break

    return candidates


# ════════════════════════════════════════════
# Stage 2: LLM検証
# ════════════════════════════════════════════

def _load_node_info(db, node_id: str) -> dict:
    """ノードのタイトルとclaim一覧を取得"""
    row = db.execute(
        "SELECT id, revision, data FROM node WHERE id=? ORDER BY revision DESC LIMIT 1",
        (node_id,)
    ).fetchone()
    if not row:
        return {"id": node_id, "revision": 0, "title": "Unknown", "claims": []}

    data = {}
    try:
        data = json.loads(row[2]) if row[2] else {}
    except json.JSONDecodeError:
        pass

    claims = db.execute(
        "SELECT claim_id, statement FROM claim WHERE node_id=? ORDER BY claim_id",
        (node_id,)
    ).fetchall()

    return {
        "id": node_id,
        "revision": row[1],
        "title": data.get("title", node_id),
        "claims": [{"claim_id": c[0], "statement": c[1]} for c in claims],
    }


def _format_claims(claims: list[dict], max_items: int = 5) -> str:
    if not claims:
        return "  (no claims)"
    lines = []
    for c in claims[:max_items]:
        lines.append(f"  - [{c['claim_id']}] {c['statement'][:120]}")
    if len(claims) > max_items:
        lines.append(f"  ... and {len(claims) - max_items} more")
    return "\n".join(lines)


def _format_evidence(db, evidence_ids: list[str], max_items: int = 3) -> str:
    if not evidence_ids:
        return "  (none)"
    lines = []
    for eid in evidence_ids[:max_items]:
        row = db.execute(
            "SELECT evidence_id, source_uri, reliability_grade FROM evidence WHERE evidence_id=?",
            (eid,)
        ).fetchone()
        if row:
            lines.append(f"  - [{row[0]}] grade={row[2]} uri={row[1] or 'n/a'}")
    return "\n".join(lines) if lines else "  (none)"


def verify_candidate(db: sqlite3.Connection, candidate: EdgeCandidate,
                     dry_run: bool = False, verbose: bool = True) -> dict:
    """Haikuで候補エッジを検証"""
    node_a = _load_node_info(db, candidate.node_a)
    node_b = _load_node_info(db, candidate.node_b)

    prompt = VERIFY_PROMPT.format(
        node_a_id=node_a["id"],
        node_a_title=node_a["title"],
        node_a_claims=_format_claims(node_a["claims"]),
        node_b_id=node_b["id"],
        node_b_title=node_b["title"],
        node_b_claims=_format_claims(node_b["claims"]),
        co_evidence=_format_evidence(db, candidate.co_evidence_ids),
        candidate_reason=candidate.reason,
        edge_types=", ".join(VALID_EDGE_TYPES),
    )

    if verbose:
        print(f"  Verifying: {candidate.node_a} ↔ {candidate.node_b} ({candidate.reason})")

    raw = _call_anthropic(prompt)

    # JSON抽出
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw, re.DOTALL)
    text = match.group(1) if match else raw
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # JSON内部を探す
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            result = json.loads(text[start:end])
        else:
            if verbose:
                print(f"    [WARN] Could not parse LLM output")
            return {"exists": False, "error": "parse_failed"}

    if not result.get("exists"):
        if verbose:
            print(f"    → No relationship found")
        return result

    # エッジ型の正規化
    edge_type = result.get("edge_type", "").upper().replace(" ", "_")
    if edge_type not in VALID_EDGE_TYPES:
        # 近似マッチ試行
        for vt in VALID_EDGE_TYPES:
            if edge_type in vt or vt in edge_type:
                edge_type = vt
                break
        else:
            edge_type = "COMPLEMENTS"  # フォールバック

    # 方向決定
    direction = result.get("direction", "A_to_B")
    if direction == "B_to_A":
        from_node, from_rev = node_b["id"], node_b["revision"]
        to_node, to_rev = node_a["id"], node_a["revision"]
    else:
        from_node, from_rev = node_a["id"], node_a["revision"]
        to_node, to_rev = node_b["id"], node_b["revision"]

    confidence = result.get("confidence", "hypothesis")
    justification = result.get("justification", "")
    justification_claims = result.get("justification_claims", [])

    if verbose:
        hyp_tag = " [HYP]" if confidence == "hypothesis" else ""
        print(f"    → {edge_type}: {from_node} → {to_node}{hyp_tag}")
        print(f"      Justification: {justification[:100]}")

    # エッジ登録
    if not dry_run:
        # from_claim / to_claim はjustification_claimsから取る
        from_claim = None
        to_claim = None
        for cid in justification_claims:
            if cid.startswith(from_node) or any(c["claim_id"] == cid for c in node_a["claims"] if node_a["id"] == from_node):
                from_claim = from_claim or cid
            elif cid.startswith(to_node) or any(c["claim_id"] == cid for c in node_b["claims"] if node_b["id"] == to_node):
                to_claim = to_claim or cid

        # HYP_EDGE隔離: hypothesisはrationale にタグ付け
        rationale_prefix = "[HYP_EDGE] " if confidence == "hypothesis" else ""
        rationale = f"{rationale_prefix}{justification}"

        edge_id = add_edge(
            db, edge_type,
            from_node, from_rev,
            to_node, to_rev,
            from_claim=from_claim,
            to_claim=to_claim,
            rationale=rationale,
            derivation_ref=None,
        )

        # co-evidenceをsupport_assessmentとして登録
        for eid in candidate.co_evidence_ids[:3]:
            add_support(db, eid, from_node, from_rev,
                        target_claim=from_claim,
                        support_role="premise",
                        rationale=f"relation_engine: co-evidence for {edge_type} edge",
                        assessor="relation_engine")

        # イベントログ
        db.execute("INSERT INTO event VALUES (?,?,?,?,?,?)", (
            _uid("ev-"), "edge_inferred", from_node,
            json.dumps({
                "edge_id": edge_id,
                "edge_type": edge_type,
                "from_node": from_node,
                "to_node": to_node,
                "confidence": confidence,
                "co_evidence_count": len(candidate.co_evidence_ids),
                "justification": justification[:200],
            }, ensure_ascii=False),
            _now(), "relation_engine"
        ))
        db.commit()

        result["edge_id"] = edge_id

    result["edge_type_normalized"] = edge_type
    result["from_node"] = from_node
    result["to_node"] = to_node
    return result


# ════════════════════════════════════════════
# G3解消
# ════════════════════════════════════════════

def resolve_g3_gaps(db: sqlite3.Connection, dry_run: bool = False, verbose: bool = True) -> dict:
    """既存G3 gapに対してco-evidence検索で解消を試行。

    G3のエッジに対して:
    1. from_node/to_nodeの共通evidenceを検索
    2. 見つかれば → derivation_ref を設定してG3を解消
    """
    gaps = db.execute("""
        SELECT gap_id, anchor_node, anchor_claim, scope, state
        FROM gap WHERE gap_type = 'unverified_edge' AND state = 'open'
    """).fetchall()

    stats = {"checked": 0, "resolved": 0, "unresolvable": 0}

    for gap in gaps:
        gap_id = gap[0]
        edge_id = gap[2]  # anchor_claim にedge_idが格納されている
        scope_data = {}
        try:
            scope_data = json.loads(gap[3]) if gap[3] else {}
        except (json.JSONDecodeError, TypeError):
            pass

        from_node = scope_data.get("from_node")
        to_node = scope_data.get("to_node")
        edge_type = scope_data.get("edge_type", "?")

        if not from_node or not to_node:
            continue

        stats["checked"] += 1

        # co-evidence検索
        co_evidence = db.execute("""
            SELECT DISTINCT sa1.evidence_id
            FROM support_assessment sa1
            JOIN support_assessment sa2 ON sa1.evidence_id = sa2.evidence_id
            WHERE sa1.target_node = ? AND sa2.target_node = ?
              AND sa1.target_node != sa2.target_node
        """, (from_node, to_node)).fetchall()

        if co_evidence:
            evidence_ids = [r[0] for r in co_evidence]
            if verbose:
                print(f"  G3 {gap_id}: {from_node}→{to_node} ({edge_type}) — "
                      f"resolved via {len(evidence_ids)} co-evidence")

            if not dry_run:
                # エッジのderivation_refを設定
                ref = f"co-evidence: {','.join(evidence_ids[:3])}"
                db.execute(
                    "UPDATE edge SET derivation_ref=? WHERE edge_id=?",
                    (ref, edge_id)
                )
                # G3を解消
                db.execute(
                    "UPDATE gap SET state='resolved', updated_at=? WHERE gap_id=?",
                    (_now(), gap_id)
                )
                db.commit()

            stats["resolved"] += 1
        else:
            stats["unresolvable"] += 1
            if verbose:
                print(f"  G3 {gap_id}: {from_node}→{to_node} ({edge_type}) — no co-evidence")

    return stats


# ════════════════════════════════════════════
# 統合エントリポイント
# ════════════════════════════════════════════

def run_relate(dry_run: bool = False, verbose: bool = True,
               max_candidates: int = 10, max_new_edges: int = 5) -> dict:
    """orchestratorから呼ばれる統合処理。

    Returns:
        {"candidates": int, "verified": int, "rejected": int,
         "hyp_edges": int, "g3_resolved": int}
    """
    db = get_db()
    init_db()

    stats = {
        "candidates": 0, "verified": 0, "rejected": 0,
        "hyp_edges": 0, "g3_resolved": 0, "errors": 0,
    }

    # 1. G3解消（co-evidence検索のみ、LLM不要）
    if verbose:
        print("--- G3 Resolution (co-evidence search) ---")
    g3_result = resolve_g3_gaps(db, dry_run=dry_run, verbose=verbose)
    stats["g3_resolved"] = g3_result["resolved"]

    # 2. 候補生成
    if verbose:
        print(f"\n--- Edge Candidate Generation ---")
    candidates = generate_candidates(db, max_candidates=max_candidates)
    stats["candidates"] = len(candidates)

    if verbose:
        print(f"  Found {len(candidates)} candidates")

    # 3. LLM検証（予算制限付き）
    new_edges = 0
    if verbose and candidates:
        print(f"\n--- LLM Verification (max {max_new_edges} new edges) ---")

    for cand in candidates:
        if new_edges >= max_new_edges:
            if verbose:
                print(f"  [BUDGET] Edge limit reached ({max_new_edges})")
            break

        try:
            result = verify_candidate(db, cand, dry_run=dry_run, verbose=verbose)
            if result.get("exists"):
                new_edges += 1
                if result.get("confidence") == "hypothesis":
                    stats["hyp_edges"] += 1
                else:
                    stats["verified"] += 1
            else:
                stats["rejected"] += 1
        except Exception as e:
            stats["errors"] += 1
            if verbose:
                print(f"    [ERROR] {e}")

    return stats


# ════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Relation Engine — edge inference + verification")
    sub = parser.add_subparsers(dest="cmd")

    p_cand = sub.add_parser("candidates", help="Show edge candidates")
    p_resolve = sub.add_parser("resolve", help="Resolve G3 gaps via co-evidence")
    p_resolve.add_argument("--dry-run", action="store_true")

    p_run = sub.add_parser("run", help="Full pipeline: candidates + verify + G3")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--max-candidates", type=int, default=10)
    p_run.add_argument("--max-edges", type=int, default=5)

    args = parser.parse_args()

    if args.cmd == "candidates":
        db = get_db()
        candidates = generate_candidates(db)
        print(f"=== Edge Candidates ({len(candidates)}) ===\n")
        for c in candidates:
            print(f"  {c.node_a} ↔ {c.node_b} | score={c.score:.1f} | {c.reason}")
            print(f"    evidence: {', '.join(c.co_evidence_ids[:3])}")

    elif args.cmd == "resolve":
        db = get_db()
        result = resolve_g3_gaps(db, dry_run=args.dry_run)
        print(f"\n=== G3 Resolution: {result} ===")

    elif args.cmd == "run":
        result = run_relate(
            dry_run=args.dry_run,
            max_candidates=args.max_candidates,
            max_new_edges=args.max_edges,
        )
        print(f"\n=== Relation Engine Results ===")
        for k, v in result.items():
            print(f"  {k}: {v}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
