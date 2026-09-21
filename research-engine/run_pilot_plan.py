#!/usr/bin/env python3
"""Create a low-cost structured pilot plan from the validated candidate critique."""

from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).resolve().parent
POLICY = ROOT / "config" / "model-policy.json"
PROMPT = ROOT / "pilot-plan-prompt.txt"
INPUT = ROOT / "work" / "candidate_critique.json"
OUTPUT = ROOT / "work" / "pilot_plan.json"
ASK = Path(r"C:\Users\akira\Documents\f3\reports\tri_review_20260718\ask_llm.py")
PYTHON = r"C:\Users\akira\Anaconda3\python.exe"


def main() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    if policy["dry_run"]:
        print("dry run: no synthesis call")
        return
    try:
        subprocess.run([PYTHON, str(ASK), policy["models"]["structured_synthesis"], str(PROMPT), str(OUTPUT), str(INPUT)], check=True, timeout=900)
    except subprocess.CalledProcessError:
        if not OUTPUT.exists() or OUTPUT.stat().st_size == 0:
            raise
    raw = OUTPUT.read_text(encoding="utf-8").strip()
    if raw.startswith("```json") and raw.endswith("```"):
        raw = raw.removeprefix("```json").removesuffix("```").strip()
    payload = json.loads(raw)
    pilot = payload.get("pilot") if isinstance(payload, dict) else None
    required = ("title", "objective", "concepts", "hypotheses", "deterministic_controls", "ai_tasks", "measurements", "independent_evidence_needed", "stop_conditions")
    if not isinstance(pilot, dict) or any(key not in pilot for key in required):
        raise SystemExit("invalid pilot plan")
    print(f"saved pilot plan: {pilot['title']}")


if __name__ == "__main__":
    main()
