"""縦串MVP: 第二価格オークション10ノード+HYPの起票

既存K-0003/K-0010/K-0007は参照資産（reference_use）。
H-0100は未検証仮説として隔離。
"""

from pathlib import Path
from mvp_store import (
    init_db, add_node, add_claim, add_edge, add_evidence, add_support,
    DB_PATH, dump_graph
)

# 既存DBがあれば削除して再作成
if DB_PATH.exists():
    DB_PATH.unlink()

db = init_db()

# ════════════════════════════════════════════
# L1 基礎科学
# ════════════════════════════════════════════

add_node(db, "B-0100", 1, "foundation", "FormalPrinciple", "THM", "draft", {
    "title": "有限選択集合における最適性判定",
    "statement_formal": "C(f,a*,D) = max_{a in D}{f(a)-f(a*)}. C=0 iff a* in argmax f(a).",
    "proof_source": "定義から直接導出（最大値の定義）",
})

add_claim(db, "B-0100#c1", "B-0100", 1,
    "有限非空集合Dと a* in D に対し、C(f,a*,D)=0 ⟺ a* in argmax_{a in D} f(a)",
    "theorem", "unverified")

# ════════════════════════════════════════════
# L2 科学
# ════════════════════════════════════════════

# S-0100: 局所形式主張（新規、MVPで検証）
add_node(db, "S-0100", 1, "science", "ScopedLaw", "LAW", "draft", {
    "title": "有限第二価格封印入札における正直入札の弱支配性",
    "domain_of_validity": "単一財、私的価値、入札者n>=2、準線形効用、{0,1,2}の評価額",
    "falsification_condition": "指定モデル内で正直入札より高い期待効用を与える逸脱戦略が存在する",
})

add_claim(db, "S-0100#c1", "S-0100", 1,
    "指定した有限第二価格封印入札では、正直入札が弱支配戦略であり、正直入札プロファイルがナッシュ均衡になる",
    "empirical", "unverified")

# K-0003: ナッシュ均衡（参照資産）
add_node(db, "K-0003", 1, "science", "Theory", "THY", "draft", {
    "title": "ナッシュ均衡と戦略的相互作用",
    "admission": "imported_reference",
    "approval_scope": "reference_use",
    "falsification_condition": "反復非協力ゲーム実験で均衡予測が系統的に外れる条件が確認された場合",
})

add_claim(db, "K-0003#c1", "K-0003", 1,
    "他の参加者の戦略を所与としたとき、どの参加者も単独で戦略を変えて利益を増やせない状態",
    "definition", "source_supported")

# K-0010: インセンティブ両立性（参照資産）
add_node(db, "K-0010", 1, "science", "Theory", "THY", "draft", {
    "title": "インセンティブ両立性",
    "admission": "imported_reference",
    "approval_scope": "reference_use",
    "falsification_condition": "支配戦略ICを満たすはずのメカニズムで真値以外の入札が支配戦略となる反例が構成された場合",
})

add_claim(db, "K-0010#c1", "K-0010", 1,
    "メカニズムがインセンティブ両立的であるとは、各参加者にとって真の情報を報告することが支配戦略であること",
    "definition", "source_supported")

# K-0007: RCT（参照資産、検証設計用）
add_node(db, "K-0007", 1, "science", "Method", "MTH", "draft", {
    "title": "ランダム化比較試験",
    "admission": "imported_reference",
    "approval_scope": "reference_use",
    "note": "無作為割付の中核主張に原典位置が不足し根拠台帳でブロック中",
})

add_claim(db, "K-0007#c1", "K-0007", 1,
    "無作為化により、処置群と統制群の間で観測・未観測の交絡因子が平均的に均等化される",
    "empirical", "unverified",
    assumptions=["十分な標本サイズ", "適切な乱数生成", "ITT原則の遵守"])

# ════════════════════════════════════════════
# L3 宇宙（世界モデル）
# ════════════════════════════════════════════

add_node(db, "U-0100", 1, "universe", "WorldModel", "WM", "draft", {
    "title": "封印入札オークション市場の戦略行動モデル",
    "domain": "単一財封印入札オークション",
    "scope": "入札者2人、評価額・入札額 in {0,1,2}、私的価値、準線形効用",
    "boundary_conditions": [
        "共謀なし",
        "予算制約なし",
        "外部性なし",
        "同額時の順位は事前固定",
    ],
    "unmodeled_factors": [
        "入札者の心理的バイアス",
        "繰り返しゲームによる学習効果",
        "情報の非対称性（共通価値）",
    ],
})

add_claim(db, "U-0100#c1", "U-0100", 1,
    "指定境界条件下で、第二価格封印入札は正直入札を弱支配戦略とする市場構造を形成する",
    "abstraction", "unverified")

# ════════════════════════════════════════════
# L4 オブジェクト
# ════════════════════════════════════════════

add_node(db, "O-0100", 1, "object", "System", None, "draft", {
    "title": "第二価格封印入札シミュレーター（版固定）",
    "identity": "mvp_auction_simulator_v1",
    "version": "1.0.0",
    "observation_interface": "全入力列挙＋効用計算",
    "operation_interface": "入札関数の差し替え（第一価格変異テスト用）",
})

# ════════════════════════════════════════════
# L5 問い・行動・検証
# ════════════════════════════════════════════

# Q-0100: 問い
add_node(db, "Q-0100", 1, "practice", "Question", "Q", "draft", {
    "title": "正直入札からの有利な逸脱は存在するか",
    "target": "U-0100",
})

add_claim(db, "Q-0100#q1", "Q-0100", 1,
    "Q1: 理想モデルで正直申告から利益の出る逸脱はあるか",
    "empirical", "unverified")

# H-0100: 仮説（隔離）
add_node(db, "H-0100", 1, "practice", "Question", "HYP", "proposed", {
    "title": "人間実験でも申告乖離が減少するか",
    "target": "U-0100",
    "note": "未検証仮説。MVPでは検証しない。",
})

add_claim(db, "H-0100#h1", "H-0100", 1,
    "H1: 誘発価値を使う人間実験でも、第二価格方式は第一価格方式より申告乖離を減らす",
    "application_hypothesis", "unverified")

# A-0100: 行動
add_node(db, "A-0100", 1, "practice", "Action", "ACT", "draft", {
    "title": "全許容入力の厳密列挙+逸脱利得検査",
    "input": "O-0100@1",
    "procedure": "入札者2人×評価額{0,1,2}×入札額{0,1,2}の全組合せを列挙し、正直入札からの逸脱利得を計算",
    "stop_condition": "全組合せの検査完了",
})

# V-0100: 検証
add_node(db, "V-0100", 1, "practice", "Verification", "VER", "draft", {
    "title": "逸脱利得検査+変異実装検出+限界記録",
    "success_criteria": "正直入札からの有利な逸脱が0件",
    "mutation_test": "第一価格変異で有利な逸脱が検出されること",
    "limitations": [
        "有限離散モデルのみ。連続評価額への拡張は未検証",
        "人間への効果はnot_run",
    ],
})

# ════════════════════════════════════════════
# 根拠（Evidence Store）
# ════════════════════════════════════════════

# Nash (1950)原論文
add_evidence(db, "E-NASH-1950", "source_excerpt",
    source_uri="doi:10.1073/pnas.36.1.48",
    source_version="1950",
    locator="p.49, Theorem 1: Equilibrium Points in N-Person Games",
    content_hash="pending_verification",  # 出典監査で確定
    origin_group="nash1950",
    reliability_grade="A")

# MIT OCW 14.12 ゲーム理論
add_evidence(db, "E-MIT-1412", "source_excerpt",
    source_uri="https://ocw.mit.edu/courses/14-12-economic-applications-of-game-theory-fall-2012/",
    source_version="Fall 2012",
    locator="Lecture 5-6: Nash Equilibrium, Dominant Strategies",
    content_hash="pending_verification",
    origin_group="mit_ocw_1412",
    reliability_grade="B")

# Vickrey (1961) 第二価格オークション原論文
add_evidence(db, "E-VICKREY-1961", "source_excerpt",
    source_uri="doi:10.2307/2977633",
    source_version="1961",
    locator="Journal of Finance 16(1), pp.8-37, Theorem on second-price sealed-bid",
    content_hash="pending_verification",
    origin_group="vickrey1961",
    reliability_grade="A")

# ════════════════════════════════════════════
# Support Assessments
# ════════════════════════════════════════════

add_support(db, "E-NASH-1950", "K-0003", 1, "K-0003#c1", "definition",
    rationale="Nash均衡の原定義", assessor="system")

add_support(db, "E-MIT-1412", "K-0003", 1, "K-0003#c1", "premise",
    rationale="MIT講義での均衡概念の解説", assessor="system")

add_support(db, "E-VICKREY-1961", "S-0100", 1, "S-0100#c1", "derivation",
    rationale="第二価格入札における正直入札の弱支配性の原証明", assessor="system")

add_support(db, "E-VICKREY-1961", "K-0010", 1, "K-0010#c1", "premise",
    rationale="Vickreyメカニズムにおけるインセンティブ両立性", assessor="system")

# ════════════════════════════════════════════
# エッジ
# ════════════════════════════════════════════

# 根拠構造エッジ
add_edge(db, "ABSTRACTS_FROM", "B-0100", 1, "S-0100", 1,
    rationale="競売の検証構造から最適性判定原理を抽出",
    derivation_ref="proof: 最大値の定義から直接")

add_edge(db, "ABSTRACTS_FROM", "S-0100", 1, "U-0100", 1,
    rationale="世界モデルから正直入札の弱支配性を抽象化")

add_edge(db, "ABSTRACTS_FROM", "U-0100", 1, "O-0100", 1,
    rationale="シミュレーターの実行結果からモデルを構成")

# 参照・対応エッジ
add_edge(db, "HAS_SCOPED_INSTANCE", "K-0003", 1, "U-0100", 1,
    rationale="ナッシュ均衡の局所適用：封印入札の均衡分析")

add_edge(db, "HAS_SCOPED_INSTANCE", "K-0010", 1, "U-0100", 1,
    rationale="ICの局所適用：第二価格入札の正直入札")

add_edge(db, "GUIDES_TEST_DESIGN", "K-0007", 1, "Q-0100", 1,
    rationale="将来の人間実験の検証設計参照（MVPでは実行しない）")

# ワークフローエッジ
add_edge(db, "ABOUT", "Q-0100", 1, "U-0100", 1)
add_edge(db, "PLANS", "Q-0100", 1, "A-0100", 1)
add_edge(db, "EXECUTES_ON", "A-0100", 1, "O-0100", 1)
add_edge(db, "PRODUCES", "A-0100", 1, "V-0100", 1)
add_edge(db, "ANSWERS", "V-0100", 1, "Q-0100", 1)

# ════════════════════════════════════════════
# 表示
# ════════════════════════════════════════════

print("=== MVP Seed Complete ===\n")
dump_graph(db)

node_count = db.execute("SELECT COUNT(*) FROM node").fetchone()[0]
edge_count = db.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
evidence_count = db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
print(f"\nTotal: {node_count} nodes, {edge_count} edges, {evidence_count} evidence records")
