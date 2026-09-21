#!/usr/bin/env python3
"""Print a read-only status summary for the research-engine pilot."""

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data" / "research.sqlite3"
POLICY = ROOT / "config" / "model-policy.json"


def main() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    if not DATABASE.exists():
        raise SystemExit("database is not initialized; run python init_db.py")
    with sqlite3.connect(DATABASE) as db:
        counts = {
            table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("artifacts", "concepts", "concept_origins", "claims", "evidence_links", "research_questions", "research_runs", "proposals", "reviews")
        }
    print(json.dumps({"dry_run": policy["dry_run"], "models": policy["models"], "counts": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
