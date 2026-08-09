#!/usr/bin/env python3
"""JW_OPT1B_扉厚折戸入り.DAT から配布版 JW_OPT1B.DAT を組み立てる。

    python3 tools/build.py

やることは2つだけ。

1. 配布しない折戸を取り除く
   ・折戸(開き60度)……建具用包絡をかけると内側の羽根が延長されて壊れる
   ・扉厚まで描く詳細版の折戸2件……折戸の軸を壁中心に合わせる Y+35 と両立しない
   いずれも理由は README.md 参照。復元したくなったら
   JW_OPT1B_扉厚折戸入り.DAT の方を使う。

2. 親子ドアー(12番)を複製して子扉400・450を末尾に足し、
   折戸(開き75度)を複製して見込線を足したものをさらに末尾に足す
   子扉寸法は座標に直接書かれた固定値なので、寸法違いは建具を分けるしかない。
   12番の行をそのまま写して "300" を置き換えるだけで、他は一切変えない。
   12番の直後ではなく末尾に足しているのは、折戸の番号(13・14番)を動かさないため。

3. 左右反転した建具を末尾に足す(17〜23番)
   建具データの書式には「反転」の指定が無く、コントロールバーに項目を
   増やすこともできない。反転させたいものは建具として別に登録するしかない。
   反転は機械的な変換なので手では書かず、mirror() で作る。

残す建具のデータには手を触れない。編集後は check.py を通すこと。
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "JW_OPT1B_扉厚折戸入り.DAT"
DST = HERE / "JW_OPT1B.DAT"

# 配布版から外す建具。元ファイル上の位置(0始まり)と建具名で二重に確かめる。
DROP = {12: "折戸（開き60度）",          # 包絡で壊れる
        14: "折戸（開き60度）",          # 扉厚を描く詳細版
        15: "折戸（開き75度）"}          # 扉厚を描く詳細版
BASE = "親子ドアー（子扉300）"                   # 複製元
WIDTHS = (400, 450)                             # 追加する子扉寸法

# 末尾に足す「見込線付きの折戸」。折戸(開き75度)を写して見込線を2本足すだけ。
FOLD = 13                          # 元ファイル上の位置(0始まり) = 14番 折戸(開き75度)
FOLD_NAME = "折戸（見込線付）"
FOLD_ADD = ["1 9   0   0   0   0   2 0 -1", "1 9   0  70   0  70   2 0 -1"]

# 左右反転して末尾に足す建具(組み立て後の建具名で指定する)。
# 左右対称なもの(引違い・両開き戸・折戸・ドアー(１レイヤ躯体線付))は
# 反転しても同じ形になるので入れない。
MIRROR = ["片引戸",
          "ドアー（見込線付）",
          "親子開き戸（見込線付）",
          "ドアー",
          "親子ドアー（子扉300）",
          "親子ドアー（子扉400）",
          "親子ドアー（子扉450）"]

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


def append_tail(lines, block):
    """最後の終端行の直後に block を差し込む(末尾に建具を1件以上足す)。"""
    tail = len(lines) - 1
    while not TERM.match(lines[tail]):
        tail -= 1
    lines[tail + 1:tail + 1] = block


def num(v):
    """座標・角度を書き戻す。-0 が出ないようにしておく。"""
    if v == 0:
        v = 0.0
    return "%g" % v


def mirror(block, div):
    """建具1件分の行を左右反転して返す。block は 建具名行〜終端行。

    反転は
        ・点番号 p → 分割数+1-p (左端と右端が入れ替わる)
        ・X の符号を変える (Y はそのまま。上下は反転しない)
        ・円弧の回り方向を変える (角度の符号を変える)
    の3つだけ。円弧コードは「中心→始点/終点」の区別なので変えない。

    X方向の伸縮規則(左ブロックは-20mm以下、右ブロックは20mm以上の端が
    枠幅に追従し、それ以外は動かない)は左右対称なので、この変換で
    伸び縮みのしかたもそのまま反転する。親子ドアーの子扉が右端から
    -300 で書いてあるものは、反転すると左端から +300 になり、
    やはり動かない側に入る。
    """
    name = HEAD.match(block[0])
    out = [block[0].replace(name.group(2).strip(), mirror_name(name.group(2).strip()))]
    for line in block[1:-1]:
        t = line.split()
        if not t or not t[0][0].isdigit():        # 基準寸法の S / s 行など
            out.append(line)
            continue
        p1, p2 = div + 1 - int(t[0]), div + 1 - int(t[1])
        x1, y1, x2, y2 = (float(v) for v in t[2:6])
        ei = next((k for k, v in enumerate(t) if v.lower() == "e"), len(t))
        s = "%d %d %5s %4s %5s %4s" % (p1, p2, num(-x1), num(y1), num(-x2), num(y2))
        if ei > 6:
            s += "   %s %s %-3s" % tuple(t[6:ei])
        if ei < len(t):
            # 角度は -180 でなく 180 と書く(同じ向きだが素直な方に揃える)
            a = -float(t[ei + 1])
            s += "  e %8s %3s" % (num(180.0 if a == -180 else a), t[ei + 2])
        out.append(s.rstrip())
    out.append(block[-1])
    return out


def mirror_name(name):
    """建具名に「左右反転」を入れる。すでに括弧があればその中に足す。"""
    return name[:-1] + "・左右反転）" if name.endswith("）") else name + "（左右反転）"


def main():
    lines = SRC.read_bytes().decode("cp932").split("\r\n")
    ent = entries(lines)
    if len(ent) != 16:
        sys.exit("扉厚折戸入りのはずが %d 件だった" % len(ent))

    names = [HEAD.match(lines[a]).group(2).strip() for a, _ in ent]
    for k, want in DROP.items():
        if names[k] != want:
            sys.exit("%d番が %s ではない: %s" % (k + 1, want, names[k]))
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

    # 見込線付きの折戸を作る。建具名を変え、終端の直前に見込線を差し込む。
    fa, fb = ent[FOLD]
    if names[FOLD] != "折戸（開き75度）":
        sys.exit("%d番が折戸（開き75度）ではない: %s" % (FOLD + 1, names[FOLD]))
    fold = lines[fa:fb + 1]
    fold[0] = fold[0].replace("折戸（開き75度）", FOLD_NAME)
    added += ["#"] + fold[:-1] + FOLD_ADD + [fold[-1]]

    # 外す建具を後ろから削る(前から削ると以降の行番号がずれる)。
    # 直前の '#' も一緒に落とす。
    for k in sorted(DROP, reverse=True):
        cut = ent[k][0]
        while lines[cut - 1].strip() == "#":
            cut -= 1
        del lines[cut:ent[k][1] + 1]

    # 末尾(最後の 999 の直後)に追加分を差し込む
    append_tail(lines, added)

    # ここまでで16件。この16件から左右反転した建具を作って末尾に足す。
    block = {}
    for a, b in entries(lines):
        m = HEAD.match(lines[a])
        block[m.group(2).strip()] = (int(m.group(1)), lines[a:b + 1])
    mir = []
    for name in MIRROR:
        if name not in block:
            sys.exit("反転させる建具が見つからない: %s" % name)
        div, src = block[name]
        mir += ["#"] + mirror(src, div)
    append_tail(lines, mir)

    # 見出しの登録件数を実際の件数に合わせる(数が違うと Jw_cad の表示が崩れる)
    count = len(entries(lines))
    if count != 16 - len(DROP) + len(WIDTHS) + 1 + len(MIRROR):
        sys.exit("組み立て後の件数が想定と違う: %d 件" % count)
    lines[2] = str(count)

    DST.write_bytes("\r\n".join(lines).encode("cp932"))
    print("%s を書き出した (%d バイト)" % (DST.name, DST.stat().st_size))


if __name__ == "__main__":
    main()
