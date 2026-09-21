"""知識OSに質問して根拠付き回答を得る

Usage:
    python ask_knowledge.py "なぜ第二価格オークションでは正直入札が最適なのか"
    python ask_knowledge.py "エントロピーと圧縮の関係は？"
    python ask_knowledge.py "Shannon符号化定理とは何か" --no-vectors
"""

import argparse
import json
import os
import sys
import urllib.request

from search_engine import hybrid_search, get_db, resolve_to_nodes, trace_evidence_chain

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-haiku-4-5-20251001"


def _expand_query(query: str) -> str:
    """日本語キーワードを英語同義語で補強してBM25ヒット率を上げる"""
    expansions = {
        "オークション": "auction",
        "第二価格": "second price Vickrey",
        "正直": "truthful bidding",
        "入札": "bidding auction",
        "ナッシュ均衡": "Nash equilibrium",
        "支配戦略": "dominant strategy",
        "インセンティブ": "incentive compatibility",
        "エントロピー": "entropy",
        "情報理論": "information theory",
        "圧縮": "compression coding",
        "ハフマン": "Huffman",
        "シャノン": "Shannon",
        "符号": "coding",
        "無作為": "randomization RCT",
        "因果": "causal inference",
        "メカニズム": "mechanism design",
        "均衡": "equilibrium",
    }
    extra = []
    for ja, en in expansions.items():
        if ja in query:
            extra.append(en)
    if extra:
        return query + " " + " ".join(extra)
    return query


def build_context(query: str, limit: int = 6, use_vectors: bool = True) -> dict:
    """検索→ノード解決→根拠追跡を実行し、LLMに渡すコンテキストを構築"""
    expanded = _expand_query(query)
    results = hybrid_search(expanded, limit, use_vectors)
    if not results:
        return {"query": query, "nodes": [], "cards": []}

    db = get_db()
    ref_ids = [rid for rid, _ in results]
    nodes = resolve_to_nodes(ref_ids)

    # 旧スキーマの検索結果（カード本文の断片）
    cards = []
    for ref_id, score in results:
        row = db.execute(
            "SELECT title, role, definition, mechanism FROM docs WHERE ref_id = ?",
            (ref_id,)
        ).fetchone()
        if row:
            cards.append({
                "ref_id": ref_id, "score": score,
                "title": row[0], "role": row[1],
                "definition": row[2][:500] if row[2] else "",
                "mechanism": row[3][:500] if row[3] else "",
            })

    # MVPノードの根拠チェーン
    node_details = []
    for n in nodes:
        chain = trace_evidence_chain(n["node_id"], n["revision"])
        node_details.append({**n, **chain})

    return {"query": query, "nodes": node_details, "cards": cards}


def format_prompt(ctx: dict) -> str:
    """コンテキストからLLMプロンプトを組み立て"""
    parts = []
    parts.append("あなたは根拠追跡可能な知識エンジンです。以下の検証済み知識を使って質問に回答してください。")
    parts.append("")
    parts.append("## ルール")
    parts.append("1. 回答は検証済みの知識（approved claimとevidence）に基づくこと")
    parts.append("2. blocked/proposedのノードは「未検証」と明示すること")
    parts.append("3. 根拠の出典（DOI、locator）を回答に含めること")
    parts.append("4. 知識ベースにない情報で補完しないこと")
    parts.append("5. 回答は簡潔に（300字以内）")
    parts.append("")

    # 検証済みノード
    if ctx["nodes"]:
        parts.append("## 検証済み知識ノード")
        for n in ctx["nodes"]:
            status_mark = "✓" if n["status"] == "approved" else "▲" if n["status"] == "blocked" else "○"
            parts.append(f"\n### {status_mark} {n['node_id']}@{n['revision']} [{n['layer']}/{n['type']}] status={n['status']}")

            if n.get("claims"):
                for c in n["claims"]:
                    parts.append(f"  Claim ({c['kind']}, {c['epistemic_status']}): {c['statement']}")

            if n.get("evidence"):
                for e in n["evidence"]:
                    hash_ok = "verified" if e["content_hash_present"] else "unverified"
                    parts.append(f"  Evidence: {e['evidence_id']} [{e['kind']}] grade={e['reliability_grade']} ({hash_ok})")
                    if e.get("source_uri"):
                        parts.append(f"    URI: {e['source_uri']}")
                    if e.get("locator"):
                        parts.append(f"    Locator: {e['locator']}")

    # カード本文（旧スキーマ）
    if ctx["cards"]:
        parts.append("\n## 関連カード（参考）")
        for c in ctx["cards"]:
            parts.append(f"\n### {c['ref_id']}: {c['title']}")
            if c["definition"]:
                parts.append(f"Definition: {c['definition']}")
            if c["mechanism"]:
                parts.append(f"Mechanism: {c['mechanism']}")

    parts.append(f"\n## 質問\n{ctx['query']}")

    return "\n".join(parts)


def call_haiku(prompt: str) -> str:
    """Claude Haiku APIを呼び出し"""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(url, json.dumps(payload).encode(), headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return "\n".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")


def ask(query: str, use_vectors: bool = True, verbose: bool = False) -> str:
    """質問→検索→根拠追跡→LLM回答の全パイプライン"""
    ctx = build_context(query, use_vectors=use_vectors)

    if not ctx["nodes"] and not ctx["cards"]:
        return "該当する知識が見つかりませんでした。"

    prompt = format_prompt(ctx)
    if verbose:
        print("=" * 60)
        print("LLM PROMPT:")
        print("=" * 60)
        print(prompt)
        print("=" * 60)

    return call_haiku(prompt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="知識OSに質問する")
    parser.add_argument("query", help="質問文")
    parser.add_argument("--no-vectors", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true", help="LLMプロンプトを表示")
    args = parser.parse_args()

    print(f"Q: {args.query}\n")
    print("検索・根拠追跡中...\n")

    answer = ask(args.query, use_vectors=not args.no_vectors, verbose=args.verbose)

    print("A:", answer)
