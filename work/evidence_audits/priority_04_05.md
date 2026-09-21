# 優先カード 4–5 の根拠監査

承認判断の材料。カード本文と承認状態は変更しない。

## K-0005 — ナッジとデフォルト効果

- 評価質問: E-05, E-06
- 検索語: `Default Effect Nudge`
- [MIT OCW: Lecture 20, Malleability and Inaccessibility of Preferences](https://www.youtube.com/watch?v=Z0vdSf8m13k)
  - 断片: "it does not impose coercion or material incentives"
  - 断片: "Nudges keep choices fully available and free"
  - 確認対象: ナッジを、報酬・罰・選択肢の削除と区別しているか。
  - 確認対象: 効果があるのは限界的な意思決定者などの条件付きであり、全員に効くと一般化していないか。

## K-0012 — 状態機械とオートマトン理論

- 評価質問: E-10, E-14
- 検索語: `Finite State Automaton`
- [MIT OCW: Introduction, Finite Automata, Regular Expressions](https://www.youtube.com/watch?v=9syvZr-9xwk)
  - 断片: "A finite automaton makes a binary decision for every string"
  - 確認対象: 有限状態機械が扱える状態・入力・遷移・受理条件を、業務状態遷移に写す際に省略していないか。
- [MIT OCW: Pushdown Automata, Conversion of CFG to PDA](https://www.youtube.com/watch?v=m9eHViDPAJQ)
  - 断片: "A grammar may allow multiple parse trees for the same string"
  - 確認対象: スタックや無制限の履歴が必要な問題を、有限状態機械だけで表せると誤認していないか。

## 次の処置

`approved`、`revise`、`merge_candidate`、`defer` のいずれかを人間が記録する。概念範囲または関係型に迷う箇所は二者レビューへ送る。
