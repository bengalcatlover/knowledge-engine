"""Re-generate Gemini's thin discipline indexes with GPT and Haiku."""
import subprocess, sys, os
from pathlib import Path

WORK = Path(__file__).parent
PROMPTS = WORK / "discipline-prompts"
ACCEPTED = WORK.parent / "accepted"
ASK_LLM = WORK.parent.parent / "ask_llm.py"

THIN = [
    "aeronautics___astronautics",
    "biological_engineering",
    "chemical_engineering",
    "comparative_media_studies",
    "earth___environmental",
    "engineering_systems",
    "history",
    "linguistics___philosophy",
    "materials_science___engineering",
    "media_arts___sciences",
    "physics",
    "special_programs",
]

MODELS = [
    ("gpt", "openai:gpt-5.6-luna"),
    ("haiku", "anthropic:claude-haiku-4-5"),
]

processes = []
for disc in THIN:
    prompt = PROMPTS / f"{disc}_prompt.txt"
    if not prompt.exists():
        print(f"SKIP (no prompt): {disc}")
        continue
    for tag, model in MODELS:
        out = ACCEPTED / f"{disc}-index.{tag}.md"
        cmd = [sys.executable, str(ASK_LLM), model, str(prompt), str(out)]
        print(f"  [{tag}] {disc}")
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        processes.append((disc, tag, p, out))

print(f"\nWaiting for {len(processes)} API calls...")
ok = fail = 0
for disc, tag, p, out in processes:
    stdout, stderr = p.communicate(timeout=600)
    if p.returncode == 0 and out.exists() and out.stat().st_size > 100:
        ok += 1
        print(f"  OK: {disc}.{tag} ({out.stat().st_size} chars)")
    else:
        fail += 1
        err = stderr.decode("utf-8", errors="replace")[:200]
        print(f"  FAIL: {disc}.{tag} rc={p.returncode} {err}")

print(f"\nDone: {ok} ok, {fail} fail")
