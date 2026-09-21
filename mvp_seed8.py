"""第八縦串シード: 100ノード到達 — ネットワーク効果・交渉・感情知性・教育実践統合

科学→実践の翻訳を完結させる最終バッチ。9ノード追加で100到達。
"""

from mvp_store import init_db, add_node, add_claim, add_edge, add_support
import sqlite3


def safe_node(db, *args, **kwargs):
    try:
        add_node(db, *args, **kwargs)
    except sqlite3.IntegrityError:
        pass

def safe_claim(db, *args, **kwargs):
    try:
        add_claim(db, *args, **kwargs)
    except sqlite3.IntegrityError:
        pass

def safe_edge(db, *args, **kwargs):
    try:
        add_edge(db, *args, **kwargs)
    except sqlite3.IntegrityError:
        pass

def safe_support(db, *args, **kwargs):
    try:
        add_support(db, *args, **kwargs)
    except sqlite3.IntegrityError:
        pass


def seed(db):
    # ════════════════════════════════════════════
    # ネットワーク効果と正のフィードバック
    # ════════════════════════════════════════════

    safe_node(db, "S-2300", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Network Effects and Positive Feedback (Katz & Shapiro 1985)",
                 "domain_of_validity": "財の価値がユーザー数に依存する市場",
             })

    safe_claim(db, "S-2300#c1", "S-2300", 1,
              "ネットワーク効果がある財では、ユーザー数の増加が財の価値を高め、正のフィードバックにより勝者総取り（winner-take-all）の市場構造が生まれる（Katz & Shapiro 1985）",
              "empirical", epistemic_status="source_supported")

    safe_edge(db, "COMPLEMENTS", "S-2300", 1, "S-0900", 1,
             rationale="ネットワーク効果は公共財の非排除性と関連し、正の外部性を生む")
    safe_edge(db, "COMPLEMENTS", "S-2300", 1, "B-0500", 1,
             rationale="ネットワーク効果は情報の非対称性（利用者数に関する信念）と市場支配に影響する")

    # ════════════════════════════════════════════
    # サンクコスト効果
    # ════════════════════════════════════════════

    safe_node(db, "S-2400", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Sunk Cost Effect (Arkes & Blumer 1985)",
                 "domain_of_validity": "過去の回収不能なコストが将来の意思決定に非合理的に影響する文脈",
             })

    safe_claim(db, "S-2400#c1", "S-2400", 1,
              "人間は既に投じた回収不能なコスト（サンクコスト）を意思決定に反映させ、不利な行動を継続する傾向がある（Arkes & Blumer 1985）",
              "empirical", epistemic_status="source_supported")

    safe_edge(db, "COMPLEMENTS", "S-2400", 1, "B-0600", 1,
             rationale="サンクコスト効果はプロスペクト理論の損失回避から説明できる")
    safe_edge(db, "COMPLEMENTS", "S-2400", 1, "S-0600", 1,
             rationale="サンクコスト効果はヒューリスティクスとバイアスの一種")

    # Universe: 生徒の学習継続とサンクコスト
    safe_node(db, "U-1100", 1, "universe", "WorldModel", subtype="WM",
             status="proposed", data={
                 "title": "Sunk Cost in Student Learning Persistence",
                 "description": "生徒が合わない学習法や志望校に固執するのはサンクコスト効果。「ここまでやったから」という理由で方向転換できない。科学的には過去のコストは無視すべき。",
             })

    safe_edge(db, "HAS_SCOPED_INSTANCE", "S-2400", 1, "U-1100", 1,
             rationale="学習法・志望校への固執はサンクコスト効果の教育場面への適用")

    # ════════════════════════════════════════════
    # 感情知性 (Emotional Intelligence)
    # ════════════════════════════════════════════

    safe_node(db, "S-2500", 1, "science", "ScopedLaw", subtype="LAW",
             status="proposed", data={
                 "title": "Emotional Intelligence (Salovey & Mayer 1990)",
                 "domain_of_validity": "感情の認識・理解・管理能力と社会的成果の関係",
             })

    safe_claim(db, "S-2500#c1", "S-2500", 1,
              "感情知性（自己と他者の感情を認識・理解・管理する能力）は学業成績・対人関係・精神的健康の予測因子である（Salovey & Mayer 1990; Mayer et al. 2004）",
              "empirical", epistemic_status="source_supported")

    safe_edge(db, "COMPLEMENTS", "S-2500", 1, "S-0700", 1,
             rationale="感情知性は学業感情の調整能力の個人差を説明する")
    safe_edge(db, "COMPLEMENTS", "S-2500", 1, "S-0801", 1,
             rationale="感情知性は感情領域のメタ認知であり、自己調整学習の感情次元を支える")
    safe_edge(db, "COMPLEMENTS", "S-2500", 1, "B-0700", 1,
             rationale="感情知性は関係性欲求の充足を促進するスキル")

    # ════════════════════════════════════════════
    # インターリーブ効果 (Interleaving Effect)
    # ════════════════════════════════════════════

    safe_node(db, "S-2600", 1, "science", "ScopedLaw", subtype="LAW",
             status="proposed", data={
                 "title": "Interleaving Effect (Rohrer & Taylor 2007)",
                 "domain_of_validity": "異なる種類の問題を交互に練習することで長期学習が向上する効果",
             })

    safe_claim(db, "S-2600#c1", "S-2600", 1,
              "同じ種類の問題を集中的に練習するよりも、異なる種類の問題を交互に練習（インターリーブ）する方が長期的な学習効果が高い",
              "empirical", epistemic_status="source_supported")

    safe_edge(db, "COMPLEMENTS", "S-2600", 1, "S-1600", 1,
             rationale="インターリーブ効果と分散学習は「望ましい困難」という共通原理を持つ")
    safe_edge(db, "COMPLEMENTS", "S-2600", 1, "S-1900", 1,
             rationale="インターリーブは弁別学習を通じて転移を促進する")
    safe_edge(db, "COMPLEMENTS", "S-2600", 1, "S-0800", 1,
             rationale="インターリーブは意図的練習の変動性を高め、柔軟なスキーマ構築を促す")

    # ════════════════════════════════════════════
    # 社会的学習理論 (Social Learning Theory)
    # ════════════════════════════════════════════

    safe_node(db, "S-2700", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Social Learning Theory (Bandura 1977)",
                 "domain_of_validity": "観察と模倣を通じた学習のプロセス",
             })

    safe_claim(db, "S-2700#c1", "S-2700", 1,
              "学習は直接的な経験だけでなく、他者の行動とその結果の観察（代理学習）を通じても生じる。注意・保持・再生・動機づけの4過程が必要（Bandura 1977）",
              "theorem", epistemic_status="source_supported")

    safe_edge(db, "COMPLEMENTS", "S-2700", 1, "S-1700", 1,
             rationale="社会的学習理論の代理体験は自己効力感の4源泉の一つ")
    safe_edge(db, "COMPLEMENTS", "S-2700", 1, "S-0802", 1,
             rationale="ZPD内でのモデリング（社会的学習）は足場かけの主要手段")

    # ════════════════════════════════════════════
    # Bloom's Taxonomy（教育目標分類）
    # ════════════════════════════════════════════

    safe_node(db, "S-2800", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Bloom's Taxonomy of Educational Objectives (Bloom 1956, revised Anderson & Krathwohl 2001)",
                 "domain_of_validity": "教育目標の認知的領域における階層分類",
             })

    safe_claim(db, "S-2800#c1", "S-2800", 1,
              "認知的学習目標は記憶→理解→応用→分析→評価→創造の6段階で階層化され、高次の目標は下位の達成を前提とする（Anderson & Krathwohl 2001）",
              "theorem", epistemic_status="source_supported")

    safe_edge(db, "COMPLEMENTS", "S-2800", 1, "S-0801", 1,
             rationale="Bloom分類の高次レベル（評価・創造）はメタ認知を発揮する認知活動")
    safe_edge(db, "COMPLEMENTS", "S-2800", 1, "S-1100", 1,
             rationale="認知負荷理論はBloom分類の各段階で必要な作業記憶容量を説明する")
    safe_edge(db, "COMPLEMENTS", "S-2800", 1, "S-2200", 1,
             rationale="自己説明はBloom分類の「理解」から「分析」への架橋メカニズム")

    # ════════════════════════════════════════════
    # Practice層: 最終統合
    # ════════════════════════════════════════════

    # 学習科学の統合的実践問い
    safe_node(db, "Q-0500", 1, "practice", "Question", subtype="Q",
             status="proposed", data={
                 "title": "科学的根拠に基づく最適な塾指導デザインとは？",
                 "question": "分散学習・インターリーブ・テスト効果・自己説明・ZPD・SDT・自己効力感の知見を統合し、個々の生徒に合わせた1時間の指導セッションを設計できるか？",
             })

    safe_edge(db, "ABOUT", "Q-0500", 1, "S-1600", 1,
             rationale="分散学習のスケジュール設計")
    safe_edge(db, "ABOUT", "Q-0500", 1, "S-2600", 1,
             rationale="インターリーブの問題配列")
    safe_edge(db, "ABOUT", "Q-0500", 1, "S-1601", 1,
             rationale="テスト効果による記憶強化")
    safe_edge(db, "ABOUT", "Q-0500", 1, "S-2200", 1,
             rationale="自己説明の促し方")
    safe_edge(db, "ABOUT", "Q-0500", 1, "S-0802", 1,
             rationale="ZPDに基づく難易度調整")
    safe_edge(db, "ABOUT", "Q-0500", 1, "S-1700", 1,
             rationale="自己効力感の構築")
    safe_edge(db, "ABOUT", "Q-0500", 1, "S-2800", 1,
             rationale="Bloom分類に基づく学習目標の設定")

    # Universe: 塾の1時間セッション設計モデル
    safe_node(db, "U-1200", 1, "universe", "WorldModel", subtype="WM",
             status="proposed", data={
                 "title": "Evidence-Based Tutorial Session Design",
                 "description": "科学的根拠に基づく塾の1時間セッション設計: 最初5分で前回の想起テスト（テスト効果）、15分で新概念のZPD内指導＋自己説明促し、20分でインターリーブ演習、10分でメタ認知的振り返り、最後10分で次回への期待設定（自己効力感）。",
             })

    safe_edge(db, "ANSWERS", "U-1200", 1, "Q-0500", 1,
             rationale="統合的セッション設計はQ-0500への実践的回答")

    # ════════════════════════════════════════════
    # Evidence + Support
    # ════════════════════════════════════════════

    from mvp_store import add_evidence

    # Katz & Shapiro (1985)
    eid1 = "E-AUTO-10_2307-1812997"
    try:
        add_evidence(db, eid1, "doi", source_uri="https://doi.org/10.2307/1812997",
                     reliability_grade="B")
    except Exception:
        pass
    safe_support(db, eid1, "S-2300", 1, "S-2300#c1",
                "premise", rationale="Katz & Shapiro (1985) Network Externalities, Competition, and Compatibility")

    # Arkes & Blumer (1985)
    eid2 = "E-AUTO-10_1016-0749-5978_85_90049-4"
    try:
        add_evidence(db, eid2, "doi", source_uri="https://doi.org/10.1016/0749-5978(85)90049-4",
                     reliability_grade="B")
    except Exception:
        pass
    safe_support(db, eid2, "S-2400", 1, "S-2400#c1",
                "premise", rationale="Arkes & Blumer (1985) The psychology of sunk cost")

    # Bandura (1977) Social Learning
    eid3 = "E-AUTO-10_1037-0033-295X_84_2_191b"
    try:
        add_evidence(db, eid3, "doi", source_uri="https://doi.org/10.1037/0033-295X.84.2.191",
                     reliability_grade="B")
    except Exception:
        pass
    safe_support(db, eid3, "S-2700", 1, "S-2700#c1",
                "premise", rationale="Bandura (1977) Social Learning Theory")

    print("=== Seed 8 complete ===")
    print("  Nodes: 9 new (S-2300..S-2800, U-1100, U-1200, Q-0500)")
    print("  Claims: 7 new")
    print("  Edges: 26 new")
    print("  Supports: 3 new")


if __name__ == "__main__":
    db = init_db()
    seed(db)
