# -*- coding: utf-8 -*-
"""src/ から dist/ を作り直す。

.py はそのまま複製する（Python は UTF-8 で読むため）。.bat / .ini / .txt
は日本語 Windows のコマンドプロンプトに合わせて CP932・CRLF に変換する。
それ以外（サンプル PDF・同梱の言語データ・PP-OCRv5 の模型など）はバイト
そのままコピーする。
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
DST = os.path.join(ROOT, "dist")

# コマンドプロンプト・メモ帳向けに CP932/CRLF へ変換するのは、この 3 つ
# だけ。拡張子で判断すると、PP-OCRv5 の辞書ファイル（.txt だが CP932 に
# 無い字を含む）まで巻き込んで壊れる。
TEXT_TO_CP932 = ("PDF文字認識.bat", "設定.ini", "使い方.txt")


def convert(src_path, dst_path):
    with open(src_path, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    with open(dst_path, "w", encoding="cp932", newline="") as f:
        f.write(text)


def sync(src_dir, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    keep = set()
    # src/tessdata/・src/tessdata_fast/ には、この作業フォルダで
    # tesseract を動かしたときに取得・複製された eng / jpn_vert / osd /
    # configs が増えていることがある（fill_tessdata() / ensure_fast_
    # tessdata() の仕様）。同梱するのは jpn.traineddata だけ（README・
    # .gitignore の方針どおり）。それ以外は初回起動時に利用者の
    # tesseract 本体または配布元から用意されるものなので、ここで
    # 一緒くたに運ぶと余計なファイルが ZIP に混ざる。
    only_stock = os.path.basename(src_dir) in ("tessdata", "tessdata_fast")
    for name in os.listdir(src_dir):
        if name in ("__pycache__",) or name.endswith(".pyc"):
            continue
        if only_stock and name != "jpn.traineddata":
            continue
        src_path = os.path.join(src_dir, name)
        dst_path = os.path.join(dst_dir, name)
        keep.add(name)
        if os.path.isdir(src_path):
            sync(src_path, dst_path)
            continue
        if name in TEXT_TO_CP932:
            convert(src_path, dst_path)
        else:
            shutil.copy2(src_path, dst_path)
    # src に無くなったものは dist からも消す（tessdata の取得済みファイル
    # など、実行時に増えるものだけ .gitignore 側で追跡から外している）
    for name in os.listdir(dst_dir):
        if name not in keep and name != "__pycache__":
            path = os.path.join(dst_dir, name)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)


def make_zip():
    """配布 ZIP（リポジトリ直下の pdf_ocr.zip）を作り直す。

    展開したときに PDF文字認識 フォルダの中身になるよう、dist/ の中身を
    その名前のフォルダに入れてから固める。
    """
    import zipfile

    repo_root = os.path.dirname(ROOT)
    zip_path = os.path.join(repo_root, "pdf_ocr.zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirnames, filenames in os.walk(DST):
            rel_dir = os.path.relpath(dirpath, DST)
            for name in filenames:
                src_path = os.path.join(dirpath, name)
                arc_path = os.path.join(
                    "PDF文字認識",
                    "" if rel_dir == "." else rel_dir, name)
                zf.write(src_path, arc_path)
    sys.stdout.write("pdf_ocr.zip を作り直しました（%.1f MB）\n"
                     % (os.path.getsize(zip_path) / 1048576.0))


def main():
    sync(SRC, DST)
    sys.stdout.write("dist/ を作り直しました（元: %s）\n" % SRC)
    if "--zip" in sys.argv[1:]:
        make_zip()


if __name__ == "__main__":
    main()
