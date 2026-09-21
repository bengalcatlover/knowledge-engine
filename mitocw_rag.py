#!/usr/bin/env python3
"""MIT OCW整形済みTXTを、出典付きで検索・文脈化するローカル知識ベース。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path

import config  # noqa: F401

ENGINE = Path(__file__).resolve().parent
CORPUS = Path(r"C:\Users\akira\OneDrive\Desktop\kyousanto-ai\mitocw-txt")
DATABASE = ENGINE / "work" / "mitocw.sqlite3"
DISCIPLINE_FILE = ENGINE / "work" / "discipline-final.json"
CHUNK_SIZE = 4_000
OVERLAP = 400


def files() -> list[Path]:
    """Return Markdown first; retain an old TXT only until it has been normalized."""
    result = []
    for path in CORPUS.rglob("*"):
        if not path.is_file() or "raw" in path.relative_to(CORPUS).parts:
            continue
        if path.name.endswith((".ai_v1.md", ".ai_v2.md", ".terra.md")):
            result.append(path)
            continue
        # 旧TXTは正規化Markdownがあるものだけを知識ベースに採用する。
        # 対応元のメタデータを復元できなかった旧TXTは、URL不明の講義を
        # 回答へ混入させないため検索対象から除外する。
    return sorted(result)


def metadata(text: str, path: Path) -> tuple[str, str, str, str]:
    header = text[:2_000]
    values = {}
    for key in ("TITLE", "SOURCE", "URL", "VIDEO_ID"):
        match = re.search(rf"^{key}:\s*(.+)$", header, flags=re.MULTILINE)
        values[key] = match.group(1).strip() if match else ""
    return values["TITLE"] or path.stem, values["SOURCE"], values["URL"], values["VIDEO_ID"]


def generate_field_id(discipline: str) -> str:
    """Generate a field_id from discipline name (e.g., 'Economics' -> 'F-ECON')."""
    # Take first 4 letters and uppercase, with F- prefix
    base = discipline.replace(" ", "").replace("&", "AND")[:4].upper()
    return f"F-{base}"


def chunks(text: str) -> list[str]:
    # ヘッダーを各断片に残して、検索結果だけでも出典を判断できるようにする。
    header, _, body = text.partition("\n\n")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if not body:
        return [header]
    result = []
    start = 0
    while start < len(body):
        end = min(len(body), start + CHUNK_SIZE)
        if end < len(body):
            boundary = body.rfind("\n", start + 2_000, end)
            if boundary > start:
                end = boundary
        result.append(header + "\n\n" + body[start:end].strip())
        if end == len(body):
            break
        start = max(end - OVERLAP, start + 1)
    return result


def connection() -> sqlite3.Connection:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE, timeout=30.0)
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(path UNINDEXED, title, url UNINDEXED, video_id UNINDEXED, content)")
    db.execute("CREATE TABLE IF NOT EXISTS sources (path TEXT PRIMARY KEY, digest TEXT NOT NULL)")
    db.execute("""
        CREATE TABLE IF NOT EXISTS course_fields (
            course_path TEXT PRIMARY KEY,
            field_id TEXT NOT NULL,
            discipline TEXT NOT NULL,
            broad_category TEXT NOT NULL
        )
    """)
    return db


def build(rebuild: bool = False) -> None:
    if rebuild and DATABASE.exists():
        DATABASE.unlink()
    db = connection()
    indexed = 0
    for path in files():
        text = path.read_text(encoding="utf-8", errors="replace")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        stored = db.execute("SELECT digest FROM sources WHERE path = ?", (str(path),)).fetchone()
        if stored and stored[0] == digest:
            continue
        title, _, url, video_id = metadata(text, path)
        if not url or not video_id:
            # 出典を辿れない講義断片は、回答の根拠として使わない。
            continue
        db.execute("DELETE FROM chunks WHERE path = ?", (str(path),))
        db.executemany(
            "INSERT INTO chunks(path, title, url, video_id, content) VALUES (?, ?, ?, ?, ?)",
            [(str(path), title, url, video_id, item) for item in chunks(text)],
        )
        db.execute("INSERT OR REPLACE INTO sources(path, digest) VALUES (?, ?)", (str(path), digest))
        indexed += 1
    db.commit()
    total = db.execute("SELECT count(DISTINCT path) FROM chunks").fetchone()[0]
    print(f"更新: {indexed}講義 / 索引済み: {total}講義 / DB: {DATABASE}")


def tag() -> None:
    """Populate course_fields from discipline-final.json using folder-path matching."""
    if not DISCIPLINE_FILE.exists():
        raise SystemExit(f"Discipline file not found: {DISCIPLINE_FILE}")

    db = connection()

    with open(DISCIPLINE_FILE, encoding="utf-8") as f:
        data = json.load(f)

    folders = data.get("folders", [])

    # Get all distinct folder names from indexed chunk paths
    try:
        db_paths = db.execute("SELECT DISTINCT path FROM chunks").fetchall()
    except sqlite3.OperationalError as e:
        print(f"Warning: Could not read paths from database: {e}")
        return

    # Extract unique parent folder names from chunk paths
    corpus_str = str(CORPUS).replace("\\", "/")
    indexed_folders: set[str] = set()
    for (p,) in db_paths:
        normalized = p.replace("\\", "/")
        if corpus_str in normalized:
            rel = normalized.split(corpus_str + "/", 1)[-1]
            folder_name = rel.split("/", 1)[0]
            indexed_folders.add(folder_name)

    tagged = 0
    for folder in folders:
        discipline = folder.get("discipline", "")
        broad_category = folder.get("broad_category", "")
        name = folder.get("name", "")

        if not discipline or not broad_category or not name:
            continue

        if name not in indexed_folders:
            continue

        field_id = generate_field_id(discipline)
        try:
            db.execute(
                "INSERT OR REPLACE INTO course_fields(course_path, field_id, discipline, broad_category) VALUES (?, ?, ?, ?)",
                (name, field_id, discipline, broad_category),
            )
            tagged += 1
        except sqlite3.Error as e:
            print(f"Error tagging {name}: {e}")

    db.commit()
    total = db.execute("SELECT COUNT(*) FROM course_fields").fetchone()[0]
    print(f"タグ付け: {tagged}コース / 合計: {total}コース / DB: {DATABASE}")


def search(query: str, limit: int, field: str | None = None, category: str | None = None) -> None:
    db = connection()
    # FTS構文の記号を除去し、語をAND検索する。英語キーワードで検索すると精度が上がる。
    terms = re.findall(r"[\w]+", query, flags=re.UNICODE)
    if not terms:
        raise SystemExit("検索語を入力してください")
    fts_query = " AND ".join(f'"{term}"' for term in terms)

    # Build query with optional field/category filters
    # course_fields.course_path stores folder names; chunks.path contains the folder name
    params: list = [fts_query]

    if field or category:
        cf_where_parts = []
        if field:
            cf_where_parts.append("cf.field_id = ?")
            params.append(field.upper())
        if category:
            cf_where_parts.append("cf.broad_category = ?")
            params.append(category)
        cf_where = " AND ".join(cf_where_parts)

        sql = f"""
            SELECT c.title, c.url, c.video_id, c.content, bm25(chunks) AS score
            FROM chunks c
            INNER JOIN course_fields cf
              ON c.path LIKE '%' || REPLACE(cf.course_path, '''', '''') || '%'
            WHERE chunks MATCH ?
              AND {cf_where}
            ORDER BY score LIMIT ?
        """
    else:
        sql = "SELECT title, url, video_id, content, bm25(chunks) AS score FROM chunks WHERE chunks MATCH ? ORDER BY score LIMIT ?"

    params.append(limit)

    rows = db.execute(sql, params).fetchall()

    if not rows:
        filter_info = ""
        if field:
            filter_info += f" --field {field}"
        if category:
            filter_info += f" --category '{category}'"
        print(f"該当なし。英語の主要語を2〜5語にして再検索してください。{filter_info}")
        return

    for number, (title, url, video_id, content, _) in enumerate(rows, 1):
        source_id = f"mitocw:{video_id or number}"
        excerpt = content[:1_600].rstrip()
        print(f"\n--- SOURCE {number} [{source_id}] ---\nTITLE: {title}\nURL: {url or 'URL未確認'}\nVIDEO_ID: {video_id}\n\n{excerpt}\n")


parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="command", required=True)

build_parser = sub.add_parser("build", help="整形済みTXTの追加・更新を索引へ反映")
build_parser.add_argument("--rebuild", action="store_true", help="索引を作り直す")

tag_parser = sub.add_parser("tag", help="discipline-final.jsonからコースフィールドをタグ付け")

search_parser = sub.add_parser("search", help="出典付き講義断片を検索（フィールド/カテゴリフィルタ対応）")
search_parser.add_argument("query")
search_parser.add_argument("--limit", type=int, default=6)
search_parser.add_argument("--field", type=str, help="分野でフィルタ（例: economics, engineering）")
search_parser.add_argument("--category", type=str, help="大カテゴリでフィルタ（例: 'Natural Sciences'）")

args = parser.parse_args()

if args.command == "build":
    build(args.rebuild)
elif args.command == "tag":
    tag()
else:
    search(args.query, args.limit, field=args.field, category=args.category)
