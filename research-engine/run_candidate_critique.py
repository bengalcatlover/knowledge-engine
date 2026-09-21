#!/usr/bin/env python3
"""Ask the low-cost critic to separate lecture hints from transfer hypotheses."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import uuid


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data" / "research.sqlite3"
POLICY = ROOT / "config" / "model-policy.json"
PROMPT = ROOT / "candidate-critique-prompt.txt"
INPUT = ROOT / "work" / "mit_concept_candidates.json"
OUTPUT = ROOT / "work" / "candidate_critique.json"
ASK = Path(r"C:\Users\akira\Documents\f3\reports\tri_review_20260718\ask_llm.py")
PYTHON = r"C:\Users\akira\Anaconda3\python.exe"


def main() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    if policy["dry_run"]:
        print("dry run: no critic call")
        return
    try:
        subprocess.run([PYTHON, str(ASK), policy["models"]["counterexample_review"], str(PROMPT), str(OUTPUT), str(INPUT)], check=True, timeout=900)
    except subprocess.CalledProcessError:
        if not OUTPUT.exists() or OUTPUT.stat().st_size == 0:
            raise
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
            (f"audit_{uuid.uuid4().hex[:12]}", "candidate_critique", policy["models"]["counterexample_review"], now, "critic separated lecture hints from transfer hypotheses"),
        )
    print(f"saved critique for {len(reviews)} candidates")


if __name__ == "__main__":
    main()
