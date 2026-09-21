# 統合Blueprint v1 — OOP型知識創造基盤

承認日: 2026-09-12
根拠: Fable 5 レビュー (review_20260912_fable.txt) + GPT-6 Astra レビュー (review_20260912_astra.txt)
判定方式: 二者一致のみ採用。不一致は defer。

---

## 1. 設計原則（不変条件）

以下は変更不可。変更するにはFable+Astraの再一致判定+人間承認が必要。

1. **ハレーションゼロ**: locator・版・content_hashがない引用は公開不能（fail-closed）
2. **カードはモデルへのハンドル**: 知識そのものではない
3. **すべての主張に確信度・出所・文脈**: 離散的認識状態（unverified/source_supported/formally_verified/empirically_supported/contradicted）を使用。数値confidenceは根拠経路数だけからは計算しない
4. **自動生成は候補層を通す**: draft→ready→approved。proposedからcanonicalへ直接遷移不可
5. **比喩遮断**: science文脈ではepistemic_status=analogyのエッジを推論から遮断
6. **emerges_from遮断**: 継承推論を遮断
7. **HYP隔離**: 応用仮説はcanonicalノードから根拠エッジを受けない。検証通過まで隔離
8. **版単位DAG**: 根拠依存グラフは版単位で有向非巡回。自己支持は禁止
9. **エッジの存在 ≠ 根拠としての有効性**: 各エッジ型に推論効果・失効伝播規則を定義

---

## 2. 5層定義

5層は全知識が直列通過する存在論ではなく、主張種別ごとに異なる根拠経路を持つガバナンス/抽象化ビュー。

| 層 | 定義 | ノードクラス | サブタイプ(Fable語彙) | 層固有の必須属性 |
|---|---|---|---|---|
| **L1 基礎科学** | 経験に依存せず証明・定義で閉じる形式体系 | `FormalPrinciple` | AXM(公理), THM(定理), DEF(定義) | statement_formal, proof_source, assumptions[] |
| **L2 科学** | 反証条件を持つ経験的理論・法則・手法 | `Theory`, `ScopedLaw`, `Method` | THY, LAW, MTH | claim, falsification_condition(空なら登録拒否), formal_basis[], domain_of_validity |
| **L3 宇宙** | 特定ドメインの世界モデル（因果構造の合成体） | `WorldModel` | WM | domain, scope, instantiates[], causal_claims[], boundary_conditions[], unmodeled_factors[] |
| **L4 オブジェクト** | 観測・操作・再同定できる具体的対象 | `Entity`, `System`, `Process`, `Artifact` | — | identity, version, state, observation_interface, operation_interface |
| **L5 問い・行動・検証** | エンジンの駆動部 | `Question`, `Action`, `Verification` | Q, HYP, ACT, VER | Q: target+hypothesis+criteria / ACT: input+procedure+stop_condition / VER: observation+comparison+judgment+limitations |

### CAU/BNDの扱い
常に独立ノードにはしない。再利用・版管理・個別反証が必要な場合だけWMから昇格。

---

## 3. 根拠ストア（5層外）

**判定: Astra案採用（Fable・Astra一致）**

根拠ペイロードは5層ノードとは別のストアに置く。

```yaml
evidence:
  evidence_id: string
  kind: source_excerpt | observation | execution_log | proof_certificate
  source_uri: string          # DOI/URL
  source_version: string
  locator: string             # ページ・節・時刻・ログ行
  content_hash: string        # fail-closed: なければ公開不能
  excerpt_or_artifact_ref: string
  origin_group: string        # 同一起源の証拠を独立証拠と数えない
  reliability_grade: A | B | C  # Fable案から吸収（A:一次査読済/B:公式二次/C:実務記録）
  limitations: []

support_assessment:
  assessment_id: string
  evidence_id: string
  target: node_id@revision#claim_id
  support_role: definition | premise | derivation | observation | counterexample
  rationale: string
  assessor: string
  assessed_at: datetime
```

**重要**: LLMの要約・合意・再生成は独立した根拠にならない。出典が主張を含意しなければ支持とは認めない。

---

## 4. 共通データ契約

**判定: Astra契約 + Fable型語彙をサブタイプとして載せる（一致）**

```yaml
node:
  id: string
  revision: integer
  layer: foundation | science | universe | object | practice
  type: enum                  # Astraクラス (FormalPrinciple, Theory, etc.)
  subtype: enum | null        # Fable語彙 (AXM, THM, THY, etc.)

  admission:
    kind: derived | imported_reference

  scope:
    domain: string
    population_or_system: string
    canonical_context: science | business | everyday  # 既存の正準文脈を吸収
    conditions: []
    exclusions: []

  claims:
    - claim_id: string
      statement: string
      kind: definition | theorem | empirical | abstraction | application_hypothesis
      assumptions: []
      evidence_refs: []       # → evidence storeへの参照
      derivation_ref: null
      epistemic_status: unverified | source_supported | formally_verified | empirically_supported | contradicted

  lifecycle:
    status: draft | ready | approved | blocked | stale | superseded
    approval_scope: null | reference_use | model_assertion | test_plan
    approval_record: null

  owner: string
  created_at: datetime
  updated_at: datetime
```

---

## 5. エッジ意味論

**判定: Astra原則（存在≠有効性）+ Fable区別を保持（一致）**

### 根拠構造エッジ（推論・失効に影響）

| エッジ型 | 方向 | 意味 | 失効伝播 | 必須属性 |
|---|---|---|---|---|
| `ABSTRACTS_FROM` | 上位→下位の導出元 | 根拠付き抽象化 | 下位変更→上位stale | derivation_ref, scope変換 |
| `DERIVES_FROM` | L1→L1 | 形式的導出 | 前提変更→結論stale | proof_ref |
| `FORMALIZED_BY` | L2→L1 | 理論の形式的基盤 | L1変更→L2 stale | — |

### 参照・対応エッジ（推論に使わない）

| エッジ型 | 方向 | 意味 | 失効伝播 | 備考 |
|---|---|---|---|---|
| `HAS_SCOPED_INSTANCE` | 理論→局所モデル | 具体化先を示す | なし | 一般理論の正しさを証明しない |
| `IMPLEMENTED_BY` | モデル→実装 | 実装対応 | 実装変更→モデル要再検証 | — |
| `GUIDES_TEST_DESIGN` | 手法→問い | 検証設計の参照 | なし | 結果を支持しない |
| `CHECKS` | 検証→対象 | 検査対象を指す | なし | 検査結果≠合格 |

### ワークフローエッジ

| エッジ型 | 方向 | 意味 |
|---|---|---|
| `ABOUT` | Q→U/O | 問いの対象 |
| `PLANS` | Q→A | 行動計画 |
| `EXECUTES_ON` | A→O@version | 実行対象 |
| `PRODUCES` | A→V | 検証結果の生成 |
| `ANSWERS` | V→Q#claim | 問いへの回答 |
| `RAISES` | O→Q | 新しい問いの発生 |

### 全層共通エッジ

| エッジ型 | 意味 | 失効伝播 |
|---|---|---|
| `CONTRADICTS` | 反証・不整合 | 対象をblocked/staleに |
| `SUPERSEDES` | 旧版の置換（旧版は削除しない） | 旧版をsuperseded |

### 廃止・非採用

- `evidences` → support_assessmentに置換（エッジではなく根拠ストアのレコード）
- `instantiates` → `HAS_SCOPED_INSTANCE`に統合（逆エッジの二重保存禁止）
- 逆関係は表示時に生成。双方向エッジを物理保存しない

---

## 6. 状態遷移（Policy Engine）

**実際に状態を書き換えるのはpolicy_engineだけ。**

```yaml
transitions:
  draft -> ready:
    requires:
      - schema_valid
      - mandatory_fields_present
      - provenance_resolved
      - haiku_audit_passed
      - deterministic_checks_passed

  draft|ready -> blocked:
    trigger:
      - missing_evidence
      - scope_violation
      - failed_test
      - budget_or_permission_violation

  ready -> approved:
    requires:
      - astra_signed_decision
      - all_invariants_pass
      - human_approval_if_required

  approved -> stale:
    trigger:
      - dependency_changed
      - source_retracted
      - accepted_counterexample
    executor: policy_engine
```

### 承認の重さの層別化（Fable案の滞留リスク緩和策）

| approval_scope | 承認プロセス | コスト |
|---|---|---|
| `reference_use` | 自動検査のみ（Haiku lint通過） | 低 |
| `model_assertion` | Haiku監査 + Astra最終判定 | 高 |
| `test_plan` | Haiku監査 + Astra判定 + 人間承認 | 最高 |

---

## 7. エージェント契約

| エージェント | 役割 | 許可される変更 | 禁止 |
|---|---|---|---|
| **Fable 5** | スキーマ設計、再帰ラウンド設計 | DesignProposal登録（人間承認後に有効化） | 日常の出典収集、ノード大量生成、自己承認 |
| **GPT-6 Astra** | 新規上位抽象・最終公開差分の判定 | Approve/Reject/RequestRevision（版・範囲固定） | 常時探索、根拠代筆、自己修正の即承認 |
| **Gemini Flash Lite** | 出典取得、抽出、正規化、局所提案 | draft作成・更新、証拠候補追加 | approved変更、仮説の事実化 |
| **Haiku** | 出典照合、型・前提・範囲の監査 | AuditResult登録、ready/blocked遷移要求 | 最終承認、根拠のない補完 |

---

## 8. 既存資産との互換

### P→K→Dの扱い
- P(perspectives) → 文脈・解釈・視点の互換ビュー
- K(concepts) → ノード/claimハンドルへの互換ビュー
- D(data/sources) → evidence storeまたはartifactへの互換ビュー
- 廃棄しない。legacy viewとして公開

### 既存33カードの移行方針
- 一括変換NG。MVP経由の逐次昇格で移行
- K-IDは安定ハンドルとして残す
- 理論と応用の混在は分割（application_hypothesisのHYP分離）
- 既存confidence値は「未検証の申告値」に降格
- 移行中は旧カードをlegacy viewで参照可能

---

## 9. 成功指標

蓄積量ではなく能力を測る。

1. 問いに対し「回答可能/未検証/前提外」を正しく分けられるか
2. 結論を出典・計算・観測まで再現できるか
3. 反例や根拠撤回で結論を適切に修正できるか
4. draft→ready中央値48時間以内（滞留SLO）
5. proposed滞留数の上限監視

---

## 10. 既存エッジ型 → 新語彙の写像表

### 設計時の想定エッジ型（graph.py由来）

| 旧エッジ型 | 新エッジ型 | 変換方式 | 備考 |
|---|---|---|---|
| `is_a` | `ABSTRACTS_FROM` | 決定的 | 方向注意（上位→下位） |
| `has_part` | scope内のclaim分割 | 要人手審査 | ノード内claimに吸収される場合あり |
| `depends_on` | `FORMALIZED_BY` or `ABSTRACTS_FROM` | 要人手審査 | 形式依存か経験依存かで分岐 |
| `uses` | `GUIDES_TEST_DESIGN` or `IMPLEMENTED_BY` | 要人手審査 | 用途による |
| `contrasts_with` | `CONTRADICTS` or scope exclusion | 要人手審査 | 反証か対比かで分岐 |
| `isomorphic_to` | 廃止候補 or 注釈 | 要人手審査 | 推論効果なし、表示用のみ |
| `supersedes` | `SUPERSEDES` | 決定的 | そのまま |

### 実データのエッジ型（カード内Relations、107本）

| 旧エッジ型 | 出現数 | 新エッジ型 | 変換方式 | 備考 |
|---|---|---|---|---|
| `related` | 67 | 要個別判定 | 要人手審査 | 意味が曖昧。推論効果なしの注釈か、実質prerequisite/complementかを個別判定 |
| `complement` | 26 | scope注釈 or `HAS_SCOPED_INSTANCE` | 要人手審査 | 補完関係。多くは推論効果なし |
| `prerequisite` | 9 | `FORMALIZED_BY` or `ABSTRACTS_FROM` | 要人手審査 | 前提依存。形式か経験かで分岐 |
| `specialization` | 3 | `HAS_SCOPED_INSTANCE` | 決定的 | 特化関係 |
| `contrast` | 1 | `CONTRADICTS` or scope exclusion | 要人手審査 | 反証か対比か |
| `application_of` | 1 | `HAS_SCOPED_INSTANCE` | 決定的 | 適用関係 |

決定的変換可能: specialization, application_of（2型、4本）
要人手審査: related, complement, prerequisite, contrast（4型、103本）
