#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""src/ (UTF-8 / LF) から dist/ (CP932 / CRLF) と配布 ZIP を生成する。

Jw_cad は .bat の REM 行と jwc_temp.txt を Shift_JIS で読み書きするため、
配布する実体は CP932 + CRLF でなければならない。
リポジトリ上で読みやすいように原本は UTF-8 で持ち、ここで変換する。

AutoHotkey スクリプト (.ahk) だけは例外で、UTF-8 (BOM 付き) + CRLF に
する。AutoHotkey は BOM が無いとシステムの ANSI として読んでしまう。
"""

import io
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
DIST = os.path.join(ROOT, "dist")

TEXT_EXT = (".bat", ".vbs", ".txt")
UTF8_EXT = (".ahk",)

# 配布 ZIP。top は ZIP 内のフォルダ名、sub は dist からの相対パス
# （"." のときは dist 直下のファイルと exclude 以外のフォルダ）。
ZIPS = (
    {"zip": "jww_moji_align.zip", "top": "文字位置揃え", "sub": ".",
     "exclude": ("描画順", "jwf設定比較")},
    {"zip": "jww_draw_order.zip", "top": "描画順", "sub": "描画順",
     "exclude": ()},
    {"zip": "jwf_diff.zip", "top": "jwf設定比較", "sub": "jwf設定比較",
     "exclude": ()},
)


def read_source(src_path):
    with io.open(src_path, encoding="utf-8", newline="") as f:
        text = f.read()
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")


def convert(src_path, dst_path):
    data = read_source(src_path).encode("cp932")
    with open(dst_path, "wb") as f:
        f.write(data)


def convert_utf8(src_path, dst_path):
    data = read_source(src_path).encode("utf-8-sig")
    with open(dst_path, "wb") as f:
        f.write(data)


def make_zip(spec):
    top = spec["top"]
    base = DIST if spec["sub"] == "." else os.path.join(DIST, spec["sub"])
    zip_path = os.path.join(ROOT, spec["zip"])

    names = []
    for dirpath, dirnames, filenames in os.walk(base):
        rel_dir = os.path.relpath(dirpath, base)
        if rel_dir == ".":
            dirnames[:] = [d for d in dirnames if d not in spec["exclude"]]
            rel_dir = ""
        for name in sorted(filenames):
            names.append(os.path.join(rel_dir, name) if rel_dir else name)
        dirnames.sort()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in sorted(names):
            zf.write(os.path.join(base, rel),
                     os.path.join(top, rel).replace(os.sep, "/"))

    print("zip    %s (%d files)" % (spec["zip"], len(names)))


def main():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)

    for dirpath, _dirnames, filenames in os.walk(SRC):
        rel = os.path.relpath(dirpath, SRC)
        out_dir = DIST if rel == "." else os.path.join(DIST, rel)
        os.makedirs(out_dir, exist_ok=True)

        for name in filenames:
            src_path = os.path.join(dirpath, name)
            dst_path = os.path.join(out_dir, name)
            if name.lower().endswith(TEXT_EXT):
                try:
                    convert(src_path, dst_path)
                except UnicodeEncodeError as exc:
                    print("CP932 に変換できない文字があります: %s (%s)"
                          % (src_path, exc), file=sys.stderr)
                    return 1
                print("cp932  %s" % os.path.relpath(dst_path, ROOT))
            elif name.lower().endswith(UTF8_EXT):
                convert_utf8(src_path, dst_path)
                print("utf8   %s" % os.path.relpath(dst_path, ROOT))
            else:
                shutil.copy2(src_path, dst_path)
                print("copy   %s" % os.path.relpath(dst_path, ROOT))

    for spec in ZIPS:
        make_zip(spec)

    return 0


if __name__ == "__main__":
    sys.exit(main())
