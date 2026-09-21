#!/usr/bin/env python3
"""評価セットに対して Recall@K を計測する。

使い方:
    python eval_recall.py                    # デフォルト K=6, ハイブリッド検索
    python eval_recall.py --k 10             # K=10
    python eval_recall.py --type scenario    # scenario問のみ
    python eval_recall.py --no-vectors       # BM25のみ（API通信なし）
    python eval_recall.py --verbose          # 各問の詳細を表示
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
EVAL_SET = ROOT / "eval_set.yaml"

# search_engine をインポート
sys.path.insert(0, str(ROOT))
from search_engine import get_db, bm25_search, hybrid_search, EMBED_FILE

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_eval_set(filter_type: str | None = None) -> list[dict]:
    with open(EVAL_SET, encoding="utf-8") as f:
        items = yaml.safe_load(f)
    if filter_type:
        items = [q for q in items if q["type"] == filter_type]
    return items


def extract_card_id(ref_id: str) -> str | None:
    m = re.search(r"K-\d{4}", ref_id)
    return m.group(0) if m else None


def evaluate(k: int, filter_type: str | None, verbose: bool, use_vectors: bool) -> None:
    questions = load_eval_set(filter_type)
    if not questions:
        print("評価対象の問いがありません。")
        sys.exit(1)

    mode = "hybrid" if (use_vectors and EMBED_FILE.exists()) else "bm25-only"
    print(f"検索モード: {mode}\n")

    hit = 0
    total = len(questions)
    results_by_type: dict[str, list[bool]] = {}

    for q in questions:
        query = q["query"]
        expected = set(q["expected"])
        qtype = q["type"]

        if use_vectors and EMBED_FILE.exists():
            results = hybrid_search(query, limit=k, use_vectors=True)
        else:
            db = get_db()
            results = bm25_search(db, query, limit=k)

        retrieved_cards = set()
        for item in results:
            ref_id = item[0] if isinstance(item, tuple) else item
            card_id = extract_card_id(str(ref_id))
            if card_id:
                retrieved_cards.add(card_id)

        is_hit = bool(expected & retrieved_cards)
        hit += is_hit
        results_by_type.setdefault(qtype, []).append(is_hit)

        if verbose:
            status = "HIT" if is_hit else "MISS"
            print(f"  [{status}] {query}")
            print(f"         期待: {sorted(expected)}  取得: {sorted(retrieved_cards)}")

    recall = hit / total * 100

    print(f"\n{'='*60}")
    print(f"  Recall@{k} = {recall:.1f}%  ({hit}/{total})")
    print(f"{'='*60}")

    for qtype in ["direct", "paraphrase", "scenario", "cross"]:
        if qtype in results_by_type:
            r = results_by_type[qtype]
            h = sum(r)
            t = len(r)
            print(f"  {qtype:12s}: {h/t*100:5.1f}%  ({h}/{t})")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recall@K 評価")
    parser.add_argument("--k", type=int, default=6)
    parser.add_argument("--type", dest="filter_type")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--no-vectors", action="store_true", help="BM25のみ（API通信なし）")
    args = parser.parse_args()
    evaluate(args.k, args.filter_type, args.verbose, use_vectors=not args.no_vectors)
