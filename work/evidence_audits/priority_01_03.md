# 優先カード 1–3 の根拠監査

この文書は承認判断の材料であり、カード本文や承認状態を変更しない。検索断片の出典URLと、カードの中核主張に直接関係する最小引用だけを記録する。

## K-0007 — RCT（ランダム化比較試験）と因果推定

- 評価質問: E-05, E-07, E-08
- 検索語: `Randomized Controlled Trial`
- [MIT OCW: 17. Reinforcement Learning, Part 2](https://www.youtube.com/watch?v=zdotUAxiPGM)
  - 断片: "the average treatment effect is inherently comparative"
  - 確認対象: 比較対象と無作為化・反実仮想の説明が、カード内で混同されていないか。
- [MIT OCW: 15. Causal Inference, Part 2](https://www.youtube.com/watch?v=g5v-NvNoJQQ)
  - 断片: "Causal inference from observational data aims to estimate the impact of an intervention"
  - 確認対象: 観察データでは仮定が必要なこと、交絡・モデル仮定の限界をカードが明記しているか。

## K-0010 — インセンティブ両立性

- 評価質問: E-01, E-03
- 検索語: `Incentive Compatibility`
- [MIT OCW: Lecture 11, Contracts and Mechanism Design](https://www.youtube.com/watch?v=cAFh3oWw6Vc)
  - 断片: "The key is the incentive constraint"
  - 確認対象: 真実申告を促す制約と、単なる報酬設計・一般的な動機付けを区別しているか。
- 同じ講義断片には複数時点の申告履歴と制約もある。
  - 確認対象: 動的な適用を主張する箇所があれば、単発モデルの結論を過剰に一般化していないか。

## K-0003 — ナッシュ均衡と戦略的相互作用

- 評価質問: E-02, E-03
- 検索語: `Nash Equilibrium`
- [MIT OCW: Lecture 5, Nash Equilibrium](https://www.youtube.com/watch?v=ftCXguW2k4o)
  - 断片: "both players are playing a best response to each other's strategy"
  - 確認対象: 均衡を最適・望ましい・協力的な結果として誤記していないか。
- [MIT OCW: Lecture 8, Backward Induction](https://www.youtube.com/watch?v=VHex0a2JFWI)
  - 断片: "every extensive form game with perfect information has a pure strategy Nash equilibrium"
  - 確認対象: 完全情報の逐次ゲームという条件を、同時手番や不完全情報の場面へ無条件に拡張していないか。

## 次の処置

各カードを `approved` にするか、具体的な修正箇所を `revise` として記録する。判断に迷う主張範囲または関係型は、Fable 5 と GPT-6 Astra の二者レビューへ送る。
