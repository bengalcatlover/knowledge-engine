"""Merge 3-model classification results with majority voting.

Usage: python merge_votes.py

Reads classify-gemini.txt, classify-gpt.txt, classify-haiku.txt
Outputs discipline-final.json and discipline-final.md
"""
import json, re, os
from collections import Counter
from datetime import datetime

WORK = os.path.dirname(os.path.abspath(__file__))
MITOCW = r"C:\Users\akira\OneDrive\Desktop\kyousanto-ai\mitocw-txt"

# --- Deterministic mapping (ground truth for numbered courses) ---
DEPT_MAP = {
    "1": ("Civil & Environmental Engineering", "Engineering"),
    "2": ("Mechanical Engineering", "Engineering"),
    "3": ("Materials Science & Engineering", "Engineering"),
    "4": ("Architecture", "Arts & Humanities"),
    "5": ("Chemistry", "Natural Sciences"),
    "6": ("EECS / Computer Science", "Computing & Engineering"),
    "7": ("Biology", "Natural Sciences"),
    "8": ("Physics", "Natural Sciences"),
    "9": ("Brain & Cognitive Sciences", "Natural Sciences"),
    "10": ("Chemical Engineering", "Engineering"),
    "11": ("Urban Studies & Planning", "Social Sciences"),
    "12": ("Earth, Atmospheric & Planetary Sciences", "Natural Sciences"),
    "14": ("Economics", "Social Sciences"),
    "15": ("Management / Sloan", "Business & Management"),
    "16": ("Aeronautics & Astronautics", "Engineering"),
    "17": ("Political Science", "Social Sciences"),
    "18": ("Mathematics", "Mathematics & Statistics"),
    "20": ("Biological Engineering", "Engineering"),
    "21A": ("Anthropology", "Arts & Humanities"),
    "21F": ("Languages", "Arts & Humanities"),
    "21G": ("Languages", "Arts & Humanities"),
    "21H": ("History", "Arts & Humanities"),
    "21L": ("Literature", "Arts & Humanities"),
    "21M": ("Music & Theater", "Arts & Humanities"),
    "21W": ("Writing", "Arts & Humanities"),
    "22": ("Nuclear Science & Engineering", "Engineering"),
    "24": ("Linguistics & Philosophy", "Arts & Humanities"),
}

# Pattern to extract dept number from folder name
# Matches: "MIT 6.xxx", "MIT 18.xxx", "MIT 21M.xxx", "6.0001", etc.
DEPT_RE = re.compile(
    r'(?:MIT\s+)?(\d{1,2}[A-Z]?)\.', re.IGNORECASE
)

# For "How We Teach" folders, extract embedded course number
HOW_WE_TEACH_RE = re.compile(
    r'How We Teach[^:]*[:：]\s*(?:MIT\s+)?(\d{1,2}[A-Z]?)\.', re.IGNORECASE
)

# RES folders: extract sub-department
RES_RE = re.compile(r'RES\.(\d{1,2})', re.IGNORECASE)


def deterministic_classify(folder):
    """Try to classify by parsing the course number. Returns (dept, discipline, broad) or None."""
    # How We Teach
    m = HOW_WE_TEACH_RE.search(folder)
    if m:
        dept = m.group(1).upper()
        if dept in DEPT_MAP:
            d, b = DEPT_MAP[dept]
            return (dept, d, b)

    # RES.X-YYY
    m = RES_RE.search(folder)
    if m and "RES" in folder.upper():
        dept = m.group(1)
        if dept in DEPT_MAP:
            d, b = DEPT_MAP[dept]
            return (dept, d + " (Supplemental)", b)

    # Standard MIT X.xxx or bare X.xxx
    m = DEPT_RE.search(folder)
    if m:
        dept = m.group(1).upper()
        if dept in DEPT_MAP:
            d, b = DEPT_MAP[dept]
            return (dept, d, b)

    return None


def parse_llm_file(path):
    """Parse LLM output into {folder_name: (dept, discipline, broad)}."""
    result = {}
    if not os.path.exists(path):
        return result
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) >= 4:
                name = parts[0].strip()
                dept = parts[1].strip()
                disc = parts[2].strip()
                broad = parts[3].strip()
                result[name] = (dept, disc, broad)
    return result


def count_lectures(folder_path):
    """Count .md and .txt lecture files in a folder."""
    count = 0
    if not os.path.isdir(folder_path):
        return 0
    for f in os.listdir(folder_path):
        if f.lower().endswith((".md", ".txt")) and not f.lower().startswith("readme"):
            count += 1
    return count


def majority_vote(votes):
    """Given list of (dept, discipline, broad) tuples, return majority."""
    if not votes:
        return None
    # Vote on broad category (most important)
    broads = [v[2] for v in votes]
    broad_winner = Counter(broads).most_common(1)[0][0]
    # Among votes with winning broad, pick most common discipline
    matching = [v for v in votes if v[2] == broad_winner]
    disc_winner = Counter(v[1] for v in matching).most_common(1)[0][0]
    dept_winner = Counter(v[0] for v in matching).most_common(1)[0][0]
    return (dept_winner, disc_winner, broad_winner)


def main():
    # Load LLM results
    gemini = parse_llm_file(os.path.join(WORK, "classify-gemini.txt"))
    gpt = parse_llm_file(os.path.join(WORK, "classify-gpt.txt"))
    haiku = parse_llm_file(os.path.join(WORK, "classify-haiku.txt"))

    print(f"LLM results: Gemini={len(gemini)}, GPT={len(gpt)}, Haiku={len(haiku)}")

    # Get all folders
    folders = sorted([
        d for d in os.listdir(MITOCW)
        if os.path.isdir(os.path.join(MITOCW, d))
        and d != "raw"
    ])

    results = []
    unclassified = []
    method_stats = {"deterministic": 0, "llm_unanimous": 0, "llm_majority": 0, "unclassified": 0}

    for folder in folders:
        lectures = count_lectures(os.path.join(MITOCW, folder))

        # Step 1: try deterministic
        det = deterministic_classify(folder)
        if det:
            results.append({
                "name": folder,
                "dept": det[0],
                "discipline": det[1],
                "broad_category": det[2],
                "lectures": lectures,
                "method": "deterministic"
            })
            method_stats["deterministic"] += 1
            continue

        # Step 2: LLM majority vote
        votes = []
        for source in [gemini, gpt, haiku]:
            if folder in source:
                votes.append(source[folder])

        if votes:
            winner = majority_vote(votes)
            unanimous = len(set(v[2] for v in votes)) == 1
            results.append({
                "name": folder,
                "dept": winner[0],
                "discipline": winner[1],
                "broad_category": winner[2],
                "lectures": lectures,
                "method": "llm_unanimous" if unanimous else "llm_majority",
                "votes": len(votes)
            })
            method_stats["llm_unanimous" if unanimous else "llm_majority"] += 1
        else:
            unclassified.append({"name": folder, "lectures": lectures})
            method_stats["unclassified"] += 1

    # Build summary
    by_broad = {}
    by_discipline = {}
    for r in results:
        b = r["broad_category"]
        d = r["discipline"]
        by_broad.setdefault(b, {"folders": 0, "lectures": 0})
        by_broad[b]["folders"] += 1
        by_broad[b]["lectures"] += r["lectures"]
        by_discipline.setdefault(d, {"folders": 0, "lectures": 0, "courses": []})
        by_discipline[d]["folders"] += 1
        by_discipline[d]["lectures"] += r["lectures"]
        by_discipline[d]["courses"].append(r["name"])

    total_lectures = sum(r["lectures"] for r in results)
    total_lectures += sum(u["lectures"] for u in unclassified)

    output = {
        "generated": datetime.now().isoformat(),
        "summary": {
            "total_folders": len(folders),
            "total_lectures": total_lectures,
            "classified": len(results),
            "unclassified": len(unclassified),
            "method_stats": method_stats,
            "by_broad_category": dict(sorted(by_broad.items())),
            "by_discipline": {k: v for k, v in sorted(by_discipline.items())}
        },
        "folders": results,
        "unclassified": unclassified
    }

    # Save JSON
    json_path = os.path.join(WORK, "discipline-final.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Saved {json_path}")

    # Generate Markdown report
    md_lines = [
        "# MIT OCW 学問分野マップ（確定版）",
        f"\n生成: {output['generated']}",
        f"\n## 全体",
        f"- フォルダ数: {len(folders)}",
        f"- 講義ユニット数: {total_lectures}",
        f"- 分類済み: {len(results)} / 未分類: {len(unclassified)}",
        f"- 判定方法: 決定論的={method_stats['deterministic']}, "
        f"LLM全会一致={method_stats['llm_unanimous']}, "
        f"LLM多数決={method_stats['llm_majority']}, "
        f"未分類={method_stats['unclassified']}",
        "\n## 大分類",
        "| カテゴリ | フォルダ数 | 講義数 | 割合 |",
        "|---|---|---|---|",
    ]
    for cat, info in sorted(by_broad.items(), key=lambda x: -x[1]["lectures"]):
        pct = info["lectures"] / total_lectures * 100 if total_lectures else 0
        md_lines.append(f"| {cat} | {info['folders']} | {info['lectures']} | {pct:.1f}% |")

    md_lines.append("\n## 分野別詳細")
    for disc, info in sorted(by_discipline.items()):
        md_lines.append(f"\n### {disc}")
        md_lines.append(f"- フォルダ数: {info['folders']}, 講義数: {info['lectures']}")
        for c in sorted(info["courses"]):
            md_lines.append(f"  - {c}")

    if unclassified:
        md_lines.append(f"\n## 未分類 ({len(unclassified)}件)")
        for u in unclassified:
            md_lines.append(f"- {u['name']} ({u['lectures']}講義)")

    # Coverage gaps
    all_depts = set(DEPT_MAP.keys())
    found_depts = set(r["dept"] for r in results if r["method"] == "deterministic")
    missing = all_depts - found_depts
    if missing:
        md_lines.append("\n## カバレッジギャップ（講義なしの学科）")
        for dept in sorted(missing):
            d, b = DEPT_MAP[dept]
            md_lines.append(f"- {dept}: {d} ({b})")

    md_path = os.path.join(WORK, "discipline-final.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"Saved {md_path}")


if __name__ == "__main__":
    main()
