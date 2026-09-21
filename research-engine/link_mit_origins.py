#!/usr/bin/env python3
"""Register MIT search metadata and link it to candidate concepts as discovery hints."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data" / "research.sqlite3"
CONTEXT = ROOT / "work" / "mit_concept_discovery_context.md"
CANDIDATES = ROOT / "work" / "mit_concept_candidates.json"


def records(text: str) -> dict[str, dict[str, str]]:
    parts = re.split(r"\n--- SOURCE \d+ \[(mitocw:[^\]]+)\] ---\n", text)
    result = {}
    for index in range(1, len(parts), 2):
        source_id, body = parts[index], parts[index + 1]
        title = re.search(r"^TITLE:\s*(.+)$", body, re.MULTILINE)
        url = re.search(r"^URL:\s*(.+)$", body, re.MULTILINE)
        if title and url and url.group(1).strip() != "URL未確認":
            result[source_id] = {"title": title.group(1).strip(), "url": url.group(1).strip()}
    return result


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    sources = records(CONTEXT.read_text(encoding="utf-8"))
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))["candidates"]
    linked = 0
    with sqlite3.connect(DATABASE) as db:
        for source_id, item in sources.items():
            db.execute(
                "INSERT OR IGNORE INTO artifacts(id, url, title, source_class, publisher, retrieved_at, original_hash, license_note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (source_id, item["url"], item["title"], "lecture", "MIT OpenCourseWare / YouTube", now, hashlib.sha256(item["url"].encode()).hexdigest(), "Discovery material only; not evidence for current technical claims."),
            )
        for candidate in candidates:
            concept = db.execute("SELECT id FROM concepts WHERE label = ? ORDER BY created_at DESC LIMIT 1", (candidate["label"],)).fetchone()
            if not concept:
                continue
            for source_id in candidate["source_ids"]:
                if source_id in sources:
                    db.execute(
                        "INSERT OR IGNORE INTO concept_origins(concept_id, artifact_id, origin_type, created_at) VALUES (?, ?, ?, ?)",
                        (concept[0], source_id, "discovery_hint", now),
                    )
                    linked += 1
    print(f"linked origins: {linked}")


if __name__ == "__main__":
    main()
