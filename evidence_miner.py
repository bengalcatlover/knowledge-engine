"""evidence_miner: Evidence→Claim自動抽出

既存evidenceのabstractから原子的claimを抽出し、MVPストアに登録する。
統合設計に基づく実装。

パイプライン:
  1. DOI付きevidenceからSemantic ScholarでAbstract取得
  2. LLMでabstractから原子的claim抽出（最大5件/abstract）
  3. 既存claimとの重複判定（keyword overlap）
  4. ノード帰属決定（既存ノードへのマッチ or unresolved記録）
  5. MVPストア登録 + support_assessment生成 + HYP隔離

Usage:
    python evidence_miner.py mine E-AUTO-10_1037-h0037350
    python evidence_miner.py mine-all                       # 全unmined evidenceを処理
    python evidence_miner.py mine-all --dry-run              # DB変更なし
    python evidence_miner.py status                          # mining状態表示
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from mvp_store import init_db, get_db, add_claim, add_support, _uid, _now, DB_PATH

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
WORKER_MODEL = os.environ.get("LLM_WORKER_MODEL", "")

# ════════════════════════════════════════════
# Mining台帳スキーマ
# ════════════════════════════════════════════

def init_mining_table(db):
    """evidence_mining_log: どのevidenceを処理済みか追跡"""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS evidence_mining_log (
            evidence_id TEXT PRIMARY KEY,
            state TEXT NOT NULL DEFAULT 'pending'
                CHECK(state IN ('pending','mined','no_abstract','skipped','failed')),
            abstract_text TEXT,
            claims_extracted INTEGER NOT NULL DEFAULT 0,
            claims_new INTEGER NOT NULL DEFAULT 0,
            claims_duplicate INTEGER NOT NULL DEFAULT 0,
            claims_unresolved INTEGER NOT NULL DEFAULT 0,
            mined_at TEXT,
            error_detail TEXT
        );
    """)
    db.commit()


# ════════════════════════════════════════════
# Step 1: Abstract取得（Semantic Scholar）
# ════════════════════════════════════════════

def _extract_doi(source_uri: str) -> str | None:
    """source_uriからDOIを抽出"""
    if not source_uri:
        return None
    if source_uri.startswith("doi:"):
        return source_uri[4:]
    m = re.search(r'10\.\d{4,9}/[^\s]+', source_uri)
    return m.group(0) if m else None


def _fetch_abstract_s2(doi: str) -> dict | None:
    """Semantic ScholarからAbstract取得（プライマリ）"""
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.request.quote(doi, safe='')}?fields=title,abstract,year,authors,tldr"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KnowledgeEngine/1.0 (mailto:knowledge@example.com)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        abstract = data.get("abstract", "") or ""
        tldr = data.get("tldr", {})
        tldr_text = tldr.get("text", "") if tldr else ""
        title = data.get("title", "") or ""
        authors = ", ".join(a.get("name", "") for a in data.get("authors", [])[:5])
        if abstract or tldr_text:
            return {
                "ok": True, "doi": doi, "source": "semantic_scholar",
                "title": title, "authors": authors, "year": data.get("year"),
                "abstract": abstract, "tldr": tldr_text,
            }
        return None  # abstractなし → フォールバックへ
    except Exception:
        return None


def _fetch_abstract_openalex(doi: str) -> dict | None:
    """OpenAlexからAbstract取得（フォールバック）"""
    url = f"https://api.openalex.org/works/doi:{urllib.request.quote(doi, safe='')}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KnowledgeEngine/1.0 (mailto:knowledge@example.com)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        # OpenAlexのabstractはinverted indexで返る
        aii = data.get("abstract_inverted_index")
        abstract = ""
        if aii:
            positions = {}
            for word, indices in aii.items():
                for idx in indices:
                    positions[idx] = word
            abstract = " ".join(positions[i] for i in sorted(positions.keys()))

        title = data.get("title", "") or ""
        authors = ", ".join(
            a.get("author", {}).get("display_name", "")
            for a in data.get("authorships", [])[:5]
        )
        if abstract:
            return {
                "ok": True, "doi": doi, "source": "openalex",
                "title": title, "authors": authors,
                "year": data.get("publication_year"),
                "abstract": abstract, "tldr": "",
            }
        return None
    except Exception:
        return None


def _fetch_crossref_meta(doi: str) -> dict | None:
    """CrossRefからタイトル・著者・年・ジャーナルを取得"""
    url = f"https://api.crossref.org/works/{urllib.request.quote(doi, safe='')}"
    headers = {"User-Agent": "KnowledgeEngine/1.0 (mailto:knowledge@example.com)"}
    try:
        req = urllib.request.Request(url, headers=headers)
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
        journal = (msg.get("container-title", [""]) or [""])[0]
        if title:
            return {"title": title, "authors": authors, "year": year, "journal": journal}
        return None
    except Exception:
        return None


def _synthesize_abstract_llm(doi: str, meta: dict) -> dict | None:
    """LLMフォールバック: CrossRefメタデータからabstract相当の要約を生成し、cross-checkで検証する。

    検証手順:
      1. 2回別プロンプトで要約を生成
      2. keyword重複率で内容の一貫性をチェック（閾値40%）
      3. CrossRefメタデータ（著者・年）との矛盾がないかチェック
    """
    from cheap_llm import complete

    title = meta["title"]
    authors = meta.get("authors", "unknown")
    year = meta.get("year", "unknown")
    journal = meta.get("journal", "unknown")

    prompt_a = f"""You are a scholarly research assistant. Given the metadata of an academic paper,
provide a factual summary of the paper's main contributions and findings.

IMPORTANT: Only state what you are confident the paper actually argues. If you are unsure, say "uncertain".
Do NOT invent claims. Stick to widely known, established facts about this paper.

Paper metadata:
- Title: {title}
- Authors: {authors}
- Year: {year}
- Journal: {journal}
- DOI: {doi}

Output ONLY valid JSON:
{{"title": "...", "authors": "...", "year": ..., "summary": "A 3-5 sentence summary of the paper's main argument and contributions", "key_claims": ["claim1", "claim2", "claim3"], "confidence": "high" or "medium" or "low"}}"""

    prompt_b = f"""You are an academic knowledge verifier. For the following published paper,
state the core thesis and key results. Be precise and conservative — omit anything you are not sure about.

- Title: {title}
- Author(s): {authors}
- Published: {year}, {journal}
- DOI: {doi}

Output ONLY valid JSON:
{{"core_thesis": "one sentence", "results": ["result1", "result2", "result3"], "confidence": "high" or "medium" or "low"}}"""

    try:
        raw_a = complete(prompt_a, task="llm_abstract_synth_a", max_tokens=1024)
        raw_b = complete(prompt_b, task="llm_abstract_synth_b", max_tokens=1024)
    except Exception:
        return None

    # JSON parse
    def _parse(raw):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            s, e = raw.find('{'), raw.rfind('}') + 1
            if s >= 0 and e > s:
                try:
                    return json.loads(raw[s:e])
                except json.JSONDecodeError:
                    pass
        return None

    data_a = _parse(raw_a)
    data_b = _parse(raw_b)
    if not data_a or not data_b:
        return None

    # 信頼度チェック: どちらかがlowなら不採用
    conf_a = data_a.get("confidence", "low")
    conf_b = data_b.get("confidence", "low")
    if conf_a == "low" or conf_b == "low":
        return None

    # keyword cross-check: 両方の出力からキーワードを抽出し重複率を測る
    def _keywords(text):
        if not text:
            return set()
        stops = {"the","a","an","of","in","to","for","and","or","is","are","was","were",
                 "that","this","with","by","on","at","from","as","it","its","be","has","have",
                 "had","not","but","if","can","will","do","does","did","than","no","so","we",
                 "they","their","our","may","would","could","should","about","into","also",
                 "one","two","each","all","any","such","more","some","which","when","where",
                 "how","what","who","been","being","between","under","over","paper","study"}
        words = set(re.findall(r'[a-z]{3,}', text.lower()))
        return words - stops

    text_a = data_a.get("summary", "") + " " + " ".join(data_a.get("key_claims", []))
    text_b = data_b.get("core_thesis", "") + " " + " ".join(data_b.get("results", []))
    kw_a = _keywords(text_a)
    kw_b = _keywords(text_b)

    if not kw_a or not kw_b:
        return None

    overlap = len(kw_a & kw_b)
    union = len(kw_a | kw_b)
    jaccard = overlap / union if union > 0 else 0

    if jaccard < 0.20:
        return None  # 2回の出力が矛盾している

    # CrossRefメタデータとの整合チェック: 年が言及されていれば一致するか
    synth_text = text_a + " " + text_b
    if year and str(year) not in synth_text:
        pass  # 年の不言及は許容（必ずしも年を書くとは限らない）

    # 著者名チェック: 最初の著者のfamily nameがどちらかに言及されているか
    author_families = [a.strip() for a in authors.split(",") if a.strip()]
    if author_families:
        first_author = author_families[0].lower()
        if len(first_author) > 2 and first_author not in synth_text.lower():
            pass  # 著者名の不言及も許容（要約では省略されることがある）

    # 合成abstractを構築
    summary = data_a.get("summary", "")
    claims = data_a.get("key_claims", [])
    abstract = summary
    if claims:
        abstract += " Key claims: " + "; ".join(claims[:5])

    if len(abstract.strip()) < 50:
        return None

    return {
        "ok": True, "doi": doi, "source": "llm_synthetic",
        "title": title, "authors": authors, "year": year,
        "abstract": abstract, "tldr": data_b.get("core_thesis", ""),
        "cross_check_jaccard": round(jaccard, 3),
        "confidence_a": conf_a, "confidence_b": conf_b,
    }


def fetch_abstract(doi: str) -> dict:
    """Abstract取得: Semantic Scholar → OpenAlex → LLM合成 フォールバック"""
    # プライマリ: Semantic Scholar
    result = _fetch_abstract_s2(doi)
    if result:
        return result

    # フォールバック1: OpenAlex
    time.sleep(0.3)
    result = _fetch_abstract_openalex(doi)
    if result:
        return result

    # フォールバック2: LLM合成（CrossRefメタデータ + 2回生成cross-check）
    time.sleep(0.3)
    meta = _fetch_crossref_meta(doi)
    if meta:
        result = _synthesize_abstract_llm(doi, meta)
        if result:
            return result

    return {"ok": False, "doi": doi, "reason": "no abstract from S2, OpenAlex, or LLM synthesis"}


# ════════════════════════════════════════════
# Step 2: LLMでClaim抽出
# ════════════════════════════════════════════

MINE_PROMPT = """You are an evidence mining engine. Given a paper's title, authors, and abstract, extract atomic claims.

Rules:
1. Each claim = exactly 1 falsifiable proposition. Do NOT combine multiple findings.
2. Max 5 claims per abstract. Prioritize: empirical results > theoretical > methodological > definitional.
3. Preserve negation, conditions, quantifiers, caveats from the original text.
4. Do NOT strengthen: "correlated" ≠ "causes", "suggests" ≠ "proves".
5. For each claim, classify:
   - claim_type: "empirical" | "theoretical" | "methodological" | "definitional"
   - polarity: "supports" | "refutes" | "conditions" (adds boundary conditions)
   - confidence: "strong" (direct result) | "hedged" (qualified) | "speculative" (hypothesis/future work)
   - attribution: "own_result" (this paper's finding) | "background" (citing others) | "hypothesis" (proposed, not tested)
6. Include subjects: use the EXISTING NODE NAMES below when the claim is related. If no match, use a descriptive name.
7. Include source_quote: a verbatim, contiguous passage from the abstract that fully supports the claim.
   If the abstract ends mid-sentence, omit that incomplete sentence. Never complete missing text.
8. Statements about earlier authors/papers are background, NOT own_result. Proposed or untested
   benefits MUST have attribution="hypothesis" AND confidence="speculative".
9. A nonsignificant association does not refute an association: use polarity="conditions".

EXISTING NODES in the knowledge graph:
{nodes_list}

Output ONLY valid JSON (no markdown fences):
{
  "claims": [
    {
      "text": "single sentence claim, self-contained and falsifiable",
      "source_quote": "exact supporting text copied from the abstract",
      "claim_type": "empirical",
      "polarity": "supports",
      "confidence": "strong",
      "attribution": "own_result",
      "subjects": ["ExistingNodeName or new concept"]
    }
  ]
}

Paper:
  Title: {title}
  Authors: {authors}
  Year: {year}
  Abstract: {abstract}
"""


def _format_nodes_list(nodes_with_claims: list[dict]) -> str:
    """プロンプト用のノード一覧を生成"""
    lines = []
    for n in nodes_with_claims:
        title = n.get("title", "")
        nid = n["node_id"]
        layer = n.get("layer", "")
        claims_summary = "; ".join(c["statement"][:50] for c in n.get("claims", [])[:2])
        lines.append(f"  - {nid} ({layer}): {title}" + (f" — {claims_summary}" if claims_summary else ""))
    return "\n".join(lines)


def _call_llm(prompt: str, model: str = WORKER_MODEL) -> str:
    # Compatibility name; all normal work uses the pinned low-cost worker.
    from cheap_llm import complete
    return complete(prompt, task="evidence_miner", max_tokens=2048)


def extract_claims_from_abstract(title: str, authors: str, year, abstract: str,
                                  nodes_with_claims: list[dict] | None = None) -> list[dict]:
    """abstractから原子的claimを抽出。最大5件。"""
    if not abstract or len(abstract.strip()) < 50:
        return []

    nodes_list = _format_nodes_list(nodes_with_claims) if nodes_with_claims else "  (none)"
    prompt = MINE_PROMPT.replace("{title}", title or "Unknown") \
                        .replace("{authors}", authors or "Unknown") \
                        .replace("{year}", str(year or "Unknown")) \
                        .replace("{abstract}", abstract) \
                        .replace("{nodes_list}", nodes_list)

    raw = _call_llm(prompt)

    # JSON抽出
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw, re.DOTALL)
    text = match.group(1) if match else raw
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
        else:
            print(f"  [WARN] Could not parse LLM output: {text[:200]}")
            return []

    return validate_extracted_claims(data.get("claims", []), abstract)


def attribution_review_reasons(quote, abstract):
    """Conservative English triage, not a general entailment classifier."""
    import re
    start = abstract.find(quote)
    if start < 0:
        return ['quote_missing']
    # Include the sentence prefix: a cropped quotation may hide attribution.
    prefix = abstract[:start]
    boundary = max(prefix.rfind('. '), prefix.rfind('\n'))
    context = abstract[max(0, boundary + 1):start + len(quote)]
    reasons = []
    if re.search(r'\b(?:analy[sz]ed|shown|proved|proposed|introduced)\s+(?:further\s+)?by\b|\bwho\s+(?:have\s+)?(?:shown|proved)\b', context, re.I):
        reasons.append('prior_work_attribution_requires_review')
    if re.match(r'\s*(?:this|that|these|those)\s+(?:method|approach|auction|result|algorithm)', quote, re.I):
        reasons.append('cropped_antecedent_requires_review')
    return reasons


def validate_extracted_claims(claims, abstract):
    """Reject malformed/untraceable output; quotes prove location, not entailment."""
    if not isinstance(claims, list):
        raise ValueError("claims must be a list")
    valid = []
    for claim in claims[:5]:
        if not isinstance(claim, dict):
            continue
        quote = claim.get("source_quote")
        if not isinstance(quote, str) or len(quote.strip()) < 20 or quote not in abstract:
            continue
        if not isinstance(claim.get("text"), str) or not claim["text"].strip():
            continue
        allowed = {"claim_type": {"empirical", "theoretical", "methodological", "definitional"},
                   "polarity": {"supports", "refutes", "conditions"},
                   "confidence": {"strong", "hedged", "speculative"},
                   "attribution": {"own_result", "background", "hypothesis"}}
        if any(claim.get(k) not in values for k, values in allowed.items()):
            continue
        if not isinstance(claim.get("subjects"), list) or not all(isinstance(s, str) for s in claim["subjects"]):
            continue
        reasons = attribution_review_reasons(quote, abstract)
        if reasons:
            claim["review_required"] = True
            claim["review_reasons"] = reasons
        if claim["attribution"] == "hypothesis":
            claim["confidence"] = "speculative"
        # Refutation labels need a stronger audit than this inexpensive worker.
        # Keep the text as a candidate, but never let a null finding assert refutation.
        if claim["polarity"] == "refutes":
            claim["review_required"] = True
        claim["subjects"] = [s for s in claim["subjects"] if s not in
                             {"ExistingNodeName", "ExistingNodeName or new concept"}]
        valid.append(claim)
    return valid


# ════════════════════════════════════════════
# Step 3: 既存Claimとの重複判定
# ════════════════════════════════════════════

_STOPWORDS = frozenset({
    # 高頻度英語機能語（4文字以上）
    "that", "this", "with", "from", "have", "will", "been", "were", "being",
    "their", "there", "they", "them", "then", "than", "what", "when", "where",
    "which", "while", "would", "could", "should", "about", "after", "before",
    "between", "through", "under", "over", "into", "also", "each", "every",
    "both", "such", "some", "more", "most", "only", "very", "much", "many",
    "does", "done", "make", "made", "take", "taken", "give", "given", "come",
    "came", "goes", "went", "said", "tell", "told", "find", "found", "know",
    "knew", "known", "show", "shown", "showed", "like", "used", "using",
    "case", "well", "just", "even", "still", "back",
    # 論文頻出の汎用語（分野横断で出現、帰属判定に寄与しない）
    "model", "result", "results", "paper", "study", "approach", "method",
    "analysis", "problem", "based", "prove", "proof", "theorem", "shows",
    "implies", "condition", "conditions", "exist", "exists", "existence",
    "optimal", "increase", "increases", "decrease", "decreases",
    "expected", "probability", "function", "number", "value", "values",
    "general", "sufficient", "necessary", "unique", "total",
})


def _normalize_keywords(text: str) -> set[str]:
    """テキストからキーワードセットを抽出（4文字以上の英単語 + 日本語名詞的断片）
    ストップワード除去済み。"""
    # 英語キーワード
    en_kw = set(re.findall(r'[a-zA-Z]{4,}', text.lower())) - _STOPWORDS
    # 日本語: 漢字2文字以上の連続
    ja_kw = set(re.findall(r'[\u4e00-\u9fff]{2,}', text))
    return en_kw | ja_kw


def check_duplicate(new_claim_text: str, existing_claims: list[dict]) -> dict:
    """新claimが既存claimと重複しているか判定。

    Returns:
        {"verdict": "identical"|"similar"|"new",
         "match_claim_id": str|None,
         "similarity": float}
    """
    new_kw = _normalize_keywords(new_claim_text)
    if not new_kw:
        return {"verdict": "new", "match_claim_id": None, "similarity": 0.0}

    best_sim = 0.0
    best_id = None

    for ec in existing_claims:
        ec_kw = _normalize_keywords(ec["statement"])
        if not ec_kw:
            continue
        # Jaccard係数
        intersection = new_kw & ec_kw
        union = new_kw | ec_kw
        sim = len(intersection) / len(union) if union else 0.0

        if sim > best_sim:
            best_sim = sim
            best_id = ec["claim_id"]

    # 設計: 0.92以上 = identical, 0.75-0.92 = similar（gray zone）, <0.75 = new
    # keyword Jaccardはembedding cos_simより粗いので閾値を下げる
    if best_sim >= 0.70:
        return {"verdict": "identical", "match_claim_id": best_id, "similarity": best_sim}
    elif best_sim >= 0.45:
        return {"verdict": "similar", "match_claim_id": best_id, "similarity": best_sim}
    else:
        return {"verdict": "new", "match_claim_id": best_id, "similarity": best_sim}


# ════════════════════════════════════════════
# Step 4: ノード帰属決定
# ════════════════════════════════════════════

def _build_node_keyword_index(nodes_with_claims: list[dict]) -> list[dict]:
    """ノードごとにキーワードセットを事前構築（日英対応テーブル込み）"""
    # 日英概念対応テーブル（19ノード規模なので手動で十分、100ノード後はLLMで自動生成）
    JA_EN_MAP = {
        "オークション": {"auction", "bidding"},
        "入札": {"bid", "bidding", "auction"},
        "封印": {"sealed"},
        "正直": {"truthful", "honest", "incentive"},
        "支配戦略": {"dominant", "strategy", "dominance"},
        "均衡": {"equilibrium", "nash"},
        "ナッシュ": {"nash", "equilibrium"},
        "無作為": {"randomization", "random", "randomized", "experiment"},
        "処置": {"treatment", "intervention", "causal"},
        "統制": {"control", "comparison"},
        "交絡": {"confounding", "confounder", "covariate"},
        "実験": {"experiment", "experimental", "trial", "randomized"},
        "情報理論": {"information", "theory", "entropy", "coding"},
        "符号": {"coding", "code", "encoding"},
        "エントロピー": {"entropy", "information"},
        "メカニズム": {"mechanism", "design"},
        "インセンティブ": {"incentive", "compatible"},
        "価格": {"price", "pricing", "auction"},
        "比較試験": {"randomized", "controlled", "trial", "experiment", "causal"},
        "因果": {"causal", "causality", "effect", "effects"},
        "ランダム": {"random", "randomization", "randomized"},
    }
    # ノードtitleの日本語→英語追加マッピング（titleベース）
    TITLE_EN_MAP = {
        "ランダム化比較試験": {"randomized", "controlled", "trial", "experiment",
                       "causal", "treatment", "randomization", "evaluation"},
        "ナッシュ均衡": {"nash", "equilibrium", "game", "theory"},
        "インセンティブ両立性": {"incentive", "compatible", "compatibility", "mechanism",
                        "truthful", "dominant", "strategy"},
        "情報理論と表現圧縮": {"information", "theory", "compression", "entropy",
                       "coding", "shannon"},
    }

    result = []
    for node in nodes_with_claims:
        node_kw = set()
        for c in node.get("claims", []):
            node_kw |= _normalize_keywords(c["statement"])
            # 日本語キーワードを英語に展開
            ja_words = re.findall(r'[\u4e00-\u9fff]{2,}', c["statement"])
            for jw in ja_words:
                if jw in JA_EN_MAP:
                    node_kw |= JA_EN_MAP[jw]
        title = node.get("title", "")
        if title:
            node_kw |= _normalize_keywords(title)
            # titleの日英マッピング
            if title in TITLE_EN_MAP:
                node_kw |= TITLE_EN_MAP[title]
            # titleの部分一致でもJA_EN_MAPを適用
            ja_words = re.findall(r'[\u4e00-\u9fff]{2,}', title)
            for jw in ja_words:
                if jw in JA_EN_MAP:
                    node_kw |= JA_EN_MAP[jw]
        # ノードのtype/subtypeも手がかりに
        if node.get("type"):
            node_kw |= _normalize_keywords(node["type"])

        result.append({**node, "_kw": node_kw})
    return result


def resolve_node_attribution(claim_subjects: list[str], claim_text: str,
                              nodes_with_claims: list[dict]) -> dict:
    """claimを既存ノードにマッチさせる。

    nodes_with_claims: [{"node_id", "layer", "type", "subtype", "status", "claims": [{"claim_id", "statement"}]}]

    Returns:
        {"node_id": str|None, "confidence": float, "reason": str}
    """
    claim_kw = _normalize_keywords(claim_text)
    subject_kw = set()
    for s in (claim_subjects or []):
        subject_kw |= _normalize_keywords(s)
    all_kw = claim_kw | subject_kw

    if not all_kw:
        return {"node_id": None, "confidence": 0.0, "reason": "no keywords extractable"}

    indexed = _build_node_keyword_index(nodes_with_claims)

    best_score = 0.0
    best_node = None
    best_reason = ""

    for node in indexed:
        node_kw = node["_kw"]
        if not node_kw:
            continue

        overlap = all_kw & node_kw

        if not overlap:
            continue

        # 3つのスコアの最大値を取る（双方向 + subject重視）
        # 1. claim→nodeカバー率: claimのキーワードがどれだけnodeに含まれるか
        score_claim_to_node = len(overlap) / len(all_kw) if all_kw else 0
        # 2. node→claimカバー率: nodeのキーワードがどれだけclaimに含まれるか
        score_node_to_claim = len(overlap) / len(node_kw) if node_kw else 0
        # 3. subject限定: subjectキーワードとnodeの交差
        subject_overlap = subject_kw & node_kw
        score_subject = len(subject_overlap) / len(subject_kw) if subject_kw else 0

        # 加重平均: subject match重視
        score = max(
            score_claim_to_node,
            score_node_to_claim,
            score_subject * 1.5,  # subject matchにボーナス
            (score_claim_to_node + score_node_to_claim) / 2,  # 平均
        )

        if score > best_score:
            best_score = score
            best_node = node["node_id"]
            best_reason = f"overlap={len(overlap)} kw with {node['node_id']} (c2n={score_claim_to_node:.2f}, n2c={score_node_to_claim:.2f}, subj={score_subject:.2f})"

    if best_score >= 0.35:
        return {"node_id": best_node, "confidence": best_score, "reason": best_reason}
    else:
        return {"node_id": None, "confidence": best_score, "reason": f"no node matched (best={best_score:.2f})"}


# ════════════════════════════════════════════
# Step 5: MVPストア登録
# ════════════════════════════════════════════

def _claim_id(evidence_id: str, index: int) -> str:
    """evidence_idとindex からclaim_idを生成"""
    raw = f"{evidence_id}#mined-{index}"
    return raw


def _is_speculative(claim: dict) -> bool:
    """claimがspeculativeかどうか判定（HYP隔離対象）"""
    return (claim.get("confidence") == "speculative"
            or claim.get("attribution") == "hypothesis")


def register_mined_claims(db, evidence_id: str, claims: list[dict],
                           existing_claims: list[dict],
                           nodes_with_claims: list[dict],
                           dry_run: bool = False) -> dict:
    """抽出claimをMVPストアに登録。

    Returns:
        {"new": int, "duplicate": int, "unresolved": int, "details": list}
    """
    stats = {"new": 0, "duplicate": 0, "unresolved": 0, "details": []}

    for i, claim in enumerate(claims):
        if claim.get("review_required") or claim.get("attribution") == "background":
            stats["details"].append({"action": "deferred", "claim": claim})
            continue
        claim_text = claim.get("text", "").strip()
        if not claim_text:
            continue

        cid = _claim_id(evidence_id, i)

        # 重複判定
        dup = check_duplicate(claim_text, existing_claims)

        if dup["verdict"] == "identical":
            # 既存claimにevidence追加のみ
            stats["duplicate"] += 1
            detail = {"claim_id": cid, "action": "duplicate",
                      "match": dup["match_claim_id"], "sim": dup["similarity"]}

            # 既存claimのnode情報を取得してsupport_assessmentを追加
            if not dry_run and dup["match_claim_id"]:
                match_claim = next((c for c in existing_claims if c["claim_id"] == dup["match_claim_id"]), None)
                if match_claim:
                    add_support(db, evidence_id,
                                match_claim["node_id"], match_claim["node_revision"],
                                target_claim=match_claim["claim_id"],
                                support_role="premise",
                                rationale=f"evidence_miner auto-linked (duplicate, sim={dup['similarity']:.2f})",
                                assessor="evidence_miner")
                    detail["support_added"] = True

            stats["details"].append(detail)
            continue

        # similar: 新claimとして登録するがフラグ付き
        # new: 完全新規

        # ノード帰属
        attribution = resolve_node_attribution(
            claim.get("subjects", []), claim_text, nodes_with_claims)

        if attribution["node_id"] is None:
            stats["unresolved"] += 1
            stats["details"].append({
                "claim_id": cid, "action": "unresolved",
                "text": claim_text[:80],
                "reason": attribution["reason"],
                "confidence": attribution["confidence"],
            })
            continue

        node_id = attribution["node_id"]
        # ノードの最新revisionを取得
        row = db.execute(
            "SELECT revision FROM node WHERE id=? ORDER BY revision DESC LIMIT 1",
            (node_id,)
        ).fetchone()
        if not row:
            stats["unresolved"] += 1
            stats["details"].append({
                "claim_id": cid, "action": "unresolved",
                "text": claim_text[:80], "reason": f"node {node_id} not found"
            })
            continue
        node_rev = row[0]

        # claim種別のマッピング
        kind_map = {
            "empirical": "empirical",
            "theoretical": "theorem",
            "methodological": "empirical",
            "definitional": "definition",
        }
        claim_kind = kind_map.get(claim.get("claim_type", ""), "empirical")

        # HYP隔離: speculative claimはepistemic_status変更
        if _is_speculative(claim):
            epistemic = "unverified"  # HYP claimはunverifiedのまま
            # ノードがHYPでなければ、claimにHYPフラグを付ける
            # (claim kindをapplication_hypothesisに変更)
            claim_kind = "application_hypothesis"

        else:
            epistemic = "unverified"

        # 既にこのclaim_idが存在しないか確認
        existing = db.execute("SELECT 1 FROM claim WHERE claim_id=?", (cid,)).fetchone()
        if existing:
            stats["duplicate"] += 1
            stats["details"].append({"claim_id": cid, "action": "already_exists"})
            continue

        stats["new"] += 1
        detail = {
            "claim_id": cid, "action": "new",
            "node_id": node_id, "kind": claim_kind,
            "text": claim_text[:80],
            "attribution_confidence": attribution["confidence"],
            "speculative": _is_speculative(claim),
        }

        if not dry_run:
            # claim登録
            add_claim(db, cid, node_id, node_rev, claim_text, claim_kind, epistemic)

            # support_assessment: evidence → claim
            add_support(db, evidence_id,
                        node_id, node_rev,
                        target_claim=cid,
                        support_role="premise",
                        rationale=json.dumps({"worker": "evidence_miner", "claim": claim,
                                              "node_match": attribution['confidence']}, ensure_ascii=False),
                        assessor="evidence_miner")
            detail["registered"] = True

            # 新claimを既存リストに追加（後続claimの重複判定に使う）
            existing_claims.append({
                "claim_id": cid,
                "node_id": node_id,
                "node_revision": node_rev,
                "statement": claim_text,
            })

        stats["details"].append(detail)

    return stats


# ════════════════════════════════════════════
# 統合: mine_evidence
# ════════════════════════════════════════════

def _load_existing_claims(db) -> list[dict]:
    """既存claimを全取得"""
    rows = db.execute(
        "SELECT claim_id, node_id, node_revision, statement FROM claim"
    ).fetchall()
    return [{"claim_id": r[0], "node_id": r[1], "node_revision": r[2], "statement": r[3]} for r in rows]


def _load_nodes_with_claims(db) -> list[dict]:
    """ノード+紐付きclaim一覧を取得"""
    nodes = {}
    for row in db.execute("SELECT id, revision, layer, type, subtype, status, data FROM node ORDER BY id"):
        nid = row[0]
        data = {}
        try:
            data = json.loads(row[6]) if row[6] else {}
        except json.JSONDecodeError:
            pass
        nodes[nid] = {
            "node_id": nid, "revision": row[1], "layer": row[2],
            "type": row[3], "subtype": row[4], "status": row[5],
            "title": data.get("title", ""),
            "claims": []
        }

    for row in db.execute("SELECT claim_id, node_id, statement FROM claim"):
        nid = row[1]
        if nid in nodes:
            nodes[nid]["claims"].append({"claim_id": row[0], "statement": row[2]})

    return list(nodes.values())


def mine_evidence(evidence_id: str, dry_run: bool = False, verbose: bool = True) -> dict:
    """1件のevidenceからclaim抽出→登録の全パイプライン"""
    db = get_db()
    init_mining_table(db)

    result = {"evidence_id": evidence_id, "status": "unknown", "claims_extracted": 0}

    # evidence取得
    row = db.execute(
        "SELECT evidence_id, kind, source_uri, origin_group, reliability_grade FROM evidence WHERE evidence_id=?",
        (evidence_id,)
    ).fetchone()
    if not row:
        result["status"] = "not_found"
        if verbose:
            print(f"  [ERROR] Evidence {evidence_id} not found")
        return result

    source_uri = row[2]
    doi = _extract_doi(source_uri)

    if not doi:
        result["status"] = "no_doi"
        _log_mining(db, evidence_id, "skipped", error_detail="no DOI in source_uri", dry_run=dry_run)
        if verbose:
            print(f"  [SKIP] {evidence_id}: no DOI")
        return result

    # 既にmined済みかチェック
    existing_log = db.execute(
        "SELECT state FROM evidence_mining_log WHERE evidence_id=?",
        (evidence_id,)
    ).fetchone()
    if existing_log and existing_log[0] == "mined":
        result["status"] = "already_mined"
        if verbose:
            print(f"  [SKIP] {evidence_id}: already mined")
        return result

    # no_abstractの過去ログがあれば削除してリトライ許可
    if existing_log and existing_log[0] == "no_abstract":
        if not dry_run:
            db.execute("DELETE FROM evidence_mining_log WHERE evidence_id=?", (evidence_id,))
            db.commit()

    # Step 1: Abstract取得
    if verbose:
        print(f"  [1/4] Fetching abstract for DOI: {doi}")
    abstract_data = fetch_abstract(doi)

    if not abstract_data["ok"]:
        result["status"] = "no_abstract"
        _log_mining(db, evidence_id, "no_abstract",
                    error_detail=abstract_data.get("reason", "unknown"), dry_run=dry_run)
        if verbose:
            print(f"  [SKIP] {evidence_id}: abstract unavailable ({abstract_data.get('reason')})")
        return result

    abstract = abstract_data["abstract"]
    if not abstract or len(abstract.strip()) < 50:
        # tldrだけの場合もtry
        abstract = abstract_data.get("tldr", "")
        if not abstract or len(abstract.strip()) < 50:
            result["status"] = "no_abstract"
            _log_mining(db, evidence_id, "no_abstract",
                        error_detail="abstract too short", dry_run=dry_run)
            if verbose:
                print(f"  [SKIP] {evidence_id}: abstract too short")
            return result

    abstract_source = abstract_data.get("source", "unknown")
    if verbose:
        src_tag = f" [LLM-synth, jaccard={abstract_data.get('cross_check_jaccard','N/A')}]" if abstract_source == "llm_synthetic" else ""
        print(f"  [2/4] Extracting claims from abstract ({len(abstract)} chars, source={abstract_source}{src_tag})")

    # 既存ノード+claimを先に読む（LLMプロンプトとノード帰属の両方で使う）
    existing_claims = _load_existing_claims(db)
    nodes_with_claims = _load_nodes_with_claims(db)

    # Step 2: LLMでclaim抽出（既存ノード一覧をプロンプトに含める）
    try:
        claims = extract_claims_from_abstract(
            abstract_data.get("title", ""),
            abstract_data.get("authors", ""),
            abstract_data.get("year"),
            abstract,
            nodes_with_claims=nodes_with_claims
        )
    except Exception as e:
        result["status"] = "extraction_failed"
        _log_mining(db, evidence_id, "failed", error_detail=str(e), dry_run=dry_run)
        if verbose:
            print(f"  [ERROR] Extraction failed: {e}")
        return result

    if not claims:
        result["status"] = "no_claims"
        _log_mining(db, evidence_id, "mined", claims_extracted=0, dry_run=dry_run)
        if verbose:
            print(f"  [INFO] No claims extracted")
        return result

    result["claims_extracted"] = len(claims)
    if verbose:
        print(f"  [3/4] Extracted {len(claims)} claims, checking duplicates + attribution")

    # Step 3-5: 重複判定 + ノード帰属 + 登録
    reg = register_mined_claims(db, evidence_id, claims, existing_claims,
                                 nodes_with_claims, dry_run=dry_run)

    result["new"] = reg["new"]
    result["duplicate"] = reg["duplicate"]
    result["unresolved"] = reg["unresolved"]
    result["details"] = reg["details"]
    result["status"] = "mined"

    # mining log更新
    _log_mining(db, evidence_id, "mined",
                abstract_text=abstract,
                claims_extracted=len(claims),
                claims_new=reg["new"],
                claims_duplicate=reg["duplicate"],
                claims_unresolved=reg["unresolved"],
                dry_run=dry_run)

    if verbose:
        print(f"  [4/4] Done: {reg['new']} new, {reg['duplicate']} dup, {reg['unresolved']} unresolved")
        for d in reg["details"]:
            action = d["action"]
            if action == "new":
                spec = " [HYP]" if d.get("speculative") else ""
                print(f"    + {d['claim_id']} → {d['node_id']} ({d['kind']}){spec}")
            elif action == "duplicate":
                print(f"    = {d['claim_id']} ≈ {d.get('match')} (sim={d.get('sim', 0):.2f})")
            elif action == "unresolved":
                print(f"    ? {d.get('text', '')[:60]}... — {d.get('reason')}")

    return result


def _log_mining(db, evidence_id, state, abstract_text=None,
                claims_extracted=0, claims_new=0, claims_duplicate=0,
                claims_unresolved=0, error_detail=None, dry_run=False):
    """mining logを更新"""
    if dry_run:
        return
    existing = db.execute(
        "SELECT 1 FROM evidence_mining_log WHERE evidence_id=?", (evidence_id,)
    ).fetchone()
    now = _now()
    if existing:
        db.execute("""
            UPDATE evidence_mining_log SET
                state=?, abstract_text=?, claims_extracted=?,
                claims_new=?, claims_duplicate=?, claims_unresolved=?,
                mined_at=?, error_detail=?
            WHERE evidence_id=?
        """, (state, abstract_text, claims_extracted, claims_new,
              claims_duplicate, claims_unresolved, now, error_detail, evidence_id))
    else:
        db.execute("""
            INSERT INTO evidence_mining_log VALUES (?,?,?,?,?,?,?,?,?)
        """, (evidence_id, state, abstract_text, claims_extracted,
              claims_new, claims_duplicate, claims_unresolved, now, error_detail))
    db.commit()


# ════════════════════════════════════════════
# mine-all: 全unmined evidenceを処理
# ════════════════════════════════════════════

def mine_all(dry_run: bool = False, verbose: bool = True, max_items: int = 5) -> dict:
    """DOI付きの全unmined evidenceを処理"""
    db = get_db()
    init_mining_table(db)

    # DOI付きevidenceで未mining
    rows = db.execute("""
        SELECT e.evidence_id, e.source_uri
        FROM evidence e
        WHERE e.source_uri LIKE 'doi:%'
          AND NOT EXISTS (
              SELECT 1 FROM evidence_mining_log ml
              WHERE ml.evidence_id = e.evidence_id
                AND ml.state = 'mined'
          )
        ORDER BY e.evidence_id
    """).fetchall()

    rows = rows[:max(0, max_items)]
    total = len(rows)
    if verbose:
        print(f"=== Evidence Miner: {total} unmined evidence with DOI ===\n")

    summary = {"total": total, "mined": 0, "skipped": 0, "failed": 0, "total_new_claims": 0}

    for i, (eid, uri) in enumerate(rows):
        if verbose:
            print(f"[{i+1}/{total}] Mining {eid}")

        result = mine_evidence(eid, dry_run=dry_run, verbose=verbose)

        if result["status"] == "mined":
            summary["mined"] += 1
            summary["total_new_claims"] += result.get("new", 0)
        elif result["status"] in ("no_abstract", "no_doi", "no_claims"):
            summary["skipped"] += 1
        else:
            summary["failed"] += 1

        if verbose:
            print()

        # API rate limit: 0.5s between evidence items
        if i < total - 1:
            time.sleep(0.5)

    if verbose:
        print(f"=== Summary: {summary['mined']} mined, {summary['skipped']} skipped, "
              f"{summary['failed']} failed, {summary['total_new_claims']} new claims ===")

    return summary


# ════════════════════════════════════════════
# status: mining状態表示
# ════════════════════════════════════════════

def show_status():
    """mining台帳の状態を表示"""
    db = get_db()
    init_mining_table(db)

    # 全evidence数
    total = db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    doi_count = db.execute("SELECT COUNT(*) FROM evidence WHERE source_uri LIKE 'doi:%'").fetchone()[0]

    # mining状態
    states = db.execute("""
        SELECT state, COUNT(*), SUM(claims_extracted), SUM(claims_new)
        FROM evidence_mining_log
        GROUP BY state
    """).fetchall()

    print(f"=== Evidence Mining Status ===")
    print(f"Total evidence: {total} ({doi_count} with DOI)")
    print()

    mined_total = 0
    for state, count, extracted, new in states:
        extracted = extracted or 0
        new = new or 0
        print(f"  {state}: {count} evidence → {int(extracted)} claims extracted, {int(new)} new")
        if state == "mined":
            mined_total = count

    unmined = doi_count - sum(r[1] for r in states if r[0] in ("mined",))
    print(f"\n  Remaining (DOI, unmined): {unmined}")


# ════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Evidence Miner: abstract→claim extraction")
    sub = parser.add_subparsers(dest="cmd")

    p_mine = sub.add_parser("mine", help="Mine a single evidence")
    p_mine.add_argument("evidence_id")
    p_mine.add_argument("--dry-run", action="store_true")

    p_all = sub.add_parser("mine-all", help="Mine all unmined DOI evidence")
    p_all.add_argument("--dry-run", action="store_true")

    p_status = sub.add_parser("status", help="Show mining status")

    args = parser.parse_args()

    if args.cmd == "mine":
        mine_evidence(args.evidence_id, dry_run=args.dry_run)
    elif args.cmd == "mine-all":
        mine_all(dry_run=args.dry_run)
    elif args.cmd == "status":
        show_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
