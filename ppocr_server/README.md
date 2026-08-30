# ここに PP-OCRv5 の server 模型を置く（測るためだけの一時置き場）

このフォルダは、PaddleOCR の **PP-OCRv5 server（大きいほうの模型）**を
実測するための受け渡し場所です。**配布物ではありません。**測り終わったら
消します。

## 置くもの（2 つ）

| 落とす場所 | 展開してできるフォルダ |
|---|---|
| https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_server_det_infer.tar | `PP-OCRv5_server_det/` |
| https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_server_rec_infer.tar | `PP-OCRv5_server_rec/` |

`.tar` のままでも、展開したフォルダごとでも、どちらでもかまいません。

## なぜ必要か

開発環境からは模型の取得先（`huggingface.co`・`modelscope.cn`・
`aistudio.baidu.com`・`paddle-model-ecology.bj.bcebos.com`）に 4 つとも
繋がりません。PyPI の PP-OCR 系 16 個・GitHub のリリース資産も探しましたが、
出回っているのは mobile（小さいほう）だけでした。

## 置いたあとにやること

```
python pdf_ocr/tools/paddle_try.py 資料.pdf --size server \
    --det-dir ppocr_server/PP-OCRv5_server_det \
    --rec-dir ppocr_server/PP-OCRv5_server_rec \
    --keyword 新耐震基準 --keyword 昭和25年
```

4 資料 64 語で測り、README の比較表に server の行を足します。

## 注意

- **GitHub のブラウザ画面からの追加は 1 ファイル 25 MB までです。**この 2 つは
  それより大きいので、`git push` で入れてください。
- 入れた分はリポジトリの履歴に残ります。測り終わって消しても、履歴からは
  消えません。それが困る場合は、こちらに渡さず、お手元で
  `pdf_ocr/tools/paddle_try.py --size server` を直接動かしてください
  （模型は初回に自動で落ちてきます）。
