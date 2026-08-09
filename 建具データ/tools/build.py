#!/usr/bin/env python3
"""JW_OPT1B_扉厚折戸入り.DAT から配布版 JW_OPT1B.DAT を組み立てる。

    python3 tools/build.py

やることは4つ。

1. 配布しない折戸を取り除く
   ・折戸(開き60度)……建具用包絡をかけると内側の羽根が延長されて壊れる
   ・扉厚まで描く詳細版の折戸2件……折戸の軸を壁中心に合わせる Y+35 と両立しない
   いずれも理由は README.md 参照。復元したくなったら
   JW_OPT1B_扉厚折戸入り.DAT の方を使う。

2. 親子ドアー(元の12番)を複製して子扉400・450を足し、
   折戸(開き75度)を複製して見込線を足したものも足す
   子扉寸法は座標に直接書かれた固定値なので、寸法違いは建具を分けるしかない。
   12番の行をそのまま写して "300" を置き換えるだけで、他は一切変えない。

3. 同名でまぎらわしい建具の名前を付け替える(ORDER の3列目)

4. 種類ごとにまとまるよう並べ替える(ORDER)
   引き系(引違い→片引戸) → 開き系(ドアー→両開き戸→親子) → 折戸 の順。
   動かすのは建具のかたまりごとで、行の中身には触れない。
   2・3 で番号が変わるので、この docstring と ORDER 以外に出てくる番号は
   すべて「並べ替える前」の番号を指している。

残す建具のデータには手を触れない。編集後は check.py を通すこと。

左右反転・上下反転は Jw_cad 本体のコントロールバーに付いているので、
反転させた建具を登録する必要はない。
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

# 並べ替えと改名。(組み立て直後の番号, その時点の建具名, 新しい建具名 or None)
# 番号は 1〜16 を1度ずつ使う。建具名は取り違え防止の確認用。
# 2番と5番は元データではどちらも「引違い（１レイヤ躯体線付）」で一覧から
# 見分けが付かないため、躯体と見込線を持つ5番の方を改名する。
ORDER = [
    ( 2, "引違い（１レイヤ躯体線付）", None),
    ( 5, "引違い（１レイヤ躯体線付）", "引違い（躯体・見込線付）"),
    ( 3, "引違い（３枚建）",           None),
    ( 4, "引違い（４枚建）",           None),
    ( 6, "片引戸",                    None),
    (11, "ドアー",                    None),
    ( 9, "ドアー（見込線付）",         None),
    ( 1, "ドアー（１レイヤ躯体線付）", None),
    ( 7, "両開き戸",                  None),
    ( 8, "両開き戸（見込線付）",       None),
    (12, "親子ドアー（子扉300）",      None),
    (14, "親子ドアー（子扉400）",      None),
    (15, "親子ドアー（子扉450）",      None),
    (10, "親子開き戸（見込線付）",     None),
    (13, "折戸（開き75度）",           None),
    (16, "折戸（見込線付）",           None),
]

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

    # 種類ごとにまとまるよう並べ替える。ついでに改名も済ませる。
    count = 16 - len(DROP) + len(WIDTHS) + 1
    ent = entries(lines)
    if len(ent) != count:
        sys.exit("並べ替え前の件数が想定と違う: %d 件" % len(ent))
    if sorted(n for n, _, _ in ORDER) != list(range(1, count + 1)):
        sys.exit("ORDER が 1〜%d を1度ずつ使っていない" % count)

    head, out = lines[:5], []
    for n, want, new in ORDER:
        a, b = ent[n - 1]
        got = HEAD.match(lines[a]).group(2).strip()
        if got != want:
            sys.exit("%d番が %s ではない: %s" % (n, want, got))
        block = lines[a:b + 1]
        if new:
            block[0] = block[0].replace(want, new)
        out += (["#"] if out else []) + block
    lines = head + out + ["", "\x1a"]

    # 見出しの登録件数を実際の件数に合わせる(数が違うと Jw_cad の表示が崩れる)
    if len(entries(lines)) != count:
        sys.exit("並べ替え後の件数が合わない")
    lines[2] = str(count)

    DST.write_bytes("\r\n".join(lines).encode("cp932"))
    print("%s を書き出した (%d バイト)" % (DST.name, DST.stat().st_size))


if __name__ == "__main__":
    main()
