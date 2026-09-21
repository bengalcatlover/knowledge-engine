# 自律研究・知識生産システム設計書

添付の`KNOWLEDGE_ARCHITECTURE.md`の5層モデルを前提に、その上で動く**自律学習ループ**を設計する。方針は一貫して「**正本は決定論的コードが守り、AIは提案・抽出・照合だけを行う**」である。

---

## 0. 設計原則（先に決める不変条件）

1. **正本（Source of Truth）は追記専用ログ**。AIは正本に直接書けない。AIの出力はすべて「提案レコード」であり、決定論的なバリデータを通過して初めて正本に追記される。
2. **すべてのレコードに出所ハッシュ**。evidence は取得時スナップショットの content-hash を持ち、後からURLが変わっても検証可能。
3. **自己生成物は根拠になれない**。`output` と AI生成の要約は evidence 型を持てない（スキーマで禁止）。
4. **昇格は決定論、降格提案はAI可**。状態昇格の判定はコードが数値基準で行う。AIは「降格すべき矛盾を見つけた」と提案するだけ。
5. **予算・レート・停止はコードが強制**。AIは予算を「知る」が「管理」しない。
6. **人間承認点は3つに固定**：(a) verified への昇格、(b) 外部への実害可能行為（送信・公開・購入・スクレイピング規約グレー領域）、(c) スキーマ変更・予算増額。

---

## 1. 構成要素とデータモデル

### 1.1 物理構成（最小構成）

```text
knowledge/
├── ledger/                  # ★正本: 追記専用 JSONL（1日1ファイル、Git管理）
│   └── 2025-05-01.jsonl
├── snapshots/               # 取得資料の content-addressed 保存（sha256/ab/cd/....txt）
├── db/knowledge.sqlite      # ledger から決定論的に再構築できる materialized view
├── views/                   # 人間用 Markdown（派生物。編集禁止、再生成可能）
│   ├── concepts/
│   ├── claims/
│   └── questions/
├── eval/                    # 評価セット（ゴールド質問・罠問題・矛盾ペア）
├── audit/                   # 監査ログ（AI呼び出し全件: prompt hash, model, cost, 出力hash）
└── config/
    ├── budget.yaml          # 予算・レート上限
    ├── domains.yaml         # 信頼ドメイン分類・多様性クォータ
    └── promotion.yaml       # 昇格基準の数値パラメータ
```

- **正本 = `ledger/*.jsonl`**。SQLiteは常に `rebuild_db.py`（決定論）で全再構築できる。破損・疑義があればledgerから巻き戻す。
- **監査ログ**：AI呼び出し1回ごとに `{timestamp, agent, model, prompt_sha256, output_sha256, tokens_in/out, cost_usd, triggering_task_id}` を追記。コスト集計と再現性検査の両方に使う。

### 1.2 エンティティ定義

すべてのレコードは共通ヘッダを持つ：

```yaml
id: "clm_01HXXXX"        # 型プレフィクス付きULID
type: claim              # source|concept|claim|evidence|relationship|hypothesis|question|experiment|decision|output
created_at / created_by  # created_by: "agent:extractor-v3" | "human:user"
supersedes: clm_01HWWW   # 更新は上書きせず新レコード＋supersedes（古い知識の保全）
```

| 型 | 必須フィールド | 補足 |
|---|---|---|
| **source** | url, retrieved_at, content_sha256, source_class（`primary_paper` / `standard` / `gov` / `textbook` / `lecture` / `blog` / `self_generated`）, publisher_domain, pub_date, license | `self_generated` は evidence 参照禁止フラグが自動で立つ |
| **concept** | label, definition, scope（適用条件）, non_scope（適用外）, origin_source_ids | 講義由来の「候補概念」はここに入るが状態は必ず candidate から |
| **claim** | statement（**1文・検証可能な形に正規化**）, concept_ids, conditions（成立条件）, limitations, status, status_history, staleness_date（再検証期限）, domain_tags | 「〜は常に正しい」型の無条件主張はバリデータが reject |
| **evidence** | claim_id, source_id, stance（`supports` / `refutes` / `qualifies`）, quote（原文抜粋≤500字）, locator（ページ/節/タイムスタンプ）, extraction_agent, independence_group | independence_group は後述の独立性判定キー |
| **relationship** | from_id, to_id, edge_type（§5）, provenance_evidence_ids, confidence, asserted_by | provenance のないエッジはバリデータが reject |
| **hypothesis** | statement, motivating_gap_id, test_plan, falsification_condition（**何が観測されたら棄却か**を必須） | 棄却条件のない仮説は保存不可 |
| **question** | text, priority_score, origin（`gap` / `contradiction` / `staleness` / `human`）, target_claim_ids, budget_allocated, status | 学習課題の単位 |
| **experiment** | question_id, plan, queries_issued, sources_fetched, cost_actual, outcome（`answered` / `partial` / `dead_end` / `budget_exceeded`）, negative_result_note | **dead_end も必ず記録**（同じ袋小路の再探索防止） |
| **decision** | subject_id, action（promote/demote/retire/approve_external/reject）, actor（`human` / `rule:promotion-v2`）, rationale, evidence_snapshot | 人間承認とルール判定の両方をここに残す |
| **output** | audience, conclusion, claim_map（結論の各文→claim_id対応）, used_concept_ids, open_issues, **is_evidence_eligible: false（固定）** | 出力層。次回の根拠に絶対にならない |

---

## 2. 自律学習ループの状態遷移

### 2.1 状態機械

```text
        ┌──────────────────────────────────────────────┐
        ▼                                              │
[S0 IDLE] → [S1 GRAPH_AUDIT] → [S2 QUESTION_GEN] → [S3 PLAN]
                                                       │ 予算承認(自動/人間)
                                                       ▼
[S8 REVIEW_QUEUE] ← [S7 PERSIST] ← [S6 VERIFY] ← [S5 EXTRACT] ← [S4 EXPLORE]
        │
        └→ 人間承認 → accepted昇格 / 差戻し(→S2)
```

### 2.2 各状態の入出力・担当・停止条件

| 状態 | 担当 | 入力 | 出力 | 失敗・停止・再試行 |
|---|---|---|---|---|
| **S1 GRAPH_AUDIT** | **決定論コード**が穴の候補を機械的列挙（孤立concept、evidence数<2のclaim、staleness超過、refutes/supports が両方あるclaim）→ AIが重要度を注釈 | SQLite全体 | gap_report（gap/contradiction/staleness のリスト） | コード部は失敗しない。AI注釈失敗時は重要度=中で続行（**AI障害でループを止めない**） |
| **S2 QUESTION_GEN** | AI生成 → コードが重複検査（既存question・dead_end experimentとの埋め込み類似度>0.9で棄却） | gap_report | question レコード（優先度、対象claim、予算見積つき） | 新規questionゼロが3サイクル連続 → **HALT**して人間へ「探索空間枯渇」報告 |
| **S3 PLAN** | AIが調査計画（検索クエリ、期待資料種別、独立性要件）→ **コードが予算チェック** | question | experiment レコード（plan状態） | 見積 > per-question上限 → 自動棄却。見積 > 日次残額 → 翌日繰越。**規約グレーな取得を含む計画 → 人間承認キューへ** |
| **S4 EXPLORE** | コード（検索API・fetch・スナップショット保存・robots.txt遵守）＋ AI（結果の関連度トリアージのみ） | experiment.plan | source レコード群＋snapshots | HTTP失敗: 指数バックオフ3回→スキップ。取得0件: outcome=dead_end で記録し S2 へ。**同一ドメイン比率>50%になったら追加取得を強制**（後述の多様性クォータ） |
| **S5 EXTRACT** | AI（主張・条件・限界の抽出）→ コードが構造検証（1文正規化、quoteがsnapshot内に実在するか文字列照合） | sources | claim草案＋evidence草案 | quote照合失敗（ハルシネーション兆候）: そのevidence破棄＋監査ログにフラグ。**同一experiment内で照合失敗率>30% → experiment全体を隔離し人間レビューへ** |
| **S6 VERIFY** | **別モデル/別プロンプトのAI**が敵対的検査：反証検索クエリを最低2本発行、既存claimとの矛盾照合、条件の欠落指摘 | claim草案 | stance付きevidence追加、contradiction レポート | 反証検索も予算内で実行。矛盾検出 → 新claimと既存claim両方に `contradicts` エッジを張り、既存側の降格判定をトリガー |
| **S7 PERSIST** | 決定論コードのみ。バリデータ通過分を ledger 追記 → SQLite反映 → views再生成 | 検証済み草案 | candidate状態のレコード | バリデータ違反は全件 reject＋理由を監査ログへ。**ここにAIは関与しない** |
| **S8 REVIEW_QUEUE** | コードが昇格基準（§3）を判定。基準充足で supported へ自動昇格。verified 候補は人間キューへ | candidates | decision レコード | 人間未応答は放置可（supportedまでで運用可能な設計にする） |

### 2.3 グローバル停止条件（コードが強制）

- 日次コスト上限到達 → その日は S0 で待機
- 未解決 contradiction が閾値（例: アクティブclaimの10%）超過 → 新規探索を止め、矛盾解消questionのみ生成
- 監査ログの quote照合失敗率が7日移動平均で15%超 → **全自動昇格を停止**し人間へ警報（モデル劣化・プロンプト回帰の検知）

---

## 3. 昇格・降格基準（`config/promotion.yaml` で数値管理、判定は決定論）

```text
candidate → supported → verified
    ↓            ↓          ↓
   (棄却)      disputed ←──┘
                  ↓
               retired
```

| 遷移 | 基準（すべてコードが機械判定） |
|---|---|
| → **candidate** | S7バリデータ通過（quote実在、1文正規化、出典あり） |
| candidate → **supported** | supports evidence ≥ 2、かつ **independence_group が2以上**（後述）、かつ refutes evidence = 0、かつ source_class に `blog`以外が1件以上 |
| supported → **verified** | supports ≥ 3・independence_group ≥ 3、うち1件は `primary_paper` / `standard` / `gov`、S6の反証検索が実行済みで棄却されなかった記録あり、**＋人間承認（decision）** |
| 任意 → **disputed** | refutes evidence が1件でも登録された瞬間に自動遷移（verifiedでも即disputed。「事後の反証は昇格実績に勝つ」） |
| disputed → 復帰 | 矛盾解消question の experiment 完了後、refutes側が撤回（supersedes）されれば元状態へ。解消不能なら conditions を分岐して claim を2つに分割（「Aは条件X下で真」「条件Y下で偽」） |
| → **retired** | (a) supersedes された、(b) staleness_date 超過かつ再検証experimentが2回 dead_end、(c) 人間判断。**retired は削除ではなく状態**。エッジも履歴も残す |

**independence_group の決定**：evidenceの独立性は決定論ルールで判定する — 同一 publisher_domain、同一著者、相互引用が判明している資料、同一プレスリリース起源は同一グループ。グループ判定に迷う場合のみAIが「非独立の疑い」を注釈し、保守側（同一グループ扱い）に倒す。

---

## 4. 過学習・偏り・自己引用・誤情報拡散の防止機構

| リスク | 具体的仕組み | 実装層 |
|---|---|---|
| **自己生成物の循環引用** | ① source_class=`self_generated` は evidence.source_id に指定不可（スキーマ制約）② output は `is_evidence_eligible: false` 固定 ③ S4取得時、snapshot本文と自システムの過去output群を n-gram照合し、**自分の文章がWebに転載されたもの**を検出して隔離 | スキーマ＋コード |
| **同一資料群への偏り** | `domains.yaml` の多様性クォータ：1つのclaimの根拠に占める単一 independence_group ≤ 50%。1つのquestionの探索で同一ドメイン取得 ≤ 40%。違反時はコードが追加探索を強制するか supported昇格を保留 | コード |
| **講義（入口）への過適合** | MIT講義は source_class=`lecture` で、**単独では supported の要件を満たせない**（独立資料必須）。講義は「概念候補の発見器」であり根拠系の主役にしない | 昇格基準 |
| **もっともらしい誤り** | ① quoteの文字列実在照合（S5）② 抽出AIと検証AIを**別モデル・別プロンプト**にする ③ `eval/traps.yaml`：意図的に混入させた既知の誤り主張（罠問題）を月次でパイプラインに流し、検出率を測る | コード＋評価 |
| **過学習（狭い成功パターンの反復）** | question生成時に origin の配分を強制：gap由来60% / contradiction由来25% / staleness由来15%。dead_end experiment との類似question は自動棄却 | コード |
| **古い知識の上書き** | 上書き禁止・supersedes のみ。staleness_date（claim種別ごとに既定値：規格=規格改定周期、論文知見=3年、講義概念=無期限）超過で再検証questionを自動生成 | スキーマ＋S1 |
| **API費用暴走** | `budget.yaml`：月額上限 → 日次上限（月額/30） → question単位上限（既定 $2）→ 1回のfetch/LLM呼び出し上限。**すべてラッパーライブラリで強制**し、超過はexceptionで即停止。監査ログから日次レポート自動生成 | コード |
| **外部実害** | 送信・公開・ログイン要求サイト・有料購入・robots.txt違反の可能性 → 実行前に decision（human approval）必須。承認キューが空応答でも読み取り系ループは継続 | コード |

---

## 5. エッジ設計 — 関係の種類を名前空間で分離

**全エッジ共通**：`provenance_evidence_ids` 必須（何を根拠にこのエッジを張ったか）。provenanceなしのエッジはバリデータが弾く。異なる名前空間のエッジ間で推論を連鎖させることを禁止する（例：類推エッジを辿って科学的含意を導かない）。

| 名前空間 | edge_type | 意味 | 張れる主体 |
|---|---|---|---|
| **sci:**（科学的関係） | `sci:causes`, `sci:enables`, `sci:contradicts`, `sci:refines`（条件を狭めて成立）, `sci:generalizes` | 主張間の論理・因果。**verified/supported の claim 間のみ**張れる | AI提案 → コード検証 → candidate状態のエッジとして保存（エッジ自体も昇格制度に乗る） |
| **cite:**（出典関係） | `cite:supports`, `cite:refutes`, `cite:qualifies`, `cite:derived_from`（concept←source） | evidence↔claim、資料の系譜。事実の帰属のみで論理関係を含まない | 抽出パイプライン（機械的） |
| **ana:**（類推） | `ana:analogous_to`, `ana:metaphor_for` | 分野横断の発想支援。**推論には使用禁止、question生成のヒントにのみ使用可** | AI自由（ただし低優先で表示） |
| **user:**（ユーザー判断） | `user:adopts`, `user:rejects`, `user:prioritizes`, `user:contextualizes`（案件文脈での限定採用） | 判断層。真偽ではなく採用の記録 | 人間のみ（decision経由） |
| **meta:**（システム管理） | `meta:supersedes`, `meta:duplicates`, `meta:generated_by`（output→使用claim） | 履歴・重複・生成系譜 | コードのみ |

**混同防止の要点**：「MIT講義がこの概念の出所である」は `cite:derived_from`、「この概念は正しい」は claim＋`cite:supports`、「ユーザーがこの方針を採る」は `user:adopts`——同じ一件の学びが**3本の異なるエッジ**に分解される。回答生成時、コードは名前空間別にエッジを取得し、AIプロンプトに「根拠(cite/sci)」「判断(user)」「発想(ana)」を別セクションで渡す。

---

## 6. 段階的ロードマップ

### Phase 0：最小実装（〜2週間、Codex/Claude Codeで構築可能）

- **決定論コード**：ledger追記・SQLite再構築・バリデータ・昇格判定・予算ラッパー・quote照合・views生成（Python、外部依存はsqlite3/httpx程度）
- **AI**：Claude Code / Codex を「S2, S3, S5, S6 の各ステップをCLIタスクとして実行するワーカー」として使う。ループのオーケストレーションは cron＋状態ファイルで、**エージェントフレームワーク不使用**
- 検索は汎用検索API 1本＋ arXiv/Crossref/標準化団体の公式API
- 人間承認は `views/review_queue.md` を見て CLI で decision 投入
- **RAGは全文埋め込み検索1本のみ**（探索層用）。GraphRAG的な複雑構成は入れない——グラフ照会はSQLで足りる規模から始める

### Phase 1：検証強化（1〜3ヶ月）

- 抽出AIと検証AIのモデル分離、罠問題の自動月次実行
- staleness再検証の自動question生成
- contradiction解消フロー（claim分割）の実装
- 評価ダッシュボード（§7の指標を週次自動集計）

### Phase 2：マルチエージェント化（3ヶ月〜、指標が安定してから）

- 役割分離：Auditor（S1-S2）/ Explorer（S3-S4）/ Extractor（S5）/ Skeptic（S6）を独立プロセス化し、**ledger経由でのみ通信**（直接対話させない＝合意の同調圧力を防ぐ）
- Skepticを複数モデルの多数決に
- hypothesis→experiment に「計算実験」（自前でコードを書いてシミュレーション検証）を追加。ただし実行はサンドボックス、結果は evidence（source_class=`experiment_internal`、独立資料1件分としてのみカウント）
- 移行条件：Phase 1で罠検出率>90%、quote照合失敗率<5%が2ヶ月継続

---

## 7. パイロットテーマと評価指標

### テーマ：**リチウムイオン電池の劣化機構と寿命予測**

選定理由：MIT OCW（電気化学・材料科学講義）に入口があり、**一次論文・公的資料（NASA/NREL公