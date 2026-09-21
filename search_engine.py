#!/usr/bin/env python3
"""ハイブリッド検索エンジン: フィールド別BM25(OR) + 埋め込み + RRF統合

使い方:
    python search_engine.py build [--include-inbox]
    python search_engine.py search "クエリ" [--limit 6]
    python search_engine.py embed                       # 埋め込み生成（API）
"""

from __future__ import annotations

import config  # noqa: F401 — load .env

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

import numpy as np
from knowledge_policy import note_usable, node_usable, claim_usable

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "work" / "search.sqlite3"
EMBED_FILE = ROOT / "work" / "embeddings.npz"
ROLES = ("accepted", "candidates", "concepts", "perspectives")

EMBED_API_KEY = os.environ.get("EMBED_API_KEY", "")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "")
EMBED_ENDPOINT = os.environ.get("EMBED_ENDPOINT", "")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ═══════════════════════════════════════════
# ソース収集 + フロントマター解析
# ═══════════════════════════════════════════

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """YAMLフロントマターとボディを分離。PyYAML不要の簡易版。"""
    fm = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]
            for line in parts[1].strip().splitlines():
                m = re.match(r'^(\w[\w_]*)\s*:\s*(.+)', line)
                if m:
                    key, val = m.group(1), m.group(2).strip()
                    if val.startswith("[") and val.endswith("]"):
                        val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",")]
                    elif val.startswith('"') and val.endswith('"'):
                        val = val[1:-1]
                    fm[key] = val
    return fm, body


def extract_section(body: str, heading: str) -> str:
    """## heading の内容を抽出。"""
    pattern = rf"##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##\s|\Z)"
    m = re.search(pattern, body, re.DOTALL)
    return m.group(1).strip() if m else ""


def sources(include_inbox: bool = False) -> list[dict]:
    output = []
    for role in ROLES:
        directory = ROOT / role
        if not directory.exists():
            continue
        for path in directory.rglob("*.md"):
            relative = path.relative_to(directory)
            if path.name.startswith("_") or path.name in {"README.md", "template.md"}:
                continue
            if not include_inbox and "_inbox" in relative.parts:
                continue
            if not include_inbox and not note_usable(role, path.relative_to(ROOT), ROOT):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            fm, body = parse_frontmatter(text)

            ref_id = fm.get("concept_id", f"{role}:{path.stem}")
            title = fm.get("canonical_name", path.stem)
            aliases = fm.get("aliases", [])
            if isinstance(aliases, str):
                aliases = [aliases]

            definition = extract_section(body, "Definition")
            mechanism = extract_section(body, "Mechanism")

            output.append({
                "ref_id": ref_id,
                "role": role,
                "path": str(path.relative_to(ROOT)),
                "title": title,
                "aliases": " ".join(aliases),
                "definition": definition,
                "mechanism": mechanism,
                "body": body,
                "digest": hashlib.sha256(text.encode()).hexdigest(),
            })
    return output


# ═══════════════════════════════════════════
# フィールド別FTS5 インデックス構築
# ═══════════════════════════════════════════

def get_db() -> sqlite3.Connection:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE)
    db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(
            title,
            aliases,
            definition,
            mechanism,
            body,
            ref_id UNINDEXED,
            role UNINDEXED,
            path UNINDEXED
        )
    """)
    db.execute("CREATE TABLE IF NOT EXISTS manifest (path TEXT PRIMARY KEY, digest TEXT NOT NULL)")
    return db


def build_index(include_inbox: bool = False) -> None:
    db = get_db()
    docs = sources(include_inbox=include_inbox)
    changed = 0
    current = set()

    for doc in docs:
        current.add(doc["path"])
        prior = db.execute("SELECT digest FROM manifest WHERE path = ?", (doc["path"],)).fetchone()
        if prior and prior[0] == doc["digest"]:
            continue
        db.execute("DELETE FROM docs WHERE path = ?", (doc["path"],))
        db.execute(
            "INSERT INTO docs(title, aliases, definition, mechanism, body, ref_id, role, path) VALUES (?,?,?,?,?,?,?,?)",
            (doc["title"], doc["aliases"], doc["definition"], doc["mechanism"], doc["body"],
             doc["ref_id"], doc["role"], doc["path"]),
        )
        db.execute("INSERT OR REPLACE INTO manifest(path, digest) VALUES (?, ?)", (doc["path"], doc["digest"]))
        changed += 1

    for (path,) in db.execute("SELECT path FROM manifest").fetchall():
        if path not in current:
            db.execute("DELETE FROM docs WHERE path = ?", (path,))
            db.execute("DELETE FROM manifest WHERE path = ?", (path,))
            changed += 1

    db.commit()
    total = db.execute("SELECT count(*) FROM docs").fetchone()[0]
    print(f"FTS更新: {changed}件 / 索引済み: {total}件")


# ═══════════════════════════════════════════
# 埋め込み生成
# ═══════════════════════════════════════════

def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embedding APIでバッチ埋め込み。"""
    results = []
    for t in texts:
        url = f"{EMBED_ENDPOINT}/models/{EMBED_MODEL}:embedContent?key={EMBED_API_KEY}"
        payload = json.dumps({"model": f"models/{EMBED_MODEL}", "content": {"parts": [{"text": t[:2048]}]}}).encode()
        req = urllib.request.Request(url, payload, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        results.append(data["embedding"]["values"])
    return results


def build_embeddings(include_inbox: bool = False) -> None:
    docs = sources(include_inbox=include_inbox)
    if not docs:
        print("ドキュメントがありません")
        return

    texts = []
    ref_ids = []
    for doc in docs:
        embed_text = f"{doc['title']}\n{doc['aliases']}\n{doc['definition'][:500]}"
        texts.append(embed_text)
        ref_ids.append(doc["ref_id"])

    # バッチ制限回避（100件ずつ）
    all_embeddings = []
    for i in range(0, len(texts), 100):
        batch = texts[i:i+100]
        embs = embed_batch(batch)
        all_embeddings.extend(embs)
        print(f"  埋め込み生成: {min(i+100, len(texts))}/{len(texts)}")

    matrix = np.array(all_embeddings, dtype=np.float32)
    # L2正規化
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    matrix = matrix / norms

    np.savez(EMBED_FILE, embeddings=matrix, ref_ids=np.array(ref_ids))
    print(f"埋め込み保存: {EMBED_FILE} ({matrix.shape})")


# ═══════════════════════════════════════════
# 検索
# ═══════════════════════════════════════════

def bm25_search(db: sqlite3.Connection, query: str, limit: int = 30, include_candidates=False) -> list[tuple[str, float]]:
    """フィールド別重み付きBM25 OR検索。title:10, aliases:8, definition:4, mechanism:2, body:1"""
    terms = re.findall(r"[\w]+", query, flags=re.UNICODE)
    if not terms:
        return []
    match_expr = " OR ".join(f'"{t}"' for t in terms)
    rows = db.execute(
        "SELECT ref_id, bm25(docs, 10.0, 8.0, 4.0, 2.0, 1.0) AS score FROM docs WHERE docs MATCH ? ORDER BY score LIMIT ?",
        (match_expr, limit),
    ).fetchall()
    return [(r[0], r[1]) for r in rows if include_candidates or _ref_usable(db, r[0])]


def _ref_usable(db, ref_id):
    row = db.execute('SELECT role,path FROM docs WHERE ref_id=?', (ref_id,)).fetchone()
    if not row or not note_usable(row[0], row[1], ROOT):
        return False
    previous = db.execute('SELECT digest FROM manifest WHERE path=?', (row[1],)).fetchone()
    return bool(previous and previous[0] == hashlib.sha256((ROOT / row[1]).read_text(encoding='utf-8').encode()).hexdigest())


def vector_search(query: str, limit: int = 30, include_candidates=False) -> list[tuple[str, float]]:
    """埋め込みによるコサイン検索。"""
    if not EMBED_FILE.exists():
        return []
    data = np.load(EMBED_FILE, allow_pickle=True)
    matrix = data["embeddings"]
    ref_ids = data["ref_ids"]

    qv = np.array(embed_batch([query])[0], dtype=np.float32)
    qv = qv / (np.linalg.norm(qv) or 1)

    scores = matrix @ qv
    top_idx = np.argsort(-scores)[:limit]
    db = get_db()
    return [(str(ref_ids[i]), float(scores[i])) for i in top_idx
            if include_candidates or _ref_usable(db, str(ref_ids[i]))]


def rrf_fuse(result_sets: list[list[tuple[str, float]]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion。"""
    scores: dict[str, float] = {}
    for results in result_sets:
        for rank, (doc_id, _) in enumerate(results):
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def hybrid_search(query: str, limit: int = 6, use_vectors: bool = True, include_candidates=False) -> list[tuple[str, float]]:
    """BM25 + ベクトル検索のRRF統合。"""
    db = get_db()
    bm25_results = bm25_search(db, query, limit=30, include_candidates=include_candidates)

    result_sets = [bm25_results]

    if use_vectors and EMBED_FILE.exists():
        vec_results = vector_search(query, limit=30, include_candidates=include_candidates)
        result_sets.append(vec_results)

    fused = rrf_fuse(result_sets)
    # The normalized graph is independent of the legacy Markdown/vector index.
    mvp = _get_mvp_db()
    if mvp:
        from knowledge_policy import usable_claim_rows
        terms = re.findall(r'[\w]+', query.lower())
        scores = {}
        for claim in usable_claim_rows(mvp):
            node = mvp.execute('SELECT data FROM node WHERE id=? AND revision=?',
                               (claim['node_id'],claim['revision'])).fetchone()
            haystack = (claim['statement']+' '+(node[0] if node else '')+' '+claim['node_id']).lower()
            score = sum(t in haystack for t in terms)
            if score:
                scores[claim['node_id']] = scores.get(claim['node_id'],0)+score
        fused = rrf_fuse([fused, sorted(scores.items(),key=lambda x:x[1],reverse=True)])
    return fused[:limit]


def search_cli(query: str, limit: int, use_vectors: bool) -> None:
    results = hybrid_search(query, limit, use_vectors)
    if not results:
        print("該当なし。")
        return
    db = get_db()
    activated = []
    for ref_id, score in results:
        activated.append(ref_id)
        row = db.execute("SELECT title, role, path FROM docs WHERE ref_id = ?", (ref_id,)).fetchone()
        if row:
            print(f"  [{ref_id}] score={score:.4f}  {row[0]}  (role={row[1]})")
        else:
            print(f"  [{ref_id}] score={score:.4f}")

    # 共活性化ログ記録
    try:
        from kb import log_query
        scores_list = [score for _, score in results]
        log_query(query, activated, searcher="search_engine", scores=scores_list)
    except Exception:
        pass  # kb.py未初期化でも検索は止めない


# ═══════════════════════════════════════════
# 新スキーマProjection: 検索結果 → MVP node → claim@revision → evidence
# ═══════════════════════════════════════════

def _get_mvp_db():
    """MVPストアへの読み取り専用接続"""
    from mvp_store import DB_PATH
    if not DB_PATH.exists():
        return None
    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA query_only=ON")
    return db


def resolve_to_nodes(ref_ids: list[str], include_candidates=False) -> list[dict]:
    """検索結果のref_idをMVPストアのノードに解決する。
    マッチしないref_idはスキップ。blocked/proposedも含めて返す（表示時にフィルタ）。"""
    mvp = _get_mvp_db()
    if not mvp:
        return []
    resolved = []
    for rid in ref_ids:
        row = mvp.execute(
            "SELECT id, revision, layer, type, subtype, status FROM node WHERE id = ? ORDER BY revision DESC LIMIT 1",
            (rid,)
        ).fetchone()
        if row and (include_candidates or node_usable(mvp, row[0], row[1])):
            resolved.append({
                "node_id": row[0], "revision": row[1], "layer": row[2],
                "type": row[3], "subtype": row[4], "status": row[5],
            })
    return resolved


def trace_evidence_chain(node_id: str, revision: int, include_candidates=False) -> dict:
    """ノードのclaim一覧と各claimに紐づくevidence locatorを返す"""
    mvp = _get_mvp_db()
    if not mvp:
        return {"claims": [], "evidence": []}

    claims = []
    for r in mvp.execute(
        "SELECT claim_id, statement, kind, epistemic_status FROM claim WHERE node_id=? AND node_revision=?",
        (node_id, revision)
    ).fetchall():
        if include_candidates or claim_usable(mvp, r[0]):
            claims.append({"claim_id": r[0], "statement": r[1], "kind": r[2], "epistemic_status": r[3]})

    evidence = []
    for r in mvp.execute("""
        SELECT e.evidence_id, e.kind, e.source_uri, e.locator, e.content_hash, e.reliability_grade,
               sa.support_role, sa.target_claim
        FROM support_assessment sa
        JOIN evidence e ON sa.evidence_id = e.evidence_id
        WHERE sa.target_node = ? AND sa.target_revision = ?
    """, (node_id, revision)).fetchall():
        if not include_candidates:
            if r[7] not in {c['claim_id'] for c in claims}:
                continue
            report = json.loads(mvp.execute('SELECT report FROM claim_validation WHERE claim_id=? ORDER BY id DESC LIMIT 1', (r[7],)).fetchone()[0])
            if r[0] not in report.get('evidence_fingerprints', {}):
                continue
        evidence.append({
            "evidence_id": r[0], "kind": r[1], "source_uri": r[2],
            "locator": r[3], "content_hash_present": r[4] is not None,
            "reliability_grade": r[5], "support_role": r[6], "target_claim": r[7],
        })

    return {"claims": claims, "evidence": evidence}


def trace_cli(query: str, limit: int, use_vectors: bool) -> None:
    """E2Eデモ: 質問 → 検索 → node解決 → claim@revision → evidence locator"""
    results = hybrid_search(query, limit, use_vectors)
    if not results:
        print("該当なし。")
        return

    db = get_db()
    ref_ids = [rid for rid, _ in results]
    nodes = resolve_to_nodes(ref_ids)

    print(f"Query: {query}")
    print(f"Search hits: {len(results)}, MVP nodes resolved: {len(nodes)}\n")

    # 検索結果（MVPノード外も含む）
    for ref_id, score in results:
        row = db.execute("SELECT title, role FROM docs WHERE ref_id = ?", (ref_id,)).fetchone()
        marker = ""
        node_match = next((n for n in nodes if n["node_id"] == ref_id), None)
        if node_match:
            marker = f" → [{node_match['status'].upper()}] {node_match['node_id']}@{node_match['revision']}"
        title = row[0] if row else "?"
        print(f"  [{ref_id}] score={score:.4f}  {title}{marker}")

    # MVPノードの根拠追跡
    if nodes:
        print("\n── Evidence Trace ──")
        for n in nodes:
            status_mark = "●" if n["status"] == "approved" else "▲" if n["status"] == "blocked" else "○"
            print(f"\n{status_mark} {n['node_id']}@{n['revision']} [{n['layer']}/{n['type']}] status={n['status']}")

            chain = trace_evidence_chain(n["node_id"], n["revision"])

            if chain["claims"]:
                for c in chain["claims"]:
                    print(f"    claim: {c['claim_id']} ({c['kind']}) [{c['epistemic_status']}]")
                    print(f"           {c['statement'][:100]}")
            else:
                print("    (no claims registered)")

            if chain["evidence"]:
                for e in chain["evidence"]:
                    hash_status = "✓" if e["content_hash_present"] else "✗"
                    print(f"    evidence: {e['evidence_id']} [{e['kind']}] grade={e['reliability_grade']} hash={hash_status}")
                    print(f"              {e['source_uri'] or '(no URI)'}")
                    print(f"              locator: {e['locator'] or '(none)'}")
                    if e["target_claim"]:
                        print(f"              → claim: {e['target_claim']}")
            else:
                print("    (no evidence)")

    # 共活性化ログ（新スキーマIDで記録）
    try:
        from kb import log_query
        activated = ref_ids
        scores_list = [score for _, score in results]
        log_query(query, activated, searcher="search_engine_trace", scores=scores_list)
    except Exception:
        pass


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ハイブリッド検索エンジン")
    parser.add_argument("--include-inbox", action="store_true")
    cmds = parser.add_subparsers(dest="command", required=True)

    cmds.add_parser("build", help="FTSインデックス構築")
    cmds.add_parser("embed", help="埋め込み生成")

    s = cmds.add_parser("search", help="ハイブリッド検索")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=6)
    s.add_argument("--no-vectors", action="store_true", help="ベクトル検索を使わない")

    t = cmds.add_parser("trace", help="検索→node→claim→evidence 根拠追跡")
    t.add_argument("query")
    t.add_argument("--limit", type=int, default=6)
    t.add_argument("--no-vectors", action="store_true", help="ベクトル検索を使わない")

    args = parser.parse_args()

    if args.command == "build":
        build_index(include_inbox=args.include_inbox)
    elif args.command == "embed":
        build_embeddings(include_inbox=args.include_inbox)
    elif args.command == "trace":
        trace_cli(args.query, args.limit, use_vectors=not args.no_vectors)
    else:
        search_cli(args.query, args.limit, use_vectors=not args.no_vectors)
