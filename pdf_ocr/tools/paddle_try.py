#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PaddleOCR（PP-OCRv5）に同じ紙面を読ませて、狙った語が取れるか数える（開発者向け）。

このツールが使っているのは tesseract だが、PaddleOCR のほうが日本語の
縦書きに強いという話がある。乗り換えの是非は、聞いた話ではなく同じ資料の
同じ語で決めたい。そのための物差し。

**これは認識器そのものを測る道具で、本体の作り込み（二度読み・縦中横の
拾い直し・弱い行の読み直し）は通らない。** 同じ土俵で比べたいときは、
tesseract 側も 1 回だけ呼んで比べること。

    # 小さいほうの模型（onnxruntime だけで動く。模型は同梱されている）
    pip install onnxocr
    python tools/paddle_try.py 資料.pdf --keyword 新耐震基準 --keyword 昭和25年

    # 大きいほうの模型（PaddleOCR 本体が要る。初回に模型を落としてくる）
    pip install paddlepaddle paddleocr
    python tools/paddle_try.py 資料.pdf --size server --keyword 新耐震基準

`--size server` は `PP-OCRv5_server_det` と `PP-OCRv5_server_rec` を使う。
模型の取得先は次の 4 つで、いずれかに繋がれば落ちてくる。

    https://huggingface.co
    https://modelscope.cn
    https://aistudio.baidu.com
    https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/

この 4 つに繋がらない環境では `--size server` は動かない。その場合は
`.../paddle3.0.0/PP-OCRv5_server_det_infer.tar` と `..._rec_infer.tar` を
別の機械で落として展開し、`--det-dir` と `--rec-dir` でその場所を渡す
（このとき取得先の確認を飛ばすために、環境変数
`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` を付ける）。
"""

import argparse
import os
import sys
import time
import unicodedata


def render(path, dpi):
    """PDF の各ページを画像にして、その場所の一覧を返す。"""
    import pypdfium2 as pdfium

    out = []
    document = pdfium.PdfDocument(path)
    base = os.path.splitext(path)[0]
    for number, page in enumerate(document, 1):
        image = page.render(scale=dpi / 72.0).to_pil()
        name = "%s_p%02d_%ddpi.png" % (base, number, dpi)
        image.save(name)
        out.append(name)
    return out


def read_onnx(images, cls=True, side=960, limit="max"):
    """同梱の PP-OCRv5（小さいほう）で読む。"""
    import cv2
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr

    ocr = ONNXPaddleOcr(use_angle_cls=cls, use_gpu=False,
                        det_limit_side_len=side, det_limit_type=limit)
    pieces = []
    for name in images:
        for page in ocr.ocr(cv2.imread(name)):
            for _box, (text, _conf) in page:
                pieces.append(text)
    return pieces


def read_paddle(images, size, det_dir, rec_dir, cls=True, side=960,
                limit="max"):
    """PaddleOCR 本体で読む。size は mobile か server。

    cls（行の上下逆を直す模型 PP-LCNet_x1_0_textline_ori）は本体とは別に
    落としてくるので、取得先に繋がらない環境では False にする。
    """
    from paddleocr import PaddleOCR

    settings = {"lang": "japan",
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": cls,
                # 文字の場所を探す前に紙面を縮める大きさ。onnxocr の既定
                # （長辺 960）に合わせないと、同じ物差しにならない。
                # PaddleOCR 本体の既定（短辺 64・上限 4000＝実質そのまま）
                # だと server の模型が 34GB 確保しようとして落ちる
                "text_det_limit_side_len": side,
                "text_det_limit_type": limit}
    # 置き場を渡すときも名前を一緒に渡す。PaddleOCR 3.7 は既定が
    # PP-OCRv6 で、名前を省くと「PP-OCRv6_medium_det のはずが
    # PP-OCRv5_server_det だった」と言って止まる
    settings["text_detection_model_name"] = "PP-OCRv5_%s_det" % size
    settings["text_recognition_model_name"] = "PP-OCRv5_%s_rec" % size
    if det_dir:
        settings["text_detection_model_dir"] = det_dir
    if rec_dir:
        settings["text_recognition_model_dir"] = rec_dir
    try:
        ocr = PaddleOCR(**settings)
    except Exception as error:                             # noqa: BLE001
        # 模型の置き場に繋がらないと、ここで止まる。原因が分かる形で返す
        sys.stderr.write(
            "模型を用意できませんでした: %s\n"
            "取得先（bcebos / aistudio / modelscope）に繋がらない環境では、\n"
            "別の機械で落とした模型を --det-dir と --rec-dir で渡してください。\n"
            % error)
        raise SystemExit(3)
    pieces = []
    for name in images:
        for page in ocr.predict(name):
            pieces.extend(page.get("rec_texts", []))
    return pieces


def squeeze(text):
    """全角・半角と空白の違いで数え損なわないようにそろえる。"""
    text = unicodedata.normalize("NFKC", "".join(text.split()))
    for before, after in (("（", "("), ("）", ")"), ("　", "")):
        text = text.replace(before, after)
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(prog="paddle_try.py", description=__doc__)
    parser.add_argument("input", help="読ませる PDF")
    parser.add_argument("--size", default="mobile",
                        choices=("mobile", "server"),
                        help="模型の大きさ（既定 mobile）")
    parser.add_argument("--engine", default="",
                        choices=("", "onnx", "paddle"),
                        help="動かし方。空なら mobile は onnx、server は paddle")
    parser.add_argument("--dpi", type=int, default=500,
                        help="ページを画像にするときの解像度（既定 500）")
    parser.add_argument("--det-dir", default="",
                        help="文字の場所を探す模型の置き場（自分で落としたとき）")
    parser.add_argument("--rec-dir", default="",
                        help="文字を読む模型の置き場（自分で落としたとき）")
    parser.add_argument("--det-side", type=int, default=960,
                        help="文字の場所を探す前に紙面を縮める大きさ"
                             "（既定 960。onnxocr の既定に合わせてある）")
    parser.add_argument("--det-limit", default="max", choices=("max", "min"),
                        help="--det-side を長辺で見るか短辺で見るか（既定 max）")
    parser.add_argument("--no-cls", action="store_true",
                        help="行の上下逆を直す模型を使わない。この模型だけは "
                             "--rec-dir でも渡せず、取得先に繋がらないと "
                             "PaddleOCR 本体が起動しない")
    parser.add_argument("--keyword", action="append", default=[],
                        help="取り出せたか確かめる語（何度でも指定できる）")
    args = parser.parse_args(argv)

    engine = args.engine or ("onnx" if args.size == "mobile" else "paddle")
    if engine == "onnx" and args.size == "server":
        sys.stderr.write("onnxocr が同梱しているのは mobile だけです。"
                         "server は --engine paddle で読ませてください。\n")
        return 2

    images = render(args.input, args.dpi)
    start = time.time()
    if engine == "onnx":
        pieces = read_onnx(images, cls=not args.no_cls, side=args.det_side,
                           limit=args.det_limit)
    else:
        pieces = read_paddle(images, args.size, args.det_dir, args.rec_dir,
                             cls=not args.no_cls, side=args.det_side,
                             limit=args.det_limit)
    spent = time.time() - start

    text = squeeze("".join(pieces))
    sys.stdout.write("模型 PP-OCRv5_%s / 動かし方 %s / %d dpi / %d ページ"
                     " / 場所探しは %s %d / 上下逆の直し %s\n"
                     % (args.size, engine, args.dpi, len(images),
                        args.det_limit, args.det_side,
                        "なし" if args.no_cls else "あり"))
    sys.stdout.write("%.1f 秒  %d 字\n" % (spent, len(text)))
    sys.stdout.write("%s\n" % text)
    missing = 0
    for word in args.keyword:
        found = squeeze(word) in text
        missing += 0 if found else 1
        sys.stdout.write("  %s %s\n" % ("○" if found else "×", word))
    if args.keyword:
        sys.stdout.write("  %d/%d\n" % (len(args.keyword) - missing,
                                        len(args.keyword)))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
