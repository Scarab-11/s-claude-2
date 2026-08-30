#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pdf_ocr.py の動作を機械的に確かめる（開発者向け）。

    python3 tools/selfcheck.py

同梱のサンプルを 0 / 90 / 180 / 270 度に回した PDF を作り、

  ① 変換後の PDF から狙った語が取り出せるか
  ② 透明な文字が、実際に文字が写っている場所に乗っているか

を確かめる。②は pdfium 自身の座標変換で文字の矩形を画面座標に直し、
その範囲に黒い画素があるかどうかで判定する（位置がずれていれば真っ白）。
"""

import ctypes
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "src", "pdf_ocr.py")
SAMPLE = os.path.join(ROOT, "src", "サンプル.pdf")

KEYWORDS = ["舗装", "山田", "2026", "A-102"]
MIN_PLACED = 0.9   # 位置が合っていると判定できた文字列の割合


def rotated_copy(src, dst, rotation):
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(src)
    writer = PdfWriter()
    for page in reader.pages:
        if rotation:
            page.rotate(rotation)
        writer.add_page(page)
    with open(dst, "wb") as f:
        writer.write(f)


def convert(src, outdir):
    subprocess.run([sys.executable, SCRIPT, "--quiet", "--overwrite",
                    "--outdir", outdir, src], check=True)
    base = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(outdir, base + "_OCR.pdf")


def extracted_text(path):
    from pypdf import PdfReader

    return " ".join("".join(page.extract_text() or ""
                            for page in PdfReader(path).pages).split())


def placement_ratio(path, scale=2.0):
    """透明テキストが黒い画素の上に乗っている割合を返す。"""
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    document = pdfium.PdfDocument(path)
    on_ink = total = 0
    for page in document:
        image = page.render(scale=scale, grayscale=True).to_pil()
        width, height = image.size
        pixels = image.load()
        textpage = page.get_textpage()
        for index in range(textpage.count_rects()):
            left, bottom, right, top = textpage.get_rect(index)
            if not textpage.get_text_bounded(left, bottom, right, top).strip():
                continue
            x0, y0 = to_device(pdfium_c, page, width, height, left, top)
            x1, y1 = to_device(pdfium_c, page, width, height, right, bottom)
            x0, x1 = max(0, min(x0, x1)), min(width - 1, max(x0, x1))
            y0, y1 = max(0, min(y0, y1)), min(height - 1, max(y0, y1))
            if x1 <= x0 or y1 <= y0:
                continue
            total += 1
            dark = sum(1 for y in range(y0, y1 + 1)
                       for x in range(x0, x1 + 1) if pixels[x, y] < 128)
            if dark / float((x1 - x0 + 1) * (y1 - y0 + 1)) > 0.02:
                on_ink += 1
        image.close()
    document.close()
    return on_ink / float(total) if total else 0.0


def to_device(pdfium_c, page, width, height, x, y):
    dx, dy = ctypes.c_int(), ctypes.c_int()
    pdfium_c.FPDF_PageToDevice(page.raw, 0, 0, width, height, 0,
                               ctypes.c_double(x), ctypes.c_double(y),
                               ctypes.byref(dx), ctypes.byref(dy))
    return dx.value, dy.value


def shared_contents_copy(src, dst):
    """全ページが同じ内容ストリームを共有する PDF を作る。

    スキャナ出力にある構造。切り離さずに重ねると、1 ページ目の文字が
    他のページにも現れてしまう（実際に起きた不具合の再現）。
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject

    reader = PdfReader(src)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    first = writer.pages[0].raw_get("/Contents")
    for page in writer.pages[1:]:
        page[NameObject("/Contents")] = first
    with open(dst, "wb") as f:
        writer.write(f)


def page_lengths(path):
    from pypdf import PdfReader

    return [len("".join((page.extract_text() or "").split()))
            for page in PdfReader(path).pages]


def check_no_leak(tmpdir):
    """ページ間で文字が混ざっていないかを確かめる。

    漏れた文字は別ページのフォントで解釈されて化けるため、語では
    見つけられない。ページごとの字数が膨らんでいないかで判定する。
    """
    normal = page_lengths(convert(SAMPLE, tmpdir))

    src = os.path.join(tmpdir, "shared.pdf")
    shared_contents_copy(SAMPLE, src)
    shared = page_lengths(convert(src, tmpdir))

    ok = (len(normal) == len(shared)
          and all(s <= n * 1.2 + 5 for n, s in zip(normal, shared)))
    print("内容共有 : %s  ページごとの字数 %s（共有なしでは %s）"
          % ("OK  " if ok else "NG  ", shared, normal))
    return 0 if ok else 1


def check_line_continuity(tmpdir):
    """1 行が途中で分断されていないかを確かめる。

    tesseract は 1 行を単語ごとに区切って返す。それを別々の文字列として
    置くと、ビューアが別の行と判断し、選択して貼り付けたときに分断され、
    通しでの検索もできなくなる（実際に起きた不具合の再現）。
    """
    import pypdfium2 as pdfium
    from pypdf import PdfReader

    out = convert(SAMPLE, tmpdir)
    phrase = "第二駐車場舗装工事"

    # 空白や改行は潰さずに見る。分断されると、まさにそこへ改行が入るため。
    by_pypdf = PdfReader(out).pages[0].extract_text() or ""
    document = pdfium.PdfDocument(out)
    by_pdfium = document[0].get_textpage().get_text_bounded()
    document.close()

    ok = phrase in by_pypdf and phrase in by_pdfium
    print("行の連続 : %s  「%s」が一続きで取り出せること（pypdf %s / pdfium %s）"
          % ("OK  " if ok else "NG  ", phrase,
             "○" if phrase in by_pypdf else "×",
             "○" if phrase in by_pdfium else "×"))
    return 0 if ok else 1


def check_mixed(tmpdir):
    """縦横が混ざったページで、両方が読めているかを確かめる。"""
    import make_sample
    from pypdf import PdfReader

    src = make_sample.make_mixed(os.path.join(tmpdir, "mixed.pdf"))
    results = {}
    for mode in ("yoko", "mixed"):
        subprocess.run([sys.executable, SCRIPT, "--quiet", "--overwrite",
                        "--mode", mode, "--suffix", "_" + mode,
                        "--outdir", tmpdir, src], check=True)
        out = os.path.join(tmpdir, "mixed_%s.pdf" % mode)
        results[mode] = "".join(
            "".join((page.extract_text() or "").split())
            for page in PdfReader(out).pages)

    yoko_text, mixed_text = results["yoko"], results["mixed"]
    横 = "建築物省エネ法"
    縦 = "住宅品質確"
    ok = (横 in mixed_text and 縦 in mixed_text and 縦 not in yoko_text)
    print("縦横混在 : %s  横「%s」%s・縦「%s」%s（横書きモードでは縦を取りこぼす: %s）"
          % ("OK  " if ok else "NG  ",
             横, "○" if 横 in mixed_text else "×",
             縦, "○" if 縦 in mixed_text else "×",
             "○" if 縦 not in yoko_text else "×"))
    return 0 if ok else 1


def check_two_column(tmpdir):
    """二段組みのページで、読む順が段ごとになっているかを確かめる。

    上から下へ（同じ高さなら左から右へ）だけで並べると、左の段の
    1 行目・右の段の 1 行目・左の段の 2 行目…と交互になる。コピーすると
    文章が互い違いになって読めない。

    tesseract の段組みの判定は当てにできない。同じ紙面でも、描き出す
    解像度が違うだけで結果が変わった（150dpi では左右を別の block に
    分けたが、300dpi では 1 つにまとめ、1 行が左右にまたがった）。
    """
    import make_sample
    from pypdf import PdfReader

    src = make_sample.make_two_column(os.path.join(tmpdir, "nidan.pdf"))
    subprocess.run([sys.executable, SCRIPT, "--quiet", "--overwrite",
                    "--outdir", tmpdir, src], check=True)
    out = os.path.join(tmpdir, "nidan_OCR.pdf")
    text = "".join("".join((page.extract_text() or "").split())
                   for page in PdfReader(out).pages)

    # 左の段の最後が、右の段の最初より前に来ていること
    left_last = text.find("いるからです")
    right_first = text.find("構造のセミナー")
    order = 0 <= left_last < right_first if right_first >= 0 else False
    # 1 行の中の語順が入れ替わっていないこと
    inline = text.find("木造住宅に") < text.find("と思われるかも") \
        if "と思われるかも" in text else False
    ok = order and inline
    print("二段組み : %s  左の段を読み切ってから右の段へ %s・"
          "行の中の語順 %s"
          % ("OK  " if ok else "NG  ",
             "○" if order else "×", "○" if inline else "×"))
    return 0 if ok else 1


def check_reversed(tmpdir):
    """色の付いた帯の上の白抜きの見出しを、色を捨てずに読んでいるか。

    利用者の資料では、オレンジの帯に白抜きで組んだ見出し
    「本書の構成とねらい」が「SAS ORE BDU)」に化けていた。原因は白黒に
    落としていたことで、輝度に直すと帯は 154、白い文字は 254 と差が 100
    しか残らない。色のままなら、青の板で 190 の差がある。

    **化けること自体は、合成した紙面では安定して再現できなかった。**
    字の大きさと圧縮を振って探したが、再現する条件は紙一重で、同じ設定の
    まま色のほうが落ちることもあった。だからここでは「化けないこと」を
    測らない。代わりに、その判断の**理由のほうを固定する**。

      1. 既定で色を捨てていないこと（GRAYSCALE と、描き出した画像の種類）
      2. 輝度より青の板のほうが差が大きいという、判断の根拠になった数字
      3. 色のまま渡しても、白抜きの見出しと黒い本文が読めること

    3 は「色にしたら壊れた」を捕まえるためのもので、白黒との優劣は見ない。
    実際の紙面での差は README「色の付いた文字と、白黒への落とし方」に
    数字で残してある。
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    sys.path.insert(0, HERE)
    import make_sample
    import pdf_ocr
    import pypdfium2 as pdfium
    from PIL import Image
    from pypdf import PdfReader

    src = make_sample.make_reversed(os.path.join(tmpdir, "shironuki.pdf"))

    # 1. 既定で色を捨てていないこと
    kept = pdf_ocr.DEFAULTS["GRAYSCALE"] == "no"
    shot = os.path.join(tmpdir, "shironuki.png")
    document = pdfium.PdfDocument(src)
    try:
        pdf_ocr.render_page(document, 0, 200, False, shot)
    finally:
        document.close()
    with Image.open(shot) as rendered:
        kept = kept and rendered.mode in ("RGB", "RGBA")

    # 2. 判断の根拠になった数字（オレンジの帯の上の白い文字）
    band, letter = (196, 110, 50), (255, 255, 255)

    def luma(rgb):
        return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]

    by_luma = abs(luma(letter) - luma(band))
    by_blue = abs(letter[2] - band[2])
    reason = by_blue > by_luma * 1.5

    # 3. 色のまま渡しても読めること
    subprocess.run([sys.executable, SCRIPT, "--quiet", "--overwrite",
                    "--outdir", tmpdir, src], check=True)
    out = os.path.join(tmpdir, "shironuki_OCR.pdf")
    text = "".join("".join((page.extract_text() or "").split())
                   for page in PdfReader(out).pages)
    read = "本書の構成とねらい" in text and "会話形式" in text

    ok = kept and reason and read
    print("白抜き   : %s  色を捨てていないこと %s・"
          "輝度より青の板の差が大きいこと %s（%d 対 %d）・"
          "見出しと本文が読めること %s"
          % ("OK  " if ok else "NG  ",
             "○" if kept else "×", "○" if reason else "×",
             int(by_luma), by_blue, "○" if read else "×"))
    return 0 if ok else 1


def check_thin_langs():
    """精度のよい言語データを、確実に使える形で用意できるかを確かめる。

    利用者の環境で、同梱した日本語データを置いてあるのに

        言語データをそろえられませんでした（eng, jpn, jpn_vert, osd）。
        速度優先版のまま読みます（精度が落ちます）。

    と出た。原因は、フォルダの中身を **tesseract に問い合わせて** 数えて
    いたこと。その問い合わせが 1 行のエラーを返すと、1 行目を見出しとして
    読み飛ばす作りだったため結果が空になり、正しくそろっているフォルダを
    捨てていた。数えるだけならこちらでできる。

    さらに、ファイルがあることと tesseract がそこを開けることは別。
    Windows では道筋に日本語が入っていると開けないことがあり、配布物の
    フォルダ名は「PDF文字認識」なのでまさにこれに当たる。開けないまま
    進むと、変換しても文字が 1 つも入らない PDF ができる。

    そこで次の 4 つを見る。

      1. フォルダの中身を、tesseract に聞かずに数えられること
      2. 置き場として使えないときは、次の候補へ移ること
      3. 候補に、今いるフォルダの下の相対の道筋を作らないこと
      4. どちらの版で読んでいるかが毎回はっきり出ること
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import pdf_ocr

    work = tempfile.mkdtemp(prefix="pdf_ocr_langs_")
    try:
        room = os.path.join(work, "tessdata")
        os.makedirs(room)
        sizes = {"jpn": 2471260, "eng": 4113088,      # 速度優先版の実寸
                 "jpn_vert": 3037480, "osd": 10562727}
        for name, size in sizes.items():
            with open(os.path.join(room, name + ".traineddata"), "wb") as f:
                f.write(b"\0" * size)
        os.makedirs(os.path.join(room, "configs"))
        with open(os.path.join(room, "configs", "tsv"), "w") as f:
            f.write("tessedit_create_tsv 1\n")

        # 1. 中身を数える。tesseract は呼ばない
        counted = pdf_ocr.langs_in_dir(room) == set(sizes)
        counted = counted and pdf_ocr.langs_in_dir(
            os.path.join(work, "ない")) == set()

        # 2. 置き場として使えないときに、次の候補へ移ること
        first = os.path.join(work, "だめな置き場")
        second = os.path.join(work, "つかえる置き場")
        os.makedirs(first)
        os.makedirs(second)
        for target in (first, second):
            for name in ("jpn",):
                with open(os.path.join(target, name + ".traineddata"),
                          "wb") as f:
                    f.write(b"\0" * (pdf_ocr.THIN_TRAINEDDATA[name] + 1))

        real = {}
        for name in ("tessdata_candidates", "tessdata_works",
                     "stock_traineddata", "find_traineddata",
                     "copy_tessdata_configs"):
            real[name] = getattr(pdf_ocr, name)
        try:
            pdf_ocr.tessdata_candidates = lambda: [first, second]
            pdf_ocr.tessdata_works = (
                lambda exe, d, lang="jpn", env=None:
                os.path.abspath(d) != os.path.abspath(first))
            pdf_ocr.stock_traineddata = lambda name: None
            # fill_tessdata が本体の置き場から複製するときだけ room を
            # 使わせる（tessdata を指定しない呼び方）。thin_traineddata の
            # 早期判定は tessdata（stored）を指定して呼ぶので、そちらは
            # 本物に任せる。ここを区別しないと、早期判定が room の
            # わざと小さくした jpn を見てしまい、速度優先版が無いのに
            # 「無い」と誤判定して adopt_local_langs が早々にあきらめる。
            pdf_ocr.find_traineddata = (
                lambda exe, name, tessdata=None:
                os.path.join(room, name + ".traineddata") if not tessdata
                else real["find_traineddata"](exe, name, tessdata))
            pdf_ocr.copy_tessdata_configs = lambda exe, target: None
            picked = pdf_ocr.adopt_local_langs("t", sorted(sizes), quiet=True)
            moved = (picked is not None
                     and os.path.abspath(picked) == os.path.abspath(second))
        finally:
            for name, value in real.items():
                setattr(pdf_ocr, name, value)

        # 3. 環境変数が無くても、相対の道筋を候補にしないこと
        keep = dict((k, os.environ.get(k))
                    for k in ("LOCALAPPDATA", "ProgramData", "APPDATA"))
        for k in keep:
            os.environ.pop(k, None)
        try:
            rooted = all(os.path.isabs(p) for p in pdf_ocr.tessdata_candidates())
        finally:
            for k, v in keep.items():
                if v is not None:
                    os.environ[k] = v

        # 4. どちらの版で読んでいるかが出ること
        quick = os.path.join(work, "quick")
        os.makedirs(quick)
        with open(os.path.join(quick, "jpn.traineddata"), "wb") as f:
            f.write(b"\0" * (pdf_ocr.THIN_TRAINEDDATA["jpn"] + 1))
        told = ("速度優先版" in pdf_ocr.langs_in_use("t", {"_TESSDATA": room})
                and "精度重視版" in pdf_ocr.langs_in_use("t",
                                                        {"_TESSDATA": quick}))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    ok = counted and moved and rooted and told
    print("言語データ: %s  tesseract に聞かずに数えること %s・"
          "開けない置き場から次へ移ること %s・"
          "相対の道筋を候補にしないこと %s・"
          "どちらの版で読むか出すこと %s"
          % ("OK  " if ok else "NG  ", "○" if counted else "×",
             "○" if moved else "×", "○" if rooted else "×",
             "○" if told else "×"))
    return 0 if ok else 1


def check_text_fixes():
    """丸数字に化けた年月と、`  に化けた かぎかっこ を戻せるか。

    精度重視版の言語データにすると、この 2 つが出るようになった。
    どちらも取りこぼしではなく、字の種類だけを間違えている。

        2025年4月   →  ②0②⑤年④月
        2024年10月  →  ⑳②④年①0月
        「構造」     →  `構造」

    実際の紙面では、開きのかぎかっこ 17 個がすべて ` になり、閉じの 」は
    17 個とも正しく、正しい 「 は 1 つも無かった。

    直しすぎないことのほうが大事なので、触ってはいけない例を厚くする。
    この紙面自体に「①構造の本を読んでも理解できない」という箇条書きと、
    本文中の「さらに、①の構造の本を…」があり、ここを数字にしてはいけない。
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import pdf_ocr

    cases = [
        # 直すもの
        ("②0②⑤年④月", "2025年4月"),
        ("⑳②④年①0月", "2024年10月"),
        ("平成⑫年", "平成12年"),
        ("木造住宅の`構造」について", "木造住宅の「構造」について"),
        ("`なぜ、構造?」と", "「なぜ、構造?」と"),
        # 触らないもの
        ("①構造の本を読んでも理解できない", "①構造の本を読んでも理解できない"),
        ("さらに、①の構造の本を", "さらに、①の構造の本を"),
        ("②構造のセミナーを受講しても", "②構造のセミナーを受講しても"),
        ("③構造を教えてくれる人が", "③構造を教えてくれる人が"),
        ("①②③", "①②③"),
        ("第①章", "第①章"),
        ("2025年4月", "2025年4月"),
        ("a=`x` のように書く", "a=`x` のように書く"),
        ("コード `print` を", "コード `print` を"),
        ("", ""),
    ]
    bad = [one for one, want in cases
           if pdf_ocr.fix_open_bracket(pdf_ocr.uncircle_numbers(one)) != want]
    ok = not bad
    print("字の直し : %s  年月の丸数字と ` のかぎかっこ（%d 例、"
          "うち触らない例 %d）%s"
          % ("OK  " if ok else "NG  ", len(cases), 10,
             "○" if ok else "× " + " ".join(bad)))
    return 0 if ok else 1


def check_conf_holes():
    """信頼度 0 で返ってきた正しい字を、捨てずに残せるか。

    利用者の報告した症状そのもの。tesseract は正しく読んだ字にも
    信頼度 0 を付けることがあり、下限 30 で捨てていた。実測（利用者の
    資料、500dpi）で、次の字がいずれも信頼度 0 で返っていた。

        構造塾      → 「構造」をご活用ください   （塾 が消える）
        地盤補強    → 地補強工事業者             （盤 が消える）
        震災による  → 災による被害               （震 が消える）

    **消えた字は前後とつながって、読める別の語になる。** 字が化けて
    いれば見て気付けるが、消えた字には気付けない。

    かといって下限をやめると、同じ資料の図の領域で罫線を「本」と
    読んだものが 24 個続いた。行として見て分ける。

    tesseract は呼ばない。TSV を直に渡す（この不具合は、返ってきた
    TSV の扱い方の問題なので、tesseract の版に左右されてはいけない）。
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import pdf_ocr

    head = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
            "left\ttop\twidth\theight\tconf\ttext")

    def row(block, line, left, top, width, height, conf, text):
        return "5\t1\t%d\t1\t%d\t1\t%d\t%d\t%d\t%d\t%.1f\t%s" % (
            block, line, left, top, width, height, conf, text)

    rows = [head]
    # 1. 横書きの本文。真ん中の「盤」だけ信頼度 0（残さねばならない）
    rows.append(row(1, 1, 100, 200, 180, 40, 93.0, "地"))
    rows.append(row(1, 1, 280, 200, 40, 40, 0.0, "盤"))
    rows.append(row(1, 1, 320, 200, 400, 40, 94.0, "補強工事業者"))
    # 2. 同じ行の末尾に付いた、自信のない断片（落とさねばならない）
    rows.append(row(1, 1, 760, 200, 40, 40, 5.0, "ゴミ"))
    # 3. 行から横に離れた字（落とさねばならない。拾うと行の位置が動く）
    rows.append(row(1, 1, 400, 900, 40, 40, 0.0, "離"))
    # 4. 罫線を読み違えた行。全部が自信なし（1 つも残してはならない）
    for step in range(6):
        rows.append(row(2, 1, 1200, 300 + step * 26, 41, 24, 12.0, "本"))
    # 5. 縦組みの本文。真ん中の「震」だけ信頼度 0（残さねばならない）
    rows.append(row(3, 1, 2000, 100, 40, 200, 91.0, "新耐"))
    rows.append(row(3, 1, 2000, 300, 40, 40, 0.0, "震"))
    rows.append(row(3, 1, 2000, 340, 40, 120, 90.0, "基準"))

    words = pdf_ocr.parse_tsv("\n".join(rows), 30)
    text = "".join(word.text for word in words)

    filled = "地盤補強工事業者" in text
    trimmed = "ゴミ" not in text and "離" not in text
    quiet = "本" not in text
    upright = "新耐震基準" in text

    # 下限そのものは効いたままであること（拾い直しを切れば元の動き）
    plain = "".join(word.text for word in
                    pdf_ocr.parse_tsv("\n".join(rows), 30, rescue=False))
    same = "盤" not in plain and "震" not in plain

    ok = filled and trimmed and quiet and upright and same
    print("信頼度0の穴: %s  挟まれた字を残すこと %s・"
          "行の端の断片を落とすこと %s・行ごとごみなら残さないこと %s・"
          "縦組みでも残すこと %s・切れば元の動きに戻ること %s"
          % ("OK  " if ok else "NG  ",
             "○" if filled else "×", "○" if trimmed else "×",
             "○" if quiet else "×", "○" if upright else "×",
             "○" if same else "×"))
    return 0 if ok else 1


def check_fake_columns():
    """横組みだけの紙面から、偽の「列」を作らないかを確かめる。

    縦書きの設定は紙面のどこを読ませても縦組みとして読むので、横組みの
    本文からも「列」ができる。その信頼度は本物の横書きとほとんど並ぶ
    （実測で 94.5 対 93.5）。1 ポイントの差で縦組みと認めると、そこに
    1 文字の読み違いが芋づる式にぶら下がり、重なっていた正しい横書きまで
    消える（実測で 9 本の偽の列ができ、本文の語が 1 つ消えた）。

    OCR は通さず、pick_columns に直接渡して確かめる。
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import pdf_ocr

    def word(text, left, top, width, height, conf, angle=0):
        return pdf_ocr.Word(text, left, top, width, height, angle=angle,
                            conf=conf)

    # 横組みの本文。紙面いっぱいに、はっきり読めている
    flat = [word("本書は木造住宅の構造について解説をしています", 60,
                 100 + row * 60, 900, 40, 93.5) for row in range(8)]
    # それを縦に読み違えた「列」。信頼度は本文とほとんど並ぶ
    fakes = [word("活し", 700, 110, 40, 110, 94.5, angle=90),
             word("意載", 300, 350, 40, 110, 94.4, angle=90)]
    junk = pdf_ocr.pick_columns(fakes, flat)

    # 紙面が狭く、割合では弾けない場合。信頼度の差だけが頼りになる
    few = [word("木造住宅の構造", 60, 100 + row * 60, 300, 40, 93.5)
           for row in range(2)]
    close = [word("造構", 120, 110, 40, 110, 94.5, angle=90)]
    narrow = pdf_ocr.pick_columns(close, few)

    # 本物の縦組み（見出しが縦のページ）。横書きは同じ場所を読めていない
    real = [word("住宅品質確保", 160, 100, 44, 320, 90.0, angle=90)]
    aside = [word("建築物省エネ法の概要", 300, 100, 400, 40, 93.0)]
    kept = pdf_ocr.pick_columns(real, aside)

    ok = not junk and not narrow and len(kept) == 1
    print("偽の列   : %s  横組みだけの紙面で列を作らないこと（%d 本）・"
          "信頼度の差が僅かなら採らないこと（%d 本）・"
          "本物の縦組みは残すこと（%d 本）"
          % ("OK  " if ok else "NG  ", len(junk), len(narrow), len(kept)))
    return 0 if ok else 1


def check_vertical_numbers(tmpdir):
    """縦組みの中の横向きの数字（縦中横）が、列の途中に収まって読めるか。

    縦書き用の言語データは横向きの数字を読めない。直し方は 2 通りあり、
    どちらも見る。

      1950 … 1 文字分の幅からはみ出す置き方。縦書きは読み飛ばすので、
             横書きで読んだ数字を列に差し込む
      25   … 二桁を 1 文字に詰めた本来の縦中横。縦書きは別の 1 文字に
             読み違えるので、その文字を数字に置き換える

    どちらも、コピーしたときに列の途中に収まっていることまで確かめる。

    同梱の精度重視版 tessdata では、いまここが NG になる。数字の読み直し
    自体は正しく動くが、`pick_columns()` がそれを「偽の列」と誤認して
    丸ごと捨てる（横書きパスがすぐ隣を僅差の信頼度で読み違えるため）。
    実物の資料（README の「未解決：合成した縦中横テストで…」）には出て
    いない、合成ページ特有の症状。
    """
    import make_sample
    from pypdf import PdfReader

    src = make_sample.make_vertical(os.path.join(tmpdir, "tatechuyoko.pdf"))
    subprocess.run([sys.executable, SCRIPT, "--quiet", "--overwrite",
                    "--mode", "mixed", "--outdir", tmpdir, src], check=True)
    out = os.path.join(tmpdir, "tatechuyoko_OCR.pdf")
    text = "".join("".join((page.extract_text() or "").split())
                   for page in PdfReader(out).pages)

    before = text.find("建築基準法ができたのが")
    inserted = text.find("1950")
    replaced = "昭和25年" in text
    ok = before >= 0 and inserted > before and replaced
    print("縦中横   : %s  差し込み「1950」%s（列の途中 %s）・"
          "置き換え「昭和25年」%s"
          % ("OK  " if ok else "NG  ",
             "○" if inserted >= 0 else "×",
             "○" if before >= 0 and inserted > before else "×",
             "○" if replaced else "×"))
    return 0 if ok else 1


def check_illustration_junk():
    """縦組みの行にくっついたイラストの読み違いが落ちるか。

    縦組みの列の上にイラストがあると、その模様が「St」のような英字に
    読まれ、同じ行として本文につながる。つながると行の枠がイラストまで
    広がり、透明な文字が本物の文字より上にずれて置かれる。紙面を見て
    選択しても、ずれた分の文字が拾えない（実際に起きた不具合の再現）。

    OCR を通さず、行をまとめる処理だけを直接確かめる。
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import pdf_ocr

    def word(text, top, height):
        item = pdf_ocr.Word(text, 100, top, 30, height, conf=90.0)
        item.line = ("1", "1", "1")
        return item

    line = [word("St", 100, 40), word("木", 150, 30),
            word("造", 182, 30), word("KHOY", 215, 40)]
    merged = pdf_ocr.merge_lines(line)

    ok = (len(merged) == 1 and merged[0].text == "木造"
          and merged[0].top == 150 and merged[0].height == 62)
    print("イラスト : %s  行の前後の英字が落ちること（%s・枠 top=%s 高さ=%s）"
          % ("OK  " if ok else "NG  ",
             "".join(w.text for w in merged),
             merged[0].top if merged else "-",
             merged[0].height if merged else "-"))
    return 0 if ok else 1


def check_tatechuyoko_digits():
    """縦中横が「数字」に化けたときも直せるか。

    二桁を 1 文字の枠に詰めた数字は、別の 1 文字に化ける。化けた先は
    かなとは限らず、桁が潰れて数字になることがある（「(昭和25年)」→
    「(昭和1年)」）。数字だからといって正しいとは限らない。
    枠ひとつ分の所に数字が二つに割れて出ることもある（「56」→「5」＋別字）。

    OCR を通さず、置き換えの判断だけを直接確かめる。
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import pdf_ocr

    def word(text, top, height=30, left=100, width=30, conf=90.0, line="本文"):
        item = pdf_ocr.Word(text, left, top, width, height, conf=conf)
        item.line = line
        return item

    def column(middle):
        """「(昭和 ○ 年)」の形をした列。○ の所が読み違えられている。"""
        return ([word("(", 4), word("昭", 36), word("和", 68)] + middle
                + [word("年", 132), word(")", 164)])

    # 25 が「1」に化けた（桁が潰れて数字になった）
    collapsed = column([word("1", 100)])
    pdf_ocr.fix_tatechuyoko(collapsed, [word("25", 102, 22, 101, 26, 95.0)])
    one = "".join(w.text for w in collapsed)

    # 56 が「5」と「ぶ」に割れた。数字のほうが大きく重なるので置き換え先に
    # なり、残る片割れは数字ではない（「56ぶ年」になっていた）
    split = column([word("5", 100, 28, 100, 18), word("ぶ", 100, 28, 118, 12)])
    pdf_ocr.fix_tatechuyoko(split, [word("56", 101, 24, 100, 30, 95.0)])
    two = "".join(w.text for w in split)

    # 同じ場所に、本文の行に属さない 1 文字がより大きく重なって居る場合。
    # そちらに数字を移すと、その字だけの行になって捨てられ、数字ごと消える
    # （「昭和年」になっていた）
    stray = column([word("1", 110)])
    stray.append(word("・", 102, 22, 101, 26, line="行の外"))
    pdf_ocr.fix_tatechuyoko(stray, [word("25", 102, 22, 101, 26, 95.0)])
    three = "".join(w.text for w in stray if w.line == "本文")

    ok = (one == "(昭和25年)" and two == "(昭和56年)"
          and three == "(昭和25年)")
    print("縦中横の数字: %s  数字に化けた（%s）・二つに割れた（%s）・"
          "本文の行を選ぶ（%s）"
          % ("OK  " if ok else "NG  ", one, two, three))
    return 0 if ok else 1


def check_sideways_digits():
    """横書きで読んだ結果の中の縦中横も直せるか。

    縦組みの紙面を横書きの設定でも読む（そのページをどちらの読みで
    採用するかは、あとで信頼度を見て決める）。横書きの設定で読んでも、
    縦中横の数字は同じように 1 文字に化ける。実測（利用者の縦組みの
    資料、横書きパスの生の読み）。

        43 → 「は」   56 → 「%」と「ぶ」   12 → 「D」

    利用者が報告した `(昭和%ぶ年)` はこの「%」と「ぶ」そのもの。
    以前は縦書きパスにしか掛けていなかったので、**横書きパスが採用された
    ページでは、信頼度 96 で見つけた数字ごと捨てていた。**

    1 文字分の大きさは、縦組みなら列の幅、横組みなら行の高さで測る。
    ふつうの大きさで置かれた数字（縦中横ではないもの）を巻き込まない
    ことのほうが大事なので、そちらの例も見る。

    OCR は通さず、置き換えの判断だけを直接確かめる。
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import pdf_ocr

    def word(text, left, width, top=100, height=30, conf=90.0, line="本文"):
        item = pdf_ocr.Word(text, left, top, width, height, conf=conf)
        item.line = line
        return item

    def row(middle):
        """「(昭和 ○ 年)」の形をした横書きの行。○ が読み違えられている。"""
        return ([word("(", 4, 30), word("昭", 36, 30), word("和", 68, 30)]
                + middle + [word("年", 132, 30), word(")", 164, 30)])

    # 56 が「%」と「ぶ」に割れた（利用者の報告そのもの）
    split = row([word("%", 100, 18), word("ぶ", 118, 12)])
    pdf_ocr.fix_tatechuyoko(split, [word("56", 100, 30, 101, 24, 96.0)],
                            upright=False)
    two = "".join(w.text for w in split)

    # 43 が「は」1 文字に化けた
    one_char = row([word("は", 100, 30)])
    pdf_ocr.fix_tatechuyoko(one_char, [word("43", 100, 34, 101, 28, 96.0)],
                            upright=False)
    one = "".join(w.text for w in one_char)

    # ふつうの大きさで置かれた数字は、行の高さに収まらない。触らない
    plain = row([word("あ", 100, 30)])
    pdf_ocr.fix_tatechuyoko(plain, [word("1995", 100, 90, 101, 28, 96.0)],
                            upright=False)
    kept = "".join(w.text for w in plain)

    # 縦組みの判断（列の幅で測る）が変わっていないこと
    tall = [pdf_ocr.Word(t, 100, top, 30, 30, conf=90.0)
            for t, top in (("(", 4), ("昭", 36), ("和", 68), ("お", 100),
                           ("年", 132), (")", 164))]
    for item in tall:
        item.line = "本文"
    pdf_ocr.fix_tatechuyoko(tall, [word("25", 101, 26, 102, 22, 95.0)])
    upright = "".join(w.text for w in tall)

    ok = (two == "(昭和56年)" and one == "(昭和43年)"
          and kept == "(昭和あ年)" and upright == "(昭和25年)")
    print("横向きの数字: %s  二つに割れた（%s）・1 文字に化けた（%s）・"
          "ふつうの大きさは触らない（%s）・縦組みは今まで通り（%s）"
          % ("OK  " if ok else "NG  ", two, one, kept, upright))
    return 0 if ok else 1


def check_latin_runs(tmpdir):
    """日本語の語が英字に化けたものを、切り出して読み直せるか。

    利用者の資料で `本書は、` が `AIS,` になっていた。紙面全体を一度に
    読ませたときだけ起きる。**同じ場所を切り出して読み直すと
    `本書は、` が信頼度 93 で返る**（元の `AIS,` は 57.9）。実測では
    言語データを日本語だけにしても `jpn+eng` のままでも、PSM を
    7 / 8 / 6 / 13 のどれにしても、切り出せば正しく返った。

    ふつうの英字（`PDF` など）を壊さないことのほうが大事なので、
    触ってはいけない例も見る。

    tesseract は呼ばない。読み直しの相手だけを差し替えて、どの語を
    選ぶかの判断を確かめる。
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import pdf_ocr
    from PIL import Image

    page = os.path.join(tmpdir, "latin.png")
    Image.new("L", (900, 200), 255).save(page)

    def word(text, left, width, conf, line="本文"):
        item = pdf_ocr.Word(text, left, 40, width, 30, conf=conf)
        item.line = line
        return item

    # 切り出して読み直した結果を、こちらで決める
    answers = {}
    real = pdf_ocr.read_patch
    pdf_ocr.read_patch = (lambda patch, exe, env=None, tessdata=None,
                          lang="jpn_vert", psm=5, floor=50.0:
                          answers.get(patch.size, []))

    def run(items, reply):
        answers.clear()
        # 切り出しの大きさで返す答えを決める（幅＝語の幅＋余白 6×2）
        for target, got in reply.items():
            answers[(target + 12, 30 + 12)] = got
        return pdf_ocr.fix_latin_runs(items, page, "tesseract")

    try:
        # 1. 日本語の行に紛れた、自信のない英字（利用者の報告そのもの）
        line = [word("AIS,", 10, 64, 57.9),
                word("2025年4月の建築基準法改正による構造部分の", 80, 600, 94.0)]
        run(line, {64: [("本書は、", 93.0, 0, 30)]})
        fixed = "".join(w.text for w in line)

        # 2. 正しく読めている英字は、信頼度が高いので触らない
        safe = [word("PDF", 10, 64, 92.0),
                word("で保存してください。図面は原本と一緒に", 80, 600, 94.0)]
        run(safe, {64: [("ピーデーエフ", 95.0, 0, 30)]})
        untouched = "".join(w.text for w in safe)

        # 3. 読み直しても日本語が返らないなら、元のまま
        keep = [word("CAD", 10, 64, 40.0),
                word("で作った図面を読み込みます。原寸で出力", 80, 600, 94.0)]
        run(keep, {64: [("CAD", 99.0, 0, 30)]})
        latin = "".join(w.text for w in keep)

        # 4. 英字ばかりの行（英文）は、そもそも対象にしない
        english = [word("the", 10, 64, 40.0), word("quick brown fox", 80, 300, 94.0)]
        run(english, {64: [("日本語", 99.0, 0, 30)]})
        alone = "".join(w.text for w in english)
    finally:
        pdf_ocr.read_patch = real

    ok = (fixed.startswith("本書は、") and untouched.startswith("PDF")
          and latin.startswith("CAD") and alone.startswith("the"))
    print("英字化け : %s  日本語に戻すこと %s・自信のある英字は触らない %s・"
          "日本語が返らなければ元のまま %s・英文の行は対象外 %s"
          % ("OK  " if ok else "NG  ",
             "○" if fixed.startswith("本書は、") else "×",
             "○" if untouched.startswith("PDF") else "×",
             "○" if latin.startswith("CAD") else "×",
             "○" if alone.startswith("the") else "×"))
    return 0 if ok else 1


def check_number_insert():
    """読み飛ばされた縦中横の数字を、行の途中に差し込めるか。

    縦中横は 1 文字に化けるとは限らず、丸ごと読み飛ばされることもある。
    利用者の機械で変換された PDF から取り出した実物。

        1950年(昭和年)   ← 25 が 1 文字も無い
        2000年(平成年)   ← 12 が無い

    化けていれば置き換える相手がいるが、無ければいない。以前はここで
    信頼度 96 で見つけた数字を捨てていた。

    捨てていた理由は、ノンブル（ページ番号）のような本文と関係のない
    数字を列に差し込まないため。**その行の語に前後を挟まれている数字
    だけ**を差し込むようにして、両方を満たす。

    OCR は通さず、差し込みの判断だけを直接確かめる。
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import pdf_ocr

    def word(text, left, top, width=30, height=30, conf=93.0, line="本文"):
        item = pdf_ocr.Word(text, left, top, width, height, conf=conf)
        item.line = line
        return item

    # 1. 横組みの行。「(昭和」と「年)」の間が空いている
    row = [word("(昭和", 4, 100, 92), word("年)", 160, 100, 60)]
    got = pdf_ocr.insert_number(row, word("25", 100, 101, 26, 22, 97.0),
                                upright=False)
    row.sort(key=lambda w: w.left)
    filled = "".join(w.text for w in row)

    # 2. ノンブル。紙面の隅に 1 つで立っていて、挟む相手がいない
    page = [word("本文の行がここにあります", 4, 100, 360)]
    lone = pdf_ocr.insert_number(page, word("011", 4, 900, 40, 20, 96.0),
                                 upright=False)

    # 3. 縦組みの列。上下に挟まれていれば差し込む
    column = [word("(昭和", 100, 4, 30, 92), word("年)", 100, 160, 30, 60)]
    upright = pdf_ocr.insert_number(column, word("25", 101, 100, 22, 26, 97.0))
    column.sort(key=lambda w: w.top)
    stacked = "".join(w.text for w in column)

    # 4. 行の端。前にしか語が無ければ差し込まない（本文の続きではない）
    edge = [word("本文の行がここに", 4, 100, 240)]
    tail = pdf_ocr.insert_number(edge, word("25", 300, 101, 26, 22, 97.0),
                                 upright=False)

    ok = (got and filled == "(昭和25年)" and not lone
          and upright and stacked == "(昭和25年)" and not tail)
    print("数字の差し込み: %s  挟まれていれば差し込む（%s）・"
          "ノンブルは差し込まない %s・縦組みでも差し込む（%s）・"
          "行の端では差し込まない %s"
          % ("OK  " if ok else "NG  ", filled,
             "○" if not lone else "×", stacked, "○" if not tail else "×"))
    return 0 if ok else 1


def check_weak_line(tmpdir):
    """自信の低い行を、その行だけ読み直して差し替えられるか。

    紙面全体を一度に読ませると、まわりに引きずられて 1 行だけ崩れる
    ことがある。利用者の資料の署名の行での実測（tesseract 5.5.3、500dpi）。

        紙面全体      2024 …… 月佐藤実   （年10 が消える）平均 57.5
        その行だけ    2024年10月佐藤実                     92

    **行としてまとめる前に呼ぶ。** まとめたあとでは「2024」と
    「月佐藤実」の 2 つに切れてしまい、消えた `年10` はちょうどその
    すきまにあるので、片方だけを切り出しても拾えない。

    行を丸ごと入れ替えるので、悪くしないことのほうが大事。触っては
    いけない例を厚くする。tesseract は呼ばず、読み直しの相手を
    差し替えて判断だけを見る。
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import pdf_ocr
    from PIL import Image

    page = os.path.join(tmpdir, "weak.png")
    Image.new("L", (900, 200), 255).save(page)

    def word(text, left, width, conf, line="本文"):
        item = pdf_ocr.Word(text, left, 40, width, 30, conf=conf)
        item.line = line
        return item

    reply = {"v": []}
    real = pdf_ocr.read_line
    pdf_ocr.read_line = (lambda patch, exe, env=None, tessdata=None,
                         lang="jpn", psm=13: reply["v"])

    def answer(pairs):
        out = []
        for index, (text, conf) in enumerate(pairs):
            item = pdf_ocr.Word(text, index * 40, 40, 38, 30, conf=conf)
            item.line = "読み直し"
            out.append(item)
        return out

    try:
        # 1. 消えた字が戻り、信頼度も上がる → 差し替える
        line = [word("2024", 10, 109, 31.5), word("月佐藤実", 180, 182, 82.4)]
        reply["v"] = answer([("2024年10月佐藤実", 92.0)])
        pdf_ocr.reread_weak_lines(line, page, "tesseract")
        fixed = "".join(w.text for w in line)

        # 2. 読み直しのほうが短い → 触らない（字を減らさない）
        short = [word("2024", 10, 109, 31.5), word("月佐藤実", 180, 182, 82.4)]
        reply["v"] = answer([("2024月", 99.0)])
        pdf_ocr.reread_weak_lines(short, page, "tesseract")
        kept = "".join(w.text for w in short)

        # 3. 読み直しのほうが信頼度が低い → 触らない
        worse = [word("2024", 10, 109, 31.5), word("月佐藤実", 180, 182, 82.4)]
        reply["v"] = answer([("2024年10月佐藤実", 40.0)])
        pdf_ocr.reread_weak_lines(worse, page, "tesseract")
        same = "".join(w.text for w in worse)

        # 4. 読み直しに漢字かなが無い → 触らない
        latin = [word("2024", 10, 109, 31.5), word("月佐藤実", 180, 182, 82.4)]
        reply["v"] = answer([("2024AB10CD", 99.0)])
        pdf_ocr.reread_weak_lines(latin, page, "tesseract")
        plain = "".join(w.text for w in latin)

        # 5. 自信のある行でも、読み直しが上回れば差し替える。**これは
        #    以前は触らなかった。全部の行を見るほうが良いと実測で分かり、
        #    条件を「信頼度が低い行」から「読み直しが上回る行」に変えた。**
        good = [word("をなくす次も多く目にします", 10, 400, 92.0)]
        reply["v"] = answer([("をなくす姿も多く目にします", 93.0)])
        pdf_ocr.reread_weak_lines(good, page, "tesseract")
        strong = "".join(w.text for w in good)
    finally:
        pdf_ocr.read_line = real

    ok = (fixed == "2024年10月佐藤実" and kept == "2024月佐藤実"
          and same == "2024月佐藤実" and plain == "2024月佐藤実"
          and strong == "をなくす姿も多く目にします")
    print("弱い行 : %s  消えた字が戻ること（%s）・短くなるなら触らない %s・"
          "信頼度が下がるなら触らない %s・漢字かなが無ければ触らない %s・"
          "上回れば自信のある行も直すこと（%s）"
          % ("OK  " if ok else "NG  ", fixed,
             "○" if kept == "2024月佐藤実" else "×",
             "○" if same == "2024月佐藤実" else "×",
             "○" if plain == "2024月佐藤実" else "×", strong))
    return 0 if ok else 1


def check_upright_pass(tmpdir):
    """横書きで読むパスにだけ、縦組み判定を切る指定が付くか。

    見開きの紙面では、右の頁が縦組みというだけで、左の頁にある横書きの
    段落まで縦組みとして読まれる。実測（利用者の縦組みの資料
    `1ca57185-____1.pdf`、500dpi、tesseract 5.5.3）。

        紙面の全体をそのまま     `改-:改=討性例人能` `1ご:法か震特性`
        段落だけ切り出して      `新耐震基準ができた3年後の1984年に…`
        紙面の全体 + この指定    `新耐震基準ができた3年後の1984年に…`

    縦組みは LANG2 の縦書きパス（PSM 5）が別に読むので、横書きの
    パスで縦組みを探す必要はない。**縦書きのパスには付けない。**
    付ければ縦組みそのものが読めなくなる。

    tesseract は呼ばず、渡した引数だけを見る。
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import pdf_ocr
    from PIL import Image

    page = os.path.join(tmpdir, "upright.png")
    Image.new("RGB", (600, 400), "white").save(page)

    BASE = {"MINCONF": "30", "NUMBERS": "no", "AUTOROTATE": "no",
            "SPARSEUNDER": "0", "SPARSEPSM": ""}
    calls = []
    real = pdf_ocr.run_tesseract

    def fake(exe, args, timeout=600, env=None, tessdata=None):
        calls.append(list(args))
        return ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
                "left\ttop\twidth\theight\tconf\ttext\n")

    def used(lang):
        for args in calls:
            if "-l" in args and args[args.index("-l") + 1] == lang:
                return "textord_tabfind_vertical_text=0" in args
        return None

    try:
        pdf_ocr.run_tesseract = fake
        # 横書きが主、縦組みを二度目に読む（混在の既定）
        pdf_ocr.ocr_image("tesseract", page, (600, 400),
                          dict(BASE, LANG="jpn+eng", PSM="3",
                               LANG2="jpn_vert+jpn", PSM2="5"), retry=False)
        flat_on = used("jpn+eng")
        vert_off = used("jpn_vert+jpn")

        # 縦組みが主のときも、縦書きのパスには付けない
        calls[:] = []
        pdf_ocr.ocr_image("tesseract", page, (600, 400),
                          dict(BASE, LANG="jpn_vert+jpn", PSM="5"), retry=False)
        first_off = used("jpn_vert+jpn")
    finally:
        pdf_ocr.run_tesseract = real

    ok = (flat_on is True and vert_off is False and first_off is False
          and pdf_ocr.upright_only(False) == ["-c",
                                              "textord_tabfind_vertical_text=0"]
          and pdf_ocr.upright_only(True) == [])
    print("読む向き : %s  横書きのパスに付くこと %s・"
          "縦書きのパスには付けないこと %s・主が縦組みでも付けないこと %s"
          % ("OK  " if ok else "NG  ",
             "○" if flat_on is True else "×",
             "○" if vert_off is False else "×",
             "○" if first_off is False else "×"))
    return 0 if ok else 1


def check_stacked_digits():
    """縦に 1 文字ずつ積まれた数字を、読み直して直せるか。

    西暦は縦組みでも 1 文字ずつ縦に積んで組む。縦書き用の言語データは
    これを 1 つの語として読もうとして外す（実測で「1950」を「1930」と
    読んだ）。信頼度は当てにならず、同じ誤読が Linux 版では 24、
    Windows 版では 87 で返ってきた。信頼度で読み直す・読み直さないを
    決めると、一番直したいものが素通りする。

    切り出しと 1 文字ずつの読み取り、そして「信頼度が高くても読み直す」
    ことを確かめる。数字の後ろに続く漢字を巻き込まないことも見る。
    """
    from PIL import Image, ImageDraw, ImageFont

    sys.path.insert(0, os.path.join(ROOT, "src"))
    sys.path.insert(0, HERE)
    import make_sample
    import pdf_ocr

    font = ImageFont.truetype(make_sample.find_font(), 40)
    image = Image.new("L", (120, 340), 252)
    draw = ImageDraw.Draw(image)
    y = 20
    for ch in ["2", "0", "2", "4", "年"]:
        draw.text((40, y), ch, font=font, fill=20)
        y += 60

    exe = pdf_ocr.find_tesseract("")
    env = pdf_ocr.ocr_env(1)
    # 枠は数字の下の「年」まで含む（tesseract が実際にそう返すため）
    word = pdf_ocr.Word("2024", 38, 20, 44, 300, conf=24.0)
    got = pdf_ocr.read_stacked(image, word, exe, env)

    handle, path = tempfile.mkstemp(prefix="pdf_ocr_check_", suffix=".png")
    os.close(handle)
    try:
        image.save(path)
        # 自信のある誤読。信頼度で選り分けていると、これが素通りする
        confident = pdf_ocr.Word("2028", 38, 20, 44, 300, conf=87.0)
        confident.line = ("1", "1", "1")
        words = [confident]
        pdf_ocr.fix_stacked_digits(words, path, exe, env)
        fixed = confident.text
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    ok = got == "2024" and fixed == "2024"
    print("積んだ数字: %s  1 文字ずつ読み直せること（「%s」→「%s」）・"
          "信頼度 87 の誤読も直すこと（「2028」→「%s」）"
          % ("OK  " if ok else "NG  ", word.text, got, fixed))
    return 0 if ok else 1


def check_gap_fill():
    """列の途中で落ちた字を、すきまを切り出して拾い直せるか。

    紙面には出ているのに、1 枚まるごと読ませると 1〜2 字だけ候補にも
    現れないことがある。実際の本で「(昭和25年)」の「昭和」が丸ごと
    消えた。切り出して読ませ直せば拾える（実測で信頼度 90）。

    「(」と「25」に挟まれた所に「昭和」を置いた列を作り、上下の相手が
    かなでも漢字でもない（かっこと数字）場合でも拾えることを見る。
    詰めて並んだ所を読みに行かないことも、同時に確かめる。
    """
    from PIL import Image, ImageDraw, ImageFont

    sys.path.insert(0, os.path.join(ROOT, "src"))
    sys.path.insert(0, HERE)
    import make_sample
    import pdf_ocr

    font = ImageFont.truetype(make_sample.find_font(), 40)
    image = Image.new("L", (140, 560), 252)
    draw = ImageDraw.Draw(image)
    # 「(昭和25年)から」の列。1 字 50px 送りで、詰めて並べる
    column = ["(", "昭", "和", "2", "5", "年", ")", "か", "ら"]
    tops = {}
    y = 20
    for ch in column:
        draw.text((45, y), ch, font=font, fill=20)
        tops[ch] = y
        y += 50

    handle, path = tempfile.mkstemp(prefix="pdf_ocr_gap_", suffix=".png")
    os.close(handle)
    words = []
    try:
        image.save(path)
        # tesseract が「昭和」を落とした状態を作る。その他は読めている
        for ch in column:
            if ch in ("昭", "和"):
                continue
            word = pdf_ocr.Word(ch, 45, tops[ch], 40, 40, angle=90, conf=90.0)
            word.line = ("1", "1", "1")
            words.append(word)
        exe = pdf_ocr.find_tesseract("")
        added = pdf_ocr.fill_vertical_gaps(words, path, exe,
                                           pdf_ocr.ocr_env(1))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    words.sort(key=lambda word: word.top)
    got = "".join(word.text for word in words)
    # 詰まっている所（「2」「5」の間など）を読みに行っていないこと
    extra = len(words) - len(column) + 2 - added
    ok = "昭和" in got and added <= 2 and extra == 0
    print("すきま拾い: %s  落ちた「昭和」を拾い直せること（「%s」）・"
          "詰まった所は触らないこと（拾い直し %d 回）"
          % ("OK  " if ok else "NG  ", got, added))
    return 0 if ok else 1


def check_fine_image(tmpdir):
    """細かい画像が小さなページに貼ってあるとき、解像度を上げて読むか。

    本を見開きで取り込んだ資料がこれにあたる。決め打ちの 300dpi で
    描き出すと元の画像を縮めてから読むことになり、小さな文字を丸ごと
    取りこぼす（実際に起きた不具合の再現）。
    """
    import make_sample
    import pypdfium2 as pdfium
    from pypdf import PdfReader

    sys.path.insert(0, os.path.join(ROOT, "src"))
    import pdf_ocr

    src = make_sample.make_dense(os.path.join(tmpdir, "dense.pdf"))
    document = pdfium.PdfDocument(src)
    found = pdf_ocr.native_dpi(document, 0)
    used = pdf_ocr.page_dpi(document, 0, 300, 600)
    document.close()

    results = {}
    for name, extra in (("fixed", ["--dpi", "300", "--maxdpi", "0"]),
                        ("auto", [])):
        subprocess.run([sys.executable, SCRIPT, "--quiet", "--overwrite",
                        "--suffix", "_" + name, "--outdir", tmpdir]
                       + extra + [src], check=True)
        out = os.path.join(tmpdir, "dense_%s.pdf" % name)
        results[name] = "".join("".join((page.extract_text() or "").split())
                                for page in PdfReader(out).pages)

    phrase = "柱頭柱脚の接合"
    ok = (500 <= found <= 600 and used == found
          and phrase in results["auto"] and phrase not in results["fixed"])
    print("画像の細かさ: %s  %ddpi と読んで %ddpi で処理・"
          "「%s」（上げると %s / 300dpi 固定では %s）"
          % ("OK  " if ok else "NG  ", found, used, phrase,
             "○" if phrase in results["auto"] else "×",
             "×" if phrase not in results["fixed"] else "○"))
    return 0 if ok else 1


def wrapped_in_form(src, dst):
    """ページの中身をまるごと Form XObject に包んだ PDF を作る。

    ページを抜き出すソフトの出力にある構造。中に入った見えない文字を
    消せないと、入れ直したときにテキスト層が二重になる。
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import (ArrayObject, DecodedStreamObject,
                               DictionaryObject, FloatObject, NameObject,
                               ContentStream)

    reader = PdfReader(src)
    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        box = page.mediabox
        form = DecodedStreamObject()
        form[NameObject("/Type")] = NameObject("/XObject")
        form[NameObject("/Subtype")] = NameObject("/Form")
        form[NameObject("/BBox")] = ArrayObject(
            [FloatObject(box.left), FloatObject(box.bottom),
             FloatObject(box.right), FloatObject(box.top)])
        form[NameObject("/Resources")] = page[NameObject("/Resources")]
        form.set_data(ContentStream(page.get_contents(), writer).get_data())

        xobjects = DictionaryObject()
        xobjects[NameObject("/Xf1")] = writer._add_object(form)
        resources = DictionaryObject()
        resources[NameObject("/XObject")] = xobjects
        page[NameObject("/Resources")] = resources

        contents = DecodedStreamObject()
        contents.set_data(b"q /Xf1 Do Q")
        page[NameObject("/Contents")] = writer._add_object(contents)
    with open(dst, "wb") as f:
        writer.write(f)
    return dst


def check_retext_in_form(tmpdir):
    """包まれた中の見えない文字も消してから入れ直せるか。"""
    from pypdf import PdfReader

    once = convert(SAMPLE, tmpdir)
    plain = page_lengths(once)

    src = wrapped_in_form(once, os.path.join(tmpdir, "wrapped.pdf"))
    subprocess.run([sys.executable, SCRIPT, "--quiet", "--overwrite",
                    "--retext", "--suffix", "_again", "--outdir", tmpdir,
                    src], check=True)
    again = page_lengths(os.path.join(tmpdir, "wrapped_again.pdf"))

    ok = (len(plain) == len(again)
          and all(a <= p * 1.4 + 5 for p, a in zip(plain, again)))
    print("入れ直し : %s  包まれた中の元の文字が消えていること"
          "（%s → %s。消せないと倍に増える）"
          % ("OK  " if ok else "NG  ", plain, again))
    return 0 if ok else 1


def main():
    sys.path.insert(0, HERE)
    failures = 0
    with tempfile.TemporaryDirectory(prefix="pdf_ocr_check_") as tmpdir:
        failures += check_no_leak(tmpdir)
        failures += check_line_continuity(tmpdir)
        failures += check_mixed(tmpdir)
        failures += check_two_column(tmpdir)
        failures += check_reversed(tmpdir)
        failures += check_thin_langs()
        failures += check_text_fixes()
        failures += check_conf_holes()
        failures += check_fake_columns()
        failures += check_vertical_numbers(tmpdir)
        failures += check_illustration_junk()
        failures += check_tatechuyoko_digits()
        failures += check_sideways_digits()
        failures += check_latin_runs(tmpdir)
        failures += check_number_insert()
        failures += check_weak_line(tmpdir)
        failures += check_upright_pass(tmpdir)
        failures += check_stacked_digits()
        failures += check_gap_fill()
        failures += check_fine_image(tmpdir)
        failures += check_retext_in_form(tmpdir)
        for rotation in (0, 90, 180, 270):
            src = os.path.join(tmpdir, "sample_%d.pdf" % rotation)
            rotated_copy(SAMPLE, src, rotation)
            out = convert(src, tmpdir)

            text = extracted_text(out)
            missing = [word for word in KEYWORDS if word not in text]
            ratio = placement_ratio(out)

            ok = not missing and ratio >= MIN_PLACED
            failures += 0 if ok else 1
            print("%3d 度 : %s  取り出せない語=%s  位置が合った割合=%.0f%%"
                  % (rotation, "OK  " if ok else "NG  ",
                     ",".join(missing) or "なし", ratio * 100))

    print("結果:", "すべて OK" if not failures else "%d 件 NG" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
