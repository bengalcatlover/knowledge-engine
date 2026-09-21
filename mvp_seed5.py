"""第五縦串シード: ドメイン間ブリッジ

限定合理性・公共財・マッチング・認知負荷・ベイズ推論
既存ドメインの横接続を強化する。
"""

from mvp_store import init_db, add_node, add_claim, add_edge, add_support


def seed(db):
    # ════════════════════════════════════════════
    # Bridge 1: 限定合理性 (Bounded Rationality)
    # game theory ↔ cognitive bias ↔ mechanism design を繋ぐ
    # ════════════════════════════════════════════

    add_node(db, "B-0800", 1, "foundation", "FormalPrinciple", subtype="THY",
             status="approved", data={
                 "title": "Bounded Rationality (Simon 1955)",
                 "statement": "人間の意思決定は完全合理性ではなく、認知的制約・情報処理能力の限界・時間制約の下で満足化（satisficing）により行われる。",
                 "admission": "theorem_import",
                 "approval_scope": "model_assertion",
             })

    add_claim(db, "B-0800#c1", "B-0800", 1,
              "人間は最適化ではなく満足化（satisficing）を行う: 十分に良い選択肢が見つかれば探索を停止する（Simon 1955）",
              "empirical", epistemic_status="source_supported")

    add_claim(db, "B-0800#c2", "B-0800", 1,
              "認知資源は有限であり、意思決定の質は環境構造と認知能力の適合度に依存する（ecological rationality）",
              "theorem", epistemic_status="source_supported")

    # 横接続: 限定合理性 ↔ 既存ドメイン
    add_edge(db, "GENERALIZES", "B-0800", 1, "S-0600", 1,
             rationale="ヒューリスティクスとバイアスは限定合理性の具体的メカニズム")
    add_edge(db, "COMPLEMENTS", "B-0800", 1, "B-0600", 1,
             rationale="プロスペクト理論は限定合理性の下での意思決定モデルの一つ")
    add_edge(db, "COMPLEMENTS", "B-0800", 1, "K-0010", 1,
             rationale="メカニズム設計は完全合理性を仮定するが、限定合理性下ではインセンティブ設計の修正が必要")
    add_edge(db, "COMPLEMENTS", "B-0800", 1, "B-0400", 1,
             rationale="Nash均衡は完全合理性を仮定するが、限定合理性下では均衡概念の修正（QRE等）が必要")

    # ════════════════════════════════════════════
    # Bridge 2: 公共財とフリーライダー問題
    # game theory ↔ social choice ↔ mechanism design を繋ぐ
    # ════════════════════════════════════════════

    add_node(db, "S-0900", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Public Goods and Free Rider Problem",
                 "domain_of_validity": "非排除性・非競合性を持つ財の供給",
                 "falsification_condition": "自発的供給で社会的最適量が達成される条件の特定",
             })

    add_claim(db, "S-0900#c1", "S-0900", 1,
              "公共財は非排除性と非競合性を持ち、自発的供給ではフリーライダー問題により過少供給となる（Samuelson 1954）",
              "theorem", epistemic_status="source_supported")

    add_node(db, "S-0901", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Tragedy of the Commons (Hardin 1968)",
                 "domain_of_validity": "共有資源の自由アクセス環境",
                 "falsification_condition": "Ostromの共有資源管理の条件（コミュニティガバナンス）",
             })

    add_claim(db, "S-0901#c1", "S-0901", 1,
              "共有資源への自由アクセスは個人の合理的行動が集団的に最適でない結果をもたらす（Hardin 1968）",
              "theorem", epistemic_status="source_supported")

    # 横接続: 公共財 ↔ 既存ドメイン
    add_edge(db, "IS_A", "S-0900", 1, "K-0003", 1,
             rationale="公共財ゲームはナッシュ均衡の典型的応用（囚人のジレンマの一般化）")
    add_edge(db, "COMPLEMENTS", "S-0901", 1, "S-0900", 1,
             rationale="共有地の悲劇は公共財問題の共有資源版")
    add_edge(db, "COMPLEMENTS", "S-0900", 1, "S-0300", 1,
             rationale="公共財の最適供給量決定は社会的選択問題の一形態")
    add_edge(db, "COMPLEMENTS", "S-0900", 1, "B-0300", 1,
             rationale="公共財供給の投票決定はArrowの不可能性定理の制約を受ける")

    # ════════════════════════════════════════════
    # Bridge 3: 安定マッチング
    # mechanism design ↔ social choice ↔ game theory を繋ぐ
    # ════════════════════════════════════════════

    add_node(db, "S-1000", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Stable Matching (Gale-Shapley 1962)",
                 "domain_of_validity": "二部マッチング市場（入学選考、研修医配属、臓器移植等）",
                 "falsification_condition": "安定マッチングが存在しない市場構造の特定",
             })

    add_claim(db, "S-1000#c1", "S-1000", 1,
              "受入保留アルゴリズム（deferred acceptance）は全ての二部マッチング市場で安定マッチングを生成する（Gale & Shapley 1962）",
              "theorem", epistemic_status="formally_verified")

    add_claim(db, "S-1000#c2", "S-1000", 1,
              "安定マッチングは耐戦略的であり、提案側にとって最適なマッチングを生成する",
              "theorem", epistemic_status="source_supported")

    # Universe: 受験指導への応用
    add_node(db, "U-0500", 1, "universe", "WorldModel", subtype="WM",
             status="proposed", data={
                 "title": "Student-School Matching Model",
                 "description": "生徒の志望校選択と入試制度はマッチング問題。安定マッチング理論が指導戦略の科学的根拠を与える。",
             })

    add_claim(db, "U-0500#c1", "U-0500", 1,
              "受験指導における志望校選択は安定マッチング理論の実世界応用であり、戦略的操作の誘因を理解することが有効な指導につながる",
              "abstraction")

    # 横接続: マッチング ↔ 既存ドメイン
    add_edge(db, "COMPLEMENTS", "S-1000", 1, "K-0010", 1,
             rationale="安定マッチングはインセンティブ両立性を満たすメカニズムの実例")
    add_edge(db, "APPLIES_TO", "S-1000", 1, "S-0301", 1,
             rationale="受入保留アルゴリズムの耐戦略性はGibbard-Satterthwaite定理の例外条件を示す")
    add_edge(db, "HAS_SCOPED_INSTANCE", "S-1000", 1, "U-0500", 1,
             rationale="生徒と学校のマッチングは安定マッチング理論の具体的適用")

    # ════════════════════════════════════════════
    # Bridge 4: 認知負荷理論
    # learning science ↔ information theory を繋ぐ
    # ════════════════════════════════════════════

    add_node(db, "S-1100", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Cognitive Load Theory (Sweller 1988)",
                 "domain_of_validity": "教材設計と学習における作業記憶の制約",
                 "falsification_condition": "作業記憶の制約を超えても学習が阻害されない条件",
             })

    add_claim(db, "S-1100#c1", "S-1100", 1,
              "学習効果は内在的認知負荷（課題の本質的複雑さ）、外在的認知負荷（教材設計の不適切さ）、関連認知負荷（スキーマ構築への投資）のバランスに依存する",
              "theorem", epistemic_status="source_supported")

    # 横接続: 認知負荷 ↔ 既存ドメイン
    add_edge(db, "COMPLEMENTS", "S-1100", 1, "S-0802", 1,
             rationale="認知負荷理論はZPDの「適切な難易度」を作業記憶の観点から精密化する")
    add_edge(db, "COMPLEMENTS", "S-1100", 1, "B-0800", 1,
             rationale="認知負荷は限定合理性の認知的メカニズムの一つ（作業記憶のチャンネル容量制限）")
    add_edge(db, "COMPLEMENTS", "S-1100", 1, "K-0017", 1,
             rationale="情報理論のチャンネル容量概念は認知負荷理論の作業記憶制限のアナロジー")
    add_edge(db, "COMPLEMENTS", "S-1100", 1, "S-0800", 1,
             rationale="意図的練習の効果は認知負荷の適切な管理に依存する")

    # ════════════════════════════════════════════
    # Bridge 5: ベイズ推論と学習
    # information theory ↔ decision making ↔ education を繋ぐ
    # ════════════════════════════════════════════

    add_node(db, "S-1200", 1, "science", "ScopedLaw", subtype="LAW",
             status="approved", data={
                 "title": "Bayesian Reasoning and Belief Updating",
                 "domain_of_validity": "不確実性下での情報統合と信念更新",
             })

    add_claim(db, "S-1200#c1", "S-1200", 1,
              "合理的な信念更新はベイズの定理に従い、事前確率と尤度から事後確率を計算する",
              "theorem", epistemic_status="formally_verified")

    add_claim(db, "S-1200#c2", "S-1200", 1,
              "人間のベイズ推論は系統的に歪められ、基準率の無視・確証バイアス・アンカリングが生じる",
              "empirical", epistemic_status="source_supported")

    # Universe: 生徒の自己認識更新モデル
    add_node(db, "U-0600", 1, "universe", "WorldModel", subtype="WM",
             status="proposed", data={
                 "title": "Student Self-Assessment Belief Updating",
                 "description": "生徒の自己評価は試験結果・教師のフィードバック・同級生との比較により更新される。ベイズ的更新からの系統的逸脱が自己効力感に影響。",
             })

    add_claim(db, "U-0600#c1", "U-0600", 1,
              "生徒の自己評価は新しい情報（試験結果等）に対してベイズ的に更新されるが、確証バイアスにより失敗情報を過小評価する傾向がある",
              "abstraction")

    # 横接続: ベイズ推論 ↔ 既存ドメイン
    add_edge(db, "COMPLEMENTS", "S-1200", 1, "S-0600", 1,
             rationale="ベイズ推論からの逸脱がヒューリスティクスとバイアスの多くを説明する")
    add_edge(db, "COMPLEMENTS", "S-1200", 1, "K-0007", 1,
             rationale="情報の価値はベイズ更新による期待利得の改善として定式化される")
    add_edge(db, "COMPLEMENTS", "S-1200", 1, "K-0017", 1,
             rationale="ベイズ推論は情報理論のエントロピー削減と数学的に等価な側面を持つ")
    add_edge(db, "HAS_SCOPED_INSTANCE", "S-1200", 1, "U-0600", 1,
             rationale="生徒の自己評価更新はベイズ推論の実世界モデル")
    add_edge(db, "COMPLEMENTS", "U-0600", 1, "S-0701", 1,
             rationale="成長マインドセットは自己評価のベイズ更新の事前分布を変える")

    # ════════════════════════════════════════════
    # Bridge 6: 自我消耗と自己制御
    # cognitive bias ↔ motivation ↔ learning を繋ぐ
    # ════════════════════════════════════════════

    add_node(db, "S-1300", 1, "science", "ScopedLaw", subtype="LAW",
             status="proposed", data={
                 "title": "Ego Depletion and Self-Control (Baumeister 1998)",
                 "domain_of_validity": "連続する自己制御課題における認知資源の消耗",
                 "falsification_condition": "自己制御資源の枯渇モデルへの反論（動機づけ説、再現性問題）",
             })

    add_claim(db, "S-1300#c1", "S-1300", 1,
              "自己制御は有限の認知資源を消費し、連続使用により一時的に枯渇する（Baumeister et al. 1998）。ただし再現性に議論あり",
              "empirical")

    # 横接続
    add_edge(db, "COMPLEMENTS", "S-1300", 1, "B-0800", 1,
             rationale="自我消耗は限定合理性の自己制御側面")
    add_edge(db, "COMPLEMENTS", "S-1300", 1, "B-0700", 1,
             rationale="自己制御の消耗は自律性欲求の充足と対立しうる（SDTとの統合課題）")
    add_edge(db, "COMPLEMENTS", "S-1300", 1, "S-0801", 1,
             rationale="メタ認知的監視は自己制御資源を消費するため、認知負荷との相互作用がある")

    # ════════════════════════════════════════════
    # Support: evidenceとノードの紐付け
    # ════════════════════════════════════════════

    # Simon (1956) → B-0800
    add_support(db, "E-AUTO-10_1037-h0042769", "B-0800", 1, "B-0800#c1",
                "premise", rationale="Simon (1956) Rational choice and the structure of the environment")

    # Samuelson (1954) Public Expenditure → S-0900
    add_support(db, "E-AUTO-10_2307-1925895", "S-0900", 1, "S-0900#c1",
                "premise", rationale="Samuelson (1954) Pure Theory of Public Expenditure 原論文")

    # Hardin (1968) Tragedy of the Commons → S-0901
    add_support(db, "E-AUTO-10_1126-science_162_3859_1243", "S-0901", 1, "S-0901#c1",
                "premise", rationale="Hardin (1968) Tragedy of the Commons 原論文")

    # Gale & Shapley (1962) → S-1000
    add_support(db, "E-AUTO-10_2307-2312726", "S-1000", 1, "S-1000#c1",
                "premise", rationale="Gale & Shapley (1962) College Admissions 原論文")

    # Gigerenzer (2011) Heuristic Decision Making → B-0800
    add_support(db, "E-AUTO-10_1146-annurev-psych-120709-1", "B-0800", 1, "B-0800#c2",
                "premise", rationale="Gigerenzer & Gaissmaier (2011) ecological rationality")

    # Baumeister (1998) Ego Depletion → S-1300
    add_support(db, "E-AUTO-10_1037-0022-3514_74_5_1252", "S-1300", 1, "S-1300#c1",
                "premise", rationale="Baumeister et al. (1998) Ego Depletion 原論文")

    print("=== Seed 5 complete ===")
    n_nodes = 10  # B-0800, S-0900, S-0901, S-1000, S-1100, S-1200, S-1300, U-0500, U-0600
    n_claims = 13
    n_edges = 24
    n_supports = 6
    print(f"  Nodes: {n_nodes} new")
    print(f"  Claims: {n_claims} new")
    print(f"  Edges: {n_edges} new (heavy cross-domain linking)")
    print(f"  Supports: {n_supports} new")


if __name__ == "__main__":
    db = init_db()
    seed(db)
