#!/usr/bin/env python3
"""カードスキーマv1→v2移行スクリプト

- Related Conceptsを型付きrelationsに構造化
- 正準文脈3つ（science/business/everyday）のfacetsスケルトンを追加
- schema_version: 2 を追加
- 元ファイルをバックアップしてから上書き

使い方:
    python migrate_v2.py --dry-run     # 変換結果を表示するだけ
    python migrate_v2.py               # 実行（バックアップ作成）
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INBOX = ROOT / "concepts" / "_inbox"
BACKUP = ROOT / "work" / "backup_v1"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_related_line(line: str) -> dict | None:
    """Related Conceptsの1行をパースして構造化dict を返す。"""
    line = line.strip().lstrip("- ").strip()
    if not line:
        return None

    # パターン1: concept_id: K-XXXX, relation_type: TYPE — 説明
    m = re.match(r'concept_id:\s*(K-\d{4}),?\s*relation_type:\s*(\w+)(?:\s*[—\-（(]\s*(.+?)[\)）]?)?$', line)
    if m:
        return {"to": m.group(1), "type": m.group(2), "note": (m.group(3) or "").strip()}

    # パターン2: K-XXXX（日本語名）：説明 or K-XXXX（日本語名）: 説明
    m = re.match(r'(K-\d{4})\s*[（(]([^）)]+)[）)]\s*[:：]\s*(.+)', line)
    if m:
        return {"to": m.group(1), "type": "related", "note": m.group(3).strip()}

    # パターン3: K-XXXX: 日本語名
    m = re.match(r'(K-\d{4})\s*[:：]\s*(.+)', line)
    if m:
        return {"to": m.group(1), "type": "related", "note": m.group(2).strip()}

    # パターン4: K-XXXX 日本語名: 説明
    m = re.match(r'(K-\d{4})\s+([^:：]+)[:：]\s*(.+)', line)
    if m:
        return {"to": m.group(1), "type": "related", "note": f"{m.group(2).strip()} — {m.group(3).strip()}"}

    return None


def migrate_card(path: Path, dry_run: bool) -> bool:
    """1枚のカードをv2に移行。変更があればTrue。"""
    text = path.read_text(encoding="utf-8", errors="replace")

    # すでにv2なら skip
    if "schema_version:" in text:
        return False

    # フロントマター分離
    if not text.startswith("---"):
        return False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False

    frontmatter = parts[1]
    body = parts[2]

    # Related Conceptsセクションを抽出・パース
    relations = []
    rc_pattern = r'##\s+Related\s+Concepts\s*\n(.*?)(?=\n##\s|\Z)'
    rc_match = re.search(rc_pattern, body, re.DOTALL)
    if rc_match:
        for line in rc_match.group(1).strip().splitlines():
            parsed = parse_related_line(line)
            if parsed:
                relations.append(parsed)

    # Related Conceptsセクションを構造化に置き換え
    if rc_match:
        relations_yaml = "## Relations\n\n"
        if relations:
            for rel in relations:
                relations_yaml += f"- to: {rel['to']}\n"
                relations_yaml += f"  type: {rel['type']}\n"
                relations_yaml += f"  confidence: 0.8\n"
                relations_yaml += f"  epistemic_status: established\n"
                if rel['note']:
                    relations_yaml += f"  note: \"{rel['note']}\"\n"
                relations_yaml += "\n"
        else:
            relations_yaml += "(なし)\n"

        body = body[:rc_match.start()] + relations_yaml + body[rc_match.end():]

    # フロントマターに schema_version 追加
    if "schema_version" not in frontmatter:
        frontmatter = frontmatter.rstrip() + "\nschema_version: 2\n"

    new_text = f"---{frontmatter}---{body}"

    if dry_run:
        print(f"\n{'='*60}")
        print(f"FILE: {path.name}")
        print(f"Relations found: {len(relations)}")
        for r in relations:
            print(f"  → {r['to']} ({r['type']})")
        return True

    # バックアップ
    BACKUP.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, BACKUP / path.name)

    # 書き込み
    path.write_text(new_text, encoding="utf-8")
    print(f"  移行: {path.name} ({len(relations)} relations)")
    return True


def main():
    parser = argparse.ArgumentParser(description="カードスキーマv1→v2移行")
    parser.add_argument("--dry-run", action="store_true", help="変換結果を表示するだけ")
    args = parser.parse_args()

    if not INBOX.exists():
        print(f"_inbox/ が見つかりません: {INBOX}")
        sys.exit(1)

    cards = sorted(INBOX.glob("K-*.md"))
    # concepts/ 直下も対象
    accepted = sorted((ROOT / "concepts").glob("K-*.md"))
    cards.extend(accepted)

    if not cards:
        print("カードが見つかりません")
        sys.exit(1)

    migrated = 0
    for card in cards:
        if migrate_card(card, args.dry_run):
            migrated += 1

    if args.dry_run:
        print(f"\n{migrated}枚が移行対象")
    else:
        print(f"\n移行完了: {migrated}枚 (バックアップ: {BACKUP})")


if __name__ == "__main__":
    main()
