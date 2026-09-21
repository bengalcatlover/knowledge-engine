# マイグレーション設計 v1

作成日: 2026-09-12

## 1. MVP対象3枚のPlacement（確定）

### K-0003: ナッシュ均衡と戦略的相互作用
- **配置**: science / Theory (THY)
- **MVPでの扱い**: reference_use（出典監査後の参照利用のみ）
- **根拠**: Nash均衡は数学的定理だが「戦略的相互作用の記述として妥当」という経験的主張を含む → L1ではなくL2
- **必須追記**: falsification_condition
- **分割**: Business Transferセクションの応用含意は将来HYPとして分離
- **出典監査結果**: YouTube URL 2本あり、DOIなし、locatorなし → content_hash = pending_verification

### K-0010: インセンティブ両立性
- **配置**: science / Theory (THY)
- **MVPでの扱い**: reference_use
- **注意**: 「ICを自社に適用すべき」という含意はカードから剥離してH-0100へ移動済み
- **出典監査結果**: YouTube URL 1本あり、DOIなし、locatorなし → content_hash = pending_verification

### K-0007: RCT（ランダム化比較試験）と因果推定
- **配置**: science / Method (MTH)
- **MVPでの扱い**: reference_use（検証設計参照のみ）
- **ステータス**: **blocked**（無作為割付の中核主張に原典位置が不足）
- **出典監査結果**: URLなし、DOIなし、locatorなし → ブロック継続
- **次のアクション**: Fisher (1935) Design of Experiments のDOI/locatorを確保してからunblock

## 2. 残り33枚のマッピング表（ドラフト）

MVP完了後の昇格パイプラインの知見を反映してから確定する。

### 変換方式の凡例
- **直接**: カード全体を1ノードとして移行可能
- **分割**: 理論部分と応用部分をそれぞれ別ノード/HYPに分離が必要
- **要審査**: 層・型の判定に人手確認が必要

| ID | canonical_name | 現field | 推奨層 | 推奨type | 変換方式 | 備考 |
|---|---|---|---|---|---|---|
| K-0001 | メカニズムデザイン | F-ECON | science | Theory | 分割 | 応用含意をHYPに分離 |
| K-0002 | オークション理論と収入等価性 | F-ECON | science | Theory | 分割 | 応用含意をHYPに分離 |
| K-0003 | ナッシュ均衡 | F-ECON | science | Theory | 直接 | MVP確定済み |
| K-0004 | 情報の非対称性 | F-ECON | science | Theory | 分割 | Screening/Signalingは別概念として分離済み |
| K-0005 | ナッジとデフォルト効果 | F-ECON | science | Method | 直接 | |
| K-0006 | 双曲割引と時間選好 | F-ECON | science | Theory | 分割 | 応用含意をHYPに分離 |
| K-0007 | RCTと因果推定 | F-ECON | science | Method | 直接 | MVP確定済み。blocked |
| K-0008 | 外部性と市場の失敗 | F-ECON | science | Theory | 分割 | ピグー税等は分離済み |
| K-0009 | 参照点依存性と損失回避 | F-ECON | science | Theory | 分割 | 応用含意をHYPに分離 |
| K-0010 | インセンティブ両立性 | F-ECON | science | Theory | 直接 | MVP確定済み |
| K-0011 | フィードバック制御 | F-EECS | foundation | FormalPrinciple | 直接 | |
| K-0012 | 状態機械とオートマトン | F-EECS | foundation | FormalPrinciple | 直接 | |
| K-0013 | グラフ探索アルゴリズム | F-EECS | foundation | FormalPrinciple | 直接 | BFS/DFS/A*分離済み |
| K-0014 | 確率的推論とベイズネットワーク | F-EECS | foundation | FormalPrinciple | 直接 | |
| K-0015 | 動的計画法 | F-EECS | foundation | FormalPrinciple | 直接 | |
| K-0016 | 分散合意アルゴリズム | F-EECS | foundation | FormalPrinciple | 直接 | |
| K-0017 | 情報理論と表現圧縮 | F-EECS | foundation | FormalPrinciple | 直接 | |
| K-0018 | 最適化理論 | F-EECS | foundation | FormalPrinciple | 分割 | 応用含意をHYPに分離 |
| K-0019 | 機械学習と学習アルゴリズム | F-EECS | science | Theory | 分割 | 応用含意をHYPに分離 |
| K-0020 | 暗号技術とセキュリティ設計 | F-EECS | science | Method | 直接 | |
| K-0021 | 線形代数と部分空間分解 | F-MATH | foundation | FormalPrinciple | 直接 | |
| K-0022 | 確率分布と大数の法則 | F-MATH | foundation | FormalPrinciple | 直接 | CLT分離済み |
| K-0023 | 勾配降下法と収束解析 | F-MATH | foundation | FormalPrinciple | 直接 | |
| K-0024 | マルコフ連鎖と定常分布 | F-MATH | foundation | FormalPrinciple | 直接 | 遷移行列等分離済み |
| K-0025 | 最尤推定と推定量の性質 | F-MATH | foundation | FormalPrinciple | 直接 | |
| K-0026 | 仮説検定と統計的意思決定 | F-MATH | foundation | FormalPrinciple | 直接 | |
| K-0027 | フーリエ解析と周波数表現 | F-MATH | foundation | FormalPrinciple | 直接 | |
| K-0028 | テイラー展開と局所近似 | F-MATH | foundation | FormalPrinciple | 直接 | ニュートン法分離済み |
| K-0029 | 回帰分析と最小二乗法 | F-MATH | foundation | FormalPrinciple | 直接 | |
| K-0030 | 主成分分析と次元削減 | F-MATH | foundation | FormalPrinciple | 直接 | |
| K-0031 | モンテカルロ法 | F-MATH | foundation | FormalPrinciple | 直接 | MCMC分離済み |
| K-0032 | 条件数と数値安定性 | F-MATH | foundation | FormalPrinciple | 直接 | |
| K-0033 | 確率過程と時系列の定常性 | F-MATH | foundation | FormalPrinciple | 直接 | |
| K-0034 | 強化学習と逐次方策最適化 | F-EECS | science | Theory | 直接 | |
| K-0035 | 両面プラットフォーム | F-ECON | universe | WorldModel | 分割 | 応用含意をHYPに分離 |
| K-0036 | データ最小化と目的限定 | F-ECON | practice | Method | 直接 | |

## 3. 統計

| 変換方式 | 件数 |
|---|---|
| 直接 | 25 |
| 分割 | 11 |
| 要審査 | 0 |

| 推奨層 | 件数 |
|---|---|
| foundation | 22 |
| science | 11 |
| universe | 1 |
| object | 0 |
| practice | 1 |

## 4. 移行方針

- 一括変換しない。MVP完了で得られた昇格パイプラインの知見を反映してから実行
- K-IDは安定ハンドルとして残す（互換ビュー）
- 「分割」対象の11枚は、理論部分をscienceノードに、応用含意をHYPに分離
- 既存confidence値は「未検証の申告値」に降格
- 旧カードはlegacy viewとして参照可能のまま維持
