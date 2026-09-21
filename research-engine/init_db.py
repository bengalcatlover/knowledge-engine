#!/usr/bin/env python3
"""Create the deterministic local database for the research-engine pilot."""

from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data" / "research.sqlite3"
SCHEMA = ROOT / "schema.sql"


def main() -> None:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE) as db:
        db.executescript(SCHEMA.read_text(encoding="utf-8"))
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise SystemExit(f"integrity check failed: {integrity}")
    print(f"initialized: {DATABASE}")


if __name__ == "__main__":
    main()
