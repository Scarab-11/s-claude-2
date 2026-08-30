#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""別の版の tesseract で、手元の PDF を読み直す（開発者向け）。

利用環境と開発環境で tesseract の版が違うと、同じ画像から違う文字が、
違う信頼度で返ってくる。実際に、同じ誤読が 5.3.4 では信頼度 24、
5.5.x では 87 だった。信頼度で分岐している所はこれで挙動が変わるので、
開発環境では直っているのに利用環境では何も変わらない、ということが
起きる。手元にその版が無いまま直そうとすると、当て推量になる。

tesserocr の wheel は tesseract 本体を同梱しているので、これを入れると
apt の版とは別の版を同じ機械で動かせる。

    pip install tesserocr
    python3 tools/repro.py 対象.pdf

pdf_ocr.run_tesseract だけを差し替えるので、それ以外は本番と同じ道を
通る。--keyword を付けると、その語が取り出せたかどうかまで見る。
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

HEAD = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext")


def build(langs_dir):
    """pdf_ocr.run_tesseract の代わりになる関数を作って返す。"""
    import tesserocr

    modes = {3: tesserocr.PSM.AUTO,
             5: tesserocr.PSM.SINGLE_BLOCK_VERT_TEXT,
             6: tesserocr.PSM.SINGLE_BLOCK,
             7: tesserocr.PSM.SINGLE_LINE,
             10: tesserocr.PSM.SINGLE_CHAR,
             11: tesserocr.PSM.SPARSE_TEXT,
             12: tesserocr.PSM.SPARSE_TEXT_OSD,
             13: tesserocr.PSM.RAW_LINE}
    opened = {}

    def run(exe, args, timeout=600, env=None, tessdata=None):
        path = args[0]
        lang = args[args.index("-l") + 1]
        psm = modes[int(args[args.index("--psm") + 1])]
        # -c 鍵=値 は、本番と同じ結果にするために必ず渡す。値ごとに
        # 別の API を開くのは、tesseract の設定項目には後から変えても
        # 効かないものがあるため
        variables = tuple(args[i + 1] for i, item in enumerate(args)
                          if item == "-c")
        key = (lang, psm, variables)
        api = opened.get(key)
        if api is None:
            api = tesserocr.PyTessBaseAPI(path=langs_dir, lang=lang, psm=psm)
            for item in variables:
                name, _, value = item.partition("=")
                api.SetVariable(name, value)
            opened[key] = api
        api.SetImageFile(path)
        api.Recognize()
        # tesserocr は見出し行を付けないので、こちらで足す
        return HEAD + "\n" + api.GetTSVText(0)

    return run, tesserocr.tesseract_version().splitlines()[0].strip()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="repro.py", description=__doc__)
    parser.add_argument("input", help="読み直す PDF")
    parser.add_argument("--mode", default="mixed", help="読み取り方（既定 mixed）")
    parser.add_argument("--tessdata",
                        default="/usr/share/tesseract-ocr/5/tessdata",
                        help="言語データの置き場所")
    parser.add_argument("--keyword", action="append", default=[],
                        help="取り出せたか確かめる語（何度でも指定できる）")
    parser.add_argument("--set", action="append", default=[], metavar="鍵=値",
                        help="設定.ini の項目を上書きする（例 --set GRAYSCALE=yes）。"
                             "設定を変えた効果も、利用環境と同じ版で比べるため")
    args = parser.parse_args(argv)

    import pdf_ocr
    from pypdf import PdfReader

    try:
        run, version = build(args.tessdata)
    except ImportError:
        sys.stderr.write("tesserocr が入っていません。pip install tesserocr\n")
        return 2
    pdf_ocr.run_tesseract = run
    sys.stdout.write("差し替えた tesseract: %s\n" % version)

    settings = pdf_ocr.build_settings(
        pdf_ocr.read_ini(os.path.join(ROOT, "src", pdf_ocr.INI_NAME)),
        args.mode)
    settings["JOBS"] = "1"
    for pair in args.set:
        key, _, value = pair.partition("=")
        settings[key.strip().upper()] = value.strip()
    font = pdf_ocr.register_font(pdf_ocr.find_font(settings.get("FONT", "")))
    dst = os.path.splitext(args.input)[0] + "_repro.pdf"
    # 変換済みの PDF を渡されても読み直せるように、元の文字は消してから
    pdf_ocr.ocr_pdf(args.input, dst, settings, "tesseract", font, False,
                    quiet=True, retext=True)

    text = "".join("".join((page.extract_text() or "").split())
                   for page in PdfReader(dst).pages)
    sys.stdout.write("%s\n" % dst)
    sys.stdout.write("%s\n" % text)
    missing = 0
    for word in args.keyword:
        found = word in text
        missing += 0 if found else 1
        sys.stdout.write("  %s %s\n" % ("○" if found else "×", word))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
