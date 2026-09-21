#!/usr/bin/env python3
"""Validate an already-saved critic result without another model call."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data" / "research.sqlite3"
OUTPUT = ROOT / "work" / "candidate_critique.json"


def main() -> None:
    raw = OUTPUT.read_text(encoding="utf-8").strip()
    if raw.startswith("```json") and raw.endswith("```"):
        raw = raw.removeprefix("```json").removesuffix("```").strip()
    payload = json.loads(raw)
    reviews = payload.get("reviews") if isinstance(payload, dict) else None
    if not isinstance(reviews, list) or not reviews or sum(bool(item.get("recommend_for_followup")) for item in reviews if isinstance(item, dict)) > 2:
        raise SystemExit("invalid critic output")
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DATABASE) as db:
        db.execute(
            "INSERT INTO audit_events(id, event_type, model_id, created_at, detail) VALUES (?, ?, ?, ?, ?)",
            (f"audit_{uuid.uuid4().hex[:12]}", "candidate_critique", "llm:worker", now, "critic output validated; follow-up candidates remain hypotheses"),
        )
    print(f"validated critique for {len(reviews)} candidates")


if __name__ == "__main__":
    main()
