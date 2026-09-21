"""frontier_manager.py — 深掘り+拡大の自動探索制御器

Phase 6 EXPANDで呼ばれる。
- Deepening: 既存ノードのfacet欠落を掘る
- Expansion: 新ドメインへの跳躍（静的シード→動的生成）
- Safety: 品質劣化・発散・孤立の自動検出と停止

設計: 合意ベース（2026-09-19）
"""

import json
import math
import sqlite3
import time
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path

# ════════════════════════════════════════════
# データモデル
# ════════════════════════════════════════════

FACETS = ["mechanism", "moderator", "boundary", "measurement", "contradiction", "application"]

# facetの重み（塾用途: 誰に・どの条件で・どう使えるかを重視）
FACET_WEIGHTS = {
    "mechanism": 0.15, "moderator": 0.20, "boundary": 0.20,
    "measurement": 0.10, "contradiction": 0.15, "application": 0.20,
}

# 深掘り戦略テンプレート（LLMコール不要）
DEEPEN_TEMPLATES = {
    "mechanism":     "What are the causal mechanisms and neural/mathematical foundations of {concept}? Include competing explanatory theories with DOIs.",
    "moderator":     "How does the effect of {concept} vary by age, prior knowledge, task difficulty, and cultural context? Focus on empirical moderator analyses with DOIs.",
    "boundary":      "Under what conditions does {concept} fail, produce null effects, or backfire? Include failed replications and meta-analytic boundary conditions with DOIs.",
    "measurement":   "How is {concept} measured? What are the validity and reliability concerns? Include scale development and measurement invariance studies with DOIs.",
    "contradiction": "What replication failures, contradictory findings, or theoretical criticisms exist for {concept}? Include DOIs.",
    "application":   "What evidence exists for applying {concept} in K-12 education and tutoring contexts? Include intervention studies with effect sizes and DOIs.",
}

# 拡大シードリスト（用途アラインメント保証済み）
EXPANSION_SEEDS = [
    {"domain": "test_anxiety_and_stereotype_threat", "alignment": 0.95,
     "bridges": ["S-1700", "S-1100"], "search": "test anxiety intervention K-12 education",
     "why": "試験不安は塾生の最大の悩み。自己効力感と認知負荷に直結"},
    {"domain": "adolescent_brain_development", "alignment": 0.85,
     "bridges": ["S-1300", "S-2500"], "search": "adolescent prefrontal cortex development executive function",
     "why": "中高生の自制心・感情調整の発達段階を知ることで指導が変わる"},
    {"domain": "parental_involvement_in_education", "alignment": 0.85,
     "bridges": ["S-2700", "B-0700"], "search": "parental involvement academic achievement meta-analysis",
     "why": "保護者との連携は塾指導の重要要素"},
    {"domain": "procrastination_and_temporal_discounting", "alignment": 0.85,
     "bridges": ["B-0800", "S-2400"], "search": "procrastination temporal discounting academic performance",
     "why": "先延ばしは生徒の悩み相談の頻出テーマ"},
    {"domain": "peer_effects_in_classrooms", "alignment": 0.80,
     "bridges": ["S-2300", "S-2700"], "search": "peer effects classroom academic performance",
     "why": "クラスメイトの影響は学習環境の主要因子"},
    {"domain": "formative_assessment", "alignment": 0.80,
     "bridges": ["S-1800", "S-2800"], "search": "formative assessment feedback student learning",
     "why": "形成的評価はフィードバック理論とBloom分類を実践に翻訳する橋"},
    {"domain": "attention_and_mind_wandering", "alignment": 0.75,
     "bridges": ["S-1100", "S-0801"], "search": "mind wandering attention classroom learning",
     "why": "注意散漫は認知負荷とメタ認知に直結する教室の現実問題"},
    {"domain": "goal_setting_theory", "alignment": 0.75,
     "bridges": ["S-2100", "S-1800"], "search": "goal setting theory academic achievement Locke Latham",
     "why": "目標設定は期待価値理論とフィードバックを統合する実践的枠組み"},
    {"domain": "sleep_and_memory_consolidation", "alignment": 0.90,
     "bridges": ["S-1602", "S-1600"], "search": "sleep memory consolidation learning adolescent",
     "why": "睡眠と記憶の関係は分散学習・記憶固定化の生理的基盤"},
    {"domain": "habit_formation", "alignment": 0.80,
     "bridges": ["B-0700", "S-0800"], "search": "habit formation automaticity learning behavior change",
     "why": "学習習慣の形成はSDTと意図的練習の実践的出口"},
    {"domain": "help_seeking_behavior", "alignment": 0.90,
     "bridges": ["S-1700", "B-0700"], "search": "help seeking academic behavior self-efficacy autonomy",
     "why": "質問できない生徒は塾で最も支援が必要"},
    {"domain": "causal_inference_in_education", "alignment": 0.70,
     "bridges": ["S-1200", "S-0600"], "search": "causal inference education randomized controlled trial",
     "why": "指導法の効果検証の方法論的基盤"},
]


@dataclass
class FrontierConfig:
    max_tasks_per_cycle: int = 3
    max_expansion_per_cycle: int = 1
    max_new_nodes_per_cycle: int = 3
    min_candidate_score: float = 0.50
    node_cooldown_cycles: int = 10
    probe_verification_threshold: float = 0.50  # DOI検証通過率
    connectivity_min_bridges: int = 2  # 新ドメインの最低接続数
    practice_reachability_threshold: float = 0.80  # practice層への到達率


@dataclass
class FrontierReport:
    deepened: list = field(default_factory=list)
    expanded: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    paused: bool = False
    pause_reasons: list = field(default_factory=list)
    topics_generated: list = field(default_factory=list)
    llm_calls_used: int = 0


# ════════════════════════════════════════════
# DBスキーマ追加
# ════════════════════════════════════════════

def init_frontier_tables(db):
    """frontier_manager用のテーブルを追加"""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS frontier_domain (
            domain_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'candidate'
                CHECK(status IN ('candidate', 'trial', 'active', 'paused')),
            alignment_score REAL NOT NULL DEFAULT 0.0,
            bridges_json TEXT NOT NULL DEFAULT '[]',
            created_cycle INTEGER NOT NULL DEFAULT 0,
            last_cycle INTEGER NOT NULL DEFAULT 0,
            trial_calls_used INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS frontier_run (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id INTEGER NOT NULL,
            mode TEXT NOT NULL CHECK(mode IN ('deepen', 'expand', 'consolidate')),
            target_node_id TEXT,
            domain_id TEXT,
            facet TEXT,
            search_query TEXT NOT NULL,
            outcome TEXT NOT NULL DEFAULT 'pending'
                CHECK(outcome IN ('pending', 'success', 'no_yield', 'rejected', 'error')),
            new_claims INTEGER NOT NULL DEFAULT 0,
            new_nodes INTEGER NOT NULL DEFAULT 0,
            new_edges INTEGER NOT NULL DEFAULT 0,
            calls_used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS node_facet (
            node_id TEXT NOT NULL,
            facet TEXT NOT NULL CHECK(facet IN
                ('mechanism','moderator','boundary','measurement','contradiction','application')),
            coverage REAL NOT NULL DEFAULT 0.0
                CHECK(coverage >= 0.0 AND coverage <= 1.0),
            last_cycle INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (node_id, facet)
        );

        CREATE TABLE IF NOT EXISTS node_domain (
            node_id TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            PRIMARY KEY (node_id, domain_id)
        );
    """)
    db.commit()


# ════════════════════════════════════════════
# グラフ健全性メトリクス
# ════════════════════════════════════════════

@dataclass
class GraphHealth:
    total_nodes: int = 0
    total_edges: int = 0
    total_claims: int = 0
    total_evidence: int = 0
    edge_node_ratio: float = 0.0
    support_ratio: float = 0.0  # supported_claims / total_claims
    practice_reachability: float = 0.0
    quality_red: bool = False
    red_reasons: list = field(default_factory=list)


def compute_graph_health(db) -> GraphHealth:
    h = GraphHealth()
    h.total_nodes = db.execute("SELECT COUNT(*) FROM node WHERE status NOT IN ('superseded')").fetchone()[0]
    h.total_edges = db.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
    h.total_claims = db.execute("SELECT COUNT(*) FROM claim").fetchone()[0]
    h.total_evidence = db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]

    h.edge_node_ratio = h.total_edges / max(h.total_nodes, 1)

    # support ratio: claims that have at least one support_assessment
    supported = db.execute("""
        SELECT COUNT(DISTINCT c.claim_id) FROM claim c
        JOIN support_assessment sa ON sa.target_claim = c.claim_id
    """).fetchone()[0]
    h.support_ratio = supported / max(h.total_claims, 1)

    # practice reachability: nodes reachable from practice layer via edges (BFS)
    practice_nodes = set(r[0] for r in db.execute(
        "SELECT id FROM node WHERE layer='practice' AND status NOT IN ('superseded')").fetchall())
    if practice_nodes:
        reachable = set(practice_nodes)
        frontier = set(practice_nodes)
        edges = db.execute("SELECT from_node, to_node FROM edge").fetchall()
        adj = {}
        for f, t in edges:
            adj.setdefault(f, set()).add(t)
            adj.setdefault(t, set()).add(f)
        while frontier:
            next_f = set()
            for n in frontier:
                for nb in adj.get(n, set()):
                    if nb not in reachable:
                        reachable.add(nb)
                        next_f.add(nb)
            frontier = next_f
        h.practice_reachability = len(reachable) / max(h.total_nodes, 1)

    # quality red flags
    if h.edge_node_ratio < 1.0:
        h.quality_red = True
        h.red_reasons.append(f"edge/node ratio {h.edge_node_ratio:.2f} < 1.0")
    if h.support_ratio < 0.30:
        h.quality_red = True
        h.red_reasons.append(f"support ratio {h.support_ratio:.2f} < 0.30")

    return h


# ════════════════════════════════════════════
# 深掘り: ノードスコアリング
# ════════════════════════════════════════════

@dataclass
class NodePriority:
    node_id: str
    title: str
    layer: str
    score: float
    least_covered_facets: list
    degree: int = 0
    claim_count: int = 0
    evidence_count: int = 0
    practice_distance: int = 99


def rank_deepening_nodes(db, *, cycle_id: int = 0, limit: int = 10) -> list:
    """深掘り対象ノードをスコアリングして返す"""
    init_frontier_tables(db)

    nodes = db.execute("""
        SELECT n.id, json_extract(n.data, '$.title'), n.layer, n.status
        FROM node n WHERE n.status NOT IN ('superseded', 'blocked')
    """).fetchall()

    # 次数を計算
    degree_map = {}
    for row in db.execute("SELECT from_node, to_node FROM edge"):
        degree_map[row[0]] = degree_map.get(row[0], 0) + 1
        degree_map[row[1]] = degree_map.get(row[1], 0) + 1

    # claim数
    claim_map = {}
    for row in db.execute("SELECT node_id, COUNT(*) FROM claim GROUP BY node_id"):
        claim_map[row[0]] = row[1]

    # evidence数（support_assessment経由）
    evidence_map = {}
    for row in db.execute("""
        SELECT target_node, COUNT(DISTINCT evidence_id)
        FROM support_assessment GROUP BY target_node
    """):
        evidence_map[row[0]] = row[1]

    # practice層ノードへのBFS距離
    practice_ids = set(r[0] for r in db.execute(
        "SELECT id FROM node WHERE layer='practice'").fetchall())
    edges = db.execute("SELECT from_node, to_node FROM edge").fetchall()
    adj = {}
    for f, t in edges:
        adj.setdefault(f, set()).add(t)
        adj.setdefault(t, set()).add(f)

    dist_to_practice = {}
    queue = [(p, 0) for p in practice_ids]
    visited = set(practice_ids)
    for p in practice_ids:
        dist_to_practice[p] = 0
    while queue:
        curr, d = queue.pop(0)
        for nb in adj.get(curr, set()):
            if nb not in visited:
                visited.add(nb)
                dist_to_practice[nb] = d + 1
                queue.append((nb, d + 1))

    # facet充足度を取得
    facet_data = {}
    for row in db.execute("SELECT node_id, facet, coverage, attempts FROM node_facet"):
        facet_data.setdefault(row[0], {})[row[1]] = {"coverage": row[2], "attempts": row[3]}

    # 最近の深掘り回数
    recent_runs = {}
    for row in db.execute("""
        SELECT target_node_id, COUNT(*) FROM frontier_run
        WHERE mode='deepen' AND cycle_id > ? GROUP BY target_node_id
    """, (max(0, cycle_id - 5),)):
        recent_runs[row[0]] = row[1]

    results = []
    for nid, title, layer, status in nodes:
        # science層とfoundation層を優先（universe/practice/objectは深掘り対象外）
        if layer not in ("science", "foundation"):
            continue

        degree = degree_map.get(nid, 0)
        claims = claim_map.get(nid, 0)
        evidence = evidence_map.get(nid, 0)
        dist = dist_to_practice.get(nid, 99)

        # facet欠落度
        nf = facet_data.get(nid, {})
        gap = 1.0 - sum(
            FACET_WEIGHTS[f] * nf.get(f, {}).get("coverage", 0.0)
            for f in FACETS
        )

        # 用途アラインメント: practice層への距離の逆数
        alignment = 1.0 / (1.0 + dist)

        # 需要圧: claimは多いがevidenceが薄い
        demand = min(claims / max(evidence + 1, 1) / 3.0, 1.0)

        # 構造的重要度: 次数中心性
        centrality = min(degree / 8.0, 1.0)

        # 反復ペナルティ
        recent = recent_runs.get(nid, 0)
        penalty = min(1.0, recent / 2.0)

        # 総合スコア
        score = (
            0.30 * alignment
            + 0.25 * gap
            + 0.20 * demand
            + 0.15 * centrality
            + 0.10 * (1.0 - penalty)  # freshness
            - 0.15 * penalty
        )

        # 最もカバーが薄いfacet上位2つ
        facet_scores = [(f, nf.get(f, {}).get("coverage", 0.0)) for f in FACETS]
        facet_scores.sort(key=lambda x: x[1])
        least_covered = [f for f, c in facet_scores[:2] if c < 1.0]

        results.append(NodePriority(
            node_id=nid, title=title or "", layer=layer, score=score,
            least_covered_facets=least_covered, degree=degree,
            claim_count=claims, evidence_count=evidence,
            practice_distance=dist,
        ))

    results.sort(key=lambda x: x.score, reverse=True)
    return results[:limit]


# ════════════════════════════════════════════
# 深掘り: トピック生成（テンプレートベース、LLM不要）
# ════════════════════════════════════════════

def generate_deepening_topics(db, nodes: list, *, max_topics: int = 4) -> list:
    """深掘り対象ノードからknowledge_amplifierに投入するトピックを生成"""
    topics = []
    for np in nodes:
        if len(topics) >= max_topics:
            break
        for facet in np.least_covered_facets:
            if len(topics) >= max_topics:
                break
            template = DEEPEN_TEMPLATES.get(facet, DEEPEN_TEMPLATES["mechanism"])
            query = template.format(concept=np.title)
            topics.append({
                "mode": "deepen",
                "node_id": np.node_id,
                "facet": facet,
                "query": query,
                "title": np.title,
                "score": np.score,
            })
    return topics


# ════════════════════════════════════════════
# 拡大: シード選択
# ════════════════════════════════════════════

def pick_expansion_candidate(db, *, cycle_id: int = 0) -> dict | None:
    """未使用のシードから最も優先度の高い拡大候補を返す"""
    init_frontier_tables(db)

    # 既に登録済み or 棄却済みのドメインを除外
    used = set(r[0] for r in db.execute("SELECT domain_id FROM frontier_domain").fetchall())
    rejected = set(r[0] for r in db.execute(
        "SELECT DISTINCT domain_id FROM frontier_run WHERE outcome='rejected' AND domain_id IS NOT NULL"
    ).fetchall())
    used = used | rejected

    # 全ノードIDを取得（ブリッジ検証用）
    existing_nodes = set(r[0] for r in db.execute("SELECT id FROM node").fetchall())

    best = None
    best_score = -1

    for seed in EXPANSION_SEEDS:
        if seed["domain"] in used:
            continue

        # ブリッジノードが実在するか
        bridge_count = sum(1 for b in seed["bridges"] if b in existing_nodes)
        if bridge_count < 2:
            continue

        # スコア計算
        bridge_strength = min(bridge_count / 3.0, 1.0)
        score = 0.45 * seed["alignment"] + 0.35 * bridge_strength + 0.20 * 0.7  # feasibility proxy

        if score > best_score:
            best_score = score
            best = {**seed, "score": score, "bridge_count": bridge_count}

    return best


# ════════════════════════════════════════════
# 拡大: 試掘（probe）
# ════════════════════════════════════════════

def probe_expansion(candidate: dict, *, dry_run: bool = False) -> dict:
    """シード候補を試掘し、DOI検証通過率を測る"""
    from knowledge_amplifier import extract_claims, full_verify
    import time

    result = {"candidate": candidate["domain"], "verified": 0, "total": 0,
              "claims": [], "passed": False}

    try:
        claims_data = extract_claims(candidate["search"], llm="worker")
    except (ValueError, KeyError, json.JSONDecodeError, OSError, TimeoutError) as e:
        result["error"] = str(e)
        return result

    dois_seen = set()
    for claim in claims_data.get("claims", [])[:5]:
        for src in claim.get("sources", []):
            doi = src.get("doi")
            if not doi or doi in dois_seen:
                continue
            dois_seen.add(doi)
            result["total"] += 1

            if dry_run:
                continue

            try:
                v = full_verify(doi, claim.get("statement", ""))
                time.sleep(0.5)
                if v.get("final_grade") in ("A", "B", "C"):
                    result["verified"] += 1
                    result["claims"].append({
                        "statement": claim.get("statement", ""),
                        "doi": doi,
                        "grade": v["final_grade"],
                    })
            except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError, OSError, KeyError):
                pass  # DOI verification failure; skip this DOI

    if result["total"] > 0:
        rate = result["verified"] / result["total"]
        result["verification_rate"] = rate
        result["passed"] = rate >= 0.50
    else:
        result["verification_rate"] = 0.0

    return result


# ════════════════════════════════════════════
# 拡大: ドメイン登録
# ════════════════════════════════════════════

def register_trial_domain(db, candidate: dict, probe_result: dict, cycle_id: int):
    """試掘通過した候補をtrialドメインとして登録"""
    domain_id = candidate["domain"]
    db.execute("""
        INSERT OR IGNORE INTO frontier_domain
        (domain_id, canonical_name, status, alignment_score, bridges_json, created_cycle, last_cycle, notes)
        VALUES (?, ?, 'trial', ?, ?, ?, ?, ?)
    """, (
        domain_id, domain_id.replace("_", " ").title(),
        candidate.get("alignment", 0.0),
        json.dumps(candidate.get("bridges", [])),
        cycle_id, cycle_id,
        f"probe: {probe_result.get('verified', 0)}/{probe_result.get('total', 0)} verified"
    ))
    db.commit()


def register_probe_claims(db, candidate: dict, probe_result: dict, *, dry_run: bool = False):
    """試掘で検証されたclaimをevidenceとして登録"""
    if dry_run:
        return 0

    from mvp_store import add_evidence
    from knowledge_amplifier import register_to_store

    registered = 0
    for claim_info in probe_result.get("claims", []):
        doi = claim_info.get("doi")
        if not doi:
            continue
        eid = f"E-AUTO-{doi.replace('/', '-').replace('.', '_')[:30]}"
        try:
            existing = db.execute("SELECT evidence_id FROM evidence WHERE evidence_id=?", (eid,)).fetchone()
            if not existing:
                grade = claim_info.get("grade", "C")
                store_grade = "A" if grade == "A" else "B" if grade == "B" else "C"
                add_evidence(db, eid, "source_excerpt",
                             source_uri=f"https://doi.org/{doi}",
                             reliability_grade=store_grade)
                registered += 1
        except (sqlite3.Error, KeyError):
            pass  # evidence registration failure; skip this claim

    return registered


# ════════════════════════════════════════════
# 予算配分
# ════════════════════════════════════════════

def compute_budget_split(health: GraphHealth, db) -> dict:
    """グラフ健全性に基づいて深掘り/拡大/整合の配分を決定"""
    if health.quality_red:
        return {"deepen": 0.0, "expand": 0.0, "consolidate": 1.0}

    # 飽和度: 最近深掘り成果があったノードの割合
    try:
        total_science = db.execute(
            "SELECT COUNT(*) FROM node WHERE layer IN ('science','foundation') AND status != 'superseded'"
        ).fetchone()[0]
        saturated = db.execute("""
            SELECT COUNT(DISTINCT nf.node_id) FROM node_facet nf
            WHERE nf.coverage >= 0.8 AND nf.facet IN ('application','moderator','boundary')
        """).fetchone()[0]
        saturation = saturated / max(total_science, 1)
    except sqlite3.OperationalError:
        saturation = 0.0

    if health.support_ratio < 0.45 or health.edge_node_ratio < 1.5:
        return {"deepen": 0.7, "expand": 0.0, "consolidate": 0.3}

    if saturation > 0.5:
        return {"deepen": 0.3, "expand": 0.6, "consolidate": 0.1}

    # デフォルト: 深掘り優位（合意: 2:1）
    return {"deepen": 0.6, "expand": 0.3, "consolidate": 0.1}


# ════════════════════════════════════════════
# 安全装置
# ════════════════════════════════════════════

def check_safety(db, health: GraphHealth, config: FrontierConfig) -> list:
    """安全装置チェック。停止理由のリストを返す（空なら安全）"""
    reasons = []

    # practice到達率
    if health.practice_reachability < config.practice_reachability_threshold:
        reasons.append(f"practice reachability {health.practice_reachability:.2f} < {config.practice_reachability_threshold}")

    # 品質レッドフラグ
    if health.quality_red:
        reasons.extend(health.red_reasons)

    # 直近の深掘り成果率
    try:
        recent = db.execute("""
            SELECT COUNT(*), SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END)
            FROM frontier_run WHERE cycle_id > (
                SELECT COALESCE(MAX(cycle_id), 0) - 5 FROM frontier_run
            )
        """).fetchone()
        if recent and recent[0] >= 6 and recent[1] == 0:
            reasons.append("6+ consecutive frontier runs with no success")
    except sqlite3.OperationalError:
        pass

    return reasons


# ════════════════════════════════════════════
# メインエントリ: run_frontier
# ════════════════════════════════════════════

def run_frontier(db, *, cycle_id: int = 0, budget_remaining: int = 6,
                 dry_run: bool = False, verbose: bool = True,
                 config: FrontierConfig | None = None) -> FrontierReport:
    """Phase 6 EXPANDの本体"""
    if config is None:
        config = FrontierConfig()

    init_frontier_tables(db)
    report = FrontierReport()

    # 0. 健全性チェック
    health = compute_graph_health(db)
    if verbose:
        print(f"  Graph health: {health.total_nodes} nodes, "
              f"edge/node={health.edge_node_ratio:.2f}, "
              f"support={health.support_ratio:.2f}, "
              f"practice_reach={health.practice_reachability:.2f}")

    # 安全装置
    safety_reasons = check_safety(db, health, config)
    if safety_reasons:
        report.paused = True
        report.pause_reasons = safety_reasons
        if verbose:
            print(f"  [SAFETY] Paused: {safety_reasons}")
        return report

    # 1. 予算配分
    split = compute_budget_split(health, db)
    calls_deepen = max(1, int(budget_remaining * split["deepen"]))
    calls_expand = max(0, int(budget_remaining * split["expand"]))
    if verbose:
        print(f"  Budget split: deepen={calls_deepen}, expand={calls_expand}, "
              f"ratio={split}")

    # 2. 深掘り
    if calls_deepen > 0:
        if verbose:
            print("\n  [DEEPEN] Ranking nodes...")
        ranked = rank_deepening_nodes(db, cycle_id=cycle_id, limit=6)
        if verbose:
            for i, np in enumerate(ranked[:5]):
                print(f"    #{i+1} {np.node_id} ({np.title[:40]}) "
                      f"score={np.score:.3f} facets={np.least_covered_facets}")

        topics = generate_deepening_topics(db, ranked, max_topics=calls_deepen)
        for t in topics:
            report.topics_generated.append(t)
            if verbose:
                print(f"    → topic: [{t['facet']}] {t['title'][:50]}")

        # knowledge_amplifierに投入
        if not dry_run and topics:
            from knowledge_amplifier import extract_claims, full_verify, register_to_store
            for t in topics[:2]:  # 1サイクル最大2トピック深掘り
                try:
                    if verbose:
                        print(f"\n  [DEEPEN] Amplifying: {t['query'][:60]}...")
                    claims_data = extract_claims(t["query"], llm="worker")
                    report.llm_calls_used += 1

                    # DOI検証
                    verifications = {}
                    for claim in claims_data.get("claims", [])[:5]:
                        for src in claim.get("sources", []):
                            doi = src.get("doi")
                            if doi and doi not in verifications:
                                v = full_verify(doi, claim.get("statement", ""))
                                verifications[doi] = v
                                time.sleep(0.3)

                    # 登録
                    registered = register_to_store(claims_data, verifications, dry_run=False)
                    new_evidence = len(registered) if registered else 0

                    # facet更新
                    if new_evidence > 0:
                        _update_facet(db, t["node_id"], t["facet"],
                                      min(1.0, 0.5), cycle_id)

                    # 実行ログ
                    _log_run(db, cycle_id, "deepen", t["node_id"], None,
                             t["facet"], t["query"],
                             "success" if new_evidence > 0 else "no_yield",
                             new_claims=len(claims_data.get("claims", [])),
                             new_evidence=new_evidence, calls=1)

                    report.deepened.append({
                        "node_id": t["node_id"], "facet": t["facet"],
                        "new_evidence": new_evidence,
                    })
                    if verbose:
                        print(f"    Registered {new_evidence} new evidence items")

                except (ValueError, KeyError, json.JSONDecodeError, sqlite3.Error, OSError, TimeoutError) as e:
                    if verbose:
                        print(f"    [ERROR] {e}")
                    _log_run(db, cycle_id, "deepen", t["node_id"], None,
                             t["facet"], t["query"], "error", calls=1)
                    report.llm_calls_used += 1

    # 3. 拡大
    if calls_expand > 0 and not dry_run:
        if verbose:
            print("\n  [EXPAND] Picking expansion candidate...")
        candidate = pick_expansion_candidate(db, cycle_id=cycle_id)
        if candidate:
            if verbose:
                print(f"    Candidate: {candidate['domain']} "
                      f"(alignment={candidate['alignment']:.2f}, "
                      f"bridges={candidate['bridge_count']})")

            # 試掘
            if verbose:
                print(f"    Probing: {candidate['search']}...")
            probe = probe_expansion(candidate, dry_run=dry_run)
            report.llm_calls_used += 1

            if probe.get("passed"):
                if verbose:
                    print(f"    Probe PASSED: {probe['verified']}/{probe['total']} "
                          f"verified (rate={probe.get('verification_rate', 0):.2f})")

                # ドメイン登録
                register_trial_domain(db, candidate, probe, cycle_id)
                new_ev = register_probe_claims(db, candidate, probe, dry_run=dry_run)

                _log_run(db, cycle_id, "expand", None, candidate["domain"],
                         None, candidate["search"], "success",
                         new_claims=len(probe.get("claims", [])),
                         new_evidence=new_ev, calls=1)

                report.expanded.append({
                    "domain": candidate["domain"],
                    "verified": probe["verified"],
                    "total": probe["total"],
                    "new_evidence": new_ev,
                })
            else:
                if verbose:
                    reason = probe.get("error", f"rate={probe.get('verification_rate', 0):.2f}")
                    print(f"    Probe FAILED: {reason}")
                _log_run(db, cycle_id, "expand", None, candidate["domain"],
                         None, candidate["search"], "rejected", calls=1)
                report.rejected.append(candidate["domain"])
        else:
            if verbose:
                print("    No viable expansion candidate (all seeds used or bridges missing)")

    return report


# ════════════════════════════════════════════
# ヘルパー
# ════════════════════════════════════════════

def _update_facet(db, node_id: str, facet: str, coverage: float, cycle_id: int):
    """node_facetテーブルを更新"""
    existing = db.execute(
        "SELECT coverage, attempts FROM node_facet WHERE node_id=? AND facet=?",
        (node_id, facet)).fetchone()
    if existing:
        new_cov = max(existing[0], coverage)
        db.execute("""
            UPDATE node_facet SET coverage=?, last_cycle=?, attempts=attempts+1
            WHERE node_id=? AND facet=?
        """, (new_cov, cycle_id, node_id, facet))
    else:
        db.execute("""
            INSERT INTO node_facet (node_id, facet, coverage, last_cycle, attempts)
            VALUES (?, ?, ?, ?, 1)
        """, (node_id, facet, coverage, cycle_id))
    db.commit()


def _log_run(db, cycle_id, mode, target_node, domain_id, facet, query, outcome,
             new_claims=0, new_evidence=0, new_edges=0, calls=0):
    """frontier_runテーブルにログ"""
    from datetime import datetime, timezone
    db.execute("""
        INSERT INTO frontier_run
        (cycle_id, mode, target_node_id, domain_id, facet, search_query, outcome,
         new_claims, new_nodes, new_edges, calls_used, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cycle_id, mode, target_node, domain_id, facet, query, outcome,
          new_claims, new_evidence, new_edges, calls,
          datetime.now(timezone.utc).isoformat()))
    db.commit()


# ════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════

def main():
    import argparse
    import config  # noqa: F401

    parser = argparse.ArgumentParser(description="Frontier Manager: deepen + expand")
    parser.add_argument("command", choices=["run", "rank", "seeds", "health", "status"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cycle", type=int, default=0)
    parser.add_argument("--budget", type=int, default=6)
    args = parser.parse_args()

    from mvp_store import init_db
    db = init_db()
    init_frontier_tables(db)

    if args.command == "health":
        h = compute_graph_health(db)
        print(f"Nodes: {h.total_nodes}")
        print(f"Edges: {h.total_edges} (ratio: {h.edge_node_ratio:.2f})")
        print(f"Claims: {h.total_claims}")
        print(f"Evidence: {h.total_evidence}")
        print(f"Support ratio: {h.support_ratio:.2f}")
        print(f"Practice reachability: {h.practice_reachability:.2f}")
        if h.quality_red:
            print(f"[RED] {h.red_reasons}")

    elif args.command == "rank":
        ranked = rank_deepening_nodes(db, cycle_id=args.cycle, limit=10)
        print(f"Top {len(ranked)} deepening candidates:")
        for i, np in enumerate(ranked):
            print(f"  #{i+1} {np.node_id} score={np.score:.3f} "
                  f"d={np.practice_distance} deg={np.degree} "
                  f"facets={np.least_covered_facets} — {np.title[:50]}")

    elif args.command == "seeds":
        cand = pick_expansion_candidate(db, cycle_id=args.cycle)
        if cand:
            print(f"Next expansion: {cand['domain']}")
            print(f"  Alignment: {cand['alignment']:.2f}")
            print(f"  Bridges: {cand['bridges']} ({cand['bridge_count']} exist)")
            print(f"  Search: {cand['search']}")
            print(f"  Score: {cand['score']:.3f}")
        else:
            print("No viable expansion candidate")

    elif args.command == "status":
        domains = db.execute("SELECT * FROM frontier_domain ORDER BY created_cycle").fetchall()
        runs = db.execute("""
            SELECT mode, outcome, COUNT(*) FROM frontier_run GROUP BY mode, outcome
        """).fetchall()
        print(f"Domains: {len(domains)}")
        for d in domains:
            print(f"  {d[0]}: {d[2]} (alignment={d[3]:.2f})")
        print(f"\nRun history:")
        for mode, outcome, count in runs:
            print(f"  {mode}/{outcome}: {count}")

    elif args.command == "run":
        report = run_frontier(db, cycle_id=args.cycle, budget_remaining=args.budget,
                              dry_run=args.dry_run, verbose=True)
        print(f"\n=== Frontier Report ===")
        print(f"  Deepened: {len(report.deepened)}")
        print(f"  Expanded: {len(report.expanded)}")
        print(f"  Rejected: {len(report.rejected)}")
        print(f"  LLM calls: {report.llm_calls_used}")
        if report.paused:
            print(f"  PAUSED: {report.pause_reasons}")


if __name__ == "__main__":
    main()
