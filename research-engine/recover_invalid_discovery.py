#!/usr/bin/env python3
"""Quarantine the first discovery run because it had no MIT source context."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data" / "research.sqlite3"
RUN_ID = "run_d91657b9fd8d"


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DATABASE) as db:
        row = db.execute("SELECT question_id FROM research_runs WHERE id = ?", (RUN_ID,)).fetchone()
        if not row:
            print("nothing to recover")
            return
        db.execute("DELETE FROM concepts WHERE created_by LIKE 'model:llm:%'")
        db.execute("UPDATE research_runs SET outcome = 'failed', completed_at = ? WHERE id = ?", (now, RUN_ID))
        db.execute("UPDATE research_questions SET status = 'proposed' WHERE id = ?", (row[0],))
        db.execute("UPDATE audit_events SET detail = 'Rejected: MIT search context had no source records; candidate output was not accepted.' WHERE run_id = ?", (RUN_ID,))
    print("invalid discovery quarantined")


if __name__ == "__main__":
    main()
