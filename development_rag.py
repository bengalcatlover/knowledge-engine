#!/usr/bin/env python3
"""このワークスペースの開発・設計資料を検索可能なプロジェクト記憶にする。"""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ENGINE = Path(__file__).resolve().parent
DATABASE = ENGINE / "work" / "development.sqlite3"
EXTENSIONS = {".md", ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css"}
EXCLUDED_PARTS = {".git", "node_modules", "__pycache__", "ocr-data", "raw", "work"}
CHUNK_SIZE = 5_000
OVERLAP = 500

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def source_files() -> list[Path]:
    found = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.stat().st_size > 1_000_000:
            continue
        found.append(path)
    return sorted(found)


def split(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]
    output, start = [], 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        if end < len(text):
            boundary = text.rfind("\n", start + 2_000, end)
            if boundary > start:
                end = boundary
        output.append(text[start:end])
        if end == len(text):
            break
        start = max(end - OVERLAP, start + 1)
    return output


def db() -> sqlite3.Connection:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(path UNINDEXED, content)")
    connection.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, digest TEXT NOT NULL)")
    return connection


def build() -> None:
    connection = db()
    updated = 0
    for path in source_files():
        content = path.read_text(encoding="utf-8", errors="replace")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        relative = str(path.relative_to(ROOT))
        prior = connection.execute("SELECT digest FROM files WHERE path = ?", (relative,)).fetchone()
        if prior and prior[0] == digest:
            continue
        connection.execute("DELETE FROM chunks WHERE path = ?", (relative,))
        connection.executemany("INSERT INTO chunks(path, content) VALUES (?, ?)", [(relative, item) for item in split(content)])
        connection.execute("INSERT OR REPLACE INTO files(path, digest) VALUES (?, ?)", (relative, digest))
        updated += 1
    connection.commit()
    count = connection.execute("SELECT count(DISTINCT path) FROM chunks").fetchone()[0]
    print(f"更新: {updated}ファイル / 索引済み: {count}ファイル / DB: {DATABASE}")


def search(query: str, limit: int) -> None:
    terms = re.findall(r"[\w]+", query, flags=re.UNICODE)
    if not terms:
        raise SystemExit("検索語を入力してください")
    match = " AND ".join(f'"{term}"' for term in terms)
    rows = db().execute(
        "SELECT path, content, bm25(chunks) AS score FROM chunks WHERE chunks MATCH ? ORDER BY score LIMIT ?", (match, limit)
    ).fetchall()
    if not rows:
        print("該当なし。別の主要語で検索してください。")
        return
    for index, (path, content, _) in enumerate(rows, 1):
        print(f"\n--- PROJECT SOURCE {index}: {path} ---\n{content}\n")


parser = argparse.ArgumentParser()
commands = parser.add_subparsers(dest="command", required=True)
commands.add_parser("build")
find = commands.add_parser("search")
find.add_argument("query")
find.add_argument("--limit", type=int, default=6)
args = parser.parse_args()

if args.command == "build":
    build()
else:
    search(args.query, args.limit)
