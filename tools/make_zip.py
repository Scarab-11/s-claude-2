#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dist/ から、外部変形ごとの配布用 ZIP をリポジトリ直下に作る。

ZIP の中は「外部変形の名前」フォルダひとつにまとまっているので、
展開してそのまま Jw_cad の外部変形フォルダへ置ける。
tools/build.py を実行して dist/ を作ってから使うこと。
"""

import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")

# ZIP名 : (ZIP内のフォルダ名, dist からの相対パスの一覧)
PACKAGES = {
    "jww_moji_align.zip": ("文字位置揃え", [
        "jww_text_align.vbs",
        "使い方.txt",
        "文字位置揃え.bat",
        "文字位置揃え_基準文字指示.bat",
        "文字位置揃え_左揃え.bat",
        "文字位置揃え_横中央揃え.bat",
        "文字位置揃え_右揃え.bat",
        "文字位置揃え_下揃え.bat",
        "文字位置揃え_縦中央揃え.bat",
        "文字位置揃え_上揃え.bat",
        "文字位置揃え_横に等間隔.bat",
        "文字位置揃え_縦に等間隔.bat",
        "テスト/sample_jwc_temp.txt",
        "テスト/sample_基準文字.txt",
        "テスト/テスト実行.bat",
        "テスト/テスト実行_基準文字.bat",
    ]),
    "jww_cut_line.zip": ("線切断", [
        "jww_cut_line.vbs",
        "使い方_線切断.txt",
        "線切断.bat",
        "線切断_円弧で切断.bat",
        "線切断_全要素で切断.bat",
        "テスト/sample_線切断.txt",
        "テスト/テスト実行_線切断.bat",
    ]),
}


def main():
    if not os.path.isdir(DIST):
        print("dist/ がありません。先に tools/build.py を実行してください。",
              file=sys.stderr)
        return 1

    for zip_name in sorted(PACKAGES):
        top, members = PACKAGES[zip_name]
        zip_path = os.path.join(ROOT, zip_name)

        missing = [m for m in members
                   if not os.path.isfile(os.path.join(DIST, m))]
        if missing:
            print("dist/ に見つからないファイルがあります: %s"
                  % ", ".join(missing), file=sys.stderr)
            return 1

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for m in members:
                z.write(os.path.join(DIST, m), "%s/%s" % (top, m))
        print("zip    %s (%d files)" % (zip_name, len(members)))

    return 0


if __name__ == "__main__":
    sys.exit(main())
