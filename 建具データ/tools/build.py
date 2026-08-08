#!/usr/bin/env python3
"""JW_OPT1B_扉厚折戸入り.DAT から配布版 JW_OPT1B.DAT を組み立てる。

    python3 tools/build.py

やることは2つだけ。

1. 扉厚まで描く詳細版の折戸(元の15・16番)を取り除く
   折戸の軸を壁中心に合わせる Y+35 の移動と両立しない(理由は README.md 参照)。
   1/100 では扉厚を描く必要がないため配布版からは外している。
   復元したくなったら JW_OPT1B_扉厚折戸入り.DAT の方を使う。

2. 親子ドアー(12番)を複製して子扉400・450を末尾に足す
   子扉寸法は座標に直接書かれた固定値なので、寸法違いは建具を分けるしかない。
   12番の行をそのまま写して "300" を置き換えるだけで、他は一切変えない。
   12番の直後ではなく末尾に足しているのは、折戸の番号(13・14番)を動かさないため。

残す建具のデータには手を触れない。編集後は check.py を通すこと。
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "JW_OPT1B_扉厚折戸入り.DAT"
DST = HERE / "JW_OPT1B.DAT"

DROP = ("折戸（開き60度）", "折戸（開き75度）")   # 末尾2件のみが対象
BASE = "親子ドアー（子扉300）"                   # 複製元
WIDTHS = (400, 450)                             # 追加する子扉寸法

TERM = re.compile(r"^\s*(999|995|991)\b")
HEAD = re.compile(r"^\s*(\d+)\s{2,}(\S.*)$")


def entries(lines):
    """(開始行, 終端行) を先頭から順に返す。"""
    out, start = [], None
    for i, line in enumerate(lines[5:], start=5):
        s = line.strip()
        if s in ("", "#", "\x1a"):
            continue
        if start is None:
            if HEAD.match(line):
                start = i
            continue
        if TERM.match(line):
            out.append((start, i))
            start = None
    return out


def main():
    lines = SRC.read_bytes().decode("cp932").split("\r\n")
    ent = entries(lines)
    if len(ent) != 16:
        sys.exit("扉厚折戸入りのはずが %d 件だった" % len(ent))

    names = [HEAD.match(lines[a]).group(2).strip() for a, _ in ent]
    for name in names[14:]:
        if name not in DROP:
            sys.exit("15・16番が想定と違う: %s" % name)
    if names[11] != BASE:
        sys.exit("12番が %s ではない: %s" % (BASE, names[11]))

    # 追加する親子ドアーを、12番の行をそのまま写して作る。
    # "300" は建具名と2行の座標にしか出てこないので単純置換で足りる。
    # 400・450 も3桁なので桁揃えも崩れない。
    a, b = ent[11]
    base = lines[a:b + 1]
    # 建具名に1つ、右端部線の行に2つ(始点X・終点X)、子扉の2行に1つずつで計5つ
    # (子扉は「線＋円弧を線色2」と「線だけ線色6」の2行で描いている)
    if sum(ln.count("300") for ln in base) != 5:
        sys.exit("12番の '300' の出現数が想定(5)と違う")
    added = []
    for w in WIDTHS:
        added += ["#"] + [ln.replace("300", str(w)) for ln in base]

    # 15番の直前の '#' から 16番の終端までを削る
    cut = ent[14][0]
    while lines[cut - 1].strip() == "#":
        cut -= 1
    del lines[cut:ent[15][1] + 1]

    # 末尾(最後の 999 の直後)に追加分を差し込む
    tail = len(lines) - 1
    while not TERM.match(lines[tail]):
        tail -= 1
    lines[tail + 1:tail + 1] = added

    # 見出しの登録件数を実際の件数に合わせる(数が違うと Jw_cad の表示が崩れる)
    count = len(entries(lines))
    if count != 14 + len(WIDTHS):
        sys.exit("組み立て後の件数が想定と違う: %d 件" % count)
    lines[2] = str(count)

    DST.write_bytes("\r\n".join(lines).encode("cp932"))
    print("%s を書き出した (%d バイト)" % (DST.name, DST.stat().st_size))


if __name__ == "__main__":
    main()
