#!/usr/bin/env python3
"""Run one bounded, low-cost concept-discovery job from MIT search excerpts."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import uuid


ROOT = Path(__file__).resolve().parent
ENGINE = ROOT.parent
DATABASE = ROOT / "data" / "research.sqlite3"
POLICY = ROOT / "config" / "model-policy.json"
PROMPT = ROOT / "concept-discovery-prompt.txt"
WORK = ROOT / "work"
ASK = Path(r"C:\Users\akira\Documents\f3\reports\tri_review_20260718\ask_llm.py")
PYTHON = r"C:\Users\akira\Anaconda3\python.exe"
QUERY = "software distributed systems testing"


def context_source_ids(text: str) -> set[str]:
    return set(re.findall(r"--- SOURCE \d+ \[(mitocw:[^\]]+)\]", text))


def require_candidate_shape(payload: object, allowed_source_ids: set[str]) -> list[dict[str, object]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise ValueError("expected a candidates array")
    candidates = payload["candidates"]
    if not 1 <= len(candidates) <= 8:
        raise ValueError("candidate count must be 1..8")
    for item in candidates:
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key].strip() for key in ("label", "domain", "why_relevant")):
            raise ValueError("candidate is missing a required string")
        if not isinstance(item.get("source_ids"), list) or not all(isinstance(value, str) and value.startswith("mitocw:") for value in item["source_ids"]):
            raise ValueError("candidate source_ids are invalid")
        if not item["source_ids"] or not set(item["source_ids"]).issubset(allowed_source_ids):
            raise ValueError("candidate refers to a source_id absent from the search context")
        if not isinstance(item.get("research_questions"), list):
            raise ValueError("candidate research_questions are invalid")
    return candidates


def main() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    WORK.mkdir(exist_ok=True)
    context = subprocess.run(
        [PYTHON, str(ENGINE / "mitocw_rag.py"), "search", QUERY, "--limit", "6"],
        cwd=ENGINE,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    context_path = WORK / "mit_concept_discovery_context.md"
    context_path.write_text(context, encoding="utf-8")
    allowed_source_ids = context_source_ids(context)
    if not allowed_source_ids:
        raise SystemExit("MIT search returned no source records; no model call was made")
    if policy["dry_run"]:
        print(f"dry run: would call {policy['models']['concept_extraction']} with {context_path}")
        return
    output_path = WORK / "mit_concept_candidates.json"
    try:
        subprocess.run(
            [PYTHON, str(ASK), policy["models"]["concept_extraction"], str(PROMPT), str(output_path), str(context_path)],
            check=True,
            timeout=900,
        )
    except subprocess.CalledProcessError:
        # The shared Windows runner can fail while printing a saved non-ASCII path.
        # A non-empty output remains a successful model result.
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise
    candidates = require_candidate_shape(json.loads(output_path.read_text(encoding="utf-8")), allowed_source_ids)
    now = datetime.now(timezone.utc).isoformat()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    with sqlite3.connect(DATABASE) as db:
        question = db.execute("SELECT id FROM research_questions WHERE status = 'proposed' ORDER BY created_at LIMIT 1").fetchone()
        if not question:
            raise SystemExit("no proposed research question; run seed_pilot.py")
        db.execute("UPDATE research_questions SET status = 'reported' WHERE id = ?", (question[0],))
        db.execute(
            "INSERT INTO research_runs(id, question_id, plan, model_policy_version, dry_run, outcome, cost_usd, created_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, question[0], f"MIT concept discovery query: {QUERY}", policy["policy_version"], 0, "partial", 0, now, now),
        )
        for item in candidates:
            concept_id = f"concept_{uuid.uuid4().hex[:12]}"
            db.execute(
                "INSERT INTO concepts(id, label, domain, scope_note, lifecycle, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (concept_id, item["label"], item["domain"], item["why_relevant"], "candidate", now, f"model:{policy['models']['concept_extraction']}"),
            )
        db.execute(
            "INSERT INTO audit_events(id, run_id, event_type, model_id, input_hash, output_hash, estimated_cost_usd, created_at, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"audit_{uuid.uuid4().hex[:12]}", run_id, "concept_discovery", policy["models"]["concept_extraction"], None, None, policy["budget_usd"]["per_run"], now, f"saved {len(candidates)} candidate concepts"),
        )
    print(f"saved {len(candidates)} candidate concepts in {run_id}")


if __name__ == "__main__":
    main()
