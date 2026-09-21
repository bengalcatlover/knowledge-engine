#!/usr/bin/env python3
"""概念グラフ: Facet解決 + 比喩遮断 + グラフ走査

使い方:
    python graph.py load                           # グラフ読み込み+統計表示
    python graph.py traverse K-0001 [--context science] [--depth 2]
    python graph.py resolve K-0008 --context business
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import config  # noqa: F401

ROOT = Path(__file__).resolve().parent
CONCEPTS = ROOT / "concepts"

# 正準文脈
CONTEXTS = ("science", "business", "everyday")


# ═══════════════════════════════════════════
# カード読み込み
# ═══════════════════════════════════════════

def parse_frontmatter_simple(text: str) -> dict:
    fm = {}
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                m = re.match(r'^(\w[\w_]*)\s*:\s*(.+)', line)
                if m:
                    key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
                    fm[key] = val
    return fm


def parse_relations(body: str) -> list[dict]:
    """## Relations セクションをパースして構造化リストに。"""
    relations = []
    rc_pattern = r'##\s+Relations\s*\n(.*?)(?=\n##\s|\Z)'
    m = re.search(rc_pattern, body, re.DOTALL)
    if not m:
        return relations

    current = {}
    for line in m.group(1).strip().splitlines():
        line = line.strip()
        if line.startswith("- to:"):
            if current:
                relations.append(current)
            current = {"to": line.split(":", 1)[1].strip()}
        elif line.startswith("type:"):
            current["type"] = line.split(":", 1)[1].strip()
        elif line.startswith("confidence:"):
            try:
                current["confidence"] = float(line.split(":", 1)[1].strip())
            except ValueError:
                current["confidence"] = 0.5
        elif line.startswith("epistemic_status:"):
            current["epistemic_status"] = line.split(":", 1)[1].strip()
        elif line.startswith("note:"):
            current["note"] = line.split(":", 1)[1].strip().strip('"')
    if current:
        relations.append(current)

    return relations


def parse_facets(body: str) -> dict[str, dict]:
    """## Facets セクションをパース。まだfacetsがないカードは空dictを返す。"""
    facets = {}
    fc_pattern = r'##\s+Facets\s*\n(.*?)(?=\n##\s|\Z)'
    m = re.search(fc_pattern, body, re.DOTALL)
    if not m:
        return facets
    # 簡易パース（将来拡張）
    return facets


def load_graph(include_candidates=False) -> dict[str, dict]:
    """全カードを読み込んでグラフ構造を返す。"""
    graph = {}
    for directory in [CONCEPTS / "_inbox", CONCEPTS]:
        if not directory.exists():
            continue
        for path in directory.glob("K-*.md"):
            from knowledge_policy import note_usable
            if not include_candidates and not note_usable('concepts', path.relative_to(ROOT), ROOT):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            fm = parse_frontmatter_simple(text)
            _, body = text.split("---", 2)[1:]  # body部分
            body = body.split("---", 1)[1] if "---" in body else body

            card_id = fm.get("concept_id", path.stem)
            title = fm.get("canonical_name", path.stem)

            # Definition抽出
            def_match = re.search(r'##\s+Definition\s*\n(.*?)(?=\n##\s|\Z)', body, re.DOTALL)
            definition = def_match.group(1).strip()[:500] if def_match else ""

            graph[card_id] = {
                "id": card_id,
                "title": title,
                "definition": definition,
                "relations": parse_relations(body),
                "facets": parse_facets(body),
                "path": str(path.relative_to(ROOT)),
                "status": fm.get("status", "unknown"),
            }

    return graph


# ═══════════════════════════════════════════
# Facet解決
# ═══════════════════════════════════════════

def resolve(card: dict, context: str = "science") -> dict:
    """カードの内容を文脈に応じて解決。facetがあればcore+deltaを合成。"""
    if card.get('status') not in ('approved','accepted') or '_inbox' in card.get('path', ''):
        return {'id': card.get('id'), 'epistemic_status': 'unverified', 'definition': '', 'context': context}
    result = {
        "id": card["id"],
        "title": card["title"],
        "definition": card["definition"],
        "context": context,
    }

    facet = card.get("facets", {}).get(context, {})
    if facet:
        if "definition_delta" in facet:
            result["definition"] = facet["definition_delta"]
        result["epistemic_status"] = facet.get("epistemic_status", "established")
    else:
        result["epistemic_status"] = "established"

    return result


# ═══════════════════════════════════════════
# グラフ走査（比喩遮断+確信度打ち切り）
# ═══════════════════════════════════════════

def traverse(
    graph: dict[str, dict],
    start_id: str,
    context: str = "science",
    max_depth: int = 2,
    min_confidence: float = 0.3,
) -> list[dict]:
    """エントリーポイントから関連カードを芋づる式に辿る。

    - 比喩遮断: science文脈ではepistemic_status=analogyのエッジを遮断
    - 確信度打ち切り: 経路上のconfidenceの積がmin_confidenceを下回ったら停止
    - emerges_from: 継承推論を遮断（部分の性質から全体を推論しない）
    """
    if start_id not in graph:
        return []

    visited = set()
    results = []

    def _walk(card_id: str, depth: int, cumulative_conf: float, path: list[str]):
        if card_id in visited or depth > max_depth:
            return
        if cumulative_conf < min_confidence:
            return

        visited.add(card_id)
        card = graph.get(card_id)
        if not card:
            return
        if card.get('status') not in ('approved','accepted') or '_inbox' in card.get('path', ''):
            return

        results.append({
            "id": card_id,
            "title": card["title"],
            "depth": depth,
            "confidence": round(cumulative_conf, 3),
            "path": " → ".join(path + [card_id]),
        })

        for rel in card.get("relations", []):
            target = rel.get("to", "")
            rel_type = rel.get("type", "related")
            conf = rel.get("confidence", 0.5)
            epistemic = rel.get("epistemic_status", "established")
            if rel.get('epistemic_status') not in ('approved','verified'):
                continue

            # 比喩遮断: science文脈ではanalogyエッジを辿らない
            if context == "science" and epistemic == "analogy":
                continue

            # emerges_from は継承推論を遮断
            if rel_type == "emerges_from":
                continue

            new_conf = cumulative_conf * conf
            _walk(target, depth + 1, new_conf, path + [card_id])

    _walk(start_id, 0, 1.0, [])
    return results


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def cmd_load():
    graph = load_graph()
    total_edges = sum(len(c["relations"]) for c in graph.values())
    print(f"カード: {len(graph)}枚 / エッジ: {total_edges}本")
    for cid, card in sorted(graph.items()):
        rels = ", ".join(r["to"] for r in card["relations"])
        print(f"  {cid} {card['title']} → [{rels}]")


def cmd_traverse(card_id: str, context: str, depth: int):
    graph = load_graph()
    if card_id not in graph:
        print(f"カード {card_id} が見つかりません")
        return

    results = traverse(graph, card_id, context=context, max_depth=depth)
    print(f"走査: {card_id} (context={context}, depth={depth})\n")
    for r in results:
        indent = "  " * r["depth"]
        print(f"{indent}[{r['id']}] {graph[r['id']]['title']}  (conf={r['confidence']}, path={r['path']})")


def cmd_resolve(card_id: str, context: str):
    graph = load_graph()
    if card_id not in graph:
        print(f"カード {card_id} が見つかりません")
        return

    result = resolve(graph[card_id], context)
    print(f"Facet解決: {card_id} (context={context})")
    print(f"  タイトル: {result['title']}")
    print(f"  定義: {result['definition'][:200]}")
    print(f"  認識論的地位: {result['epistemic_status']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="概念グラフ")
    cmds = parser.add_subparsers(dest="command", required=True)

    cmds.add_parser("load", help="グラフ読み込み+統計")

    t = cmds.add_parser("traverse", help="グラフ走査")
    t.add_argument("card_id")
    t.add_argument("--context", default="science", choices=CONTEXTS)
    t.add_argument("--depth", type=int, default=2)

    r = cmds.add_parser("resolve", help="Facet解決")
    r.add_argument("card_id")
    r.add_argument("--context", default="science", choices=CONTEXTS)

    args = parser.parse_args()

    if args.command == "load":
        cmd_load()
    elif args.command == "traverse":
        cmd_traverse(args.card_id, args.context, args.depth)
    elif args.command == "resolve":
        cmd_resolve(args.card_id, args.context)
