#!/usr/bin/env python3
"""建具データ(JW_OPT*.DAT)の中身を検査して一覧表示する。

    python3 tools/check.py JW_OPT1B.DAT
    python3 tools/check.py JW_OPT1B.DAT --lines     ← データ行も表示

文字コード(CP932)・改行(CRLF)・見出しの登録件数と実際の件数の一致を確認し、
各建具の分割数・建具名・行数・使われている属性をまとめて出す。
編集後は必ずこれを通してから Jw_cad に入れること。
"""

import re
import sys

TERM = re.compile(r"^\s*(999|995|991)\b")
HEAD = re.compile(r"^\s*(\d+)\s{2,}(\S.*)$")


def attr_of(line):
    """データ行から「線色 線種 レイヤ」を取り出す。属性欄が無ければ None。

    データ行の並びは
        始点番号 終点番号 X1 Y1 X2 Y2 [線色 線種 レイヤ] [e 角度 コード]
    で、先頭6項目が座標。7項目目以降を見て 'e' が来たら属性欄は無い。
    """
    t = line.split()
    if len(t) < 7 or t[6] in ("e", "E"):
        return None
    return " ".join(t[6:9])


def load(path):
    raw = open(path, "rb").read()
    try:
        text = raw.decode("cp932")
    except UnicodeDecodeError as e:
        sys.exit("CP932 として読めない: %s" % e)
    if b"\r\n" not in raw:
        sys.exit("改行が CRLF でない")
    return raw, text.split("\r\n")


def entries(lines, limit=None):
    """(開始行, 終端行, 分割数, 建具名) を先頭から順に返す。

    limit を渡すとその件数で読み取りを止める。JW_OPT1.DAT のように
    最後の建具より後ろに書式説明が付いているファイルに対応するため。
    """
    out, start = [], None
    for i, line in enumerate(lines[5:], start=5):
        s = line.strip()
        if s in ("", "#", "\x1a"):
            continue
        if start is None:
            m = HEAD.match(line)
            if m:
                start, div, name = i, m.group(1), m.group(2).strip()
            continue
        if TERM.match(line):
            out.append((start, i, div, name))
            start = None
            if limit is not None and len(out) >= limit:
                break
    if start is not None:
        sys.exit("%d 行目の建具に終端(999/995/991)がない" % (start + 1))
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "JW_OPT1B.DAT"
    show_lines = "--lines" in sys.argv
    raw, lines = load(path)
    declared = lines[2].strip()
    ent = entries(lines, int(declared) if declared.isdigit() else None)

    print("%s  %d バイト / CRLF %d 行" % (path, len(raw), raw.count(b"\r\n")))
    print("見出し: %s" % lines[0])
    print("登録件数: %s / 実際の件数: %d %s"
          % (declared, len(ent), "OK" if declared == str(len(ent)) else "★不一致★"))
    print()

    for n, (a, b, div, name) in enumerate(ent, 1):
        # 先頭が数字でない行(基準寸法の S / s 行)はデータ行ではない
        data = [ln for ln in lines[a + 1:b] if ln.split() and ln.split()[0][0].isdigit()]
        seen = [attr_of(ln) for ln in data]
        attrs = sorted({s for s in seen if s})
        if any(s is None for s in seen):
            attrs.append("属性欄なし")
        # 終端の後ろに数値が付いていると見込・枠幅がその寸法に固定される。
        # 差し替えのときに前の建具の終端を残すと気づきにくいので必ず出す。
        term = lines[b].split()
        fix = "  ★見込%s・枠幅%s固定" % (term[1], term[2]) if len(term) >= 3 else ""
        print("%2d  分割%-2s %-28s %2d行  終端%-4s  属性: %s%s"
              % (n, div, name, len(data), term[0], " / ".join(attrs) or "なし", fix))
        if show_lines:
            for ln in lines[a + 1:b + 1]:
                print("      " + ln)

    if declared != str(len(ent)):
        sys.exit(1)


if __name__ == "__main__":
    main()
