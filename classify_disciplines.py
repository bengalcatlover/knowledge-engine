#!/usr/bin/env python3
"""
Classify MIT OCW lectures by discipline and generate inventory reports.
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

# MIT Department mappings
DEPARTMENTS = {
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
    "21F": ("Languages / Foreign Studies", "Arts & Humanities"),
    "21G": ("Languages / Global Studies", "Arts & Humanities"),
    "21H": ("History", "Arts & Humanities"),
    "21L": ("Literature", "Arts & Humanities"),
    "21M": ("Music & Theater", "Arts & Humanities"),
    "21W": ("Writing", "Arts & Humanities"),
    "22": ("Nuclear Science & Engineering", "Engineering"),
    "24": ("Linguistics & Philosophy", "Arts & Humanities"),
    "CMS": ("Comparative Media Studies", "Arts & Humanities"),
    "ESD": ("Engineering Systems", "Engineering"),
    "HST": ("Health Sciences & Technology", "Natural Sciences"),
    "IDS": ("Data, Systems & Society", "Computing & Engineering"),
    "MAS": ("Media Arts & Sciences", "Computing & Engineering"),
    "RES": ("Supplemental Resources", "Cross-disciplinary"),
    "STS": ("Science, Technology & Society", "Social Sciences"),
    "SP": ("Special Programs", "Cross-disciplinary"),
    "EC": ("Edgerton Center", "Cross-disciplinary"),
    "PE": ("Physical Education", "Cross-disciplinary"),
    "ES": ("Experimental Study Group", "Cross-disciplinary"),
    "OLL": ("Open Learning Library", "Cross-disciplinary"),
}

# Special folders that don't follow MIT X.XXX pattern
SPECIAL_FOLDERS = {
    r"^\(Selected Lectures\) MIT 7\.05": ("Biology", "Natural Sciences", "Biology"),
    r"^6\.0001": ("EECS / Computer Science", "Computing & Engineering", "6.0001"),
    r"^6\.041": ("EECS / Computer Science", "Computing & Engineering", "6.041"),
    r"^A Vision of Linear Algebra": ("Mathematics", "Mathematics & Statistics", "A Vision of Linear Algebra"),
    r"^Highlights of Calculus": ("Mathematics", "Mathematics & Statistics", "Highlights of Calculus"),
    r"^How To Speak": ("Special Programs", "Cross-disciplinary", "How To Speak"),
    r"^AI 101": ("IDS / Data, Systems & Society", "Computing & Engineering", "AI 101"),
    r"^ChemLab Boot Camp": ("Chemistry", "Natural Sciences", "ChemLab Boot Camp"),
    r"^Chalk Radio": ("Special Programs", "Cross-disciplinary", "Chalk Radio"),
    r"^Lecture Clips": ("Special Programs", "Cross-disciplinary", "Lecture Clips"),
    r"^MIT Learn Differential Equations": ("Mathematics", "Mathematics & Statistics", "Differential Equations"),
    r"^MIT Linear Finite Element Analysis": ("Engineering Systems", "Engineering", "Linear FEA"),
    r"^MIT Nonlinear Finite Element Analysis": ("Engineering Systems", "Engineering", "Nonlinear FEA"),
    r"^MIT Calculus Revisited": ("Mathematics", "Mathematics & Statistics", "Calculus Revisited"),
    r"^MIT Chemistry Behind the Magic": ("Chemistry", "Natural Sciences", "Chemistry Behind Magic"),
    r"^MIT Digital Lab Techniques Manual": ("Chemistry", "Natural Sciences", "Lab Techniques"),
    r"^MIT Electronic Feedback Systems": ("EECS / Computer Science", "Computing & Engineering", "Feedback Systems"),
    r"^MIT Exploring Black Holes": ("Physics", "Natural Sciences", "Black Holes"),
    r"^MIT Making Science": ("Special Programs", "Cross-disciplinary", "Making Science"),
    r"^MIT STEM Concept Videos": ("Special Programs", "Cross-disciplinary", "STEM Concept Videos"),
    r"^MIT Understanding Lasers": ("Physics", "Natural Sciences", "Lasers"),
    r"^MIT Vibrations and Waves": ("Physics", "Natural Sciences", "Vibrations & Waves"),
    r"^Electromagnetic Fields": ("EECS / Computer Science", "Computing & Engineering", "EM Fields"),
    r"^Drennan": ("Chemistry", "Natural Sciences", "Drennan"),
    r"^MIT Lean Enterprise": ("Management / Sloan", "Business & Management", "Lean Enterprise"),
    r"^How We Teach": ("Special Programs", "Cross-disciplinary", "How We Teach"),
    r"Subscribers|Celebrating|OCW|OpenCourseWare|My Top|From MIT Open Learning": ("Meta", "Cross-disciplinary", "Meta"),
}

def extract_dept_from_folder(folder_name):
    """
    Extract MIT department number from folder name.
    Patterns:
    - "MIT X.XXX" or "MIT XX.XXX"
    - "How We Teach X.XXX"
    """
    # Standard pattern: MIT 1.001 or MIT 18.01
    match = re.search(r'MIT\s+(\d+[A-Z]?(?:\.\d+)?)', folder_name)
    if match:
        return match.group(1)

    # How We Teach pattern: How We Teach 6.004
    match = re.search(r'How We Teach\s+(\d+[A-Z]?(?:\.\d+)?)', folder_name)
    if match:
        return match.group(1)

    return None

def classify_folder(folder_name):
    """
    Classify a folder by discipline and broad category.
    Returns: (dept_number_or_id, discipline, broad_category)
    """
    # Check special folders first
    for pattern, (discipline, category, code) in SPECIAL_FOLDERS.items():
        if re.search(pattern, folder_name, re.IGNORECASE):
            return (code, discipline, category)

    # Try to extract MIT department number
    dept_num = extract_dept_from_folder(folder_name)
    if dept_num:
        # Normalize: "6" -> "6", "21A" -> "21A", "1.001" -> "1"
        base_dept = dept_num.split('.')[0] if '.' in dept_num else dept_num

        if base_dept in DEPARTMENTS:
            discipline, category = DEPARTMENTS[base_dept]
            return (base_dept, discipline, category)

    return (None, None, None)

def count_content_files(folder_path):
    """Count .md and .txt files in a folder, excluding README files."""
    count = 0
    try:
        for file in os.listdir(folder_path):
            if file.upper().startswith('README'):
                continue
            if file.endswith(('.md', '.txt')):
                count += 1
    except (PermissionError, OSError):
        pass
    return count

def scan_mitocw_folders(base_path):
    """Scan all folders in mitocw-txt directory."""
    results = []
    unclassified = []

    if not os.path.isdir(base_path):
        print(f"Error: Base path does not exist: {base_path}")
        return results, unclassified

    # Get all subdirectories (excluding 'raw')
    try:
        folders = [f for f in os.listdir(base_path)
                   if os.path.isdir(os.path.join(base_path, f)) and f != 'raw']
    except (PermissionError, OSError) as e:
        print(f"Error reading directory: {e}")
        return results, unclassified

    for folder_name in sorted(folders):
        folder_path = os.path.join(base_path, folder_name)

        # Count files
        lecture_count = count_content_files(folder_path)

        # Classify
        dept_id, discipline, category = classify_folder(folder_name)

        if discipline is None:
            unclassified.append(folder_name)
        else:
            results.append({
                'name': folder_name,
                'dept_number': dept_id,
                'discipline': discipline,
                'broad_category': category,
                'lecture_count': lecture_count
            })

    return results, unclassified

def generate_json_report(results, unclassified, output_path):
    """Generate JSON inventory report."""
    # Summary statistics
    total_folders = len(results)
    total_lectures = sum(r['lecture_count'] for r in results)

    # Aggregate by broad category
    by_category = defaultdict(lambda: {'folders': 0, 'lectures': 0})
    by_discipline = defaultdict(lambda: {'folders': 0, 'lectures': 0, 'courses': []})

    for r in results:
        category = r['broad_category']
        discipline = r['discipline']

        by_category[category]['folders'] += 1
        by_category[category]['lectures'] += r['lecture_count']

        by_discipline[discipline]['folders'] += 1
        by_discipline[discipline]['lectures'] += r['lecture_count']
        by_discipline[discipline]['courses'].append(r['name'])

    # Sort courses within each discipline
    for disc in by_discipline:
        by_discipline[disc]['courses'].sort()

    report = {
        'generated': datetime.now(timezone.utc).isoformat(),
        'summary': {
            'total_folders': total_folders,
            'total_lectures': total_lectures,
            'by_broad_category': dict(sorted(by_category.items())),
            'by_discipline': dict(sorted(by_discipline.items()))
        },
        'folders': results,
        'unclassified': sorted(unclassified)
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report

def generate_markdown_report(report, output_path):
    """Generate human-readable markdown report."""
    summary = report['summary']
    by_category = summary['by_broad_category']
    by_discipline = summary['by_discipline']
    unclassified = report['unclassified']

    lines = []
    lines.append("# MIT OCW Discipline Inventory")
    lines.append("")
    lines.append(f"Generated: {report['generated']}")
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- **Total Folders Scanned**: {summary['total_folders']}")
    lines.append(f"- **Total Lecture Units**: {summary['total_lectures']}")
    lines.append(f"- **Unclassified Folders**: {len(unclassified)}")
    lines.append("")

    # Broad Category Summary
    lines.append("## Coverage by Broad Category")
    lines.append("")
    lines.append("| Category | Folders | Lectures | % of Total |")
    lines.append("|----------|---------|----------|------------|")

    total_lectures = summary['total_lectures']
    for category in sorted(by_category.keys()):
        stats = by_category[category]
        pct = (stats['lectures'] / total_lectures * 100) if total_lectures > 0 else 0
        lines.append(f"| {category} | {stats['folders']} | {stats['lectures']} | {pct:.1f}% |")
    lines.append("")

    # Discipline Details
    lines.append("## Discipline Details")
    lines.append("")

    for discipline in sorted(by_discipline.keys()):
        stats = by_discipline[discipline]
        lines.append(f"### {discipline}")
        lines.append("")
        lines.append(f"- **Folders**: {stats['folders']}")
        lines.append(f"- **Total Lectures**: {stats['lectures']}")
        lines.append("")
        lines.append("**Courses:**")
        lines.append("")
        for course in stats['courses']:
            lines.append(f"- {course}")
        lines.append("")

    # Unclassified Folders
    if unclassified:
        lines.append("## Unclassified Folders")
        lines.append("")
        lines.append(f"Total: {len(unclassified)}")
        lines.append("")
        for folder in unclassified:
            lines.append(f"- {folder}")
        lines.append("")

    # Coverage Gaps
    lines.append("## Coverage Gaps")
    lines.append("")
    lines.append("Standard MIT departments with no OCW lectures:")
    lines.append("")

    covered_depts = set()
    for result in report['folders']:
        if result['dept_number'] and result['dept_number'] in DEPARTMENTS:
            covered_depts.add(result['dept_number'])

    gaps = []
    for dept_id in sorted(DEPARTMENTS.keys()):
        if dept_id not in covered_depts:
            discipline, category = DEPARTMENTS[dept_id]
            gaps.append(f"- {dept_id}: {discipline}")

    if gaps:
        for gap in gaps:
            lines.append(gap)
    else:
        lines.append("(All standard departments covered)")
    lines.append("")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

def main():
    base_path = r"C:/Users/akira/OneDrive/Desktop/kyousanto-ai/mitocw-txt"
    json_output = r"C:/Users/akira/OneDrive/Desktop/clauce/knowledge-engine/work/discipline-inventory.json"
    md_output = r"C:/Users/akira/OneDrive/Desktop/clauce/knowledge-engine/work/discipline-map.md"

    print(f"Scanning MIT OCW folders in: {base_path}")
    results, unclassified = scan_mitocw_folders(base_path)

    print(f"Found {len(results)} classified folders, {len(unclassified)} unclassified")

    # Generate reports
    report = generate_json_report(results, unclassified, json_output)
    print(f"JSON report written to: {json_output}")

    generate_markdown_report(report, md_output)
    print(f"Markdown report written to: {md_output}")

    print("\nSummary:")
    print(f"  Total Folders: {report['summary']['total_folders']}")
    print(f"  Total Lectures: {report['summary']['total_lectures']}")
    print(f"  Unclassified: {len(unclassified)}")

if __name__ == '__main__':
    main()
