#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""src/ (UTF-8 / LF) から dist/ (CP932 / CRLF) を生成する。

Jw_cad は .bat の REM 行と jwc_temp.txt を Shift_JIS で読み書きするため、
配布する実体は CP932 + CRLF でなければならない。
リポジトリ上で読みやすいように原本は UTF-8 で持ち、ここで変換する。

ただし .py は変換しない。Python 3 のソースは既定で UTF-8 として
読まれるため、CP932 に変換すると中の日本語リテラルが壊れる。
CP932 への変換はスクリプトが jwc_temp.txt を書き出すときに
行っている。
"""

import io
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
DIST = os.path.join(ROOT, "dist")

TEXT_EXT = (".bat", ".vbs", ".txt")


def convert(src_path, dst_path):
    with io.open(src_path, encoding="utf-8", newline="") as f:
        text = f.read()
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    data = text.encode("cp932")
    with open(dst_path, "wb") as f:
        f.write(data)


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
            else:
                shutil.copy2(src_path, dst_path)
                print("copy   %s" % os.path.relpath(dst_path, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
