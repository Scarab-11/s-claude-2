# PP-OCRv5 server 模型（配布用）

`onnx/det.onnx`・`onnx/rec.onnx` は、PDF文字認識アプリ（`pdf_ocr/`）が
`PP-OCRv5 server` エンジンを選んだときに、初回だけ取得しに行く模型です
（`pdf_ocr/src/pdf_ocr.py` の `PPOCR_SERVER_URLS` からこのフォルダの
`raw.githubusercontent.com` 経由の URL を参照しています）。**配布 ZIP には
含めていません**（1 ファイル 100MB 未満なので、GitHub のファイルサイズ
制限には収まりますが、それでも 165MB は大きいため、選んだときだけ
取得する方式にしています）。

## 経緯

もとは PaddleOCR 公式の `PP-OCRv5_server_det_infer.tar`・
`_rec_infer.tar`（PaddlePaddle 形式）をここで受け取り、
`pdf_ocr/tools/paddle_try.py --size server` で実測してから、
`onnx` に変換して `onnx/` に置きました。実測・変換とも完了したため、
元の `.tar` 2 つ（計 169MB、もう使っていない）は削除しました。

## 注意

- `onnx/det.onnx`・`onnx/rec.onnx` を動かすときの前処理・後処理の実装は
  `pdf_ocr/src/ppocr_onnx.py`、比較の実測値は `pdf_ocr/README.md` を参照。
- ライセンスは PaddleOCR 本体と同じ Apache License 2.0（Copyright (c)
  PaddlePaddle Authors）。
