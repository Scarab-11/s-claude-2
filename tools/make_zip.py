#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dist/ から配布用の ZIP を作る。

Jw_cad を使うだけの人が git を触らずに済むよう、外部変形ごとに
「そのまま外変フォルダへコピーできるフォルダ」を ZIP にしておく。

ファイル名は UTF-8 フラグ付きで格納する。Windows の
エクスプローラはこのフラグを見るので、日本語のファイル名でも
文字化けせずに展開できる。

    python3 tools/build.py     # src -> dist
    python3 tools/make_zip.py  # dist -> *.zip
"""

import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, 'dist')

# ZIP に記録する日時。同じ中身なら同じバイト列になるよう固定する。
FIXED_DATE = (2026, 1, 1, 0, 0, 0)

# 出力する ZIP ごとに、展開後のフォルダ名と収めるファイルを並べる。
PACKAGES = {
    'jww_ceiling_plan.zip': ('天井伏図生成', [
        '天井伏図生成.bat',
        'レイヤ調査.bat',
        'jww_ceiling_plan.py',
        '天伏図ルール.txt',
        '使い方_天井伏図生成.txt',
        'テスト/天伏図テスト実行.bat',
        'テスト/sample_平面図.txt',
    ]),
    'jww_moji_align.zip': ('文字位置揃え', [
        'jww_text_align.vbs',
        '使い方.txt',
        '文字位置揃え.bat',
        '文字位置揃え_基準文字指示.bat',
        '文字位置揃え_左揃え.bat',
        '文字位置揃え_横中央揃え.bat',
        '文字位置揃え_右揃え.bat',
        '文字位置揃え_下揃え.bat',
        '文字位置揃え_縦中央揃え.bat',
        '文字位置揃え_上揃え.bat',
        '文字位置揃え_横に等間隔.bat',
        '文字位置揃え_縦に等間隔.bat',
        'テスト/テスト実行.bat',
        'テスト/テスト実行_基準文字.bat',
        'テスト/sample_jwc_temp.txt',
        'テスト/sample_基準文字.txt',
    ]),
}


def main():
    if not os.path.isdir(DIST):
        print('dist/ がありません。先に tools/build.py を実行してください。',
              file=sys.stderr)
        return 1

    for zip_name, (folder, members) in PACKAGES.items():
        missing = [m for m in members
                   if not os.path.exists(os.path.join(DIST, m))]
        if missing:
            print(f'{zip_name}: dist/ に無いファイルがあります: {missing}',
                  file=sys.stderr)
            return 1

        out = os.path.join(ROOT, zip_name)
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for m in members:
                # 格納日時を固定する。ファイルの更新時刻をそのまま
                # 入れると、中身が同じでも実行のたびに ZIP のバイト列が
                # 変わり、git の差分がタイムスタンプだけで出てしまう。
                info = zipfile.ZipInfo(f'{folder}/{m}', FIXED_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(os.path.join(DIST, m), 'rb') as f:
                    z.writestr(info, f.read())
        print(f'zip    {zip_name}  ({len(members)} ファイル)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
