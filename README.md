# 入試問題から科学知識を育てるエンジン

大学入試問題のPDFを入口に、問題本文の背景にある科学的知識を収集・検索・参照できる形へ育てる。対象は入試対策の解説に限らない。問題が扱う科学的な主張、研究方法、論争、社会的含意を、出典を保って読み出すための知識基盤である。

## 使い方

1. PDFを `exam-inbox` に保存する。
2. `python ingest_exams.py scan` を実行する。初回または更新済みのPDFからテキストを抽出し、`work/extractions` と `work/research-queue.json` を作る。
3. `research-queue.json` の未処理項目を、[科学的調査の規則](research-policy.md)に従って調べる。結果は `candidates` に保存する。
4. 検証できた知識だけを `accepted` に移す。AIは通常、`accepted` と原資料を優先して参照する。`candidates` は仮説・追加調査用であり、事実として断定しない。

```text
exam-inbox/PDF
  -> work/extractions/       問題本文の抽出
  -> work/research-queue.json  調べる主題の待ち行列
  -> candidates/             出典付きの調査候補
  -> accepted/               検証済みの知識
```

## 自動化の範囲

`ingest_exams.py` はPDFの新規・更新を検出し、抽出と待ち行列の更新を行う。研究の内容は、指定した科学的ソースだけから作る。見つけた資料を原資料と同じ扱いにはしない。

PDFが画像だけで文字を持たない場合は、日本語・英語OCRで抽出する。OCRの誤読はあり得るため、引用・数値・設問の細部を根拠にするときはページ画像または原PDFで確認する。

## 実行例

```powershell
python ingest_exams.py scan
python ingest_exams.py status
```

## 現在の制限

- 主題・問いの精密な抽出と周辺研究の調査にはAIとネットワーク接続が必要。
- 自動で作られた候補は、査読状況・原文・対象集団・研究限界を確認するまで確定知識にしない。
- 本文の著作権は原資料に残る。知識ノートには必要最小限の引用と書誌情報だけを保存する。
