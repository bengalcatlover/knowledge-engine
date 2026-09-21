#!/usr/bin/env python3
"""Store the model-generated pilot plan as an unreviewed proposal, never as evidence."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data" / "research.sqlite3"
PLAN = ROOT / "work" / "pilot_plan.json"


def main() -> None:
    raw = PLAN.read_text(encoding="utf-8").strip()
    if raw.startswith("```json") and raw.endswith("```"):
        raw = raw.removeprefix("```json").removesuffix("```").strip()
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get("pilot"), dict):
        raise SystemExit("invalid pilot plan")
    with sqlite3.connect(DATABASE) as db:
        exists = db.execute("SELECT 1 FROM proposals WHERE proposal_type = 'pilot_plan' AND body_json = ?", (json.dumps(payload, sort_keys=True),)).fetchone()
        if exists:
            print("pilot plan already stored")
            return
        db.execute(
            "INSERT INTO proposals(id, proposal_type, body_json, status, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (f"proposal_{uuid.uuid4().hex[:12]}", "pilot_plan", json.dumps(payload, sort_keys=True), "unreviewed", datetime.now(timezone.utc).isoformat(), "model:llm:worker"),
        )
    print("pilot plan stored as unreviewed proposal")


if __name__ == "__main__":
    main()
