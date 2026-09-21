"""知識増幅器: LLMから知識を吸い出し、4層検証してMVPストアに投入

検証パイプライン:
  Layer 1: CrossRef — DOI実在確認
  Layer 2: OpenAlex — CrossRefフォールバック + 引用関係
  Layer 3: Semantic Scholar — abstract取得 + claim意味一致判定
  Layer 4: マルチLLM cross-check — 複数LLMの出典一致度

Usage:
    python knowledge_amplifier.py "Nash equilibrium"
    python knowledge_amplifier.py "information theory entropy" --depth 2
    python knowledge_amplifier.py "second price auction" --dry-run
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

from config import LLM_API_KEY, LLM_SECONDARY_KEY, WORKER_MODEL


# ════════════════════════════════════════════
# LLM呼び出し
# ════════════════════════════════════════════

def _call_llm(prompt: str, model: str = WORKER_MODEL) -> str:
    # Compatibility name; all normal work uses the pinned low-cost worker.
    from cheap_llm import complete
    return complete(prompt, task="knowledge_amplifier", max_tokens=2048)


def _call_secondary(prompt: str, model: str = "") -> str:
    """Secondary LLM for cross-check"""
    LLM_SECONDARY_ENDPOINT = os.environ.get("LLM_SECONDARY_ENDPOINT", "")
    url = f"{LLM_SECONDARY_ENDPOINT}?key={LLM_SECONDARY_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return data["candidates"][0]["content"]["parts"][0]["text"]


# ════════════════════════════════════════════
# Step 1: LLMからclaim+出典を抽出
# ════════════════════════════════════════════

EXTRACT_PROMPT = """You are a knowledge extraction engine. Given a topic, output 5-8 core claims with their academic sources.

Rules:
1. Each claim must be a single, falsifiable statement
2. Each source MUST include a DOI if one exists
3. Include: author, year, title, journal, DOI, specific page/theorem/section
4. Do NOT invent DOIs — if unsure, write null for doi
5. Include 2-3 related topics for further exploration

Output ONLY valid JSON (no markdown fences):
{
  "topic": "...",
  "claims": [
    {
      "statement": "...",
      "kind": "definition|theorem|empirical|abstraction",
      "sources": [
        {
          "author": "...",
          "year": 1948,
          "title": "...",
          "journal": "...",
          "doi": "10.xxxx/..." or null,
          "locator": "Theorem 1, p.49"
        }
      ]
    }
  ],
  "related_topics": ["topic1", "topic2", "topic3"]
}

Topic: {topic}
"""


def extract_claims(topic: str, llm: str = "worker") -> dict:
    """LLMにトピックを投げてclaim+出典を抽出"""
    prompt = EXTRACT_PROMPT.replace("{topic}", topic)
    if llm == "secondary":
        raw = _call_secondary(prompt)
    else:
        raw = _call_llm(prompt)

    # JSON抽出
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw, re.DOTALL)
    text = match.group(1) if match else raw
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise ValueError(f"Could not parse LLM output:\n{text[:500]}")


# ════════════════════════════════════════════
# Layer 1: CrossRef API — DOI実在確認
# ════════════════════════════════════════════

def verify_crossref(doi: str) -> dict | None:
    if not doi:
        return None
    url = f"https://api.crossref.org/works/{urllib.request.quote(doi, safe='')}"
    headers = {"User-Agent": "KnowledgeEngine/1.0 (mailto:knowledge@example.com)"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        msg = data.get("message", {})
        title = msg.get("title", [""])[0] if msg.get("title") else ""
        authors = ", ".join(a.get("family", "") for a in msg.get("author", []))
        year = None
        for df in ["published-print", "published-online", "created"]:
            if df in msg:
                parts = msg[df].get("date-parts", [[]])[0]
                if parts:
                    year = parts[0]
                    break
        return {
            "source": "crossref", "doi": doi, "verified": True,
            "title": title, "authors": authors, "year": year,
            "journal": (msg.get("container-title", [""])  or [""])[0],
            "page_count": msg.get("page", ""),
        }
    except urllib.error.HTTPError as e:
        return {"source": "crossref", "doi": doi, "verified": False,
                "reason": f"HTTP {e.code}" if e.code != 404 else "not found"}
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as e:
        return {"source": "crossref", "doi": doi, "verified": False, "reason": str(e)}


# ════════════════════════════════════════════
# Layer 2: OpenAlex API — フォールバック + 引用関係
# ════════════════════════════════════════════

def verify_openalex(doi: str) -> dict | None:
    if not doi:
        return None
    url = f"https://api.openalex.org/works/doi:{urllib.request.quote(doi, safe='')}"
    headers = {"User-Agent": "KnowledgeEngine/1.0 (mailto:knowledge@example.com)"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        authors = ", ".join(
            a.get("author", {}).get("display_name", "")
            for a in data.get("authorships", [])[:5]
        )
        return {
            "source": "openalex", "doi": doi, "verified": True,
            "title": data.get("title", ""),
            "authors": authors,
            "year": data.get("publication_year"),
            "cited_by_count": data.get("cited_by_count", 0),
            "referenced_works_count": len(data.get("referenced_works", [])),
            "openalex_id": data.get("id", ""),
            "open_access": data.get("open_access", {}).get("is_oa", False),
            "oa_url": data.get("open_access", {}).get("oa_url"),
        }
    except urllib.error.HTTPError:
        return {"source": "openalex", "doi": doi, "verified": False, "reason": "not found"}
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as e:
        return {"source": "openalex", "doi": doi, "verified": False, "reason": str(e)}


# ════════════════════════════════════════════
# Layer 3: Semantic Scholar — abstract + claim意味一致
# ════════════════════════════════════════════

def verify_semantic_scholar(doi: str, claim_statement: str = "") -> dict | None:
    if not doi:
        return None
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.request.quote(doi, safe='')}?fields=title,abstract,year,authors,citationCount,tldr"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KnowledgeEngine/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        abstract = data.get("abstract", "") or ""
        tldr = data.get("tldr", {})
        tldr_text = tldr.get("text", "") if tldr else ""
        authors = ", ".join(a.get("name", "") for a in data.get("authors", [])[:5])

        # claim意味一致の簡易判定: claimのキーワードがabstract/tldrに含まれるか
        relevance = "unknown"
        if claim_statement and (abstract or tldr_text):
            source_text = (abstract + " " + tldr_text).lower()
            keywords = re.findall(r'[a-zA-Z]{4,}', claim_statement.lower())
            if keywords:
                hit = sum(1 for kw in keywords if kw in source_text)
                ratio = hit / len(keywords)
                if ratio >= 0.4:
                    relevance = "likely_relevant"
                elif ratio >= 0.2:
                    relevance = "possibly_relevant"
                else:
                    relevance = "low_relevance"

        return {
            "source": "semantic_scholar", "doi": doi, "verified": True,
            "title": data.get("title", ""),
            "authors": authors,
            "year": data.get("year"),
            "citation_count": data.get("citationCount", 0),
            "abstract_available": bool(abstract),
            "abstract_snippet": abstract[:200] if abstract else "",
            "tldr": tldr_text[:200] if tldr_text else "",
            "claim_relevance": relevance,
        }
    except urllib.error.HTTPError:
        return {"source": "semantic_scholar", "doi": doi, "verified": False, "reason": "not found"}
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as e:
        return {"source": "semantic_scholar", "doi": doi, "verified": False, "reason": str(e)}


# ════════════════════════════════════════════
# Layer 4: Unpaywall — OA PDF URL + ページ数
# ════════════════════════════════════════════

def check_unpaywall(doi: str) -> dict | None:
    if not doi:
        return None
    url = f"https://api.unpaywall.org/v2/{urllib.request.quote(doi, safe='')}?email=knowledge@example.com"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        best = data.get("best_oa_location", {}) or {}
        return {
            "source": "unpaywall", "doi": doi,
            "is_oa": data.get("is_oa", False),
            "oa_url": best.get("url_for_pdf") or best.get("url"),
            "version": best.get("version", ""),
            "journal": data.get("journal_name", ""),
        }
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError, OSError):
        return {"source": "unpaywall", "doi": doi, "is_oa": False}


# ════════════════════════════════════════════
# Layer 5: マルチLLM cross-check
# ════════════════════════════════════════════

CROSSCHECK_PROMPT = """Given this claim, provide the single most authoritative academic source with DOI.
Reply with ONLY JSON: {{"doi": "10.xxx/yyy", "author": "...", "year": 1234, "title": "..."}}
If no DOI exists, set doi to null.

Claim: {claim}
"""


def cross_check_claim(claim_statement: str) -> dict:
    """複数LLMに同じclaimの出典を独立に聞き、DOI一致度を算出"""
    prompt = CROSSCHECK_PROMPT.replace("{claim}", claim_statement)
    results = {}

    # Primary worker
    try:
        raw = _call_llm(prompt)
        match = re.search(r'\{.*?\}', raw, re.DOTALL)
        if match:
            results["worker"] = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        results["worker"] = None

    # Secondary worker
    try:
        raw = _call_secondary(prompt)
        match = re.search(r'\{.*?\}', raw, re.DOTALL)
        if match:
            results["secondary"] = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        results["secondary"] = None

    # DOI一致度
    dois = set()
    for llm, data in results.items():
        if data and data.get("doi"):
            dois.add(data["doi"])

    agreement = "no_data"
    if len(dois) == 0:
        agreement = "no_doi_from_any"
    elif len(dois) == 1 and len([d for d in results.values() if d and d.get("doi")]) >= 2:
        agreement = "unanimous"
    elif len(dois) == 1:
        agreement = "single_source"
    else:
        agreement = "disagreement"

    return {
        "responses": results,
        "unique_dois": list(dois),
        "agreement": agreement,
    }


# ════════════════════════════════════════════
# 4層統合検証パイプライン
# ════════════════════════════════════════════

def full_verify(doi: str, claim_statement: str = "", do_crosscheck: bool = False) -> dict:
    """4層すべてを通す統合検証"""
    result = {"doi": doi, "layers": {}, "final_grade": "F", "issues": []}

    # Layer 1: CrossRef
    cr = verify_crossref(doi)
    result["layers"]["crossref"] = cr
    time.sleep(0.2)

    if not cr or not cr.get("verified"):
        # Layer 2: OpenAlexフォールバック
        oa = verify_openalex(doi)
        result["layers"]["openalex"] = oa
        time.sleep(0.2)
        if not oa or not oa.get("verified"):
            result["issues"].append("DOI not found in CrossRef or OpenAlex")
            result["final_grade"] = "REJECTED"
            return result
        else:
            result["layers"]["crossref"] = {"source": "crossref", "doi": doi, "verified": False, "reason": "fallback to openalex"}
    else:
        # OpenAlexも引用数のために呼ぶ
        oa = verify_openalex(doi)
        result["layers"]["openalex"] = oa
        time.sleep(0.2)

    # Layer 3: Semantic Scholar
    ss = verify_semantic_scholar(doi, claim_statement)
    result["layers"]["semantic_scholar"] = ss
    time.sleep(0.5)  # S2 rate limit

    if ss and ss.get("verified"):
        if ss.get("claim_relevance") == "low_relevance":
            result["issues"].append("abstract does not match claim (low keyword overlap)")

    # Layer 4: Unpaywall
    up = check_unpaywall(doi)
    result["layers"]["unpaywall"] = up

    # 最終グレード算出
    score = 0
    # DOI実在 (+3)
    if (cr and cr.get("verified")) or (oa and oa.get("verified")):
        score += 3
    # abstract取得可能 (+1)
    if ss and ss.get("abstract_available"):
        score += 1
    # claim関連性 (+2 / +1 / 0)
    if ss and ss.get("claim_relevance") == "likely_relevant":
        score += 2
    elif ss and ss.get("claim_relevance") == "possibly_relevant":
        score += 1
    # 引用数 (+1 if > 10)
    citations = 0
    if ss and ss.get("citation_count"):
        citations = ss["citation_count"]
    elif oa and oa.get("cited_by_count"):
        citations = oa["cited_by_count"]
    if citations > 10:
        score += 1
    # OA (+0.5)
    if up and up.get("is_oa"):
        score += 0.5

    if score >= 6:
        result["final_grade"] = "A"
    elif score >= 4:
        result["final_grade"] = "B"
    elif score >= 3:
        result["final_grade"] = "C"
    else:
        result["final_grade"] = "D"

    result["score"] = score
    result["citation_count"] = citations

    return result


# ════════════════════════════════════════════
# MVPストアに投入
# ════════════════════════════════════════════

def register_to_store(claims_data: dict, verifications: dict, dry_run: bool = False):
    if dry_run:
        return []
    from mvp_store import init_db, add_evidence
    db = init_db()
    registered = []

    for claim in claims_data.get("claims", []):
        for src in claim.get("sources", []):
            doi = src.get("doi")
            if not doi:
                continue
            v = verifications.get(doi)
            if not v or v.get("final_grade") == "REJECTED":
                continue

            eid = f"E-AUTO-{doi.replace('/', '-').replace('.', '_')[:30]}"
            existing = db.execute("SELECT evidence_id FROM evidence WHERE evidence_id=?", (eid,)).fetchone()
            if existing:
                continue

            grade = v.get("final_grade", "C")
            # grade mapping: A→A, B→B, C/D→C (MVPストアはA/B/Cのみ)
            store_grade = "A" if grade == "A" else "B" if grade == "B" else "C"

            limitations = []
            if v.get("issues"):
                limitations.extend(v["issues"])
            limitations.append("LLM提示→4層自動検証済み")

            ss = v.get("layers", {}).get("semantic_scholar", {})
            abstract_snippet = ss.get("abstract_snippet", "") if ss else ""

            try:
                add_evidence(db, eid, "source_excerpt",
                    source_uri=f"doi:{doi}",
                    source_version=str(v.get("layers", {}).get("crossref", {}).get("year", "") or
                                       v.get("layers", {}).get("openalex", {}).get("year", "")),
                    locator=src.get("locator"),
                    content_hash="pending_verification",
                    origin_group="llm_amplified",
                    reliability_grade=store_grade,
                    limitations=limitations)
                registered.append({
                    "evidence_id": eid, "doi": doi, "grade": grade,
                    "title": (v.get("layers", {}).get("crossref", {}).get("title", "") or
                              v.get("layers", {}).get("openalex", {}).get("title", "")),
                    "citations": v.get("citation_count", 0),
                    "claim": claim["statement"][:80],
                })
            except (sqlite3.Error, KeyError) as e:
                print(f"  WARN: Failed to register {eid}: {e}")

    return registered


# ════════════════════════════════════════════
# メインループ: 芋づる式展開
# ════════════════════════════════════════════

def amplify(topic: str, depth: int = 1, dry_run: bool = False, crosscheck: bool = False, verbose: bool = False):
    visited = set()
    queue = [(topic, 0)]
    all_results = []

    while queue:
        current_topic, current_depth = queue.pop(0)
        if current_topic in visited or current_depth > depth:
            continue
        visited.add(current_topic)

        print(f"\n{'='*60}")
        print(f"[depth={current_depth}] Topic: {current_topic}")
        print(f"{'='*60}")

        # LLMからclaim抽出
        print("  Extracting claims from LLM...")
        try:
            claims_data = extract_claims(current_topic)
        except (ValueError, json.JSONDecodeError, urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"  ERROR: {e}")
            continue

        claims = claims_data.get("claims", [])
        print(f"  Claims extracted: {len(claims)}")

        # 全DOI収集
        all_dois = []
        doi_to_claim = {}
        for claim in claims:
            for src in claim.get("sources", []):
                doi = src.get("doi")
                if doi and doi not in doi_to_claim:
                    all_dois.append((doi, src))
                    doi_to_claim[doi] = claim.get("statement", "")

        print(f"  DOIs to verify (4-layer): {len(all_dois)}")
        verifications = {}
        stats = {"A": 0, "B": 0, "C": 0, "D": 0, "REJECTED": 0}

        for doi, src in all_dois:
            claim_text = doi_to_claim.get(doi, "")
            v = full_verify(doi, claim_text, do_crosscheck=crosscheck)
            verifications[doi] = v
            grade = v.get("final_grade", "?")
            stats[grade] = stats.get(grade, 0) + 1

            # 表示
            if grade == "REJECTED":
                mark = "✗ REJECTED"
            else:
                mark = f"✓ Grade {grade}"

            cr = v.get("layers", {}).get("crossref", {})
            ss = v.get("layers", {}).get("semantic_scholar", {})
            oa = v.get("layers", {}).get("openalex", {})
            up = v.get("layers", {}).get("unpaywall", {})

            title = (cr.get("title") or oa.get("title", "") if oa else "")[:60]
            citations = v.get("citation_count", 0)
            relevance = ss.get("claim_relevance", "?") if ss else "?"
            is_oa = "OA" if (up and up.get("is_oa")) else "closed"

            print(f"    {mark} | {doi}")
            print(f"         {title}")
            print(f"         citations={citations}  relevance={relevance}  {is_oa}")
            if v.get("issues"):
                for issue in v["issues"]:
                    print(f"         ⚠ {issue}")

        # マルチLLM cross-check (オプション)
        crosscheck_results = {}
        if crosscheck:
            print(f"\n  Cross-checking {len(claims)} claims across LLMs...")
            for i, claim in enumerate(claims):
                cc = cross_check_claim(claim["statement"])
                crosscheck_results[claim["statement"][:50]] = cc
                print(f"    Claim {i+1}: agreement={cc['agreement']}, dois={cc['unique_dois']}")
                time.sleep(0.5)

        print(f"\n  Verification results: {stats}")

        # 登録
        if not dry_run:
            registered = register_to_store(claims_data, verifications)
            if registered:
                print(f"  Registered {len(registered)} evidence records:")
                for r in registered:
                    print(f"    [{r['grade']}] {r['evidence_id']}: {r['title'][:50]} (cited: {r['citations']})")
        else:
            print("  [DRY RUN] Skipping registration")

        result = {
            "topic": current_topic, "depth": current_depth,
            "claims": len(claims), "dois_checked": len(all_dois),
            "stats": stats,
            "crosscheck": crosscheck_results if crosscheck else None,
        }
        all_results.append(result)

        # 関連トピック展開
        related = claims_data.get("related_topics", [])
        for rt in related:
            if rt not in visited:
                queue.append((rt, current_depth + 1))
                print(f"  → Queued: {rt}")

    # サマリー
    print(f"\n{'='*60}")
    print("AMPLIFICATION SUMMARY")
    print(f"{'='*60}")
    total = {"checked": 0, "A": 0, "B": 0, "C": 0, "D": 0, "REJECTED": 0}
    for r in all_results:
        total["checked"] += r["dois_checked"]
        for g in ["A", "B", "C", "D", "REJECTED"]:
            total[g] += r["stats"].get(g, 0)

    print(f"Topics explored: {len(all_results)}")
    print(f"DOIs checked: {total['checked']}")
    print(f"  Grade A (high confidence): {total['A']}")
    print(f"  Grade B (verified):        {total['B']}")
    print(f"  Grade C (weak):            {total['C']}")
    print(f"  Grade D (minimal):         {total['D']}")
    print(f"  REJECTED (hallucination):  {total['REJECTED']}")
    accepted = total["A"] + total["B"] + total["C"] + total["D"]
    if total["checked"] > 0:
        print(f"Acceptance rate: {accepted}/{total['checked']} ({accepted/total['checked']*100:.0f}%)")
        print(f"Hallucination rate: {total['REJECTED']}/{total['checked']} ({total['REJECTED']/total['checked']*100:.0f}%)")

    out_path = Path(__file__).parent / "work" / "amplification_result.json"
    out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {out_path}")

    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="知識増幅器 (4層検証)")
    parser.add_argument("topic", help="起点トピック")
    parser.add_argument("--depth", type=int, default=1, help="芋づる展開の深さ")
    parser.add_argument("--dry-run", action="store_true", help="DB登録せず検証のみ")
    parser.add_argument("--crosscheck", action="store_true", help="マルチLLM cross-checkを有効化")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    amplify(args.topic, depth=args.depth, dry_run=args.dry_run,
            crosscheck=args.crosscheck, verbose=args.verbose)
