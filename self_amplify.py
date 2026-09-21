#!/usr/bin/env python3
"""知識基盤の自己増幅ループ（質問格子 → 検索 → 監査ログ）。

自己生成した問いは利用者の問いや外部証拠ではない。したがって、このスクリプトは
候補カードを作らず、すべてのイベントを ``synthetic_self_amplification`` として記録する。

使い方:
    python self_amplify.py --dry-run
    python self_amplify.py --limit 50              # ローカルBM25のみ
    python self_amplify.py --offset 50 --limit 50
    python self_amplify.py --offset 500 --limit 10 --vectors  # 埋め込みで標本検証
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from kb import append_event, log_query
from graph import load_graph
from search_engine import hybrid_search

ROOT = Path(__file__).resolve().parent
EVAL_SET = ROOT / "eval_set.yaml"
ACTOR = "synthetic_self_amplification"

# クラス単体を、定義・機構・境界・失敗・反例・転用・測定・時間変化の
# 全方向から問う。テンプレートは問いの構造だけを与え、新しい事実は足さない。
SINGLE_CLASS_AXES = (
    "{concept}とは何で、近い概念と何が違うか",
    "{concept}はどの因果的または論理的な仕組みで働くか",
    "{concept}が成り立つために必要な前提は何か",
    "{concept}が壊れる境界条件と観測できる失敗は何か",
    "{concept}に見えるが実際には別物である反例は何か",
    "{concept}を事業・制度・ソフトウェア設計へ移すときの注意は何か",
    "{concept}が効いているかを何で測定・検証できるか",
    "{concept}は時間遅延、反復、規模の変化でどう振る舞うか",
)

# クラス間では、補完・緊張・因果順序・合成・文脈差を問う。ここで
# 既存カードにない説明単位が必要なら、後段のMIT検索と人間レビューが候補化する。
PAIR_CLASS_AXES = (
    "{left}と{right}はどの条件で補完し合うか",
    "{left}と{right}を同時に使うと、どんな失敗やトレードオフが起きるか",
    "{left}と{right}のどちらを先に設計・検証すべきか、その理由は何か",
    "{left}と{right}の相互作用から、単独では説明できない現象はあるか",
    "{left}と{right}は科学・ビジネス・日常の文脈でどう意味が変わるか",
)

# 概念名から始めず、現実の問題からクラスを引くための入口。いずれも事実の
# 断定ではなく「どの概念が説明・設計に使えるか」という問いの型である。
LIFE_SITUATIONS = (
    "家計管理と大きな買い物の判断",
    "学習計画を続けられない問題",
    "家族・チーム内の役割分担",
    "健康習慣を定着させる試み",
    "情報過多の中での意思決定",
    "失敗後に立て直すための振り返り",
)

BUSINESS_SITUATIONS = (
    "価格とインセンティブの設計",
    "採用・評価・報酬の仕組み",
    "営業予測と需要変動への対応",
    "在庫・納期・品質の同時管理",
    "AIエージェントを含む業務自動化",
    "プロダクトのA/Bテストと因果検証",
    "不正・セキュリティ・権限管理",
    "複数部門の意思決定と合意形成",
)

SCIENTIFIC_DOMAINS = (
    "生命科学",
    "物理学",
    "化学",
    "心理学",
    "社会科学",
    "医学・公衆衛生",
    "地球科学",
    "ロボティクス",
)


def generate_questions() -> list[str]:
    """全クラスと全クラス対を、設計上の質問軸で網羅する。"""
    items = yaml.safe_load(EVAL_SET.read_text(encoding="utf-8"))
    questions: list[str] = []
    seen: set[str] = set()

    def add(question: str) -> None:
        if question not in seen:
            seen.add(question)
            questions.append(question)

    # 利用者に近い評価質問も残し、検索品質の変化を継続観測する。
    for item in items:
        add(item["query"].strip())

    graph = load_graph()
    cards = [graph[card_id] for card_id in sorted(graph) if card_id.startswith("K-")]
    for card in cards:
        for template in SINGLE_CLASS_AXES:
            add(template.format(concept=card["title"]))
        for situation in LIFE_SITUATIONS:
            add(f"{situation}で、{card['title']}は何を説明し、どこで使えないか")
        for situation in BUSINESS_SITUATIONS:
            add(f"{situation}を設計する際に、{card['title']}をどう使い、何を検証すべきか")
        for domain in SCIENTIFIC_DOMAINS:
            add(f"{domain}で、{card['title']}に対応する現象・モデル・反例は何か")

    # 順序に依存しない全ペア。既知エッジの有無で事前に除外しない。
    # 既知関係の再検証も、未知の組の概念ギャップ検出も必要なためである。
    for index, left in enumerate(cards):
        for right in cards[index + 1:]:
            for template in PAIR_CLASS_AXES:
                add(template.format(left=left["title"], right=right["title"]))
    return questions


def run(offset: int, limit: int, use_vectors: bool, dry_run: bool) -> None:
    all_questions = generate_questions()
    questions = all_questions[offset:offset + limit]
    print(f"質問格子: total={len(all_questions)} / batch={len(questions)} / offset={offset} / vectors={use_vectors} / dry_run={dry_run}")
    for position, question in enumerate(questions, start=1):
        if dry_run:
            print(f"  [{position}] {question}")
            continue
        results = hybrid_search(question, limit=6, use_vectors=use_vectors)
        cards = [ref_id for ref_id, _ in results if ref_id.startswith("K-")]
        if not cards:
            # 検索不能を捨てず、候補調査の入口として追記する。ここではカードを
            # 作らず、MIT検索と外部根拠の確認を終えた後だけ _inbox/ を作る。
            append_event(
                event_type="query_gap_detected",
                payload={
                    "query": question,
                    "origin": ACTOR,
                    "retrieval": "bm25" if not use_vectors else "hybrid",
                    "reason": "no_concept_card_retrieved",
                },
                actor=ACTOR,
            )
            print(f"  [{position}] 知識の穴を記録: {question}")
            continue
        log_query(question, cards, actor=ACTOR)
        print(f"  [{position}] 記録: {', '.join(cards)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="自己生成問いによる検索ログ蓄積")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0, help="質問格子内の開始位置")
    parser.add_argument("--vectors", action="store_true", help="埋め込み検索を使う（API通信あり）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.limit < 1 or args.offset < 0:
        raise SystemExit("--limit は1以上、--offset は0以上にしてください")
    run(args.offset, args.limit, use_vectors=args.vectors, dry_run=args.dry_run)
