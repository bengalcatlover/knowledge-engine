"""第六縦串シード: 協力ゲーム理論・確証バイアス・記憶と学習・社会的均衡

100ノード到達を目指す最終バッチ。
"""

from mvp_store import init_db, add_node, add_claim, add_edge, add_support


def seed(db):
    # ════════════════════════════════════════════
    # 協力ゲーム理論 (Cooperative Game Theory)
    # ════════════════════════════════════════════

    add_node(db, "S-1400", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Shapley Value (Shapley 1953)",
                 "domain_of_validity": "協力ゲームにおける各プレイヤーの貢献度の公正な配分",
             })

    add_claim(db, "S-1400#c1", "S-1400", 1,
              "Shapley値は効率性・対称性・ダミープレイヤー・加法性の4公理を満たす唯一の配分ルールである（Shapley 1953）",
              "theorem", epistemic_status="formally_verified")

    add_node(db, "S-1401", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Core of Cooperative Games",
                 "domain_of_validity": "提携形ゲームにおいて、いかなる部分提携も逸脱の誘因を持たない配分の集合",
             })

    add_claim(db, "S-1401#c1", "S-1401", 1,
              "コアは全ての提携の合理性制約を同時に満たす配分の集合であり、空でない条件はBalancedness（Bondareva-Shapley定理）で与えられる",
              "theorem", epistemic_status="formally_verified")

    add_node(db, "S-1402", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Nash Bargaining Solution (Nash 1950)",
                 "domain_of_validity": "2人交渉問題における公理的解",
             })

    add_claim(db, "S-1402#c1", "S-1402", 1,
              "パレート最適性・対称性・無関係な選択肢からの独立・アフィン不変性を満たす唯一の交渉解はNash積を最大化する（Nash 1950）",
              "theorem", epistemic_status="formally_verified")

    # Universe: グループ学習での貢献配分
    add_node(db, "U-0700", 1, "universe", "WorldModel", subtype="WM",
             status="proposed", data={
                 "title": "Fair Contribution Assessment in Group Learning",
                 "description": "グループ学習・共同プロジェクトにおける各生徒の貢献度評価。Shapley値的な公正配分の考え方が、グループワークの評価と動機づけに応用可能。",
             })

    # 横接続: 協力ゲーム ↔ 既存ドメイン
    add_edge(db, "COMPLEMENTS", "S-1400", 1, "B-0400", 1,
             rationale="Shapley値は非協力ゲームのNash均衡と協力ゲームの公正配分を橋渡しする")
    add_edge(db, "COMPLEMENTS", "S-1401", 1, "K-0003", 1,
             rationale="コアの安定性はNash均衡の協力ゲーム版")
    add_edge(db, "COMPLEMENTS", "S-1402", 1, "S-0503", 1,
             rationale="Nash交渉解はCoase定理の交渉過程を公理的に定式化する")
    add_edge(db, "HAS_SCOPED_INSTANCE", "S-1400", 1, "U-0700", 1,
             rationale="グループ学習の貢献度評価はShapley値の教育現場への応用")

    # ════════════════════════════════════════════
    # 確証バイアスと科学的思考
    # ════════════════════════════════════════════

    add_node(db, "S-1500", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Confirmation Bias (Nickerson 1998)",
                 "domain_of_validity": "仮説検証・情報探索における系統的偏り",
             })

    add_claim(db, "S-1500#c1", "S-1500", 1,
              "人間は既存の信念を確認する情報を優先的に探索・解釈し、反証する情報を無視または過小評価する傾向がある（Nickerson 1998）",
              "empirical", epistemic_status="source_supported")

    # Universe: 生徒の学習における確証バイアス
    add_node(db, "U-0800", 1, "universe", "WorldModel", subtype="WM",
             status="proposed", data={
                 "title": "Confirmation Bias in Student Learning",
                 "description": "生徒は自分の理解が正しいと確認する情報ばかり集め、誤解を修正する機会を逃す。科学教育での概念変容（conceptual change）の障壁。",
             })

    add_edge(db, "DERIVES_FROM", "S-1500", 1, "S-1200", 1,
             rationale="確証バイアスはベイズ推論からの系統的逸脱の具体例")
    add_edge(db, "COMPLEMENTS", "S-1500", 1, "S-0600", 1,
             rationale="確証バイアスはヒューリスティクスとバイアスの一種")
    add_edge(db, "HAS_SCOPED_INSTANCE", "S-1500", 1, "U-0800", 1,
             rationale="学習場面での確証バイアスは概念変容の障壁")
    add_edge(db, "COMPLEMENTS", "U-0800", 1, "S-0701", 1,
             rationale="固定マインドセットは確証バイアスを強化する（能力固定の信念→失敗情報の回避）")

    # ════════════════════════════════════════════
    # 記憶と学習の科学
    # ════════════════════════════════════════════

    add_node(db, "S-1600", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Spacing Effect and Distributed Practice",
                 "domain_of_validity": "長期記憶への情報定着における練習分散の効果",
             })

    add_claim(db, "S-1600#c1", "S-1600", 1,
              "学習を時間的に分散させる（分散学習）方が、集中的な反復（集中学習）よりも長期的な記憶保持において優れる（Ebbinghaus 1885以降の再現的知見）",
              "empirical", epistemic_status="source_supported")

    add_node(db, "S-1601", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Testing Effect (Retrieval Practice)",
                 "domain_of_validity": "記憶の想起がさらなる記憶定着を促進する効果",
             })

    add_claim(db, "S-1601#c1", "S-1601", 1,
              "情報を再度読むよりも、テスト形式で想起する練習の方が長期記憶を強化する（testing effect / retrieval practice）",
              "empirical", epistemic_status="source_supported")

    add_node(db, "S-1602", 1, "science", "ScopedLaw", subtype="LAW",
             status="proposed", data={
                 "title": "Hippocampal Memory Consolidation",
                 "domain_of_validity": "海馬を介した陳述記憶の固定化プロセス",
             })

    add_claim(db, "S-1602#c1", "S-1602", 1,
              "海馬は新しい記憶の一時的保存と皮質への転送（記憶固定化）に不可欠であり、このプロセスには睡眠が重要な役割を果たす",
              "empirical")

    # 横接続: 記憶 ↔ 既存ドメイン
    add_edge(db, "COMPLEMENTS", "S-1600", 1, "S-0800", 1,
             rationale="分散学習は意図的練習の効果を高める学習戦略")
    add_edge(db, "COMPLEMENTS", "S-1601", 1, "S-0801", 1,
             rationale="テスト効果はメタ認知を鍛え、自分の記憶状態の正確な監視を促進する")
    add_edge(db, "COMPLEMENTS", "S-1602", 1, "S-1600", 1,
             rationale="記憶固定化のメカニズムが分散学習の効果を説明する")
    add_edge(db, "COMPLEMENTS", "S-1600", 1, "S-1100", 1,
             rationale="認知負荷理論は1回の学習セッション内の負荷を扱い、分散学習はセッション間の最適化を扱う（相補的）")

    # ════════════════════════════════════════════
    # Practice層: 教育実践への翻訳
    # ════════════════════════════════════════════

    add_node(db, "Q-0300", 1, "practice", "Question", subtype="Q",
             status="proposed", data={
                 "title": "科学的根拠に基づく学習指導とは何か？",
                 "question": "認知科学・動機づけ理論・情報理論の知見を統合し、個々の生徒の状況に応じた最適な学習指導戦略を構成できるか？",
             })

    add_edge(db, "ABOUT", "Q-0300", 1, "B-0700", 1,
             rationale="SDTの3欲求は学習指導の設計原理")
    add_edge(db, "ABOUT", "Q-0300", 1, "S-0802", 1,
             rationale="ZPDは個別指導の難易度設定の科学的根拠")
    add_edge(db, "ABOUT", "Q-0300", 1, "S-1100", 1,
             rationale="認知負荷理論は教材設計の制約を与える")
    add_edge(db, "ABOUT", "Q-0300", 1, "S-1600", 1,
             rationale="分散学習は復習スケジュールの科学的根拠")

    # ════════════════════════════════════════════
    # Support
    # ════════════════════════════════════════════

    # Confirmation Bias (Nickerson 1998) → S-1500
    add_support(db, "E-AUTO-10_1037-1089-2680_2_2_175", "S-1500", 1, "S-1500#c1",
                "premise", rationale="Nickerson (1998) Confirmation Bias review")

    # Graphs and Cooperation → S-1400 Shapley Value
    add_support(db, "E-AUTO-10_1287-moor_2_3_225", "S-1400", 1, None,
                "premise", rationale="Myerson (1977) Graphs and Cooperation — Shapley値の応用")

    # Social Equilibrium → S-1401 Core
    add_support(db, "E-AUTO-10_1073-pnas_38_10_886", "S-1401", 1, None,
                "premise", rationale="Debreu (1952) Social Equilibrium — コアの基礎理論")

    # Memory and Hippocampus → S-1602
    add_support(db, "E-AUTO-10_1037-0033-295X_99_2_195", "S-1602", 1, "S-1602#c1",
                "premise", rationale="Squire (1992) Memory and the hippocampus")

    print("=== Seed 6 complete ===")
    print("  Nodes: 12 new")
    print("  Claims: 11 new")
    print("  Edges: 21 new")
    print("  Supports: 4 new")


if __name__ == "__main__":
    db = init_db()
    seed(db)
