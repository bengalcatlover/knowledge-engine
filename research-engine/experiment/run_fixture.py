#!/usr/bin/env python3
"""Record comparable fixture traces without invoking an LLM or external service."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixture.json"
TRACES = ROOT / "traces"


def execute(task: dict[str, object], condition: str) -> dict[str, object]:
    records = task["input_records"]
    if not isinstance(records, list) or not all(isinstance(row, dict) and isinstance(row.get("value"), int) for row in records):
        raise ValueError("invalid fixture records")
    result = {"count": len(records), "sum": sum(row["value"] for row in records)}
    return {
        "condition": condition,
        "agent_calls": 0,
        "tool_calls": 0,
        "retries": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0,
        "result": result,
        "success": result == task["expected"],
        "note": "fixture-only; no model or condition-specific optimization was invoked"
    }


def main() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    task = fixture["task"]
    traces = [execute(task, condition) for condition in fixture["conditions"]]
    payload = {
        "run_id": f"fixture_{uuid.uuid4().hex[:12]}",
        "experiment_id": fixture["experiment_id"],
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "limits": fixture["limits"],
        "traces": traces
    }
    TRACES.mkdir(exist_ok=True)
    path = TRACES / f"{payload['run_id']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved trace: {path}")


if __name__ == "__main__":
    main()
