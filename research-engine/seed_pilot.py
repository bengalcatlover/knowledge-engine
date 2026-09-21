#!/usr/bin/env python3
"""Register the first bounded research question without calling an AI model."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data" / "research.sqlite3"
QUESTION = "Which parts of an AI-agent workflow should be deterministic controls, and which parts can use low-cost models while preserving measurable quality?"


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DATABASE) as db:
        existing = db.execute("SELECT id FROM research_questions WHERE question = ?", (QUESTION,)).fetchone()
        if existing:
            print(f"existing question: {existing[0]}")
            return
        question_id = f"q_{uuid.uuid4().hex[:12]}"
        db.execute(
            "INSERT INTO research_questions(id, question, origin, priority_reason, status, budget_reserved_usd, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (question_id, QUESTION, "human", "The pilot connects autonomous repair, quality evaluation, and AI cost optimization.", "proposed", 0.25, now),
        )
    print(f"created question: {question_id}")


if __name__ == "__main__":
    main()
