#!/usr/bin/env python3
"""JW_OPT1B_16件版.DAT から 15・16番を取り除いて JW_OPT1B.DAT を作る。

    python3 tools/make14.py

15・16番は扉厚まで描く詳細版の折戸で、折戸の軸を壁中心に合わせる Y+35 の
移動と両立しない(理由は README.md 参照)。1/100 では扉厚を描く必要がないため
配布版からは外している。復元したくなったら 16件版の方を使う。

このスクリプトは行を削って見出しの登録件数を書き換えるだけで、
残す建具のデータには一切手を触れない。
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "JW_OPT1B_16件版.DAT"
DST = HERE / "JW_OPT1B.DAT"
DROP = ("折戸（開き60度）", "折戸（開き75度）")   # 末尾2件のみが対象
TERM = re.compile(r"^\s*(999|995|991)\b")
HEAD = re.compile(r"^\s*(\d+)\s{2,}(\S.*)$")


def main():
    lines = SRC.read_bytes().decode("cp932").split("\r\n")

    # 建具の開始行を先頭から拾う
    starts, in_entry = [], False
    for i, line in enumerate(lines[5:], start=5):
        s = line.strip()
        if s in ("", "#", "\x1a"):
            continue
        if not in_entry and HEAD.match(line):
            starts.append(i)
            in_entry = True
        elif in_entry and TERM.match(line):
            in_entry = False

    if len(starts) != 16:
        sys.exit("16件版のはずが %d 件だった" % len(starts))
    for i in starts[14:]:
        if HEAD.match(lines[i]).group(2).strip() not in DROP:
            sys.exit("15・16番が想定と違う: %s" % lines[i])

    # 15番の直前の '#' から 16番の終端までを削る
    cut = starts[14]
    while lines[cut - 1].strip() == "#":
        cut -= 1
    end = starts[15]
    while not TERM.match(lines[end]):
        end += 1

    del lines[cut:end + 1]
    lines[2] = lines[2].replace("16", "14")

    DST.write_bytes("\r\n".join(lines).encode("cp932"))
    print("%s を書き出した (%d バイト)" % (DST.name, DST.stat().st_size))


if __name__ == "__main__":
    main()
