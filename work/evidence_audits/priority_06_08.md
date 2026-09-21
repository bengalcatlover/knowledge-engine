# 優先カード 6–8 の根拠監査

承認判断の材料。カード本文と承認状態は変更しない。

## K-0015 — 動的計画法

- 評価質問: E-11, E-13
- 検索語: `Dynamic Programming`
- [MIT OCW: Dynamic Programming II](https://www.youtube.com/watch?v=ENyox7kNKeY)
  - 断片: "Define subproblems"、"Relate subproblem solutions with a recurrence"
  - 確認対象: 部分問題、再帰関係、計算結果の再利用が必要な条件を明記しているか。
- [MIT OCW: Dynamic Programming I](https://www.youtube.com/watch?v=OQ5jsbhAv_M)
  - 断片: "subproblem dependencies must form a DAG"
  - 確認対象: 循環する依存関係に、DAGとしてのメモ化を無条件に適用していないか。

## K-0018 — 最適化理論

- 評価質問: E-13, E-16
- 検索語: `Optimization Theory`
- 今回の検索上位断片は、一般化理論・近似理論であり、カード中核の最適化問題、制約、目的関数、解法の根拠としては十分に直接的ではない。
- 処置: 今回の断片をカード根拠へ追加しない。既存の Source Refs を人間が確認し、必要なら「constrained optimization」「robust optimization」などで追加検索する。

## K-0001 — メカニズムデザイン

- 評価質問: E-01
- 検索語: `Mechanism Design`
- [MIT OCW: Lecture 11, Contracts and Mechanism Design](https://www.youtube.com/watch?v=cAFh3oWw6Vc)
  - 断片: "the contract creates the right incentives"
  - 確認対象: 制度の目的と参加者の私的誘因を整合させる説明になっているか。
  - 確認対象: 真実申告を保証する主張が、契約・情報・参加制約の前提なしに広がっていないか。

## 次の処置

K-0015 と K-0001 は本文と既存Source Refsの照合を行う。K-0018は追加根拠の取得が先であり、現時点の検索断片だけで承認しない。
