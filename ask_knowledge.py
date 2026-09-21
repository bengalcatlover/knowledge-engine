"""知識OSに質問して根拠付き回答を得る

Usage:
    python ask_knowledge.py "なぜ第二価格オークションでは正直入札が最適なのか"
    python ask_knowledge.py "エントロピーと圧縮の関係は？"
    python ask_knowledge.py "Shannon符号化定理とは何か" --no-vectors
"""

import argparse
import json
import sys


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")



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


def build_context(query: str, limit: int = 6, use_vectors: bool = False) -> dict:
    from answer_service import context
    return context(query)


def format_prompt(ctx: dict) -> str:
    return json.dumps(ctx, ensure_ascii=False)


def call_worker(prompt: str) -> str:
    # Compatibility helper; no direct high-cost provider path.
    from cheap_llm import complete
    return complete(prompt, 'answer_evidence_selection', 512)


def ask(query: str, use_vectors: bool = False, verbose: bool = False) -> str:
    from answer_service import answer
    result = answer(query)
    if verbose:
        print(json.dumps({'status': result['status'], 'claim_ids': result['claim_ids']}, ensure_ascii=False))
    return result['answer']


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
