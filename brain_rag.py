#!/usr/bin/env python3
"""知識ノートを役割を保ったまま検索する共通入口。"""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from knowledge_policy import note_usable
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "work" / "brain.sqlite3"
ROLES = ("accepted", "candidates", "concepts", "perspectives")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def sources(include_inbox: bool = False) -> list[tuple[str, Path]]:
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
            output.append((role, path))
    return output


def connection() -> sqlite3.Connection:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE)
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS notes USING fts5(ref_id UNINDEXED, role UNINDEXED, path UNINDEXED, content)")
    db.execute("CREATE TABLE IF NOT EXISTS manifest (path TEXT PRIMARY KEY, digest TEXT NOT NULL)")
    return db


def build(include_inbox: bool = False) -> None:
    db = connection()
    changed = 0
    current = set()
    for role, path in sources(include_inbox=include_inbox):
        content = path.read_text(encoding="utf-8", errors="replace")
        relative = str(path.relative_to(ROOT))
        current.add(relative)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        prior = db.execute("SELECT digest FROM manifest WHERE path = ?", (relative,)).fetchone()
        if prior and prior[0] == digest:
            continue
        ref_id = f"{role}:{path.stem}"
        db.execute("DELETE FROM notes WHERE path = ?", (relative,))
        db.execute("INSERT INTO notes(ref_id, role, path, content) VALUES (?, ?, ?, ?)", (ref_id, role, relative, content))
        db.execute("INSERT OR REPLACE INTO manifest(path, digest) VALUES (?, ?)", (relative, digest))
        changed += 1
    for (path,) in db.execute("SELECT path FROM manifest").fetchall():
        if path not in current:
            db.execute("DELETE FROM notes WHERE path = ?", (path,))
            db.execute("DELETE FROM manifest WHERE path = ?", (path,))
            changed += 1
    db.commit()
    total = db.execute("SELECT count(*) FROM notes").fetchone()[0]
    print(f"更新: {changed}ノート / 索引済み: {total}ノート / DB: {DATABASE}")


def search(query: str, limit: int, roles: list[str] | None, include_candidates=False) -> None:
    terms = re.findall(r"[\w]+", query, flags=re.UNICODE)
    if not terms:
        raise SystemExit("検索語を入力してください")
    match = " OR ".join(f'"{term}"' for term in terms)
    clauses, values = ["notes MATCH ?"], [match]
    if roles:
        accepted = [role for role in roles if role in ROLES]
        if not accepted:
            raise SystemExit("roleは accepted, candidates, concepts, perspectives から指定してください")
        clauses.append("role IN (" + ",".join("?" for _ in accepted) + ")")
        values.extend(accepted)
    rows = connection().execute(
        "SELECT ref_id, role, path, content, bm25(notes) FROM notes WHERE " + " AND ".join(clauses) + " ORDER BY bm25(notes)", values
    ).fetchall()
    rows = [r for r in rows if include_candidates or (
        note_usable(r[1], r[2], ROOT) and
        (ROOT / r[2]).read_text(encoding='utf-8') == r[3])][:limit]
    if not rows:
        print("該当なし。別の主要語で検索してください。")
        return
    activated = []
    for ref_id, role, path, content, _ in rows:
        activated.append(ref_id)
        label = 'CANDIDATE/DIAGNOSTIC' if include_candidates else 'NOTE'
        print(f"\n--- {label} [{ref_id}] role={role} path={path} ---\n{content[:2_000].rstrip()}\n")

    # 共活性化ログ記録
    try:
        from kb import log_query
        log_query(query, activated, searcher="brain_rag")
    except Exception:
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-inbox", action="store_true", help="explicit diagnostic access to drafts")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build")
    find = commands.add_parser("search")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=6)
    find.add_argument("--roles", nargs="+")
    args = parser.parse_args()
    if args.command == "build":
        build(include_inbox=args.include_inbox)
    else:
        search(args.query, args.limit, args.roles, include_candidates=args.include_inbox)
