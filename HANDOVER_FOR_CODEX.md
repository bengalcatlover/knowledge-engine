# Knowledge Engine 引き継ぎ書（Codex向け）

更新日: 2026-09-11

---

## 1. このシステムは何か

OOP的な構造で世界のあらゆるもの（知識・行動・物理・意味）を記述する**自律成長型知識基盤**。MIT OCW講義4,258本と、ユーザー自身の判断・開発経験を構造化し、根拠ある回答を生成する。

**核心思想**: 属人知（暗黙知）= クラスのインスタンス。科学知 = クラス定義。属人知を入力すると科学概念に紐づけ、使うたびに穴を検知して自律成長する。

行動規則の正本は `AI_BRAIN.md`。

---

## 2. 完了済みフェーズ

### Phase 0〜3-3（知識基盤構築）
- MIT OCW 4,258本の講義整形・35分野分類
- 概念カード K-0001〜K-0033（経済学10、CS10、数学/統計13）
- perspectives P-0001〜P-0004（ユーザーの4本柱ビジョン）
- OOP設計レビュー（Fable5+GPT-6 Astra）完了

### Phase 1（検索修復）— 完了
- BM25 AND→OR化 + フィールド別FTS + Gemini埋め込み + RRF統合
- **Recall@6: 6% → 100%**（50問評価セット）
- ファイル: `search_engine.py`, `eval_set.yaml`, `eval_recall.py`

### Phase 2（台帳層+ライフサイクル）— 完了
- 追記専用イベントログ（SQLite, append-onlyトリガー付き）
- ライフサイクル管理（draft→candidate→accepted→deprecated）
- 共活性化ログ記録（検索ごとに自動記録）
- Git SHA記録によるスナップショット
- ファイル: `kb.py`, `work/state.sqlite3`

### Phase 3（Facet/文脈+型付きエッジ）— 完了
- 33枚全てスキーマv2に移行（`schema_version: 2`, Relations構造化）
- 101本の型付きエッジ（type, confidence, epistemic_status付き）
- Facet解決 + 比喩遮断 + グラフ走査（確信度打ち切り）
- ファイル: `graph.py`, `migrate_v2.py`, `work/backup_v1/`

---

## 3. 次にやること（Phase 4: 共活性化マイニング）

### 目的
使用ログから「概念の穴」を自動検出し、CompositionCard候補を生成する。

### 依存
- Phase 2のイベントログに数百クエリ分のログが蓄積されていること
- （律速はログ蓄積。まず実際に検索を使い込む期間が必要）

### 実装内容
1. **共活性化ペア抽出**: `kb.py coactivation --min-freq 3` は実装済み。データが必要
2. **noveltyスコアリング**: 共通上位概念を持たないカードセットに高スコア
3. **CompositionCard候補生成**: `_inbox/`に自動生成、人間承認ゲート
4. **`emerges_from`関係**: `has_part`とは別。継承推論を遮断するアノテーション

### 参考設計
- `work/reply_proceed_fable5.txt` — Fable5の実装ロードマップ
- `work/reply_proceed_gpt6astra.txt` — GPT-6 Astraの実装ロードマップ

### 重要ルール
- 検索回数は真理の証拠にしない
- AI生成カードはそのカード自身の独立証拠にならない
- 同じ元資料を引用する複数生成物は1証拠群として数える
- 自動生成連鎖は深度2で停止、人間ゲートを挟む

---

## 4. Phase 5以降の予定

| Phase | 内容 | 工数 | 依存 |
|---|---|---|---|
| 5 | TruthValue型(Boolean/Probability/Fuzzy/Interval/Unknown) + model_ref実行 | 2週 | Phase 3 |
| 6 | CompositionCard + 創発Claim（既知現象5つで検証） | 3〜4週 | Phase 4+5 |

詳細設計は `work/reply_fable5.txt`（苦しい領域の解法）と `work/reply_gpt6astra.txt` に保存済み。

---

## 5. ファイル構成

```
knowledge-engine/
├── AI_BRAIN.md                    ← 行動規則の正本
├── KNOWLEDGE_ARCHITECTURE.md      ← 5層アーキテクチャ設計書
├── HANDOVER_FOR_CODEX.md          ← この引き継ぎ書
│
├── search_engine.py               ← ハイブリッド検索（BM25+Gemini埋め込み+RRF）
├── kb.py                          ← 統治ツール（イベントログ、ライフサイクル、共活性化）
├── graph.py                       ← 概念グラフ（Facet解決、比喩遮断、グラフ走査）
├── eval_set.yaml                  ← 50問評価セット
├── eval_recall.py                 ← Recall@K計測スクリプト
├── migrate_v2.py                  ← v1→v2移行（完了済み）
├── brain_rag.py                   ← 旧検索（OR化済み、後方互換）
├── mitocw_rag.py                  ← MIT OCW講義検索
├── development_rag.py             ← 開発ソース検索
│
├── concepts/
│   └── _inbox/K-0001〜K-0033.md   ← 全33枚（schema_version:2、Relations構造化済み）
├── perspectives/P0001〜P0004.md   ← ユーザーの4本柱ビジョン
├── accepted/                      ← 一次資料で検証済み（空）
├── candidates/                    ← 未検証の調査候補（空）
│
├── _meta/
│   ├── counters.yaml              ← ID連番管理（concept=33, perspective=4）
│   └── schemas/                   ← スキーマ定義
│
├── work/
│   ├── search.sqlite3             ← フィールド別FTSインデックス（37文書）
│   ├── state.sqlite3              ← イベントログ+共活性化DB
│   ├── embeddings.npz             ← Gemini埋め込み（37文書×3072次元）
│   ├── brain.sqlite3              ← brain_rag用FTS（旧、37文書）
│   ├── mitocw.sqlite3             ← MIT OCW FTS（16,532チャンク）
│   ├── backup_v1/                 ← v1カードバックアップ
│   ├── reply_fable5.txt           ← Fable5の設計提案（苦しい領域の解法）
│   ├── reply_gpt6astra.txt        ← GPT-6 Astraの設計提案
│   ├── reply_proceed_fable5.txt   ← Fable5の実装ロードマップ
│   └── reply_proceed_gpt6astra.txt← GPT-6 Astraの実装ロードマップ
│
├── indexes/fields/                ← 35分野別MIT講義インデックス
└── research-engine/               ← 自動研究パイプライン（未稼働）
```

---

## 6. コマンドリファレンス

### 検索（search_engine.py）
```bash
cd knowledge-engine
python search_engine.py --include-inbox build          # FTSインデックス構築
python search_engine.py --include-inbox embed          # Gemini埋め込み生成（API通信あり）
python search_engine.py search "損失回避"              # ハイブリッド検索
python search_engine.py search "損失回避" --no-vectors # BM25のみ（API通信なし）
```

### 統治（kb.py）
```bash
python kb.py init                                      # state DB初期化
python kb.py log-query "クエリ" K-0001,K-0003          # クエリログ記録
python kb.py promote K-0001                            # candidate→accepted（ファイル移動+イベント記録）
python kb.py deprecate K-0012                          # deprecated化
python kb.py status K-0001                             # カード状態+履歴表示
python kb.py events --limit 20                         # イベント一覧
python kb.py coactivation --min-freq 3                 # 共活性化ペア分析
```

### グラフ（graph.py）
```bash
python graph.py load                                   # グラフ読み込み+統計
python graph.py traverse K-0009 --context science --depth 2  # グラフ走査
python graph.py resolve K-0008 --context business      # Facet解決
```

### 評価（eval_recall.py）
```bash
python eval_recall.py                                  # ハイブリッド検索のRecall@6
python eval_recall.py --no-vectors                     # BM25のみのRecall@6
python eval_recall.py --verbose                        # 各問の詳細表示
python eval_recall.py --type scenario                  # scenario問のみ
```

### 旧検索（brain_rag.py, mitocw_rag.py）
```bash
python brain_rag.py --include-inbox build
python brain_rag.py --include-inbox search "keyword" --limit 6
python mitocw_rag.py search "keyword" --limit 6
```

---

## 7. 設計上の不変ルール

1. **ハレーションゼロ**: Source Refsに架空引用を絶対に書かない。検索→引用確定→生成の順序厳守
2. **三層リンク**: perspectives → concepts → MIT OCW講義
3. **カードは知識そのものではなくモデルへのハンドル/インターフェース**
4. **すべての主張に確信度・出所・文脈を付ける**
5. **自動生成は即時採用せず候補層を通す**（_inbox/ → ユーザー確認 → concepts/）
6. **比喩遮断**: science文脈ではepistemic_status=analogyのエッジを遮断
7. **emerges_from は継承推論を遮断**（部分の性質から全体を推論しない）
8. **正準文脈3つ**: science / business / everyday
9. **aliasは同義語のみ**。独自定義を持つものは別概念カードにする
10. **コスト意識**: Gemini/haiku優先。Fable5/GPT-6 Astraは設計レビュー時のみ

---

## 8. 概念カード一覧（33枚）

### 経済学（F-ECON）: K-0001〜K-0010
| ID | canonical_name |
|---|---|
| K-0001 | メカニズムデザイン |
| K-0002 | オークション理論と収入等価性 |
| K-0003 | ナッシュ均衡と戦略的相互作用 |
| K-0004 | 情報の非対称性とスクリーニング・シグナリング |
| K-0005 | ナッジとデフォルト効果 |
| K-0006 | 双曲割引と時間選好 |
| K-0007 | RCT（ランダム化比較試験）と因果推定 |
| K-0008 | 外部性と市場の失敗 |
| K-0009 | 参照点依存性と損失回避 |
| K-0010 | インセンティブ両立性 |

### CS（F-EECS）: K-0011〜K-0020
| ID | canonical_name |
|---|---|
| K-0011 | フィードバック制御とクローズドループシステム |
| K-0012 | 状態機械とオートマトン理論 |
| K-0013 | グラフ探索アルゴリズム（BFS/DFS/A*） |
| K-0014 | 確率的推論とベイズネットワーク |
| K-0015 | 動的計画法 (Dynamic Programming) |
| K-0016 | 分散合意アルゴリズム (Distributed Consensus) |
| K-0017 | 情報理論と表現圧縮 |
| K-0018 | 最適化理論 (Optimization Theory) |
| K-0019 | 機械学習と学習アルゴリズム |
| K-0020 | 暗号技術とセキュリティ設計 |

### 数学/統計: K-0021〜K-0033
| ID | canonical_name |
|---|---|
| K-0021 | 線形代数と部分空間分解 |
| K-0022 | 確率分布と大数の法則 |
| K-0023 | 勾配降下法と収束解析 |
| K-0024 | マルコフ連鎖と定常分布 |
| K-0025 | 最尤推定と推定量の性質 |
| K-0026 | 仮説検定と統計的意思決定 |
| K-0027 | フーリエ解析と周波数表現 |
| K-0028 | テイラー展開と局所近似 |
| K-0029 | 回帰分析と最小二乗法 |
| K-0030 | 主成分分析と次元削減 |
| K-0031 | モンテカルロ法と確率的シミュレーション |
| K-0032 | 条件数と数値安定性 |
| K-0033 | 確率過程と時系列の定常性 |

---

## 9. API情報

| 用途 | プロバイダー | モデル |
|---|---|---|
| 埋め込み | Gemini | gemini-embedding-001（ほぼ無料） |
| 機械的作業 | Gemini | gemini-3.1-flash-lite |
| 設計レビュー | Anthropic | claude-fable-5 |
| 設計レビュー | OpenAI | gpt-5.6-sol |

APIキーは `ask_llm.py`（`C:\Users\akira\Documents\f3\reports\tri_review_20260718\ask_llm.py`）に記載。

---

## 10. 検索品質ベースライン

| 検索方式 | Recall@6 |
|---|---|
| BM25 AND（旧） | 6.0% |
| BM25 OR | 30.0% |
| ハイブリッド（BM25+Gemini+RRF） | **100.0%** |

カテゴリ別（ハイブリッド）:
- direct: 100% (17/17)
- paraphrase: 100% (13/13)
- scenario: 100% (15/15)
- cross: 100% (5/5)
