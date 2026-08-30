#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""src/ (UTF-8 / LF) から dist/ (CP932 / CRLF) を生成する。

Jw_cad は .bat の REM 行と jwc_temp.txt を Shift_JIS で読み書きするため、
配布する実体は CP932 + CRLF でなければならない。コマンドプロンプトも
日本語 Windows では CP932 なので、bat と説明書きは同じ扱いにする。
リポジトリ上で読みやすいように原本は UTF-8 で持ち、ここで変換する。

.py は Python 3 が UTF-8 として読むので、変換せずにそのまま複製する。
"""

import io
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (原本, 配布物) の組。ツールが増えたらここに足す。
TREES = [
    (os.path.join(ROOT, "src"), os.path.join(ROOT, "dist")),
    (os.path.join(ROOT, "pdf_ocr", "src"), os.path.join(ROOT, "pdf_ocr", "dist")),
]

TEXT_EXT = (".bat", ".vbs", ".txt", ".ini")


def convert(src_path, dst_path):
    with io.open(src_path, encoding="utf-8", newline="") as f:
        text = f.read()
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    data = text.encode("cp932")
    with open(dst_path, "wb") as f:
        f.write(data)


def build(src, dist):
    if os.path.isdir(dist):
        shutil.rmtree(dist)

    for dirpath, dirnames, filenames in os.walk(src):
        # Python が勝手に作る中間ファイルは配布物に入れない。
        # tessdata（精度重視版の言語データ）は入れる。社内ネットワークから
        # 取りに行けない環境でもそのまま使えるようにするため、配布物に
        # 同梱する方針にした。
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        filenames = [f for f in filenames if not f.endswith(".pyc")]
        rel = os.path.relpath(dirpath, src)
        out_dir = dist if rel == "." else os.path.join(dist, rel)
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


def main():
    for src, dist in TREES:
        if not os.path.isdir(src):
            continue
        status = build(src, dist)
        if status:
            return status
    return 0


if __name__ == "__main__":
    sys.exit(main())
