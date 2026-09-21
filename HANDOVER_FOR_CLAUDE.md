# 共通引き継ぎ: 世界モデル知識エンジン

## 続行結果（2026-09-14 文献の帰属確認）

保留中の15-competitiveの2主張について著者提出版と原著者の業績一覧を照合。後続論文による先行研究の紹介であることを確認した。原著全文の条件検証は残るため保留を維持。
`evidence_miner.py`に引用の文脈から先行著者への帰属と欠落した参照先を検出する保留規則を追加。登録・ノード生成の既存review_required境界で止める。
追加3件を含めpytest36件＋契約9件が通過。DB整合性正常、通常利用可能2件。追加LLM API呼び出し0。
詳細と次の作業: `work/verification_pilot/LITERATURE_FOLLOWUP.md`。

## 最新実行結果（2026-09-14 二者提案を採用・実装）

ユーザーの実行指示により候補境界、10件検証、固定QA評価、gap1件処理を完了した。
詳細正本: `work/verification_pilot/IMPLEMENTATION_RESULT.md`。
40ノード・107主張・71根拠・50関係・147支持評価。**現在通常利用可能なのは検査記録がある2主張のみ**。古いstatus名だけでは利用を許可しない。
10件中2件を明示範囲の形式検査で確認、8件保留。42件の回帰テストと固定QA10問が通過。Haiku含意判定は校正6件中5ラベル一致で、自動昇格には未採用。
通常検索・回答は`knowledge_policy.py`で候補を除外。`verify_pilot.py`をオーケストレーターへ接続。領域拡張はまだ保留。
Question型のgap1件を有限モデルの条件付き回答として解決し、質問そのものは主張へ昇格させていない。

## 最新の追記（2026-09-14 低コスト運用へ移行）

その後ユーザー依頼でFable 5 / GPT-6 Astraに次期方針を相談した。回答と一致点・相違点は `work/next_policy_20260914_summary.md`。両者は領域拡大より検証経路と候補隔離を優先するが、先行順位と自動昇格方式は異なる。レビュー後の新実装・カード承認は未実施。

ユーザー指示により、通常生成はGPT-4.1 nano固定へ変更した。旧記述のHaiku固定は現行ではない。
`work/LOW_COST_OPERATION.md` を先に読むこと。現状は40ノード・107主張・69根拠・50関係・145支持評価。
今回の増分は未検証主張2件と仮説関係1件。低価格モデルの出力は候補用途に限定し、自動承認しない。
`cheap_llm.py` に入力・出力・呼び出し数・概算費用上限とキャッシュを実装。高額モデルへの自動昇格なし。
1サイクルのAPI費用は概算$0.002683、少量評価込み$0.0036836。18件のテストとDB整合性確認が通過。
過去の収束カウントには通信失敗が混在していたため、新しい `verified-v2` 収量判定のみ次回へ継承する。

以下は移行前の設計・実績記録。

## ユーザーの最終意図

「餌をやらなくても知識を勝手に増やし、クラスを増やし、インスタンスを突き合わせて、知識を抜く」

目標はMIT講義カード集ではない。根拠に戻れる世界モデルを、再帰的に増幅する知識OSにする。

```text
基礎科学(foundation) → 科学(science) → 宇宙(universe) → オブジェクト(object) → 実践(practice)
```

- MIT OCWは根拠供給源の一つであり、世界モデルの中心ではない。
- 上位概念は、根拠付き下位概念からの追跡経路を必須とする。
- 成功指標はノード数ではなく、根拠追跡・再現・反例での更新・重要な問いへの回答能力。

## モデル運用

- Claude Opus: 中間管理職（統合・指示・実装）
- Fable 5.1 + GPT-6 Astra (o3): 設計・最終レビュー。二者一致のみ採用、不一致は `defer`
- Claude Haiku 4.5: 安い作業（claim抽出、DOI検証、分類、エッジ検証）
- `ask_llm.py`: Fable/Astra/GeminiへのAPI呼び出しスクリプト

## 現在の状態（2026-09-14）

### 全体メトリクス
- **40ノード** / **49エッジ** / **69エビデンス** / **105 claims** / **142 support_assessments**
- **6ドメイン**: 第二価格オークション、情報理論、メカニズムデザイン、情報経済学、契約理論、ベイズ意思決定理論
- Edge/node比: **1.23**（健全域）
- Evidence coverage: **99%** / Independent coverage: **30%**
- Gap台帳: open 17 / resolved 6（充足率 26%）
- 契約テスト9本全通過 (`test_mvp_contract.py`)

### ノード分布
| 層 | ノード数 | 例 |
|---|---|---|
| foundation | 3 | 検証構造、Huffman符号、情報価格理論 |
| science | 26 | ナッシュ均衡、インセンティブ両立性、情報理論、rational inattention等 |
| universe | 2 | オークション戦略モデル、離散無記憶源モデル |
| object | 2 | 最適化シミュレーター、Huffman Coder |
| practice | 7 | 問い、検証計画、検証結果 |

### ノード状態
| 状態 | 数 | 説明 |
|---|---|---|
| approved | 17 | 初期シードおよび手動承認済み |
| proposed | 22 | node_factoryが自動生成。independent evidence >= 2で昇格可能 |
| blocked | 1 | K-0007（DOI以前の文献、正しい動作） |

### エッジ型（15種）
| 型 | 数 | 用途 |
|---|---|---|
| HAS_SCOPED_INSTANCE | 18 | 理論→具体的適用例 |
| ABSTRACTS_FROM | 6 | 抽象化元への参照 |
| IS_A | 5 | クラス分類 |
| COMPLEMENTS | 4 | 相補関係（Fable/Astra推奨型） |
| ABOUT / PLANS / PRODUCES / EXECUTES_ON | 2各 | ワークフロー型 |
| GENERALIZES | 2 | 一般化関係 |
| DEPENDS_ON / DERIVES_FROM / SPECIALIZES / APPLIES_TO | 1各 | 依存・導出・特殊化・適用 |
| GUIDES_TEST_DESIGN / ANSWERS | 1各 | 検証設計・回答 |

## 実装済みコンポーネント（全8モジュール）

| ファイル | 機能 | 状態 |
|---|---|---|
| `mvp_store.py` | SQLiteベース根拠ストア、policy engine | ✅ 稼働中 |
| `knowledge_amplifier.py` | LLM→claim+DOI→4層検証→自動登録 | ✅ 稼働中 |
| `evidence_miner.py` | evidence→abstract取得→claim抽出→重複判定→ノード帰属→登録 | ✅ 稼働中 |
| `gap_detector.py` | G1/G2/G3検出、冪等台帳、auto-linking | ✅ 稼働中 |
| `node_factory.py` | unresolved claim→LLM分類→provisional生成→昇格判定 | ✅ 稼働中 |
| `relation_engine.py` | co-evidence候補生成→Haiku LLM検証→HYP_EDGE隔離→G3解消 | ✅ 稼働中 |
| `autonomous_orchestrator.py` | 7フェーズサイクル+予算制御+サーキットブレーカー | ✅ 稼働中 |
| `test_mvp_contract.py` | 9本の契約テスト | ✅ 全通過 |

### 補助コンポーネント
| ファイル | 機能 |
|---|---|
| `ask_knowledge.py` | 質問→BM25検索→根拠追跡→Haiku回答 |
| `search_engine.py` | Projection層（ノード解決→claim→evidence追跡） |
| `mvp_seed2.py` | 情報理論ドメインのシード |
| `mvp_huffman_sim.py` | シャノン符号化定理の検証シミュレータ |

## オーケストレーターの使い方

```bash
python autonomous_orchestrator.py run               # 1サイクル実行
python autonomous_orchestrator.py run --budget low   # 低予算テスト
python autonomous_orchestrator.py run --dry-run      # DB変更なし
python autonomous_orchestrator.py status             # 直近サイクル履歴
python autonomous_orchestrator.py audit              # 品質メトリクス
```

### 7フェーズサイクル
```
1. repair   — gap_detector (G1/G2/G3) + evidence充填
2. extract  — evidence_miner: evidence→claim抽出
3. grow     — node_factory: ノード生成
4. relate   — relation_engine: エッジ推論 + G3解消
5. promote  — provisional→active|archived 判定
6. expand   — frontier_manager: ドメイン拡大 (100ノード後)
7. audit    — 品質メトリクス + サーキットブレーカー
```

### 予算制御（1サイクルあたり）
| リソース | normal | low |
|---|---|---|
| LLMコール | 200 | 30 |
| 外部APIコール | 500 | 60 |
| 新ノード | 20 | 5 |
| 新エッジ | 50 | 10 |
| wall time | 1800s | 300s |

### サーキットブレーカー（5条件）
1. ハレーション棄却率 > 40% → 停止
2. provisional比率 > 30%（N>=50で判定）→ 拡大凍結
3. dispute滞留 > 10件 → 人間レビュー完了まで停止
4. 成長率 > 20%/サイクル（N>=50で判定）→ 停止
5. 3サイクル連続 新verified claim < 3 → 休止

## 4層DOI検証パイプライン

```
LLMがDOI付き論文を提示
  → CrossRef: DOIが実在するか確認
  → OpenAlex: フォールバック + 引用数 + OA状態
  → Semantic Scholar: abstract取得 + claim意味一致判定
  → Unpaywall: OA PDF URL
  → 合格: Grade A/B/C で登録
  → 不合格: REJECTED（実測12-28%がハレーション）
```

## evidence_miner パイプライン

```
evidence(DOI) → Semantic Scholar/OpenAlex でabstract取得
  → Haiku LLMでclaim抽出（1 abstract最大5 claims）
  → ストップワード除去 + keyword Jaccard で既存claim重複判定
  → ノード帰属: keyword類似度（閾値0.35）+ JP-EN bilingual対応
  → 帰属成功: claim登録 + support_assessment生成
  → 帰属失敗(unresolved): node_factoryで新ノード候補に
```

### ノード帰属の改善履歴
- v1: keyword Jaccard閾値0.20、ストップワードなし → K-0007に64件集中（シンクノード現象）
- v2（現行）: 50+語ストップワード除去、閾値0.35に引き上げ → 解消

## relation_engine パイプライン

```
Stage 1: co-evidence候補生成
  同じevidenceが2ノードをsupport → エッジ候補
  既存エッジのペアは除外

Stage 2: Haiku LLM検証
  両ノードのclaim一覧 + co-evidence情報をプロンプトに渡す
  → exists: true/false
  → edge_type: 15種から選択
  → confidence: "verified" or "hypothesis"
  → verified → エッジ登録
  → hypothesis → [HYP_EDGE]タグ付きで登録（隔離）
  → exists=false → 棄却

G3解消: 既存G3のfrom_node/to_nodeにco-evidenceがあれば
  → derivation_ref設定 → G3をresolved
```

## 設計上の不変条件

1. **evidence-backed原則** — claim/edgeとも根拠必須。「LLMが言った」は根拠にならない
2. **HYP隔離** — LLM直感はHYP層、事実グラフに直接書かない
3. **骨格は人間承認、肉付けは全自動** — 基盤ノードは人間が決定、evidence追加は自動
4. **derivation_depth上限** — 自動生成物の自動再消費による幻覚増幅を遮断（max 3）
5. **削除しない、archiveする** — データは消さず状態遷移で管理
6. **independent_coverage** — evidence_minerの自己参照supportを除外した真の支持率を監視
7. **冪等台帳** — gap/miningは冪等キーで同一処理の重複を防止

## 発見された設計課題と対処

### Fable 5.1 + GPT-6 Astra レビュー指摘（2026-09-14）

| 指摘 | 状態 | 対処 |
|---|---|---|
| coverage 98%は循環参照で膨張（evidence_minerの自己support） | ✅ 解決 | independent_coverage指標を追加（現在30%） |
| 小規模Nでの比率ベースサーキットブレーカー誤発火 | ✅ 解決 | N>=50の最小サンプル数ガード |
| エッジ成長フェーズの欠落 | ✅ 解決 | Phase 4 RELATE追加、relation_engine.py実装 |
| ストップワードなしのJaccardでシンクノード現象 | ✅ 解決 | 50+語ストップワード除去 + 閾値0.35 |
| 閉世界仮定（棄却クラスの欠如） | ✅ 解決 | 閾値未満はunresolved → node_factoryへ |
| LLM自己確認ループ | ⚠ 注意中 | DOI/abstract非LLM検証層あり。初期昇格は手動監査推奨 |
| G2消費フェーズ不在 | ⏳ 未対処 | 100ノード後のfrontier_managerで対処予定 |
| 否定・矛盾の表現不足 | ⏳ 未対処 | CONTRADICTSエッジ型は定義済み、実データでは未発生 |

### ノード帰属のembedding化（Fable/Astra合意、未実装）
- keyword Jaccardの限界: 語彙外の同義語に弱い
- 推奨: MiniLM/multilingual-e5でembedding一次判定 → 境界例のみHaikuでLLM分類
- 40ノード規模では現行keywordで十分。100ノード超で導入推奨

## 成長履歴

| 時点 | ノード | Claims | Evidence | Edges | ドメイン |
|---|---|---|---|---|---|
| MVP初期 | 19 | 11 | 23 | 19 | 2（オークション+情報理論） |
| evidence_miner稼働後 | 19 | 45 | 23 | 19 | 2 |
| メカニズムデザイン投入後 | 33 | 66 | 49 | 40 | 4 |
| 情報経済学投入後（現在） | 40 | 105 | 69 | 49 | 6 |

## 次にやること

### 短期（40→100ノード）
1. **evidence第3バッチ投入** — 社会的選択理論、ゲーム理論基礎（cooperative/non-cooperative）、Bayesゲーム深掘り
2. **proposed 22件の昇格** — 追加evidence投入でindependent evidence >= 2を満たす
3. **no_abstract evidence再試行** — API制限解除後に17件を再マイニング
4. **ノード帰属embedding化** — 100ノード超でkeywordの限界が来る前に導入

### 中期（100ノード到達後）
1. **B: frontier_manager.py** — 境界ノード検出 + スコアリング + 自動ドメイン拡大
2. **完全自律サイクル** — cron/scheduler で1日4サイクル自動実行
3. **ask_knowledge.py強化** — 回答不能ログで需要駆動の拡大

### 設計判断（Fable 5.1 + GPT-6 Astra 合意）
- B（frontier_manager）は100ノード到達まで急がない（統計が効かない）
- 100ノード到達の方法: 隣接ドメインを小バッチで投入し、claim品質・検証済みエッジ・gap増減を確認しながら進める
- ノード数を目標にしない。independent_coverageとedge/node比を品質指標とする

## 設計資料の場所

| ファイル | 内容 |
|---|---|
| `work/akiraG_overview.md` | あきらぐ（知識OS）の全体像・ポジショニング |
| `work/unified_blueprint_v1.md` | OOP型知識創造基盤の統合設計（Fable/Astra承認済み） |
| `work/autonomous_loop_fable.txt` | Fable 5の自律ループ全体設計 |
| `work/autonomous_loop_astra.txt` | GPT-6 Astraの自律ループ全体設計 |
| `work/next_step_fable.txt` | Fable 5.1の次ステップ提言（2026-09-14） |
| `work/next_step_astra.txt` | GPT-6 Astraの次ステップ提言（2026-09-14） |
| `work/node_attribution_fable.txt` | Fable 5.1のノード帰属問題レビュー |
| `work/node_attribution_astra.txt` | GPT-6 Astraのノード帰属問題レビュー |
| `work/gap_detector_fable.txt` | Fable 5のGap Detector設計 |
| `work/gap_detector_astra.txt` | GPT-6 AstraのGap Detector設計 |
| `work/review_world_model_blueprint_fable.txt` | 世界モデル設計案（Fable） |
| `work/review_world_model_blueprint_astra.txt` | 世界モデル設計案（Astra） |
| `work/proof_B0200.md` | シャノン符号化定理の形式証明 |
| `work/mvp_huffman_result.json` | Huffmanシミュレーション結果 |
