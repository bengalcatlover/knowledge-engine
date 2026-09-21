#!/usr/bin/env python3
"""固定評価セットのカード被覆状態を集計する。回答の真偽は採点しない。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from graph import load_graph

ROOT = Path(__file__).resolve().parent
DEFAULT_SUITE = ROOT / "work" / "evaluation_questions.yaml"
REPORTS = ROOT / "work" / "evaluation_reports"


def card_has_sources(card: dict) -> bool:
    text = (ROOT / card["path"]).read_text(encoding="utf-8", errors="replace")
    return "## Source Refs" in text or "## Source References" in text


def evaluate(suite_path: Path) -> dict:
    suite = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    graph = load_graph()
    rows = []
    for item in suite["questions"]:
        expected = item["expected_cards"]
        cards = [graph.get(card_id) for card_id in expected]
        missing = [card_id for card_id, card in zip(expected, cards) if card is None]
        source_missing = [card_id for card_id, card in zip(expected, cards) if card and not card_has_sources(card)]
        statuses = {card["status"] for card in cards if card}
        if missing or source_missing:
            result = "gap"
        elif statuses == {"accepted"}:
            result = "accepted_ready"
        elif "revise" in statuses:
            result = "revision_required"
        elif "defer" in statuses:
            result = "deferred"
        else:
            result = "draft_only"
        rows.append({
            "id": item["id"], "domain": item["domain"], "question": item["question"],
            "expected_cards": expected, "card_statuses": sorted(statuses),
            "missing_cards": missing, "source_missing": source_missing, "result": result,
        })
    counts = {key: sum(row["result"] == key for row in rows) for key in ("accepted_ready", "revision_required", "deferred", "draft_only", "gap")}
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "suite": str(suite_path.relative_to(ROOT)), "total": len(rows),
        "pass_threshold": suite["pass_rule"]["minimum_grounded_answers"], "counts": counts, "questions": rows,
        "note": "draft_onlyはカード被覆の存在を示すだけで、根拠付き回答の合格ではない。",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="評価セットのカード被覆を集計")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = evaluate(args.suite)
    print(json.dumps({key: report[key] for key in ("total", "pass_threshold", "counts", "note")}, ensure_ascii=False, indent=2))
    if args.write:
        REPORTS.mkdir(parents=True, exist_ok=True)
        path = REPORTS / f"coverage_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"report: {path.relative_to(ROOT)}")
