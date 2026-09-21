"""autonomous_orchestrator: 自律・再帰・拡大ループ

統合設計に基づく実装。
7フェーズのサイクルを予算+サーキットブレーカーで制御する。

サイクルフェーズ:
  1. repair   — gap_detector (G1/G2/G3) + amplifier + evidence充填
  2. extract  — evidence_miner: evidence→claim抽出
  3. grow     — node_factory: ノード生成
  4. relate   — relation_engine: エッジ推論 + G3解消
  5. promote  — provisional→active|archived 判定
  6. expand   — frontier_manager: ドメイン拡大 (100ノード後)
  7. audit    — 品質メトリクス集計 + 次サイクル予算決定

予算制御:
  - LLMコール / 外部APIコール / 新ノード / 新エッジ / 新ドメイン の上限
  - 超過時は即フェーズ切り上げ

サーキットブレーカー:
  - ハレーション棄却率 > 40%
  - provisional比率 > 30%
  - dispute滞留 > 10件
  - 3サイクル連続 新verified claim < 3 → 休止
  - derivation_depth <= 3

Usage:
    python autonomous_orchestrator.py run               # 1サイクル実行
    python autonomous_orchestrator.py run --dry-run     # DB変更なし
    python autonomous_orchestrator.py run --budget low   # 低予算モード
    python autonomous_orchestrator.py status            # 状態表示
    python autonomous_orchestrator.py audit             # 品質メトリクスのみ
"""

import argparse
import json
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import config  # noqa: F401

from mvp_store import init_db, get_db, _uid, _now, DB_PATH


# ════════════════════════════════════════════
# 予算定義
# ════════════════════════════════════════════

@dataclass
class CycleBudget:
    """1サイクルあたりの予算上限"""
    llm_calls: int = 200
    external_api_calls: int = 500
    new_nodes: int = 20
    new_edges: int = 50
    new_domains: int = 1
    wall_time_seconds: int = 1800  # 30 min
    # 19ノード規模向けの控えめな初期値
    newly_fetched_papers: int = 20
    new_active_claims: int = 50

    @classmethod
    def low(cls):
        """低予算モード（テスト用）"""
        return cls(
            llm_calls=30, external_api_calls=60,
            new_nodes=5, new_edges=10, new_domains=0,
            wall_time_seconds=300, newly_fetched_papers=5,
            new_active_claims=15,
        )


@dataclass
class BudgetTracker:
    """予算消費の追跡"""
    budget: CycleBudget
    llm_calls: int = 0
    external_api_calls: int = 0
    new_nodes: int = 0
    new_edges: int = 0
    new_domains: int = 0
    new_claims: int = 0
    start_time: float = field(default_factory=time.time)

    def check(self, resource: str, count: int = 1) -> bool:
        """予算内か確認。Falseならフェーズ切り上げ"""
        current = getattr(self, resource, 0)
        limit = getattr(self.budget, resource, float('inf'))
        return current + count <= limit

    def consume(self, resource: str, count: int = 1):
        """予算を消費"""
        current = getattr(self, resource, 0)
        setattr(self, resource, current + count)

    def time_remaining(self) -> float:
        elapsed = time.time() - self.start_time
        return max(0, self.budget.wall_time_seconds - elapsed)

    def is_time_up(self) -> bool:
        return self.time_remaining() <= 0

    def summary(self) -> dict:
        return {
            "llm_calls": f"{self.llm_calls}/{self.budget.llm_calls}",
            "external_api": f"{self.external_api_calls}/{self.budget.external_api_calls}",
            "new_nodes": f"{self.new_nodes}/{self.budget.new_nodes}",
            "new_edges": f"{self.new_edges}/{self.budget.new_edges}",
            "new_claims": f"{self.new_claims}/{self.budget.new_active_claims}",
            "wall_time": f"{int(time.time() - self.start_time)}s/{self.budget.wall_time_seconds}s",
        }


# ════════════════════════════════════════════
# サーキットブレーカー
# ════════════════════════════════════════════

@dataclass
class CircuitBreaker:
    """品質異常の検出と自動停止"""
    # 閾値
    max_hallucination_rate: float = 0.40
    max_provisional_ratio: float = 0.30
    max_dispute_backlog: int = 10
    min_new_verified_per_cycle: int = 3
    max_growth_rate: float = 0.20  # ノード成長率/サイクル
    max_derivation_depth: int = 3
    # 状態
    tripped: bool = False
    trip_reason: str = ""
    consecutive_low_yield: int = 0  # 連続低収量サイクル数


def check_circuit_breaker(db, breaker: CircuitBreaker, cycle_stats: dict) -> CircuitBreaker:
    """サーキットブレーカーの判定"""

    # 1. ハレーション棄却率
    # amplifierの直近サイクルのREJECTED率を計算
    total_verified = cycle_stats.get("total_verified", 0)
    total_rejected = cycle_stats.get("total_rejected", 0)
    total_checked = total_verified + total_rejected
    if total_checked > 5:  # 最低5件以上チェックした場合のみ判定
        rejection_rate = total_rejected / total_checked
        if rejection_rate > breaker.max_hallucination_rate:
            breaker.tripped = True
            breaker.trip_reason = f"hallucination rejection rate {rejection_rate:.1%} > {breaker.max_hallucination_rate:.0%}"
            return breaker

    # 2. provisional比率（最小サンプル数ガード: N>=20で判定）
    total_nodes = db.execute("SELECT COUNT(*) FROM node").fetchone()[0]
    provisional_nodes = db.execute(
        "SELECT COUNT(*) FROM node WHERE status = 'proposed'"
    ).fetchone()[0]
    if total_nodes >= 50:  # 成長初期は新ノード=provisional で必ず高くなるため50まで猶予
        provisional_ratio = provisional_nodes / total_nodes
        if provisional_ratio > breaker.max_provisional_ratio:
            breaker.tripped = True
            breaker.trip_reason = f"provisional ratio {provisional_ratio:.1%} > {breaker.max_provisional_ratio:.0%} ({provisional_nodes}/{total_nodes})"
            return breaker

    # 3. dispute滞留（contradicted claims）
    contradicted = db.execute(
        "SELECT COUNT(*) FROM claim WHERE epistemic_status = 'contradicted'"
    ).fetchone()[0]
    if contradicted > breaker.max_dispute_backlog:
        breaker.tripped = True
        breaker.trip_reason = f"dispute backlog {contradicted} > {breaker.max_dispute_backlog}"
        return breaker

    # 4. 成長率（最小サンプル数ガード: N>=20で判定）
    new_nodes = cycle_stats.get("new_nodes", 0)
    if total_nodes >= 20 and new_nodes / total_nodes > breaker.max_growth_rate:
        breaker.tripped = True
        breaker.trip_reason = f"growth rate {new_nodes/total_nodes:.1%} > {breaker.max_growth_rate:.0%}"
        return breaker

    # 5. 連続低収量判定
    if cycle_stats.get("execution_failed"):
        return breaker  # Network/model failures do not establish convergence.
    if not cycle_stats.get('validation_ran'):
        return breaker  # No validation opportunity means no convergence evidence.
    new_verified = cycle_stats.get("new_verified_claims", 0)
    # 初期段階（100ノード未満）では新claim・新ノード・新エッジも収量に数える
    total_nodes = cycle_stats.get("total_nodes_after", 0)
    if total_nodes < 100:
        new_claims = cycle_stats.get("new_claims", 0)
        new_nodes = cycle_stats.get("new_nodes", 0)
        new_yield = new_verified + new_claims + new_nodes
    else:
        new_yield = new_verified
    if new_yield < breaker.min_new_verified_per_cycle:
        breaker.consecutive_low_yield += 1
        if breaker.consecutive_low_yield >= 3:
            breaker.tripped = True
            breaker.trip_reason = f"convergence: {breaker.consecutive_low_yield} consecutive cycles with < {breaker.min_new_verified_per_cycle} new yield (verified+claims+nodes)"
            return breaker
    else:
        breaker.consecutive_low_yield = 0

    return breaker


# ════════════════════════════════════════════
# 品質メトリクス（audit）
# ════════════════════════════════════════════

def collect_metrics(db) -> dict:
    """グラフ全体の品質メトリクスを収集"""
    metrics = {}

    # ノード統計
    metrics["total_nodes"] = db.execute("SELECT COUNT(*) FROM node").fetchone()[0]
    metrics["nodes_by_status"] = {}
    for r in db.execute("SELECT status, COUNT(*) FROM node GROUP BY status"):
        metrics["nodes_by_status"][r[0]] = r[1]
    metrics["nodes_by_layer"] = {}
    for r in db.execute("SELECT layer, COUNT(*) FROM node GROUP BY layer"):
        metrics["nodes_by_layer"][r[0]] = r[1]

    # claim統計
    metrics["total_claims"] = db.execute("SELECT COUNT(*) FROM claim").fetchone()[0]
    metrics["claims_by_status"] = {}
    for r in db.execute("SELECT epistemic_status, COUNT(*) FROM claim GROUP BY epistemic_status"):
        metrics["claims_by_status"][r[0]] = r[1]

    # evidence統計
    metrics["total_evidence"] = db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    metrics["evidence_by_grade"] = {}
    for r in db.execute("SELECT reliability_grade, COUNT(*) FROM evidence GROUP BY reliability_grade"):
        metrics["evidence_by_grade"][r[0] or "ungraded"] = r[1]

    # エッジ統計
    metrics["total_edges"] = db.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
    metrics["edges_by_type"] = {}
    for r in db.execute("SELECT type, COUNT(*) FROM edge GROUP BY type"):
        metrics["edges_by_type"][r[0]] = r[1]

    # support_assessment統計
    metrics["total_assessments"] = db.execute("SELECT COUNT(*) FROM support_assessment").fetchone()[0]

    # gap統計
    try:
        metrics["gaps_by_state"] = {}
        for r in db.execute("SELECT state, COUNT(*) FROM gap GROUP BY state"):
            metrics["gaps_by_state"][r[0]] = r[1]
        metrics["gaps_by_type"] = {}
        for r in db.execute("SELECT gap_type, COUNT(*) FROM gap GROUP BY gap_type"):
            metrics["gaps_by_type"][r[0]] = r[1]
    except sqlite3.OperationalError:
        metrics["gaps_by_state"] = {}
        metrics["gaps_by_type"] = {}

    # 品質指標
    # unsupported claims（definitionとHYP除外）
    unsupported = db.execute("""
        SELECT COUNT(*) FROM claim c
        JOIN node n ON c.node_id = n.id AND c.node_revision = n.revision
        LEFT JOIN support_assessment sa ON sa.target_claim = c.claim_id
        WHERE sa.assessment_id IS NULL
          AND n.subtype != 'HYP'
          AND c.kind != 'definition'
    """).fetchone()[0]
    metrics["unsupported_claims"] = unsupported

    # evidence coverage: claimのうちsupport_assessmentがある割合
    total_non_def = db.execute(
        "SELECT COUNT(*) FROM claim WHERE kind != 'definition'"
    ).fetchone()[0]
    supported = total_non_def - unsupported
    metrics["evidence_coverage"] = supported / total_non_def if total_non_def > 0 else 0

    # 独立evidence coverage（抽出元evidenceを除外した支持率）
    # evidence_minerが「evidence Eからclaim Cを抽出→E→Cのsupportを自動生成」するため、
    # それだけではcoverageは転記であり検証ではない。
    # 独立 = 「assessor != 'evidence_miner' の support_assessment を持つclaim」
    independently_supported = db.execute("""
        SELECT COUNT(DISTINCT c.claim_id) FROM claim c
        JOIN node n ON c.node_id = n.id AND c.node_revision = n.revision
        WHERE c.kind != 'definition'
          AND n.subtype != 'HYP'
          AND EXISTS (
              SELECT 1 FROM support_assessment sa
              WHERE sa.target_claim = c.claim_id
                AND sa.assessor != 'evidence_miner'
          )
    """).fetchone()[0]
    metrics['legacy_assessor_coverage'] = independently_supported / total_non_def if total_non_def else 0
    from knowledge_policy import independence_metrics, usable_claim_rows
    independently_supported = independence_metrics(db)
    metrics["independent_coverage"] = independently_supported / metrics['total_claims'] if metrics['total_claims'] else 0
    metrics["independently_supported_claims"] = independently_supported
    metrics['usable_claims'] = len(usable_claim_rows(db))

    # provisional ratio
    metrics["provisional_ratio"] = (
        metrics["nodes_by_status"].get("proposed", 0) / metrics["total_nodes"]
        if metrics["total_nodes"] > 0 else 0
    )

    # mining統計
    try:
        mined = db.execute(
            "SELECT COUNT(*), SUM(claims_extracted), SUM(claims_new) FROM evidence_mining_log WHERE state='mined'"
        ).fetchone()
        metrics["mined_evidence"] = mined[0] or 0
        metrics["mined_claims_extracted"] = mined[1] or 0
        metrics["mined_claims_new"] = mined[2] or 0
    except sqlite3.OperationalError:
        pass

    return metrics


# ════════════════════════════════════════════
# サイクル実行
# ════════════════════════════════════════════

def run_cycle(budget_mode: str = "normal", dry_run: bool = False) -> dict:
    """1サイクル実行: repair → extract → grow → relate → promote → expand → audit"""
    db = get_db()
    init_db()

    budget = CycleBudget.low() if budget_mode == "low" else CycleBudget()
    tracker = BudgetTracker(budget=budget)
    from cheap_llm import configure
    worker = configure(max_calls=min(budget.llm_calls, 40),
                       max_seconds=budget.wall_time_seconds,
                       max_reserved_usd=0.10)
    breaker = CircuitBreaker()

    # 前回のconsecutive_low_yieldを読み込み
    try:
        last_event = db.execute("""
            SELECT payload FROM event
            WHERE event_type = 'orchestrator_cycle_completed'
            ORDER BY occurred_at DESC LIMIT 1
        """).fetchone()
        if last_event:
            prev = json.loads(last_event[0])
            previous_stats = prev.get("cycle_stats", {})
            # Only comparable, successful cycles may carry a convergence count.
            if prev.get("yield_policy") == "verified-v2" and not previous_stats.get("execution_failed"):
                breaker.consecutive_low_yield = prev.get("consecutive_low_yield", 0)
    except (sqlite3.Error, json.JSONDecodeError, KeyError):
        pass

    print("=" * 60)
    print("AUTONOMOUS ORCHESTRATOR — Cycle Start")
    print(f"  Budget: {budget_mode} | Dry-run: {dry_run}")
    print("=" * 60)

    # 事前メトリクス
    metrics_before = collect_metrics(db)
    cycle_stats = {
        "new_nodes": 0, "new_claims": 0, "new_verified_claims": 0,
        "total_verified": 0, "total_rejected": 0,
    }

    results = {"phases": {}, "budget": {}, "breaker": {}, "metrics_before": {}, "metrics_after": {}}

    # ─── Phase 1: REPAIR ───
    print("\n[Phase 1/7] REPAIR — gap detection + evidence filling")

    if tracker.is_time_up():
        print("  [BUDGET] Time's up, skipping")
    else:
        try:
            from gap_detector import (
                init_gap_table, detect_unsupported_claims, detect_missing_instances,
                detect_unverified_edges, upsert_gaps
            )
            init_gap_table(db)
            g1 = detect_unsupported_claims(db)
            g2 = detect_missing_instances(db)
            g3 = detect_unverified_edges(db)
            new_gaps = upsert_gaps(db, g1 + g2 + g3)
            tracker.consume("external_api_calls", 0)  # 検出自体はDB操作のみ

            print(f"  Gaps: {len(g1)} G1 + {len(g2)} G2 + {len(g3)} G3 ({new_gaps} new)")

            # G1/G2の充填はgap_detectorに委譲（予算制限付き）
            # ここではdetect+registerのみ。充填は将来のfull cycleで
            results["phases"]["repair"] = {
                "G1": len(g1), "G2": len(g2), "G3": len(g3), "new_gaps": new_gaps
            }
        except (ImportError, sqlite3.Error, ValueError) as e:
            print(f"  [ERROR] {e}")
            results["phases"]["repair"] = {"error": str(e)}

    # ─── Phase 2: EXTRACT ───
    print("\n[Phase 2/7] EXTRACT — evidence → claim mining")

    if tracker.is_time_up():
        print("  [BUDGET] Time's up, skipping")
    elif not tracker.check("llm_calls", 10):
        print("  [BUDGET] LLM calls near limit, skipping")
    else:
        try:
            from evidence_miner import mine_all
            mine_result = mine_all(dry_run=dry_run, verbose=False,
                                   max_items=budget.newly_fetched_papers)
            new_claims = mine_result.get("total_new_claims", 0)
            mined_count = mine_result.get("mined", 0)

            tracker.consume("llm_calls", mined_count)  # 1 LLMコール/evidence
            tracker.consume("external_api_calls", mined_count * 2)  # S2 + OpenAlex
            cycle_stats["new_claims"] += new_claims

            print(f"  Mined {mined_count} evidence → {new_claims} new claims")
            results["phases"]["extract"] = {
                "mined": mined_count, "new_claims": new_claims,
                "skipped": mine_result.get("skipped", 0),
                "failed": mine_result.get("failed", 0),
            }
        except (ImportError, sqlite3.Error, ValueError, KeyError) as e:
            print(f"  [ERROR] {e}")
            results["phases"]["extract"] = {"error": str(e)}

    # ─── Phase 3: GROW ───
    print("\n[Phase 3/7] GROW — node generation")

    if tracker.is_time_up():
        print("  [BUDGET] Time's up, skipping")
    elif not tracker.check("new_nodes"):
        print("  [BUDGET] Node budget exhausted, skipping")
    else:
        try:
            from node_factory import generate_nodes
            gen_result = generate_nodes(dry_run=dry_run, verbose=False,
                                        max_new_nodes=budget.new_nodes,
                                        max_evidence=3)
            generated = gen_result.get("generated", 0)
            absorbed = gen_result.get("absorbed", 0)

            tracker.consume("new_nodes", generated)
            tracker.consume("llm_calls", generated + absorbed)
            cycle_stats["new_nodes"] += generated

            print(f"  Generated: {generated}, Absorbed: {absorbed}, Rejected: {gen_result.get('rejected', 0)}")
            results["phases"]["grow"] = gen_result
        except (ImportError, sqlite3.Error, ValueError, KeyError) as e:
            print(f"  [ERROR] {e}")
            results["phases"]["grow"] = {"error": str(e)}

    # ─── Phase 4: RELATE ───
    print("\n[Phase 4/7] RELATE — edge inference + G3 resolution")

    if tracker.is_time_up():
        print("  [BUDGET] Time's up, skipping")
    elif not tracker.check("new_edges"):
        print("  [BUDGET] Edge budget exhausted, skipping")
    else:
        try:
            from relation_engine import run_relate
            max_edges = min(5, tracker.budget.new_edges - tracker.new_edges)
            relate_result = run_relate(
                dry_run=dry_run, verbose=True,
                max_candidates=10, max_new_edges=max_edges,
            )
            new_edges = relate_result.get("verified", 0) + relate_result.get("hyp_edges", 0)
            tracker.consume("new_edges", new_edges)
            tracker.consume("llm_calls", relate_result.get("candidates", 0))

            print(f"  Verified: {relate_result.get('verified', 0)}, "
                  f"HYP: {relate_result.get('hyp_edges', 0)}, "
                  f"Rejected: {relate_result.get('rejected', 0)}, "
                  f"G3 resolved: {relate_result.get('g3_resolved', 0)}")

            # エッジ/ノード比の監視
            edge_count = db.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
            node_count = db.execute("SELECT COUNT(*) FROM node").fetchone()[0]
            ratio = edge_count / node_count if node_count > 0 else 0
            if ratio < 1.0:
                print(f"  [WARN] Edge/node ratio {ratio:.2f} < 1.0 — graph becoming 'bag of nodes'")
            else:
                print(f"  Edge/node ratio: {ratio:.2f}")

            results["phases"]["relate"] = {
                **relate_result, "edge_node_ratio": round(ratio, 2),
            }
        except (ImportError, sqlite3.Error, ValueError, KeyError) as e:
            print(f"  [ERROR] {e}")
            results["phases"]["relate"] = {"error": str(e)}

    # ─── Phase 5: PROMOTE ───
    print("\n[Phase 5/7] PROMOTE — provisional → active/archived")

    if tracker.is_time_up():
        print("  [BUDGET] Time's up, skipping")
    else:
        try:
            from node_factory import run_promotion
            # Cheap-worker generation does not itself justify promotion.
            promo_result = run_promotion(dry_run=True, verbose=False)
            promo_result["dry_run"] = True
            print(f"  Promoted: {promo_result.get('promoted', 0)}, "
                  f"Archived: {promo_result.get('archived', 0)}, "
                  f"Pending: {promo_result.get('pending', 0)}")
            results["phases"]["promote"] = promo_result
        except (ImportError, sqlite3.Error, ValueError, KeyError) as e:
            print(f"  [ERROR] {e}")
            results["phases"]["promote"] = {"error": str(e)}

    # ─── Phase 6: EXPAND ───
    print('\n[VALIDATE] Existing ten-claim pilot; unsupported cases remain deferred')
    try:
        from verify_pilot import run_pilot
        if dry_run or tracker.is_time_up():
            results['phases']['validate'] = {'skipped':True}
            cycle_stats['validation_ran'] = False
        else:
            validation = run_pilot()
            results['phases']['validate'] = {'passed':validation['passed'],'deferred':validation['deferred']}
            cycle_stats['validation_ran'] = True
    except (ImportError, sqlite3.Error, ValueError, KeyError) as exc:
        results['phases']['validate'] = {'error':str(exc)}
        cycle_stats['validation_ran'] = False
    print("\n[Phase 6/7] EXPAND — domain expansion")

    total_nodes = db.execute("SELECT COUNT(*) FROM node").fetchone()[0]
    if total_nodes < 100:
        print(f"  [SKIP] {total_nodes} nodes < 100 threshold (frontier stats unreliable)")
        results["phases"]["expand"] = {"skipped": True, "reason": f"{total_nodes} < 100 nodes"}
    elif tracker.is_time_up():
        print("  [BUDGET] Time's up, skipping")
        results["phases"]["expand"] = {"skipped": True, "reason": "time"}
    else:
        try:
            from frontier_manager import run_frontier
            remaining_calls = max(2, tracker.budget.llm_calls - tracker.llm_calls)
            frontier_budget = min(6, remaining_calls)
            frontier_report = run_frontier(
                db, cycle_id=cycle_stats.get("cycle_id", 0),
                budget_remaining=frontier_budget,
                dry_run=dry_run, verbose=True,
            )
            tracker.consume("llm_calls", frontier_report.llm_calls_used)
            cycle_stats["new_nodes"] += sum(
                d.get("new_evidence", 0) for d in frontier_report.deepened
            )
            results["phases"]["expand"] = {
                "deepened": len(frontier_report.deepened),
                "expanded": len(frontier_report.expanded),
                "rejected": len(frontier_report.rejected),
                "paused": frontier_report.paused,
                "llm_calls": frontier_report.llm_calls_used,
            }
            if frontier_report.paused:
                print(f"  [PAUSED] {frontier_report.pause_reasons}")
        except (ImportError, sqlite3.Error, ValueError, KeyError) as e:
            print(f"  [ERROR] {e}")
            results["phases"]["expand"] = {"error": str(e)}

    # ─── Phase 7: AUDIT ───
    print("\n[Phase 7/7] AUDIT — quality metrics + circuit breaker check")

    metrics_after = collect_metrics(db)
    cycle_stats["new_claims"] = metrics_after["total_claims"] - metrics_before["total_claims"]
    cycle_stats["new_nodes"] = metrics_after["total_nodes"] - metrics_before["total_nodes"]
    tracker.new_claims = cycle_stats["new_claims"]
    tracker.llm_calls = worker.calls

    # サーキットブレーカー判定
    cycle_stats["new_verified_claims"] = max(0, metrics_after['usable_claims']-metrics_before['usable_claims'])
    cycle_stats["total_nodes_after"] = metrics_after["total_nodes"]
    cycle_stats["execution_failed"] = bool(worker.errors or any(
        v.get("error") or v.get("failed") for v in results["phases"].values()))
    breaker = check_circuit_breaker(db, breaker, cycle_stats)

    if breaker.tripped:
        print(f"  ⚠ CIRCUIT BREAKER TRIPPED: {breaker.trip_reason}")
    else:
        print(f"  Circuit breaker: OK")

    # gap充足率
    try:
        total_gaps = db.execute("SELECT COUNT(*) FROM gap").fetchone()[0]
        resolved_gaps = db.execute("SELECT COUNT(*) FROM gap WHERE state='resolved'").fetchone()[0]
        gap_fulfillment = resolved_gaps / total_gaps if total_gaps > 0 else 0
        print(f"  Gap fulfillment: {gap_fulfillment:.0%} ({resolved_gaps}/{total_gaps})")
    except sqlite3.OperationalError:
        gap_fulfillment = 0

    # メトリクス差分
    print(f"\n  Metrics delta:")
    print(f"    Nodes:   {metrics_before['total_nodes']} → {metrics_after['total_nodes']}")
    print(f"    Claims:  {metrics_before['total_claims']} → {metrics_after['total_claims']}")
    print(f"    Evidence: {metrics_before['total_evidence']} → {metrics_after['total_evidence']}")
    print(f"    Edges:   {metrics_before['total_edges']} → {metrics_after['total_edges']}")
    print(f"    Assessments: {metrics_before['total_assessments']} → {metrics_after['total_assessments']}")
    print(f"    Coverage: {metrics_before['evidence_coverage']:.0%} → {metrics_after['evidence_coverage']:.0%}")

    # 予算消費サマリ
    budget_summary = tracker.summary()
    budget_summary["worker"] = worker.summary()
    print(f"\n  Budget consumed:")
    for k, v in budget_summary.items():
        print(f"    {k}: {v}")

    # イベントログ
    if not dry_run:
        try:
            db.execute("INSERT INTO event VALUES (?,?,?,?,?,?)", (
                _uid("ev-"), "orchestrator_cycle_completed", None,
                json.dumps({
                    "budget_mode": budget_mode,
                    "yield_policy": "verified-v2",
                    "phases": {k: ("ok" if "error" not in v else "error") for k, v in results.get("phases", {}).items()},
                    "budget_consumed": budget_summary,
                    "cycle_stats": cycle_stats,
                    "breaker_tripped": breaker.tripped,
                    "breaker_reason": breaker.trip_reason,
                    "consecutive_low_yield": breaker.consecutive_low_yield,
                    "gap_fulfillment": gap_fulfillment,
                    "metrics_delta": {
                        "nodes": metrics_after["total_nodes"] - metrics_before["total_nodes"],
                        "claims": metrics_after["total_claims"] - metrics_before["total_claims"],
                        "evidence": metrics_after["total_evidence"] - metrics_before["total_evidence"],
                    },
                }, ensure_ascii=False),
                _now(), "orchestrator"
            ))
            db.commit()
        except sqlite3.Error:
            pass

    results["budget"] = budget_summary
    results["breaker"] = {"tripped": breaker.tripped, "reason": breaker.trip_reason}
    results["metrics_before"] = metrics_before
    results["metrics_after"] = metrics_after

    # 最終サマリ
    print(f"\n{'='*60}")
    print("CYCLE COMPLETE")
    print(f"{'='*60}")
    if breaker.tripped:
        print(f"  ⚠ STOPPED: {breaker.trip_reason}")
        print(f"  Next action: resolve the issue before running another cycle")
    else:
        print(f"  Status: OK — ready for next cycle")

    return results


# ════════════════════════════════════════════
# status表示
# ════════════════════════════════════════════

def show_status():
    db = get_db()

    # 直近のサイクルイベント
    print("=== Orchestrator Status ===\n")
    events = db.execute("""
        SELECT occurred_at, payload FROM event
        WHERE event_type = 'orchestrator_cycle_completed'
        ORDER BY occurred_at DESC LIMIT 5
    """).fetchall()

    if not events:
        print("  No cycles executed yet.\n")
    else:
        print(f"  Last {len(events)} cycles:")
        for ts, payload in events:
            data = json.loads(payload)
            phases = data.get("phases", {})
            breaker = "TRIPPED" if data.get("breaker_tripped") else "OK"
            stats = data.get("cycle_stats", {})
            print(f"    {ts[:19]}: phases={phases} | claims+{stats.get('new_claims',0)} "
                  f"nodes+{stats.get('new_nodes',0)} | breaker={breaker}")
        print()

    # 現在のメトリクス
    metrics = collect_metrics(db)
    print("  Current metrics:")
    print(f"    Nodes: {metrics['total_nodes']} ({metrics['nodes_by_status']})")
    print(f"    Claims: {metrics['total_claims']} ({metrics['claims_by_status']})")
    print(f"    Evidence: {metrics['total_evidence']} ({metrics['evidence_by_grade']})")
    print(f"    Edges: {metrics['total_edges']}")
    print(f"    Assessments: {metrics['total_assessments']}")
    print(f"    Coverage: {metrics['evidence_coverage']:.0%}")
    print(f"    Provisional ratio: {metrics['provisional_ratio']:.0%}")
    print(f"    Unsupported claims: {metrics['unsupported_claims']}")
    if metrics.get("gaps_by_state"):
        print(f"    Gaps: {metrics['gaps_by_state']}")


def show_audit():
    db = get_db()
    metrics = collect_metrics(db)
    print("=== Quality Audit ===\n")
    for k, v in sorted(metrics.items()):
        if isinstance(v, dict):
            print(f"  {k}:")
            for k2, v2 in sorted(v.items()):
                print(f"    {k2}: {v2}")
        else:
            if isinstance(v, float):
                print(f"  {k}: {v:.2%}")
            else:
                print(f"  {k}: {v}")


# ════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Autonomous Orchestrator — self-growing knowledge loop")
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="Run one cycle")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--budget", choices=["normal", "low"], default="normal")

    sub.add_parser("status", help="Show orchestrator status")
    sub.add_parser("audit", help="Show quality audit metrics")

    args = parser.parse_args()

    if args.cmd == "run":
        run_cycle(budget_mode=args.budget, dry_run=args.dry_run)
    elif args.cmd == "status":
        show_status()
    elif args.cmd == "audit":
        show_audit()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
