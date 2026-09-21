# 原典追跡と抽出境界の補強 — 2026-09-14

対象：E-AUTO-10_1145-1566374_1566402#factory-1 / factory-2。両件とも保留を継続する。

## 確認できたこと

- 著者提出版 https://arxiv.org/abs/1303.4438v1 の概要は、15-competitiveをFeige、Flaxman、Hartline、Kleinbergの2005年研究に帰属させている。対象はdigital goodsの特定のrandom sampling auction。一般のランダムサンプリング手法全体の保証ではない。
- 同ページは2009年ACM ECに予備版があると記載する。2009年版と2013年版を同一本文とみなして置換してはいけない。
- 原著者の業績ページ https://www.cs.cornell.edu/~rdk/pubs_topic.html に原著 On the Competitive Ratio of the Random Sampling Auction と著者4名、7600から15への改善が記載されている。原著候補PDFは https://www.cs.cornell.edu/~rdk/papers/wine367a.pdf 。今回は全文・定理条件・ベンチマークの検証は未実施。
- 後続論文による15という結果の紹介は、別の独立した証明として数えない。原著と後続論文は別の文献でも、この主張の根拠の系統は区別して審査する必要がある。

## 実装

安価な抽出モデルがown_resultと出しても、引用の文頭まで戻って既存著者への帰属を検出した場合はreview_requiredにする。this methodなどで始まる参照先の欠けた引用も保留。既存の登録・ノード生成経路がこのフラグを除外する。英語の限定した検出規則であり、検出されないことは文献支持の合格を意味しない。

既存DBの主張文・支持状態・独立性判定は変更していない。通常利用可能な2件を維持。新たなLLM API呼び出しなし。

## 次の検証

原著本文を取得し、競争比の比較対象、期待値、入札・供給条件を特定する。その後に候補文の限定修正と文献支持レビューを行う。引用一致だけでpassedにしない。他の保留6件も未解決。

MIT検索による概念上の確認：Lecture 5: Nash Equilibrium https://www.youtube.com/watch?v=ftCXguW2k4o の検索断片は弱支配戦略とナッシュ条件を区別している。既存の有限オークション検査でも両条件を別々に検査する方針を維持した。15-competitiveの根拠には使用していない。perspectives/確認済みconcepts検索は該当なし。
