# 定期実行用の指示

`exam-inbox` に置かれた新規または更新済みのPDFだけを処理する。

1. `python ingest_exams.py scan` を実行し、`work/research-queue.json` を読む。
2. `state` が `needs_topic_extraction` の項目だけを処理する。抽出テキストを読み、科学的に検証可能な主張・概念・研究上の問いを分ける。
3. [research-policy.md](research-policy.md)に従い、査読論文、学術索引、政府・国立研究機関・国際機関の一次資料だけを調べる。企業ページ、ブログ、ニュース解説、検索スニペットを根拠にしない。
4. 主題ごとに `candidates/<PDFのID>-<短い主題>.md` を作る。主張、出典、研究設計、限界、問題文との関係、未解決点、状態`candidate`を記録する。引用・DOI・数値を推測で補わない。
5. 調査済みの待ち行列項目だけを `candidate_ready` に更新する。PDFの本文や元資料を書き換えない。`accepted` へ移さない。
6. 新しい候補ができたときだけ、このタスクに短く知らせる。新規PDFがなければ何も通知しない。

画像PDFで本文が抽出できなければ、OCRが必要であることだけを記録し、推測で調査を始めない。
