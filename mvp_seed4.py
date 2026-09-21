"""第四縦串シード: 認知科学・行動経済学・教育心理学

科学的知識を現実の悩み相談・学習指導に翻訳するための基盤ドメイン。
"""

from mvp_store import init_db, add_node, add_claim, add_edge, add_support


def seed(db):
    # ════════════════════════════════════════════
    # Domain 4: 認知バイアスと意思決定 (Cognitive Bias & Decision Making)
    # ════════════════════════════════════════════

    # Foundation: Prospect Theory
    add_node(db, "B-0600", 1, "foundation", "FormalPrinciple", subtype="THY",
             status="approved", data={
                 "title": "Prospect Theory (Kahneman & Tversky 1979)",
                 "statement": "人間の意思決定は期待効用理論から系統的に逸脱する。損失回避・参照点依存・確率の非線形重み付けが特徴。",
                 "admission": "theorem_import",
                 "approval_scope": "model_assertion",
             })

    add_claim(db, "B-0600#c1", "B-0600", 1,
              "人間は利得と損失を非対称に評価し、同じ大きさの損失は利得の約2倍の心理的重みを持つ（損失回避）",
              "empirical", epistemic_status="source_supported")

    add_claim(db, "B-0600#c2", "B-0600", 1,
              "意思決定は絶対的な結果ではなく参照点からの変化に基づいて行われる（参照点依存）",
              "theorem", epistemic_status="source_supported")

    # Science: Heuristics and Biases
    add_node(db, "S-0600", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Heuristics and Biases (Tversky & Kahneman 1974)",
                 "domain_of_validity": "不確実性下での人間の判断",
                 "falsification_condition": "十分な訓練と即時フィードバックがある領域ではバイアスが減少する",
             })

    add_claim(db, "S-0600#c1", "S-0600", 1,
              "人間は代表性・利用可能性・アンカリングの3つのヒューリスティクスに依存し、系統的なバイアスを生む（Tversky & Kahneman 1974）",
              "empirical", epistemic_status="source_supported")

    add_claim(db, "S-0600#c2", "S-0600", 1,
              "利用可能性ヒューリスティク: 思い出しやすい事例の頻度・確率を過大評価する（Tversky & Kahneman 1973）",
              "empirical", epistemic_status="source_supported")

    # Universe: 生徒の進路選択モデル
    add_node(db, "U-0300", 1, "universe", "WorldModel", subtype="WM",
             status="proposed", data={
                 "title": "Student Decision Making under Uncertainty",
                 "description": "進路選択・学習戦略選択における不確実性下の意思決定モデル。参照点は同級生の成績・親の期待・過去の自分。",
             })

    add_claim(db, "U-0300#c1", "U-0300", 1,
              "生徒の進路選択は期待効用最大化ではなく、損失回避と参照点依存で歪められる",
              "abstraction")

    # ════════════════════════════════════════════
    # Domain 5: 動機づけと自己決定理論 (Motivation & Self-Determination)
    # ════════════════════════════════════════════

    # Foundation: Self-Determination Theory
    add_node(db, "B-0700", 1, "foundation", "FormalPrinciple", subtype="THY",
             status="approved", data={
                 "title": "Self-Determination Theory (Deci & Ryan 2000)",
                 "statement": "内発的動機づけは自律性・有能感・関係性の3つの基本的心理欲求の充足により促進される。",
                 "admission": "theorem_import",
                 "approval_scope": "model_assertion",
             })

    add_claim(db, "B-0700#c1", "B-0700", 1,
              "自律性・有能感・関係性の3つの基本的心理欲求が内発的動機づけの必要条件である（Deci & Ryan 2000）",
              "theorem", epistemic_status="source_supported")

    add_claim(db, "B-0700#c2", "B-0700", 1,
              "外的報酬は内発的動機づけを低下させうる（アンダーマイニング効果、Deci 1971; Deci, Koestner & Ryan 1999）",
              "empirical", epistemic_status="source_supported")

    # Science: Academic Emotions
    add_node(db, "S-0700", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Academic Emotions and Self-Regulated Learning (Pekrun 2002)",
                 "domain_of_validity": "学業における感情と学習行動の関係",
                 "falsification_condition": "感情状態が学習成果に影響しない条件の特定",
             })

    add_claim(db, "S-0700#c1", "S-0700", 1,
              "学業上の感情（enjoyment, anxiety, boredom）は自己調整学習と成績に直接影響する（Pekrun et al. 2002）",
              "empirical", epistemic_status="source_supported")

    # Science: Growth Mindset vs Fixed Mindset
    add_node(db, "S-0701", 1, "science", "ScopedLaw", subtype="LAW",
             status="proposed", data={
                 "title": "Growth Mindset Theory (Dweck 2006)",
                 "domain_of_validity": "学習と能力に対する信念が学業成績に影響する文脈",
                 "falsification_condition": "マインドセット介入の効果量が小さいメタ分析結果",
             })

    add_claim(db, "S-0701#c1", "S-0701", 1,
              "能力は努力で伸びるという信念（成長マインドセット）を持つ生徒は、困難に直面しても粘り強く取り組む",
              "empirical")

    # Universe: 塾の生徒の動機づけモデル
    add_node(db, "U-0400", 1, "universe", "WorldModel", subtype="WM",
             status="proposed", data={
                 "title": "Student Motivation Model in Tutorial Context",
                 "description": "塾環境での生徒の動機づけ: 自律性（自分で選ぶ）、有能感（できるようになる実感）、関係性（先生・仲間との繋がり）が学習の質を決める。",
             })

    add_claim(db, "U-0400#c1", "U-0400", 1,
              "塾での学習効果は外的報酬（成績・点数）よりも自律性の支援（学習内容の選択権・ペースの自己決定）に依存する",
              "abstraction")

    # ════════════════════════════════════════════
    # Domain 6: 学習科学と知識構造 (Learning Science)
    # ════════════════════════════════════════════

    # Science: Deliberate Practice
    add_node(db, "S-0800", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Deliberate Practice (Ericsson 1993)",
                 "domain_of_validity": "スキル習得における意図的な練習の役割",
             })

    add_claim(db, "S-0800#c1", "S-0800", 1,
              "エキスパートレベルの能力獲得には10年以上の意図的練習（即時フィードバック・限界への挑戦・集中的反復）が必要である（Ericsson 1993）",
              "empirical", epistemic_status="source_supported")

    # Science: Metacognition and Learning
    add_node(db, "S-0801", 1, "science", "ScopedLaw", subtype="LAW",
             status="proposed", data={
                 "title": "Metacognition and Self-Regulated Learning",
                 "domain_of_validity": "学習者が自分の認知プロセスを監視・制御する能力と学業成績の関係",
             })

    add_claim(db, "S-0801#c1", "S-0801", 1,
              "メタ認知能力（自分が何を知らないかを知る能力）は学業成績の強い予測因子であり、直接指導で改善可能",
              "empirical")

    # Science: Zone of Proximal Development
    add_node(db, "S-0802", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Zone of Proximal Development (Vygotsky 1978)",
                 "domain_of_validity": "教育的足場かけ（scaffolding）による学習促進",
                 "falsification_condition": "足場かけなしでも同等の学習成果が得られる条件",
             })

    add_claim(db, "S-0802#c1", "S-0802", 1,
              "学習者が独力では解決できないが、適切な支援があれば達成できる領域（ZPD）での課題設定が最も効果的な学習を生む（Vygotsky 1978）",
              "theorem", epistemic_status="source_supported")

    # ════════════════════════════════════════════
    # エッジ: ドメイン間の接続
    # ════════════════════════════════════════════

    # Prospect Theory → Heuristics (同じ研究プログラム)
    add_edge(db, "DERIVES_FROM", "B-0600", 1, "S-0600", 1,
             rationale="プロスペクト理論はヒューリスティクスとバイアス研究プログラムの延長線上にある")

    # Prospect Theory → 生徒の意思決定モデル
    add_edge(db, "HAS_SCOPED_INSTANCE", "B-0600", 1, "U-0300", 1,
             rationale="生徒の進路選択はプロスペクト理論の損失回避と参照点依存で説明できる")

    # SDT → 塾の動機づけモデル
    add_edge(db, "HAS_SCOPED_INSTANCE", "B-0700", 1, "U-0400", 1,
             rationale="塾での学習動機づけはSDTの3欲求モデルの具体的適用")

    # SDT → Academic Emotions
    add_edge(db, "COMPLEMENTS", "B-0700", 1, "S-0700", 1,
             rationale="自己決定理論と学業感情はともに内発的動機づけの異なる側面を扱う")

    # ZPD → Deliberate Practice
    add_edge(db, "COMPLEMENTS", "S-0802", 1, "S-0800", 1,
             rationale="ZPDと意図的練習は「適切な難易度での挑戦」という共通原理を持つ")

    # Metacognition → SDT (自律性としてのメタ認知)
    add_edge(db, "COMPLEMENTS", "S-0801", 1, "B-0700", 1,
             rationale="メタ認知は自己決定理論の自律性欲求の認知的基盤")

    # Growth Mindset → SDT
    add_edge(db, "COMPLEMENTS", "S-0701", 1, "B-0700", 1,
             rationale="成長マインドセットは有能感の知覚を支え、SDTの動機づけメカニズムと補完的")

    # Heuristics → インセンティブ両立性 (K-0010)
    add_edge(db, "COMPLEMENTS", "S-0600", 1, "K-0010", 1,
             rationale="認知バイアスの存在はインセンティブ設計において合理性仮定の修正を要求する")

    # ════════════════════════════════════════════
    # Support: evidenceとノードの紐付け
    # ════════════════════════════════════════════

    # Kahneman & Tversky (1979) Prospect Theory → B-0600
    add_support(db, "E-AUTO-10_2307-1914185", "B-0600", 1, "B-0600#c1",
                "premise", rationale="Kahneman & Tversky (1979) Prospect Theory 原論文")

    # Tversky & Kahneman (1974) Heuristics → S-0600
    add_support(db, "E-AUTO-10_1126-science_185_4157_1124", "S-0600", 1, "S-0600#c1",
                "premise", rationale="Tversky & Kahneman (1974) Judgment under Uncertainty 原論文")

    # Tversky & Kahneman (1973) Availability → S-0600
    add_support(db, "E-AUTO-10_1016-0010-0285(73)90033-9", "S-0600", 1, "S-0600#c2",
                "premise", rationale="Tversky & Kahneman (1973) Availability heuristic 原論文")

    # Deci & Ryan (2000) SDT → B-0700
    add_support(db, "E-AUTO-10_1207-S15327965PLI1104_01", "B-0700", 1, "B-0700#c1",
                "premise", rationale="Deci & Ryan (2000) Self-Determination Theory overview")

    # Deci (1971) + Deci, Koestner & Ryan (1999) Undermining → B-0700
    add_support(db, "E-AUTO-10_1037-h0035519", "B-0700", 1, "B-0700#c2",
                "premise", rationale="Deci (1971) 外的報酬のアンダーマイニング効果の原論文")
    add_support(db, "E-AUTO-10_1037-0033-2909_125_6_627", "B-0700", 1, "B-0700#c2",
                "premise", rationale="Deci, Koestner & Ryan (1999) アンダーマイニング効果のメタ分析")

    # Pekrun et al. (2002) Academic Emotions → S-0700
    add_support(db, "E-AUTO-10_1207-s15326985ep3702_4", "S-0700", 1, "S-0700#c1",
                "premise", rationale="Pekrun et al. (2002) Academic emotions in self-regulated learning")

    print("=== Seed 4 complete ===")
    print("  Nodes: 12 new (B-0600, B-0700, S-0600..S-0802, U-0300, U-0400)")
    print("  Claims: 14 new")
    print("  Edges: 8 new")
    print("  Supports: 7 new")


if __name__ == "__main__":
    db = init_db()
    seed(db)
