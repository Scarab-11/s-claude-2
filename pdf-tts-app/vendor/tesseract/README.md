# vendor/tesseract

画像から文字を読み取る（OCR）ために使用しているライブラリ一式です。
CDNを使わず、すべてローカルに置いています。

| ファイル | 出所 | バージョン | ライセンス |
|---|---|---|---|
| `tesseract.min.js`, `worker.min.js` | npm `tesseract.js` | 5.1.1 | Apache-2.0（`LICENSE.md`） |
| `core/tesseract-core-*-lstm.wasm.js` | npm `tesseract.js-core` | 5.1.1 | Apache-2.0（`LICENSE`） |
| `lang/*.traineddata.gz` | npm `@tesseract.js-data/{jpn,jpn_vert,eng}` の `4.0.0_best_int` | 1.0.0 | Apache-2.0（tessdata） |

`core/` には LSTM 版のみを置いています。アプリは常に OEM=1（LSTM_ONLY）で動かすため、
tesseract.js が要求するのは `tesseract-core-simd-lstm.wasm.js`（WebAssembly SIMD 対応環境）か
`tesseract-core-lstm.wasm.js`（非対応環境）のどちらかだけです。

`lang/` の学習データは `4.0.0_best_int`（tessdata_best の整数量子化版）です。
標準版は日本語だけで16MB以上あるのに対し約2MBで、精度はほぼ同等です。
