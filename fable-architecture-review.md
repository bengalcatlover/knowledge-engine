# レビュー結果

## 1. 重大な穴（重要度順）

### 穴1: スキルがClaude Code専用で、Codex側の手順が薄い（再現性の根幹が崩れている）
`SKILL.md`にはAI_BRAIN.mdにない規則が複数ある：**「講義全文を会話へ読み込まない」「検索が弱いときの再検索戦略」「記事のセクション順」**。CodexはSkills機構を持たないため、これらの規則はCodexでは一切効かない。「大量資料を丸ごと詰めて浅くなる問題を避ける」という目的の核心ルールが、片方のエージェントにしか届いていない。

### 穴2: 検索結果のスキーマが未定義で、URL捏造の温床がある
「講義タイトルと元動画URLを記録する」と要求しているが、`mitocw_rag.py search`の出力にタイトル・URLが含まれる保証がどこにも書かれていない。字幕チャンク→動画URLの対応がメタデータとして返らないなら、エージェントは**URLをもっともらしく生成する**。引用規則が逆に捏造を誘発する設計になっている。

### 穴3: `perspectives/` の定義とAI起草ノートが矛盾している
`perspectives/`は「**ユーザーの**問い、開発経験、仮説、判断」であり「外部の事実と混同しない」と定義した直後に、「概念ノートを増やすとき」でAIが同じディレクトリに書き込む運用を許している。数十回の依頼後、`perspectives/`はAIの推測とユーザーの本物の判断が区別不能になり、「ユーザーの解釈として使う」という前提自体が壊れる。

### 穴4: 正本が実質3つに分裂している
記事の書き方が `AI_BRAIN.md`（5項目）、`SKILL.md`（6項目・順序指定）、さらに未添付の `mitocw-article-workflow.md` / `external-brain.md` に分散。しかも項目が微妙に違う（SKILL側には「参照資料」がある）。片方だけ更新すればドリフトする。

### 穴5: パス参照が壊れている・壊れやすい
- `SKILL.md`の`../../AI_BRAIN.md`：スキルが`.claude/skills/mitocw-knowledge/`にあるなら`../../`は`.claude/`直下かプロジェクトルートで、`knowledge-engine/AI_BRAIN.md`に届かない可能性が高い。
- `C:\Users\akira\Anaconda3\python.exe`のハードコード＋PowerShell前提：Codexのサンドボックスやシェル環境で壊れる。

### 穴6: `build`の実行方針が不一致
AI_BRAIN.mdは手順4で毎回`build`→`search`。SKILL.mdは「整形処理が進行中なら」のみ`build`。エージェントごとに実行コストと挙動が変わる。

### 穴7: 発火条件の非対称
CLAUDE.mdは`@import`で**常時**全文注入。AGENTS.mdは「thinking, research...を含む依頼なら読む」という条件付きで、Codexが読み飛ばす余地がある。同じ品質を出す前提が最初のターンで既に非対称。

---

## 2. 最小で強い設計

```
project-root/
├── AGENTS.md          # ポインタ＋Codex固有差分のみ（10行以内）
├── CLAUDE.md          # @import のみ（現状維持でよい）
├── .claude/skills/mitocw-knowledge/SKILL.md  # 発火条件＋AI_BRAINへの委譲のみ
└── knowledge-engine/
    ├── AI_BRAIN.md    # 唯一の正本。全ルールをここに集約（150行以内を維持）
    ├── accepted/  candidates/  outputs/
    └── perspectives/
        ├── _inbox/    # AI起草ノート（author: ai-draft）
        └── *.md       # ユーザー承認済みのみ
```

**4つの柱：**

1. **共通Markdown正本**：ルールはAI_BRAIN.mdだけに書く。AGENTS.md/CLAUDE.md/SKILL.mdは「読め」＋ツール固有の差分だけ。`mitocw-article-workflow.md`と`external-brain.md`は内容をAI_BRAIN.mdに吸収して削除するか、AI_BRAIN.mdから一方向リンクにする。CLAUDE.mdが常時全文注入する以上、AI_BRAIN.mdの短さ自体が設計要件。

2. **検索**：`mitocw_rag.py`の出力を `[source_id] lecture_title | video_url | chunk（〜500字）` の固定形式にし、AI_BRAIN.mdに「**URLは検索結果メタデータからのみ転記。無ければ『URL未確認』と明記**」と書く。`build`は「資料を追加・整形した直後のみ」に統一。`mitocw-txt/`配下の直接読み込みは全面禁止し、検索ヒットチャンク（上限6件）のみ許可——これがコンテキスト肥大の唯一で十分な防波堤。

3. **概念ノート**：front matterに`author: user | ai-draft`を必須化。AI起草は`perspectives/_inbox/`にのみ書き、ユーザーが読んで書き直し`status: evolving`に上げたものだけ`perspectives/`直下へ移動。エージェント側の規則は「`_inbox/`のノートはユーザーの解釈として引用してはならない」。

4. **記事出力**：`outputs/`のfront matterに`sources:`（source_id/URLのリスト）と`perspectives:`（使用したノートのパス）を必須化。「講義原文の連続引用は2文まで、それ以上は自分の言葉で抽象化」を明文化——「要約を直接転載しない」より検証可能な規則になる。

---

## 3. Codex / Claude Code差分による実装上の問題

| 差分 | 問題 | 対処 |
| --- | --- | --- |
| Skills機構 | SKILL.mdの独自ルールがCodexに届かない | SKILL.mdを空洞化しAI_BRAIN.mdへ全移管。SKILLは発火トリガーとして残す |
| `@import` vs 条件付き参照 | Claudeは毎ターン全文保持、Codexは読み忘れ得る | AGENTS.mdを無条件の「最初に必ず読む」に変更 |
| 常時注入のコスト | AI_BRAIN.mdが肥大するとClaude側で毎ターン課税 | 正本を短く保ち、雛形類は別ファイル参照に |
| シェル環境 | CodexはPowerShell/絶対パス前提が壊れうる | `python mitocw_rag.py ...`＋「cwdは`knowledge-engine/`」に統一。絶対パスが必要なら`run_rag.ps1`/`run_rag.sh`のラッパー2本を置く |
| 相対パス解決 | SKILL.mdの`../../AI_BRAIN.md`はスキル配置依存 | プロジェクトルート基準の`knowledge-engine/AI_BRAIN.md`と書く |
| コマンド承認 | Codexは`build`のような重い書き込みコマンドで承認フローに引っかかる | `build`を例外運用にすることで頻度自体を下げる |

---

## 4. そのまま適用できる修正案

**AGENTS.md（全置換）：**

```md
# Shared external brain

Before doing anything substantive, read `knowledge-engine/AI_BRAIN.md` and follow it.
It is the single source of truth for source boundaries, retrieval, and output rules.

Codex-specific notes:
- There is no Skills mechanism here. The retrieval procedure in AI_BRAIN.md is the canonical one.
- Run all RAG commands from `knowledge-engine/` using `python mitocw_rag.py ...` / `python development_rag.py ...`.
- Never open files under `mitocw-txt/` directly. Use search results only.
```

**SKILL.md（本文を全置換、front matterは維持）：**

```md
# MIT OCW外部知能

`knowledge-engine/AI_BRAIN.md`が唯一の正本である。検索手順・出力規則・引用規則はすべてそこに従う。

このスキル固有の注意:
- 実行場所は`knowledge-engine/`。`python mitocw_rag.py search "keywords" --limit 6`
- 検索が弱いときは、専門語・講義名・同義語で最大3回まで再検索する。
```

**AI_BRAIN.md への追記（3ブロック）：**

```md
## 検索結果の使用規則

- `mitocw-txt/`配下のファイルを直接開いてはならない。使えるのは検索ヒットのチャンクのみ（依頼あたり最大6件）。
- 講義タイトルとURLは、検索結果のメタデータからのみ転記する。メタデータに無ければ「URL未確認」と明記し、URLを生成しない。
- `build`は資料を追加・再整形した直後のみ実行する。通常の依頼では`search`のみ。
```

```md
## 概念ノートの帰属（「概念ノートを増やすとき」を差し替え）

- AIが起草するノートは`perspectives/_inbox/`に置き、front matterに`author: ai-draft`を付ける。
- `_inbox/`のノートを「ユーザーの解釈」として出力に引用してはならない。
- ユーザーが内容を確認・書き直したものだけを`perspectives/`直下へ移し、`author: user`に変える。
```

```md
## outputs/の必須front matter

---
sources: []        # 検索結果のsource_id / URL
perspectives: []   # 使用したperspectivesノートのパス
status: draft
---
講義原文の連続引用は2文まで。それ以上は自分の言葉で抽象化して書く。
```

**AI_BRAIN.md からの削除・変更：**
- 手順3・4のコマンド例から`C:\Users\akira\Anaconda3\python.exe`を削除し、`python`＋「cwdは`knowledge-engine/`」に統一。
- 手順4の「MIT索引を更新し」を「（資料追加直後を除き）索引更新は不要。検索のみ行う」に変更。

**追加で必要な非Markdown作業（1点だけ）：** `mitocw_rag.py`の検索出力に`title`と`video_url`を含める。これが無い限り、Markdown側の引用規則は執行不能。