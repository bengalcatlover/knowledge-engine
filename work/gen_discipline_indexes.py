"""Generate discipline index MDs by dispatching to 3 cheap LLMs in parallel.

Usage: python gen_discipline_indexes.py

Reads discipline-final.json, collects lecture titles per discipline,
creates prompts, and dispatches to Gemini Flash-Lite / GPT-5.6 Luna / Haiku.
"""
import json, os, re, subprocess, sys
from pathlib import Path

WORK = Path(__file__).parent
ROOT = WORK.parent.parent  # clauce/
MITOCW = Path(r"C:\Users\akira\OneDrive\Desktop\kyousanto-ai\mitocw-txt")
ASK_LLM = ROOT / "ask_llm.py"
OUT_DIR = WORK.parent / "accepted"  # knowledge-engine/accepted/
PROMPT_DIR = WORK / "discipline-prompts"
PROMPT_DIR.mkdir(exist_ok=True)

MODELS = [
    "gemini:gemini-3.1-flash-lite",
    "openai:gpt-5.6-luna",
    "anthropic:claude-haiku-4-5",
]

# Skip Meta folders
SKIP_DISCIPLINES = {"Meta"}


def load_inventory():
    with open(WORK / "discipline-final.json", encoding="utf-8") as f:
        return json.load(f)


def get_lecture_titles(folder_name):
    """Get sorted list of lecture titles from a folder."""
    folder = MITOCW / folder_name
    if not folder.is_dir():
        return []
    titles = []
    seen = set()
    for f in sorted(folder.iterdir()):
        if f.suffix in (".md", ".txt") and not f.name.lower().startswith("readme"):
            # Extract title from first line
            try:
                with open(f, encoding="utf-8") as fh:
                    first_lines = fh.read(500)
                m = re.search(r'TITLE:\s*(.+)', first_lines)
                if m:
                    title = m.group(1).strip()
                    if title not in seen:
                        seen.add(title)
                        titles.append(title)
            except:
                pass
    return titles


def build_discipline_data(inventory):
    """Group folders by discipline, collect titles."""
    disciplines = {}
    for folder in inventory["folders"]:
        disc = folder["discipline"]
        # Merge "X (Supplemental)" into "X"
        base_disc = re.sub(r'\s*\(Supplemental\)$', '', disc)
        if base_disc in SKIP_DISCIPLINES:
            continue
        if base_disc not in disciplines:
            disciplines[base_disc] = {
                "broad_category": folder["broad_category"],
                "courses": [],
                "total_lectures": 0,
            }
        titles = get_lecture_titles(folder["name"])
        disciplines[base_disc]["courses"].append({
            "name": folder["name"],
            "lectures": folder["lectures"],
            "titles": titles,
        })
        disciplines[base_disc]["total_lectures"] += folder["lectures"]
    return disciplines


def make_prompt(disc_name, disc_data):
    """Create the prompt for generating a discipline index."""
    courses_text = ""
    for course in disc_data["courses"]:
        courses_text += f"\n### {course['name']} ({course['lectures']} lectures)\n"
        for t in course["titles"][:30]:  # cap at 30 titles per course
            courses_text += f"- {t}\n"
        if len(course["titles"]) > 30:
            courses_text += f"- ... and {len(course['titles']) - 30} more\n"

    prompt = f"""You are creating a discipline knowledge index for: {disc_name}
Broad category: {disc_data['broad_category']}
Total courses: {len(disc_data['courses'])}
Total lecture units: {disc_data['total_lectures']}

Below are the courses and their lecture titles from MIT OpenCourseWare.

YOUR TASK: Generate a structured discipline index in Markdown with these sections:

1. **YAML frontmatter** with: discipline, broad_category, courses (count), lectures (count)

2. **カバー範囲** (Coverage): Group the courses into sub-topics/themes. For each theme, list which courses cover it and at what level (introductory/intermediate/advanced).

3. **使える武器** (Applicable Weapons): What concepts, methods, frameworks from this discipline can be applied to real-world business problems? Be specific. Give concrete application examples. Think: consulting, AI products, automation, decision-making.

4. **キーコンセプト** (Key Concepts): List the 10-20 most important transferable concepts from these lectures. For each, one line: concept name + what it means + where it appears (course name).

5. **薄い/ない領域** (Gaps): What important topics in this discipline are NOT covered or very thinly covered by these lectures?

6. **他分野との接続** (Cross-discipline connections): How does this discipline connect to other fields? What concepts transfer?

Write in Japanese. Be specific and concrete, not generic. This index will be used to decide where to dig deeper for business applications.

COURSES AND LECTURES:
{courses_text}
"""
    return prompt


def main():
    inventory = load_inventory()
    disciplines = build_discipline_data(inventory)

    print(f"Disciplines to process: {len(disciplines)}")

    # Assign disciplines to models round-robin
    disc_list = sorted(disciplines.items())
    assignments = {m: [] for m in MODELS}
    for i, (name, data) in enumerate(disc_list):
        model = MODELS[i % len(MODELS)]
        assignments[model].append((name, data))

    # Generate prompts and dispatch
    processes = []
    for model, items in assignments.items():
        for disc_name, disc_data in items:
            safe_name = re.sub(r'[^\w\-]', '_', disc_name).lower().strip('_')

            # Write prompt
            prompt_path = PROMPT_DIR / f"{safe_name}_prompt.txt"
            prompt_path.write_text(make_prompt(disc_name, disc_data), encoding="utf-8")

            # Output path
            out_path = OUT_DIR / f"{safe_name}-index.md"

            # Dispatch
            cmd = [
                sys.executable, str(ASK_LLM),
                model, str(prompt_path), str(out_path)
            ]
            print(f"  [{model.split(':')[0][:3]}] {disc_name} -> {out_path.name}")
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            processes.append((disc_name, model, p, out_path))

    # Wait for all
    print(f"\nWaiting for {len(processes)} API calls...")
    results = {"ok": 0, "fail": 0}
    for disc_name, model, p, out_path in processes:
        stdout, stderr = p.communicate(timeout=600)
        if p.returncode == 0 and out_path.exists() and out_path.stat().st_size > 100:
            results["ok"] += 1
            print(f"  OK: {disc_name} ({out_path.stat().st_size} chars)")
        else:
            results["fail"] += 1
            err = stderr.decode("utf-8", errors="replace")[:200]
            print(f"  FAIL: {disc_name} [{model}] rc={p.returncode} {err}")

    print(f"\nDone: {results['ok']} ok, {results['fail']} fail")


if __name__ == "__main__":
    main()
