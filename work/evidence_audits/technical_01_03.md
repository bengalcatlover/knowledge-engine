# 技術系評価経路 1–3 の根拠監査

承認判断の材料。カード本文と承認状態は変更しない。

## K-0013 — グラフ探索アルゴリズム

- 評価質問: E-11
- [MIT OCW: Depth-First Search](https://www.youtube.com/watch?v=IBfWDYSffUU)
  - 断片: "Breadth-first search (BFS) explores vertices level by level."
  - 断片: "DFS ... path found by DFS is not necessarily shortest."
  - 確認対象: BFS/DFS/A*の目的と保証を混同していないか。DFSの経路を最短経路と主張していないか。

## K-0014 — 確率的推論とベイズネットワーク

- 評価質問: E-12
- [MIT OCW: Computational Cognitive Science Part 3](https://www.youtube.com/watch?v=dfsPKoHv_F4)
  - 断片: "graphs ... capture ... structure of the world and then put probabilities on those structures"
  - 断片: "languages for representing causal structure ... probabilistic inference"
  - 確認対象: 条件付き確率による推論と、因果構造の仮定を分けて記述しているか。

## K-0016 — 分散合意アルゴリズム

- 評価質問: E-14
- [MIT OCW: Proof of Work and Mining](https://www.youtube.com/watch?v=zYzEmBlJ77s)
  - 断片: "Distributed consensus allows multiple computers to agree on a globally ordered log"
  - 確認対象: 合意、認可、二重支払い防止を同一の機能として混同していないか。
  - 確認対象: Paxos/PBFTなどの許可型前提と、Sybil攻撃を扱う許可不要系の前提を区別しているか。

## 次の処置

各カードの定義、境界条件、関係型を既存Source Refsと照合する。保証範囲に迷いがあれば二者レビューへ送る。
