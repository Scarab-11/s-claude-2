#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""動作確認用の「画像だけの PDF」を作る（src/サンプル.pdf の原本）。

スキャンした紙を模して、わざと少し傾け、薄い汚れを入れてある。
    python3 tools/make_sample.py
"""

import os
import random

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "src", "サンプル.pdf")

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    r"C:\Windows\Fonts\msgothic.ttc",
]

W, H = 1240, 1754          # A4 を 150dpi で

PAGE1 = [
    (46, "工事写真台帳"),
    (34, ""),
    (34, "現場名   第二駐車場 舗装工事"),
    (34, "発注者   南川市 建設部 道路課"),
    (34, "施工者   株式会社 山田建設"),
    (34, "工期     2026年4月1日 から 2026年6月30日"),
    (34, "図面番号 A-102   縮尺 1/100"),
    (34, ""),
    (34, "備考"),
    (30, "  ・アスファルト舗装 t=50mm"),
    (30, "  ・区画線 白色 実線 W=150mm"),
    (30, "  ・排水勾配 2.0% 以上を確保すること"),
]

PAGE2 = [
    (40, "数量表"),
    (30, ""),
    (30, "番号   品名           単位   数量    単価"),
    (30, "1      As合材         t      12.5    18,400"),
    (30, "2      再生砕石 RC-40  m3     34.0     4,250"),
    (30, "3      区画線 W=150    m     186.0     1,180"),
    (30, "4      集水桝 300角    箇所     6.0    32,000"),
    (30, ""),
    (30, "合計                                  1,284,600"),
]


def find_font():
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    raise SystemExit("日本語フォントが見つかりません")


def make_page(lines, font_path, seed):
    random.seed(seed)
    image = Image.new("L", (W, H), 252)
    draw = ImageDraw.Draw(image)
    y = 190
    for size, text in lines:
        if text:
            font = ImageFont.truetype(font_path, size)
            draw.text((150, y), text, font=font, fill=25)
        y += int(size * 1.9)

    # スキャンらしく、薄い汚れと紙のムラを足す
    pixels = image.load()
    for _ in range(4000):
        x = random.randrange(W)
        y = random.randrange(H)
        pixels[x, y] = max(0, pixels[x, y] - random.randrange(40, 120))

    return image.rotate(0.4, resample=Image.BICUBIC, fillcolor=252)


def make_mixed(path):
    """縦横が混ざったページを作る（表の見出しが縦組みの資料を模した検証用）。

    tools/selfcheck.py から呼ばれる。リポジトリには入れない。
    """
    font_path = find_font()
    image = Image.new("L", (W, H), 252)
    draw = ImageDraw.Draw(image)

    # 横書きの本文
    font = ImageFont.truetype(font_path, 34)
    y = 180
    for line in ["建築物省エネ法（概要）", "住宅性能表示基準について",
                 "高層建築物の防災対策"]:
        draw.text((300, y), line, font=font, fill=25)
        y += 80

    # 左端の見出しは縦組み
    font = ImageFont.truetype(font_path, 38)
    y = 180
    for char in "住宅品質確保":
        draw.text((160, y), char, font=font, fill=25)
        y += 52

    # 表の罫線
    draw.rectangle((130, 150, 1100, 460), outline=60, width=3)
    draw.line((270, 150, 270, 460), fill=60, width=3)

    image.convert("RGB").save(path, "PDF", resolution=150.0)
    return path


def make_two_column(path):
    """二段組み（見開き）のページを作る。

    上から下へだけで並べると、左の段の 1 行目・右の段の 1 行目…と
    交互になり、コピーした文章が互い違いになる。tools/selfcheck.py から
    呼ばれる。リポジトリには入れない。
    """
    font_path = find_font()
    image = Image.new("L", (2400, 1000), 252)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 30)

    left = ["本書は、木造住宅の「構造」について解説をしています。",
            "木造住宅に「なぜ、構造」と思われるかもしれません。",
            "一般的に構造計算は、鉄骨造や鉄筋コンクリート造",
            "などの大規模な建築物に対して行うものだと思われて",
            "いるからです。木造住宅の世界では経験と勘でした。"]
    right = ["構造のセミナーを受講しても理解できない、構造を",
             "教えてくれる人が身近にいないという方は、筆者が",
             "行っている構造塾をご活用ください。筆者自らが、",
             "本書の内容をわかりやすく解説する講座を開催し、",
             "構造を気軽に相談できる窓口も開設しています。"]
    y = 120
    for one, other in zip(left, right):
        draw.text((120, y), one, font=font, fill=25)
        draw.text((1320, y), other, font=font, fill=25)
        y += 90

    image.convert("RGB").save(path, "PDF", resolution=150.0)
    return path


def make_reversed(path):
    """色の付いた帯の上に、白抜きで組んだ見出しを置いたページを作る。

    実際の書籍でよくある組み方。白黒（グレースケール）に落としてから
    読むと、この見出しだけが読めなくなる。オレンジ（196,110,50）は
    輝度に直すと 154 まで明るくなり、白い文字（254）との差が 100 しか
    残らないため。色のまま渡せば、青の板で 190 の差がある。

    tools/selfcheck.py から呼ばれる。リポジトリには入れない。
    """
    font_path = find_font()
    image = Image.new("RGB", (1800, 700), (252, 252, 250))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 44)

    # 白抜きの見出し（オレンジの帯 ＋ 白い文字）
    draw.rectangle((110, 90, 700, 170), fill=(196, 110, 50))
    draw.text((130, 100), "本書の構成とねらい", font=font, fill=(255, 255, 255))

    # 同じページに、ふつうの黒い本文も置く。色を捨てないようにした変更で
    # こちらが悪くなっていないことも、同時に見るため。
    body = ["本書は、項目ごとに会話形式の文章と図解で構成されています。",
            "読者の方は、最初に会話を通じて興味や疑問を持ちます。"]
    y = 260
    for line in body:
        draw.text((120, y), line, font=font, fill=(25, 25, 25))
        y += 110

    image.save(path, "PDF", resolution=200.0)
    return path


def make_vertical(path):
    """縦組みの中に横向きの数字が入るページ（縦中横）を作る。

    数字の入れ方を 2 通り用意する。

      ("1950",)  … 1 文字分の幅からはみ出す置き方。縦書きの読み取りは
                   ここを読み飛ばすので、横書きで読んだ数字を列に
                   差し込んで直す
      ["2", "5"] … 二桁を 1 文字分の枠に詰めた、本来の縦中横。縦書きの
                   読み取りは、ここを別の 1 文字に読み違える。その 1 文字を
                   数字に置き換えて直す

    tools/selfcheck.py から呼ばれる。リポジトリには入れない。
    """
    font_path = find_font()
    image = Image.new("L", (900, 1300), 251)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 32)
    small = ImageFont.truetype(font_path, 26)
    tiny = ImageFont.truetype(font_path, 20)

    columns = [
        ["建", "築", "基", "準", "法", "が", "で", "き", "た", "の", "が",
         ("1950",), "年", "（", "昭", "和", ["2", "5"], "年", "）", "。"],
        ["耐", "震", "基", "準", "が", "変", "わ", "っ", "た", "の", "が",
         ("1981",), "年", "。"],
    ]
    x = 900 - 150
    for column in columns:
        y = 150
        for item in column:
            if isinstance(item, tuple):
                draw.text((x - 4, y + 4), item[0], font=small, fill=20)
                y += 40
            elif isinstance(item, list):
                # 二桁を 1 文字分の枠に詰める（縦中横）
                for offset, digit in enumerate(item):
                    draw.text((x + offset * 17, y + 8), digit, font=tiny, fill=20)
                y += 38
            else:
                draw.text((x, y), item, font=font, fill=20)
                y += 38
        x -= 100

    image.convert("RGB").save(path, "PDF", resolution=150.0)
    return path


def make_dense(path, page_width=300.0, page_height=200.0):
    """細かい画像を小さなページに貼った PDF を作る（本の見開きを模した検証用）。

    紙面を 570dpi ほどで取り込んだ画像が、300dpi 相当の小さなページに
    貼られている状態。決め打ちの解像度で描き出すと画像を縮めてから読む
    ことになり、小さな文字を丸ごと取りこぼす。

    tools/selfcheck.py から呼ばれる。リポジトリには入れない。
    """
    font_path = find_font()
    width = int(page_width / 72.0 * 570)
    height = int(page_height / 72.0 * 570)
    image = Image.new("L", (width, height), 252)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 24)
    y = 80
    for line in ["建築基準法の改正について", "耐震性能の移り変わり",
                 "壁量計算と柱頭柱脚の接合"]:
        draw.text((90, y), line, font=font, fill=30)
        y += 60

    # 取り込んだ紙らしく、細かい汚れを足す（縮めると文字とまざる）
    random.seed(7)
    pixels = image.load()
    for _ in range(width * height // 120):
        pixels[random.randrange(width), random.randrange(height)] = \
            random.randrange(150, 230)

    image.convert("RGB").save(path, "PDF", resolution=570.0)
    return path


def main():
    font_path = find_font()
    pages = [make_page(PAGE1, font_path, 1), make_page(PAGE2, font_path, 2)]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pages[0].save(OUT, "PDF", resolution=150.0, save_all=True,
                  append_images=pages[1:])
    print("作成しました: %s (%.0f KB)"
          % (OUT, os.path.getsize(OUT) / 1024.0))


if __name__ == "__main__":
    main()
