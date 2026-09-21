"""
search-gold-set.json の 40 問を mitocw_rag.py で自動検証するスクリプト。
フィルタなし検索と（該当する場合）フィルタあり検索の両方を実行し、
Recall@6 とフィルタ汚染を報告する。
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # knowledge-engine/
DB_PATH = ROOT / "work" / "mitocw.sqlite3"
GOLD_PATH = Path(__file__).resolve().parent / "search-gold-set.json"

# gold-set の field_filter → DB の field_id
FIELD_MAP = {
    "economics": "F-ECON",
    "eecs___computer_science": "F-EECS",
    "mathematics": "F-MATH",
    "physics": "F-PHYS",
    "brain___cognitive_sciences": "F-BRAI",
    "management___sloan": "F-MANA",
}

# expected_courses の番号 → path に含まれる文字列（MIT講義フォルダ名の一部）
# 例: "14.12" → フォルダパスに "14-12" や "14.12" を含む
def course_matches_path(course_num: str, path: str) -> bool:
    """expected_courses のコース番号がパスに含まれるか（. と - を両方試す）"""
    variants = [
        course_num,
        course_num.replace(".", "-"),
        course_num.replace(".", "_"),
    ]
    path_lower = path.lower()
    return any(v.lower() in path_lower for v in variants)


def _run_fts(conn, terms: list[str], limit: int, field_id: str | None):
    """指定された語リストでFTS検索を実行し、結果行を返す"""
    fts_query = " AND ".join(f'"{t}"' for t in terms)
    params: list = [fts_query]

    if field_id:
        sql = """
            SELECT c.title, c.url, c.video_id, c.path, bm25(chunks) AS score
            FROM chunks c
            INNER JOIN course_fields cf
              ON c.path LIKE '%' || REPLACE(cf.course_path, '''', '''') || '%'
            WHERE chunks MATCH ?
              AND cf.field_id = ?
            ORDER BY score LIMIT ?
        """
        params.append(field_id)
    else:
        sql = """
            SELECT title, url, video_id, path, bm25(chunks) AS score
            FROM chunks
            WHERE chunks MATCH ?
            ORDER BY score LIMIT ?
        """
    params.append(limit)

    try:
        return conn.execute(sql, params).fetchall()
    except Exception:
        return []


def search_db(query: str, limit: int = 6, field_id: str | None = None):
    """FTS検索。ヒット0の場合、語数を1つずつ減らして最小2語までリトライする"""
    conn = sqlite3.connect(str(DB_PATH))
    terms = re.findall(r"[\w]+", query, flags=re.UNICODE)
    if not terms:
        conn.close()
        return [], len(terms)

    # 全語でまず試す。ヒット0なら語を末尾から削って再試行
    for n in range(len(terms), 1, -1):
        subset = terms[:n]
        rows = _run_fts(conn, subset, limit, field_id)
        if rows:
            conn.close()
            return rows, n
    conn.close()
    return [], 0


def check_recall(rows, expected_courses: list[str]) -> dict:
    """ヒット行のパスに expected_courses が含まれるか検査"""
    if not expected_courses:
        # gap_detection: expected_courses が空 → ヒットの有無にかかわらずGAP扱い
        return {
            "found": [],
            "missing": [],
            "recall": 1.0,
            "is_gap": True,
        }

    found = []
    for ec in expected_courses:
        for row in rows:
            path = row[3] or ""
            if course_matches_path(ec, path):
                found.append(ec)
                break

    missing = [ec for ec in expected_courses if ec not in found]
    recall = len(found) / len(expected_courses) if expected_courses else 0.0
    return {"found": found, "missing": missing, "recall": recall, "is_gap": False}


def main():
    with open(GOLD_PATH, encoding="utf-8") as f:
        queries = json.load(f)

    total = len(queries)
    results_nofilter = []
    results_filtered = []

    print(f"=== 配管テスト: {total} 問 ===\n")

    for q in queries:
        qid = q["query_id"]
        query_en = q["query_en"]
        expected = q["expected_courses"]
        field_filter = q["field_filter"]
        category = q["category"]

        # --- フィルタなし検索 ---
        rows, used_n = search_db(query_en, limit=6)
        r = check_recall(rows, expected)
        results_nofilter.append(r)
        status = "OK" if r["recall"] == 1.0 else ("GAP" if r["is_gap"] else "MISS")
        miss_str = f" missing={r['missing']}" if r["missing"] else ""
        terms_total = len(re.findall(r"[\w]+", query_en, flags=re.UNICODE))
        trim_info = f" (used {used_n}/{terms_total} terms)" if used_n < terms_total else ""
        print(f"[{qid}] no-filter: recall={r['recall']:.2f} ({status}){trim_info}{miss_str}")

        # --- フィルタあり検索（field_filterがある場合のみ）---
        if field_filter and field_filter in FIELD_MAP:
            fid = FIELD_MAP[field_filter]
            rows_f, used_n_f = search_db(query_en, limit=6, field_id=fid)
            r_f = check_recall(rows_f, expected)
            results_filtered.append({"qid": qid, **r_f, "field": field_filter})

            status_f = "OK" if r_f["recall"] == 1.0 else "MISS"
            miss_str_f = f" missing={r_f['missing']}" if r_f["missing"] else ""
            hit_count = len(rows_f)
            print(f"         filtered({field_filter}): recall={r_f['recall']:.2f} ({status_f}) hits={hit_count}{miss_str_f}")

    # --- サマリー ---
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    # フィルタなし
    recalls_nf = [r["recall"] for r in results_nofilter if not r["is_gap"]]
    gaps = [r for r in results_nofilter if r["is_gap"]]
    avg_recall_nf = sum(recalls_nf) / len(recalls_nf) if recalls_nf else 0
    perfect_nf = sum(1 for r in recalls_nf if r == 1.0)
    print(f"\nフィルタなし:")
    print(f"  平均 Recall@6: {avg_recall_nf:.3f}")
    print(f"  完全一致:      {perfect_nf}/{len(recalls_nf)}")
    print(f"  Gap検出問題:   {len(gaps)} 問")

    # フィルタあり
    if results_filtered:
        recalls_f = [r["recall"] for r in results_filtered]
        avg_recall_f = sum(recalls_f) / len(recalls_f) if recalls_f else 0
        perfect_f = sum(1 for r in recalls_f if r == 1.0)
        zero_hits = sum(1 for r in results_filtered if r["recall"] == 0 and not r.get("is_gap"))
        print(f"\nフィルタあり:")
        print(f"  平均 Recall@6: {avg_recall_f:.3f}")
        print(f"  完全一致:      {perfect_f}/{len(recalls_f)}")
        print(f"  ヒット0件:     {zero_hits}/{len(recalls_f)}")


if __name__ == "__main__":
    main()
