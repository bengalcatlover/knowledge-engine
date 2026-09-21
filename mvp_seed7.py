"""第七縦串シード: 自己効力感・フィードバック・転移・類推的推論

学習の科学を縦に深め、横にもう一段広げる。100ノード到達。
"""

from mvp_store import init_db, add_node, add_claim, add_edge, add_support


def seed(db):
    # ════════════════════════════════════════════
    # 自己効力感 (Self-Efficacy)
    # SDT ↔ 学習成果 ↔ 動機づけ を繋ぐ重要概念
    # ════════════════════════════════════════════

    add_node(db, "S-1700", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Self-Efficacy Theory (Bandura 1977)",
                 "domain_of_validity": "課題遂行に対する自己の能力への信念が行動・動機づけ・達成に影響する文脈",
             })

    add_claim(db, "S-1700#c1", "S-1700", 1,
              "自己効力感は成功体験・代理体験・言語的説得・情動的喚起の4源泉から形成され、行動の選択・努力・持続に直接影響する（Bandura 1977）",
              "theorem", epistemic_status="source_supported")

    add_claim(db, "S-1700#c2", "S-1700", 1,
              "自己効力感は学業成績の最も強力な予測因子の一つであり、能力そのものよりも成果を予測する",
              "empirical", epistemic_status="source_supported")

    # Universe: 生徒の自己効力感モデル
    add_node(db, "U-0900", 1, "universe", "WorldModel", subtype="WM",
             status="proposed", data={
                 "title": "Student Self-Efficacy in Tutorial Context",
                 "description": "塾環境での自己効力感: 小さな成功体験の積み重ね、先生の言語的激励、同級生のモデリングが自己効力感を構築する。",
             })

    add_edge(db, "COMPLEMENTS", "S-1700", 1, "B-0700", 1,
             rationale="自己効力感はSDTの有能感欲求と密接に関連するが、課題固有の信念である点で異なる")
    add_edge(db, "COMPLEMENTS", "S-1700", 1, "S-0701", 1,
             rationale="成長マインドセットは自己効力感の形成条件を支える信念体系")
    add_edge(db, "COMPLEMENTS", "S-1700", 1, "S-0802", 1,
             rationale="ZPD内の課題成功が自己効力感の最も強力な源泉（成功体験）を生む")
    add_edge(db, "HAS_SCOPED_INSTANCE", "S-1700", 1, "U-0900", 1,
             rationale="塾での自己効力感構築は理論の直接適用")
    add_edge(db, "COMPLEMENTS", "U-0900", 1, "U-0600", 1,
             rationale="自己効力感は自己評価のベイズ更新の事前信念を形成する")

    # ════════════════════════════════════════════
    # フィードバックの科学
    # ════════════════════════════════════════════

    add_node(db, "S-1800", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Feedback and Learning (Hattie & Timperley 2007)",
                 "domain_of_validity": "教育場面におけるフィードバックの効果",
             })

    add_claim(db, "S-1800#c1", "S-1800", 1,
              "効果的なフィードバックは4つのレベル（課題・プロセス・自己調整・自己）で機能し、課題レベルとプロセスレベルが最も効果的（Hattie & Timperley 2007）",
              "empirical", epistemic_status="source_supported")

    add_claim(db, "S-1800#c2", "S-1800", 1,
              "フィードバックの効果量は教育介入の中で最大級（d=0.73）であるが、フィードバックの種類により効果は大きく異なる",
              "empirical", epistemic_status="source_supported")

    add_edge(db, "COMPLEMENTS", "S-1800", 1, "S-0800", 1,
             rationale="意図的練習の核心要素は即時フィードバックであり、フィードバック理論がその質を定義する")
    add_edge(db, "COMPLEMENTS", "S-1800", 1, "S-1700", 1,
             rationale="適切なフィードバックは自己効力感の源泉（成功体験の認識）を強化する")
    add_edge(db, "COMPLEMENTS", "S-1800", 1, "S-0801", 1,
             rationale="自己調整レベルのフィードバックはメタ認知能力を直接育成する")

    # ════════════════════════════════════════════
    # 学習の転移 (Transfer of Learning)
    # ════════════════════════════════════════════

    add_node(db, "S-1900", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Transfer of Learning: Near and Far",
                 "domain_of_validity": "ある文脈で学んだ知識・スキルが別の文脈で適用される条件",
             })

    add_claim(db, "S-1900#c1", "S-1900", 1,
              "近転移（類似文脈への適用）は比較的容易に起こるが、遠転移（異なるドメインへの適用）は構造的類似性の認識を必要とし、自発的には稀である",
              "empirical", epistemic_status="source_supported")

    # Universe: 教科間の知識転移
    add_node(db, "U-1000", 1, "universe", "WorldModel", subtype="WM",
             status="proposed", data={
                 "title": "Cross-Subject Knowledge Transfer in Education",
                 "description": "数学で学んだ論理的思考を物理や経済学に転移させる。構造的類似性を明示的に指導することで遠転移を促進できる。",
             })

    add_edge(db, "COMPLEMENTS", "S-1900", 1, "S-1100", 1,
             rationale="認知負荷理論は転移に必要なスキーマ構築の条件を規定する")
    add_edge(db, "COMPLEMENTS", "S-1900", 1, "S-0802", 1,
             rationale="ZPDでの学習は転移可能なスキーマの構築を促進する")
    add_edge(db, "HAS_SCOPED_INSTANCE", "S-1900", 1, "U-1000", 1,
             rationale="教科間の知識転移は転移理論の教育実践への応用")

    # ════════════════════════════════════════════
    # 類推的推論 (Analogical Reasoning)
    # ════════════════════════════════════════════

    add_node(db, "S-2000", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Structure Mapping in Analogy (Gentner 1983)",
                 "domain_of_validity": "類推的推論の認知プロセス",
             })

    add_claim(db, "S-2000#c1", "S-2000", 1,
              "類推は表面的類似ではなく構造的類似（関係の対応）に基づいて行われ、構造写像理論がその認知メカニズムを説明する（Gentner 1983）",
              "theorem", epistemic_status="source_supported")

    add_edge(db, "COMPLEMENTS", "S-2000", 1, "S-1900", 1,
             rationale="類推的推論は遠転移の主要なメカニズム")
    add_edge(db, "COMPLEMENTS", "S-2000", 1, "S-1200", 1,
             rationale="類推はベイズ的な構造推論の一形態と見なせる")

    # ════════════════════════════════════════════
    # 動機づけの期待価値理論
    # SDT + 自己効力感を統合する上位理論
    # ════════════════════════════════════════════

    add_node(db, "S-2100", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Expectancy-Value Theory of Motivation (Eccles & Wigfield 2002)",
                 "domain_of_validity": "課題選択と達成行動における期待と価値の役割",
             })

    add_claim(db, "S-2100#c1", "S-2100", 1,
              "達成行動は成功への期待（自分にできるか）と課題の主観的価値（やる意味があるか）の2要因で予測される（Eccles & Wigfield 2002）",
              "theorem", epistemic_status="source_supported")

    add_edge(db, "COMPLEMENTS", "S-2100", 1, "S-1700", 1,
             rationale="自己効力感は期待価値理論の「期待」成分に対応する")
    add_edge(db, "COMPLEMENTS", "S-2100", 1, "B-0700", 1,
             rationale="SDTの内発的動機づけは期待価値理論の「価値」成分を説明する")
    add_edge(db, "COMPLEMENTS", "S-2100", 1, "B-0600", 1,
             rationale="プロスペクト理論の参照点依存は期待と価値の主観的評価を歪める")

    # ════════════════════════════════════════════
    # メタ認知のもう一歩: 自己説明効果
    # ════════════════════════════════════════════

    add_node(db, "S-2200", 1, "science", "ScopedLaw", subtype="LAW",
             status="proposed", data={
                 "title": "Self-Explanation Effect (Chi et al. 1989)",
                 "domain_of_validity": "学習中に自分に説明することで理解が深まる効果",
             })

    add_claim(db, "S-2200#c1", "S-2200", 1,
              "学習者が資料を自分の言葉で説明する（自己説明）ことで、ギャップの検出と知識の統合が促進され、学習効果が向上する",
              "empirical")

    add_edge(db, "COMPLEMENTS", "S-2200", 1, "S-0801", 1,
             rationale="自己説明はメタ認知の発現形態であり、理解の監視を能動的に行う")
    add_edge(db, "COMPLEMENTS", "S-2200", 1, "S-1601", 1,
             rationale="自己説明とテスト効果は「能動的想起」という共通メカニズムを持つ")

    # ════════════════════════════════════════════
    # Practice層の拡充
    # ════════════════════════════════════════════

    add_node(db, "Q-0400", 1, "practice", "Question", subtype="Q",
             status="proposed", data={
                 "title": "生徒の動機づけが低下したとき、科学的に何ができるか？",
                 "question": "SDT・自己効力感・期待価値理論の知見を統合し、具体的な指導行動として翻訳できるか？",
             })

    add_edge(db, "ABOUT", "Q-0400", 1, "B-0700", 1,
             rationale="SDTの自律性支援")
    add_edge(db, "ABOUT", "Q-0400", 1, "S-1700", 1,
             rationale="自己効力感の4源泉の活用")
    add_edge(db, "ABOUT", "Q-0400", 1, "S-2100", 1,
             rationale="期待と価値の両面からの介入設計")

    # ════════════════════════════════════════════
    # Support
    # ════════════════════════════════════════════

    # Bandura (1977) Self-Efficacy → S-1700
    add_support(db, "E-AUTO-10_1037-0033-295X_84_2_191", "S-1700", 1, "S-1700#c1",
                "premise", rationale="Bandura (1977) Self-efficacy 原論文")

    # Hattie & Timperley (2007) Power of Feedback → S-1800
    add_support(db, "E-AUTO-10_3102-003465430298487", "S-1800", 1, "S-1800#c1",
                "premise", rationale="Hattie & Timperley (2007) The Power of Feedback")

    # Gentner (1983) Structure Mapping → S-2000
    add_support(db, "E-AUTO-10_1037-0003-066X_52_1_45", "S-2000", 1, "S-2000#c1",
                "premise", rationale="Gentner (1997) Structure mapping in analogy and similarity")

    # Eccles & Wigfield (2002) Motivational Beliefs → S-2100
    add_support(db, "E-AUTO-10_1146-annurev_psych_53_10090", "S-2100", 1, "S-2100#c1",
                "premise", rationale="Eccles & Wigfield (2002) Motivational Beliefs, Values, and Goals")

    print("=== Seed 7 complete ===")
    print("  Nodes: 11 new")
    print("  Claims: 12 new")
    print("  Edges: 25 new")
    print("  Supports: 4 new")


if __name__ == "__main__":
    db = init_db()
    seed(db)
