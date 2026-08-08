# -*- coding: utf-8 -*-
"""JW_OPT1_元データ.DAT から JW_OPT1.DAT を組み立てる。

JW_OPT1B.DAT と同じ仕様を当てる:
  端部線          → 0 0 -11 （選択色・選択レイヤ・包絡の建具性質を解除）
  枠・躯体・見込線 → 線色2
  扉・障子・戸     → 線色6
  扉の円弧        → 線色2(コード10 = 円弧のみ)、扉の線 → 線色6(コード16 = 線のみ)
  中心線          → Y −50〜120・線色6・実線・建具属性あり
                     (-11 にすると閉じた領域を横切る部分が中間線消去で切られる)
元データの [13][14](扉厚付き折戸)は削除する。
"""
import re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "JW_OPT1_元データ.DAT"
DST = HERE / "JW_OPT1.DAT"

NAME = re.compile(r'^(\d+)\s{2,}(\S.*?)\s*$'); TERM = re.compile(r'^\s*99[0-9]\b')
DROP = (13, 14)                      # 扉厚付きの折戸
END, MOVE, FRAME = "0 0 -11", "6 0 -1", "2 0 -1"

# 建具ごと: ends=端部線, move=動く部分, arcs=円弧付き, keep=そのまま,
#           drop=削る行, extra=足す行, center=('extend',行) or ('add',) or None,
#           to3=分割2→3
# [5][6] は両端の枠(線色2)を消し、代わりに開口いっぱいの見込線を足す。
#   端部線(選択色)と合わせて開口が矩形になる。
T = {
 1: dict(move={0,1,2}, keep={3,4,5,6}, center=('extend',1)),
 2: dict(move={0,1,2,3,4}),
 3: dict(ends={2,6}, center=('add',), to3=True),
 4: dict(ends={2,8}, move={3,4,5}, center=('extend',4)),
 5: dict(ends={2,10}, move={3,4,5,6,7}, drop={0,1,8,9},
         extra=[(['1','4','0','0','0','0'], FRAME), (['1','4','0','70','0','70'], FRAME)]),
 6: dict(ends={2,12}, move={3,4,5,6,7,8,9}, center=('extend',6), drop={0,1,10,11},
         extra=[(['1','5','0','0','0','0'], FRAME), (['1','5','0','70','0','70'], FRAME)]),
 7: dict(arcs={14}, center=('add',), to3=True),
 8: dict(ends={3,6}, arcs={10}, center=('add',), to3=True),
 9: dict(move={5}, center=('add',), to3=True),
10: dict(move={5}, center=('add',), to3=True),
11: dict(move={3,4,5,6,7,8,9,10,11,12,13,17,18,19}, center=('extend',12)),
12: dict(move={3,4,5,6,7,8,9,10,11,12,13,17,18,19}, center=('extend',12)),
15: dict(move={0,1,2,3,4,5,6}, center=('extend',2)),
16: dict(ends={3,9}, move={4,5,6,7,8}, center=('extend',5)),
17: dict(ends={1,9}, move={3,4,5,6,11,12,13,14}, center=('add',), to3=True),
18: dict(ends={1,15}, move={3,4,5,6,8,9,10,11,12,17,18,19,20}, center=('extend',8)),
19: dict(ends={0,3}, arcs={4}, center=('add',), to3=True),
20: dict(ends={0,3}, arcs={4}, center=('add',), to3=True),
21: dict(ends={0,3}, arcs={4}, center=('add',), to3=True),
22: dict(ends={0,7}, move={3}, arcs={4,8}, center=('extend',3)),
23: dict(ends={0,6}, move={3}, center=('extend',3)),
24: dict(keep=set(range(9))),         # 既に線色指定あり・中心線の対象外
}


def fmt(coords, attr, tail=""):
    """座標6個 + 属性 + (あれば円弧指定) を桁を揃えて1行にする。"""
    c = "%-3s %-3s %6s %6s %6s %6s" % tuple(coords)
    return ("%s  %-8s%s" % (c, attr, tail)).rstrip()


def main():
    L = SRC.read_bytes().decode("cp932").split("\r\n")
    cut = next(i for i, x in enumerate(L) if x.startswith("====="))
    head, doc = L[:cut], L[cut:]

    ents, i = [], 0
    while i < len(head):
        m = NAME.match(head[i])
        if not m: i += 1; continue
        n, name = int(m.group(1)), m.group(2)
        body, j, term = [], i + 1, "999"
        while j < len(head):
            s = head[j].strip()
            if s:
                if TERM.match(s): term = s; j += 1; break
                body.append(s)
            j += 1
        ents.append([n, name, body, term]); i = j
    if len(ents) != 24: sys.exit("24件のはずが %d 件" % len(ents))

    out, num = [], 0
    for k, (n, name, body, term) in enumerate(ents, 1):
        if k in DROP: continue
        t = T[k]
        ends, move = t.get("ends", set()), t.get("move", set())
        arcs, keep = t.get("arcs", set()), t.get("keep", set())
        drop, extra = t.get("drop", set()), t.get("extra", [])
        center, catt = t.get("center"), "-1"   # 中心線は建具属性あり
        if t.get("to3"):
            n = 3
            body = [re.sub(r'^(\S+)\s+(\S+)', lambda m: "%s %s" % (
                    m.group(1).replace("2", "3"), m.group(2).replace("2", "3")), s)
                    for s in body]
        cblk = (n + 1) // 2                       # 中央のブロック番号

        lines = []
        for idx, s in enumerate(body):
            if idx in drop: continue
            if idx in keep: lines.append(s); continue
            tk = s.split()
            ei = next((q for q, v in enumerate(tk) if v.lower() == "e"), len(tk))
            co = tk[:6]
            if center and center[0] == "extend" and idx == center[1]:
                lines.append(fmt([co[0], co[1], co[2], "-50", co[4], "120"], "6 1 " + catt))
                continue
            if idx in arcs:                        # 円弧と扉の線を分ける
                ang = tk[ei + 1]
                lines.append(fmt(co, "2 0 -11", "  e %8s  10" % ang))
                lines.append(fmt(co, "6 0 -11", "  e %8s  16" % ang))
                continue
            attr = END if idx in ends else MOVE if idx in move else FRAME
            lines.append(fmt(co, attr))
        for co, attr in extra:
            lines.append(fmt(co, attr))
        if center and center[0] == "add":
            lines.append(fmt([cblk, cblk, "0", "-50", "0", "120"], "6 1 " + catt))

        num += 1
        out += ["#", "%-16s [%d]" % (n, num)] + lines + [term]

    res = ["#建具一般平面図", "#", str(len(ents) - len(DROP)), "999"] + out + doc
    DST.write_bytes("\r\n".join(res).encode("cp932"))
    print("%s (%d バイト, %d件)" % (DST.name, DST.stat().st_size, len(ents) - len(DROP)))


main()
