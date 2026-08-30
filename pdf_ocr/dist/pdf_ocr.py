#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画像PDF（スキャンPDF）を、文字の選択・検索ができるPDFに変換する。

見た目はそのままに、文字が写っている位置へ「見えない文字」を重ねる。
元のページはそのまま残すので、画質は落ちない。

    ① pypdfium2  … ページを画像に描画する
    ② tesseract  … OCR して単語ごとの位置(TSV)を受け取る
    ③ reportlab  … 見えない文字だけのページを組み立てる
    ④ pypdf      … 元のページに重ねて保存する

使い方:
    python pdf_ocr.py [オプション] 入力.pdf [入力2.pdf ...]

オプションは --help を参照。既定値は同じフォルダの 設定.ini で変えられる。
"""

from __future__ import annotations

import argparse
import configparser
import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

PROG = "PDF文字認識"
INI_NAME = "設定.ini"

# 版。実行するたびに画面の先頭に出す。手元のファイルを入れ替えたつもりで
# 古いものが動いていると、直したはずの不具合がそのまま残って見えるため、
# どの版が動いているかをその場で確かめられるようにしておく。
VERSION = "2026.08.30f"

# --mode で選ぶ読み取り方の初期値（設定.ini の同名セクションで上書きできる）
MODES = {
    "yoko": {"LANG": "jpn+eng", "PSM": "3", "NAME": "横書きの日本語"},
    "tate": {"LANG": "jpn_vert+jpn", "PSM": "5", "NAME": "縦書きの日本語"},
    "zumen": {"LANG": "jpn+eng", "PSM": "11", "NAME": "図面（文字が散在）"},
    "eng": {"LANG": "eng", "PSM": "3", "NAME": "英数字が中心"},
    # 横書きで読んだあと、縦書きでもう一度読んで、縦組みの所だけ差し替える
    "mixed": {"LANG": "jpn+eng", "PSM": "3", "NAME": "縦横混在",
              "LANG2": "jpn_vert+jpn", "PSM2": "5"},
    # 資料の種類を選ばせない既定の読み方。縦横混在で読み、取れた文字列が
    # 少ないページだけ、図面向けの読み方でもう一度読んで多いほうを採る。
    # 「どれを使うか」を利用者に判断させないための組み合わせ。
    "auto": {"LANG": "jpn+eng", "PSM": "3", "NAME": "自動",
             "LANG2": "jpn_vert+jpn", "PSM2": "5",
             "SPARSEPSM": "11", "SPARSEUNDER": "12"},
}

DEFAULTS = {
    "DPI": "300",
    "MAXDPI": "600",      # 貼られた画像が細かいときに上げてよい上限。0 で固定
    "MINCONF": "30",
    "SUFFIX": "_OCR",
    "SKIPTEXTPAGES": "yes",
    "TEXTPAGECHARS": "100",  # この字数以上あるページを「文字入り」と見なす
    # 白黒に落としてから読むと、色の付いた地の上に白抜きで組んだ見出しが
    # 読めなくなる。輝度で見るとオレンジの帯（154）と白い文字（254）の差は
    # 100 しかないが、色のまま渡せば青の板で 190 の差がある。実測でも、
    # 白黒に落とすと「本書の構成とねらい」が「SAS ORE BDU)」に化けた。
    # 手元の 2 ページで、狙った語の数は 7/16→10/16、13/16→15/16 と
    # どちらも色のまま渡したほうが多く取れたので、既定では色を捨てない。
    "GRAYSCALE": "no",
    "NUMBERS": "yes",     # 縦組みの中の横向きの数字（縦中横）を拾い直すか
    "LANG2": "",          # 2 回目に読むときの言語（空なら 1 回だけ読む）
    "PSM2": "5",          # 2 回目のページ分割モード
    "AUTOROTATE": "yes",  # 横倒しのスキャンを自動で立て直してから読む
    "MAXPIXELS": "40000000",  # 1 ページの画像の上限。大判図面で効く
    "JOBS": "0",          # 0 なら CPU 数から自動
    "TESSERACT": "",      # tesseract.exe の場所（空なら自動で探す）
    "FONT": "",           # 透明テキストに使うフォント（空なら自動で探す）
    "OUTDIR": "",         # 出力先フォルダ（空なら入力と同じ場所）
    # 1 回目（横書き想定）・2 回目（縦書き想定、LANG2 があるときだけ）を
    # それぞれ何で読むか。tesseract / ppocr_mobile / ppocr_server。
    "ENGINE1": "tesseract",
    "ENGINE2": "tesseract",
}

# 透明テキスト層に使うフォントの候補。日本語が入るので CJK フォントを埋め込む。
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msgothic.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
    r"C:\Windows\Fonts\YuGothM.ttc",
    r"C:\Windows\Fonts\YuGothR.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
]

# 足りない言語データの取得先（Tesseract 公式の配布リポジトリ / Apache-2.0）
# 社内ネットワークによってどちらか一方しか通らないことがあるので、順に試す。
#
# tessdata_best を使う。3 つある版を実際の紙面 2 つで比べたところ、
# 標準の tessdata と同じ精度（どちらも 16 語中 15 語）で、しかも小さく速い。
#
#     版              jpn の大きさ   狙った語        1 ページの時間
#     tessdata_fast     2.4 MB       9/16・15/16    34 秒・16 秒
#     tessdata         35.7 MB      15/16・15/16    85 秒・53 秒
#     tessdata_best    14.3 MB      15/16・15/16    52 秒・46 秒
#
# 小さいぶん、この ZIP に同梱もできる。社内ネットワークから取りに行けなくても
# そのまま使えるようにするため、配布物には tessdata フォルダを入れてある。
TESSDATA_URLS = [
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/%s.traineddata",
    "https://github.com/tesseract-ocr/tessdata_best/raw/main/%s.traineddata",
]

TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""),
                 r"Programs\Tesseract-OCR\tesseract.exe"),
]

TESSERACT_HELP = """
tesseract が見つかりませんでした。OCR 本体なので、先に入れてください。

  1. https://github.com/UB-Mannheim/tesseract/wiki にある
     tesseract-ocr-w64-setup-….exe をダウンロードして実行する
  2. 画面が進んで「Choose Components」が出たら、一覧の
     Additional language data (download) を [+] で開き
       Japanese            … 横書きの日本語
       Japanese (vertical) … 縦書きの日本語
     にチェックを入れる（ここを飛ばすと日本語が読めません）
  3. インストール先は既定の C:\\Program Files\\Tesseract-OCR のままでよい
  4. 入れ終わったら、この bat をもう一度実行する

別の場所に入れてある場合は 設定.ini の TESSERACT に
tesseract.exe のフルパスを書いてください。
"""

# このツールが使う言語データと、その役割
LANG_ROLES = {
    "jpn": "横書きの日本語",
    "jpn_vert": "縦書きの日本語",
    "eng": "英数字",
    "osd": "ページの向きの自動判定",
}

# 「これより小さければ速度優先版」と見なす大きさ（バイト）。
# 日本語は 速度優先 2.4 MB / 標準 35.7 MB、英数字は 4.1 MB / 23.5 MB と
# 桁が違うので、大きさだけで見分けられる。縦書き用の jpn_vert は
# 速度優先版と標準版がほぼ同じ大きさ（3.0 MB）なので入れない。
# 日本語だけを見る。英数字の eng も速度優先版だが、入れ替えても結果は
# 変わらなかった（利用者の紙面で 15/16 のまま、誤って足された `out記載`
# も日本語を替えただけで消えた）。同梱を 15 MB 減らせるので入れない。
THIN_TRAINEDDATA = {
    "jpn": 8000000,
}

# 丸数字と、それが表す数字。① から ⑳ まで。年月日の数字が丸数字に
# 化けたときに戻すのに使う（uncircle_numbers を参照）。
CIRCLED_DIGITS = dict(
    (chr(0x2460 + i), str(i + 1)) for i in range(20))


def tessdata_help(missing, target_dir):
    """手で言語データを置くための案内文。落とすファイルを名指しする。"""
    lines = [
        "",
        "言語データを用意できませんでした（社内ネットワークで外に出られない等）。",
        "手で置けば動きます。ネットにつながる PC で、下のリンクを開いて",
        "ファイルを保存してください（ブラウザで開くとダウンロードが始まります）。",
        "",
        "  足りないのは次の %d 個だけです。すでに入っている分は出していない"
        % len(missing),
        "  ので、ここに出ているファイルだけ置けば足ります。",
        "",
    ]
    for name in missing:
        role = LANG_ROLES.get(name, "")
        lines.append("  %s.traineddata%s" % (name, "  … " + role if role else ""))
        lines.append("    %s" % (TESSDATA_URLS[0] % name))
    lines += [
        "",
        "  保存したファイルを、このフォルダにそのまま置く:",
        "    %s" % target_dir,
        "",
        "  ※ ファイル名は変えないでください。",
        "     tessdata フォルダが無ければ作ってください。",
        "",
        "tesseract のインストーラを実行し直し、Choose Components の",
        "Additional language data から Japanese / Japanese (vertical) を",
        "追加する方法でも用意できます。",
        "",
    ]
    return "\n".join(lines)


class Word(object):
    """OCR が読み取った 1 かたまりの文字と、その画像上の位置（ピクセル）。

    angle は画像の中での文字の向き（時計回りの度数）。
    0 は左から右、90 は上から下（縦書き）、180 は上下逆、270 は下から上。
    """

    __slots__ = ("text", "left", "top", "width", "height", "angle", "line",
                 "conf")

    def __init__(self, text, left, top, width, height, angle=0, line=None,
                 conf=0.0):
        self.text = text
        self.left = left
        self.top = top
        self.width = width
        self.height = height
        self.angle = angle
        self.line = line          # 同じ行の単語をまとめるための目印
        self.conf = conf          # tesseract の確からしさ（0〜100）


# --------------------------------------------------------------------------
# 設定
# --------------------------------------------------------------------------

def read_ini(path):
    """設定.ini を読む。UTF-8 でも CP932（メモ帳で保存）でも読めるようにする。"""
    parser = configparser.ConfigParser()
    if not path or not os.path.isfile(path):
        return parser
    for encoding in ("utf-8-sig", "cp932"):
        try:
            with io.open(path, encoding=encoding) as f:
                parser.read_file(f)
            return parser
        except (UnicodeDecodeError, configparser.Error):
            parser = configparser.ConfigParser()
    sys.stderr.write("設定.ini を読めませんでした。既定値で実行します。\n")
    return parser


def build_settings(ini, mode):
    """既定値 → モード別の初期値 → 設定.ini の順に上書きして設定を決める。"""
    settings = dict(DEFAULTS)
    settings.update({k: v for k, v in MODES[mode].items() if k != "NAME"})
    for section in ("settings", mode):
        if ini.has_section(section):
            for key, value in ini.items(section):
                if value.strip():
                    settings[key.upper()] = value.strip()
    return settings


def as_bool(value):
    return str(value).strip().lower() in ("yes", "true", "1", "on", "はい")


def as_int(value, fallback):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback


# --------------------------------------------------------------------------
# 外部プログラム・フォントを探す
# --------------------------------------------------------------------------

def find_tesseract(preferred):
    if preferred:
        if os.path.isfile(preferred):
            return preferred
        found = shutil.which(preferred)
        if found:
            return found
    found = shutil.which("tesseract")
    if found:
        return found
    for path in TESSERACT_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    return None


def tesseract_langs(exe, tessdata=None):
    command = [exe]
    if tessdata:
        command += ["--tessdata-dir", tessdata]
    command.append("--list-langs")
    try:
        out = subprocess.run(command, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, check=False)
    except OSError:
        return set()
    text = out.stdout.decode("utf-8", "replace")
    return set(line.strip() for line in text.splitlines()[1:] if line.strip())


def usable_lang(available, wanted):
    """使える言語データだけを残す。jpn_vert が無い環境でも動かすため。"""
    if not available:
        return wanted, []
    parts = [p for p in wanted.split("+") if p]
    ok = [p for p in parts if p in available]
    missing = [p for p in parts if p not in available]
    if not ok:
        ok = ["jpn"] if "jpn" in available else sorted(available)[:1]
    return "+".join(ok), missing


def local_tessdata_dir():
    """このツールが言語データを置く場所。

    まずは本体と同じフォルダの tessdata。そこへ書けないこともある
    （Program Files の下に置いた、共有フォルダが読み取り専用、など）ので、
    書けなければ利用者ごとの作業フォルダに逃がす。ここで黙って
    あきらめると、**精度重視版がいつまでも用意されず、しかも利用者には
    何も見えない**。実際にそれで「何も変わらない」が起きた。
    """
    beside = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "tessdata")
    if os.path.isdir(beside) or writable_dir(beside):
        return beside
    base = (os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            or os.path.expanduser("~"))
    return os.path.join(base, "PDF文字認識", "tessdata")


def wanted_langs(settings, all_japanese=False):
    """このツールが使う言語データの一覧。"""
    if all_japanese:
        return ["jpn", "jpn_vert", "eng", "osd"]
    names = []
    for key in ("LANG", "LANG2"):
        for name in (settings.get(key) or "").split("+"):
            if name and name not in names:
                names.append(name)
    if as_bool(settings.get("AUTOROTATE", "no")) and "osd" not in names:
        names.append("osd")
    return names


def tessdata_dirs(exe):
    """言語データが置かれている場所の候補を、探す順に返す。"""
    dirs = []
    prefix = os.environ.get("TESSDATA_PREFIX", "")
    if prefix:
        dirs.append(prefix)
        dirs.append(os.path.join(prefix, "tessdata"))
    if exe:
        exe_dir = os.path.dirname(os.path.abspath(exe))
        dirs.append(os.path.join(exe_dir, "tessdata"))
        dirs.append(os.path.join(os.path.dirname(exe_dir), "share",
                                 "tessdata"))
    dirs.append("/usr/share/tesseract-ocr/5/tessdata")
    dirs.append("/usr/share/tessdata")
    seen = []
    for path in dirs:
        if path and os.path.isdir(path) and path not in seen:
            seen.append(path)
    return seen


def find_traineddata(exe, name, tessdata=None):
    directories = ([tessdata] if tessdata else []) + tessdata_dirs(exe)
    for directory in directories:
        path = os.path.join(directory, name + ".traineddata")
        if os.path.isfile(path):
            return path
    return None


def writable_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".pdf_ocr_write_test")
        with open(probe, "wb") as f:
            f.write(b"x")
        os.remove(probe)
        return True
    except OSError:
        return False


def download_traineddata(name, target_dir, quiet=False):
    """公式の配布先から言語データを 1 つ取ってくる。"""
    import urllib.request

    temp_path = os.path.join(target_dir, name + ".traineddata.part")
    if not quiet:
        sys.stdout.write("  %s の言語データを取得しています …\n" % name)
        sys.stdout.flush()

    last_error = None
    for template in TESSDATA_URLS:
        request = urllib.request.Request(
            template % name, headers={"User-Agent": "pdf_ocr"})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                with open(temp_path, "wb") as f:
                    while True:
                        chunk = response.read(262144)
                        if not chunk:
                            break
                        f.write(chunk)
            last_error = None
            break
        except Exception as exc:                        # noqa: BLE001
            last_error = exc
            try:
                os.remove(temp_path)
            except OSError:
                pass

    if last_error is not None:
        raise RuntimeError("%s を取得できませんでした（%s）" % (name, last_error))

    if os.path.getsize(temp_path) < 100000:             # 中身がおかしい
        os.remove(temp_path)
        raise RuntimeError("%s の中身が壊れています" % name)
    final_path = os.path.join(target_dir, name + ".traineddata")
    os.replace(temp_path, final_path)
    if not quiet:
        sys.stdout.write("  %s を入れました（%.1f MB）\n"
                         % (name, os.path.getsize(final_path) / 1048576.0))
    return final_path


def copy_tessdata_configs(exe, target):
    """tesseract の設定ファイル（configs / tessconfigs）を置き場に複製する。

    --tessdata-dir を指定すると、tesseract は言語データだけでなく
    **出力形式の設定ファイルもそのフォルダから探す**。このツールは
    出力形式に "tsv" を使うので、configs/tsv が無いとそれを黙って
    無視し、表ではなくただの文章を返す。すると読み取り位置が 1 つも
    取れず、**変換しても文字が 1 つも入らない PDF ができる**。
    エラーにならないので気づきにくい。

    言語データを本体の置き場からこちらへ移すときは、必ず一緒に運ぶ。
    """
    for name in ("configs", "tessconfigs"):
        destination = os.path.join(target, name)
        if os.path.isdir(destination):
            continue
        for directory in tessdata_dirs(exe):
            source = os.path.join(directory, name)
            if os.path.isdir(source):
                try:
                    shutil.copytree(source, destination)
                except OSError:                         # noqa: BLE001
                    pass
                break


def thin_traineddata(exe, name, tessdata=None):
    """その言語データが「速度優先版」なら、その場所を返す。無ければ None。

    tesseract の言語データには 3 つの版がある。日本語の大きさで並べると

        tessdata_fast     jpn  2.4 MB   速いかわりに精度が落ちる
        tessdata（標準）  jpn 35.7 MB   精度重視。このツールが取ってくる版
        tessdata_best     jpn 14.3 MB   最高精度。いちばん遅い

    Windows のインストーラ（UB-Mannheim）が入れるのは **速度優先版**。
    このツールは足りない言語データを標準版から取ってくるが、
    インストーラが既に置いていると「足りている」と見なして触らないため、
    速度優先版のまま使い続けることになる。

    実際の紙面（横組み二段の見開き）で、狙った 16 語のうち取り出せた数。

        速度優先版   9/16
        標準版      13/16
        最高精度版  13/16

    速度優先版でだけ落ちていたのは「経験と勘」「震災による倒」
    「ぜひとも」「構造検討や構造計算」「誰でも理解できる構造の本」
    「さらり」。誤って足された `mult記載` `out記載` も標準版では出ない。
    直し方をいくら変えても届かなかった誤りが、版を替えるだけで消える。

    見分けは大きさで足りる。速度優先版の jpn は 2.4 MB、標準版は
    35.7 MB と桁が違う。縦書き用の jpn_vert は速度優先版と標準版で
    ほぼ同じ大きさ（3.0 MB）なので、見分けず、置き換えもしない。
    """
    least = THIN_TRAINEDDATA.get(name)
    if not least:
        return None
    path = find_traineddata(exe, name, tessdata)
    if not path:
        return None
    try:
        return path if os.path.getsize(path) < least else None
    except OSError:                                     # noqa: BLE001
        return None


def langs_in_dir(directory):
    """そのフォルダに入っている言語データの名前を、ファイル名から数える。

    **tesseract には聞かない。** 以前は `--list-langs` で数えていたが、
    その問い合わせが失敗すると「1 つも入っていない」と読み違え、正しく
    そろっているフォルダを捨てて速度優先版のまま読み進めていた。
    実際に利用者の環境で、同梱した jpn を置いてあるのに
    「言語データをそろえられませんでした（eng, jpn, jpn_vert, osd）」と
    出た。tesseract が 1 行だけのエラーを返すと、その 1 行目を見出しとして
    読み飛ばす作りだったため、結果が空になっていた。

    フォルダに何があるかは、こちらで数えれば確実に分かる。
    """
    try:
        names = os.listdir(directory)
    except OSError:
        return set()
    tail = ".traineddata"
    return set(name[:-len(tail)] for name in names if name.endswith(tail))


def tessdata_works(exe, directory, lang="jpn", env=None):
    """その置き場を指定して、tesseract が実際に読めるかを確かめる。

    ファイルがあることと、tesseract がそこを開けることは別。Windows では
    道筋に日本語が入っていると開けないことがあり（配布物のフォルダ名が
    「PDF文字認識」なのでまさにこれ）、開けないまま進むと、変換しても
    文字が 1 つも入らない PDF ができる。エラーにならないので気づけない。

    そこで、小さな画像を 1 枚その場で作って読ませ、通るかどうかを見る。
    中身は問わない。落ちずに終わればその置き場は使える。
    """
    from PIL import Image, ImageDraw

    handle, path = tempfile.mkstemp(prefix="pdf_ocr_try_", suffix=".png")
    os.close(handle)
    try:
        image = Image.new("RGB", (160, 60), (255, 255, 255))
        ImageDraw.Draw(image).rectangle((20, 20, 40, 40), fill=(0, 0, 0))
        image.save(path)
        image.close()
        run_tesseract(exe, [path, "stdout", "-l", lang, "--psm", "6"],
                      timeout=120, env=env, tessdata=directory)
        return True
    except Exception:                                   # noqa: BLE001
        return False
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def tessdata_candidates():
    """精度のよい言語データを置ける場所を、試す順に返す。

    1 つ目はツールの隣。ここが使えれば、持ち運びも入れ替えも簡単。
    ただし **道筋に日本語が入っていると tesseract が置き場を開けない**
    ことがある（配布物のフォルダ名が「PDF文字認識」なのでまさにこれ）。
    そのときのために、英数字だけになりやすい場所も候補にしておく。

    tesseract 本体の置き場は候補に入れない。そこへ書くと、この道具の
    ためだけに利用者の tesseract を書き換えることになり、他のソフトの
    読み取り結果まで変えてしまう。
    """
    places = [local_tessdata_dir()]
    for name in ("LOCALAPPDATA", "ProgramData", "APPDATA", "HOME"):
        base = os.environ.get(name, "")
        # 空のときに os.path.join すると、今いるフォルダの下に相対の
        # 道筋ができてしまう。設定されているものだけを候補にする
        if base and os.path.isdir(base):
            places.append(os.path.join(base, "pdf_ocr", "tessdata"))
    places.append(os.path.join(tempfile.gettempdir(), "pdf_ocr_tessdata"))

    seen = []
    for path in places:
        full = os.path.abspath(path)
        if full not in seen:
            seen.append(full)
    return seen


def stock_traineddata(name):
    """配布物に同梱してある言語データの場所。無ければ None。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "tessdata", name + ".traineddata")
    return path if os.path.isfile(path) else None


def fill_tessdata(exe, target, needed):
    """その置き場に、必要な言語データと設定ファイルをそろえる。

    同梱してあるものを優先し、無いものは tesseract 本体の置き場から複製する。
    tesseract は置き場を 1 つしか見ないので、1 つでも欠けるとそこを指定
    した時点で読めなくなる。設定ファイル（configs）も同じ理由で要る。
    """
    if not writable_dir(target):
        return False
    for name in needed:
        destination = os.path.join(target, name + ".traineddata")
        if os.path.isfile(destination):
            continue
        source = stock_traineddata(name) or find_traineddata(exe, name)
        if source and os.path.abspath(source) != os.path.abspath(destination):
            try:
                shutil.copy2(source, destination)
            except OSError:                             # noqa: BLE001
                pass
    copy_tessdata_configs(exe, target)
    return True


def adopt_local_langs(exe, needed, quiet=False):
    """同梱の（または前に用意した）精度のよい言語データを使えるようにする。

    置ける場所を順に試し、**実際に tesseract がそこを読めたもの**を採る。
    ファイルがそろっていることだけで決めない。以前はそこで決めていて、
    しかも「そろっているか」を tesseract への問い合わせで数えていたため、
    問い合わせが失敗しただけで「1 つも無い」と読み違えていた
    （利用者の環境で実際にそうなった）。

    使える置き場を返す。用意できなければ None。
    """
    if not any(stock_traineddata(name) for name in THIN_TRAINEDDATA):
        stored = local_tessdata_dir()
        if not any(name in langs_in_dir(stored)
                   and not thin_traineddata(exe, name, stored)
                   for name in THIN_TRAINEDDATA):
            return None

    tried = []
    for target in tessdata_candidates():
        if not fill_tessdata(exe, target, needed):
            tried.append((target, "フォルダを作れない"))
            continue
        have = langs_in_dir(target)
        missing = [name for name in needed if name not in have]
        if missing:
            tried.append((target, "%s が足りない" % " ".join(missing)))
            continue
        if not tessdata_works(exe, target):
            tried.append((target, "tesseract がこの置き場を開けない"))
            continue
        return target

    if not quiet:
        for target, why in tried:
            sys.stdout.write("  言語データの置き場に使えません（%s）: %s\n"
                             % (why, target))
    return None


def upgrade_langs(exe, needed, quiet=False, tessdata=None):
    """速度優先版しか無いときに、精度重視版を取ってきて用意する。

    配布物には精度重視版の日本語データを同梱しているので、ふつうはここに
    来ない。同梱を消してしまったときや、古い配布物から入れ替えたときの
    ための道。**tesseract 本体の置き場は書き換えない。**

    用意できた置き場を返す（用意しなければ None）。
    """
    thin = [name for name in needed if thin_traineddata(exe, name, tessdata)]
    if not thin:
        return None

    for target in tessdata_candidates():
        if not writable_dir(target):
            continue
        todo = [name for name in thin
                if thin_traineddata(exe, name, target)
                or name not in langs_in_dir(target)]
        if todo and not quiet:
            sys.stdout.write(
                "  言語データ %s が速度優先版でした。精度重視版を取得します。\n"
                % " ".join(todo))
        for name in todo:
            destination = os.path.join(target, name + ".traineddata")
            try:
                path = download_traineddata(name, target, quiet)
                if os.path.getsize(path) < THIN_TRAINEDDATA[name]:
                    raise RuntimeError("%s の中身が足りません（途中で切れた）"
                                       % name)
            except (RuntimeError, OSError) as exc:
                sys.stderr.write("  %s\n" % exc)
                try:
                    os.remove(destination)
                except OSError:
                    pass
        if not fill_tessdata(exe, target, needed):
            continue
        have = langs_in_dir(target)
        if not all(name in have for name in needed):
            continue
        if all(thin_traineddata(exe, name, target) for name in thin):
            continue
        if not tessdata_works(exe, target):
            continue
        return target

    sys.stderr.write(
        "  精度重視版の言語データを用意できませんでした。\n"
        "  速度優先版のまま読みます（精度が落ちます）。\n")
    return None


def stock_fast_traineddata(name):
    """配布物に同梱してある速度優先版（tessdata_fast）の言語データの場所。

    今のところ jpn だけ用意している。eng・jpn_vert は精度重視版と速度優先版で
    差が無いと分かっている（thin_traineddata の説明を参照）ため、速度優先版
    でも精度重視版と同じものをそのまま使う。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "tessdata_fast", name + ".traineddata")
    return path if os.path.isfile(path) else None


def tessdata_fast_candidates():
    """速度優先版 tessdata を置ける場所を、試す順に返す（tessdata_candidates() と同じ考え方）。"""
    places = [os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "tessdata_fast")]
    for name in ("LOCALAPPDATA", "ProgramData", "APPDATA", "HOME"):
        base = os.environ.get(name, "")
        if base and os.path.isdir(base):
            places.append(os.path.join(base, "pdf_ocr", "tessdata_fast"))
    places.append(os.path.join(tempfile.gettempdir(), "pdf_ocr_tessdata_fast"))
    seen = []
    for path in places:
        full = os.path.abspath(path)
        if full not in seen:
            seen.append(full)
    return seen


_tessdata_fast_cache = {}


def ensure_fast_tessdata(exe, needed, tessdata_accurate, quiet=False):
    """速度優先版（`tesseract（速度重視）`）の tessdata 置き場を用意する。

    jpn だけ同梱の速度優先版に差し替え、eng・jpn_vert・osd は精度重視版の
    置き場（tessdata_accurate、または利用者の tesseract 本体）から複製する
    （差が無いため）。用意できた置き場を返す（用意できなければ None）。
    一度用意したら、同じ実行の中では覚えておいて作り直さない。
    """
    key = (exe, tuple(sorted(needed)))
    if key in _tessdata_fast_cache:
        return _tessdata_fast_cache[key]
    result = None
    for target in tessdata_fast_candidates():
        if not writable_dir(target):
            continue
        ok = True
        for name in needed:
            destination = os.path.join(target, name + ".traineddata")
            if os.path.isfile(destination):
                continue
            if name == "jpn":
                source = stock_fast_traineddata("jpn")
            else:
                source = (find_traineddata(exe, name, tessdata_accurate)
                          or stock_traineddata(name))
            if not source:
                ok = False
                break
            try:
                if os.path.abspath(source) != os.path.abspath(destination):
                    shutil.copy2(source, destination)
            except OSError:                                 # noqa: BLE001
                ok = False
                break
        if not ok:
            continue
        copy_tessdata_configs(exe, target)
        have = langs_in_dir(target)
        if not all(name in have for name in needed):
            continue
        if not tessdata_works(exe, target):
            continue
        result = target
        break
    _tessdata_fast_cache[key] = result
    return result


def ensure_langs(exe, needed, available, quiet=False):
    """足りない言語データを用意する。使うべき tessdata フォルダを返す。

    tesseract は言語データの置き場を 1 つしか見ないため、足りない分を
    自分のフォルダへ入れる場合は、すでにある分もそこへ複製する。
    戻り値が None なら、tesseract の既定の置き場のままでよい。
    """
    missing = [name for name in needed if name not in available]
    if not missing:
        return None, []

    # まず tesseract 本体の置き場に足せないか試す（書き込めれば一番簡単）
    system_dirs = tessdata_dirs(exe)
    target = None
    for directory in system_dirs:
        if writable_dir(directory):
            target = directory
            break

    local = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "tessdata")
    use_local = target is None
    if use_local:
        if not writable_dir(local):
            raise RuntimeError("言語データを置くフォルダを作れませんでした: %s"
                               % local)
        target = local

    failed = []
    for name in missing:
        try:
            download_traineddata(name, target, quiet)
        except RuntimeError as exc:
            failed.append(name)
            sys.stderr.write("  %s\n" % exc)

    if not use_local:
        return None, failed, target

    # 自分のフォルダを使うときは、すでにある分もそこへ複製しておく
    for name in needed:
        destination = os.path.join(target, name + ".traineddata")
        if os.path.isfile(destination):
            continue
        source = find_traineddata(exe, name)
        if source:
            shutil.copy2(source, destination)
    copy_tessdata_configs(exe, target)
    return target, failed, target


def find_font(preferred):
    if preferred and os.path.isfile(preferred):
        return preferred
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def register_font(path):
    """透明テキスト用のフォントを登録し、フォント名を返す。

    日本語を確実にコピー・検索できるように、実体のあるフォントを
    埋め込む（ToUnicode が付くので、どのビューアでも文字が取り出せる）。
    見つからないときだけ、埋め込みなしの CID フォントで代用する。
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont, TTFError
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    if path:
        name = "OCRTEXT"
        try:
            if path.lower().endswith(".ttc"):
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
            else:
                pdfmetrics.registerFont(TTFont(name, path))
            return name
        except (TTFError, IOError, ValueError) as exc:
            sys.stderr.write("フォント %s を使えませんでした（%s）。\n" % (path, exc))
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    return "HeiseiKakuGo-W5"


# --------------------------------------------------------------------------
# OCR
# --------------------------------------------------------------------------

def font_round_trip(font_name, sample="確認申請テスト"):
    """置いた見えない文字を、本当に読み出せるかを実際に試す。"""
    from pypdf import PdfReader

    words = [Word(sample, 0, 0, 100 * len(sample), 100)]
    try:
        data = build_overlay(words, 400.0, 100.0, 400, 100, font_name)
        text = PdfReader(io.BytesIO(data)).pages[0].extract_text() or ""
    except Exception:                                   # noqa: BLE001
        return False
    return sample in "".join(text.split())


def upright_only(vertical):
    """横書きで読むパスに足す、tesseract への指定。

    見開きの紙面では、右の頁が縦組みというだけで、左の頁にある**横書きの
    段落まで縦組みとして読まれます**。実測（利用者の縦組みの資料
    `1ca57185-____1.pdf`、500dpi、tesseract 5.5.3、jpn+eng/PSM 3）。

    | 読ませ方 | その段落の結果 |
    |---|---|
    | 紙面の全体をそのまま | `改-:改=討性例人能` `1ご:法か震特性` |
    | 段落だけ切り出して PSM 6 | `新耐震基準ができた3年後の1984年に「4号特例」が始まりました。` |
    | 紙面の全体 + 下の指定 | `新耐震基準ができた3年後の1984年に「4号特例」が始まりました。` |

    切り出せば読めるのに紙面ごとだと読めない、その原因がこれでした。
    字が潰れているのでも、解像度が足りないのでもなく、**読む向きの
    判定を間違えている**だけです。縦組みは LANG2 の縦書きパス（PSM 5）が
    別に読むので、横書きのパスで縦組みを探す必要はありません。
    """
    return [] if vertical else ["-c", "textord_tabfind_vertical_text=0"]


# --------------------------------------------------------------------------
# PP-OCRv5（ONNX 版）。tesseract の代わりに横書き・縦書きのどちらかの
# パスを担わせられる。model は "mobile"（同梱、21 MB）と "server"
# （165 MB、確認してから取得）の 2 つ。detect/recognize の中身は
# ppocr_onnx.py（PaddleOCR 由来の後処理、Apache-2.0）にある。
# --------------------------------------------------------------------------
PPOCR_ENGINES = ("ppocr_mobile", "ppocr_server")

# server の模型は 100 MB を超えるファイルが 2 つあり、ZIP には同梱できない
# （GitHub は 1 ファイル 100 MB 超を弾く）。選んだときに確認したうえで、
# このリポジトリに置いた ONNX 版を取りに行く（paddlepaddle は要らない。
# pdf_ocr/README.md の「① 枠組みの 721 MB → 理由になりません」を参照）。
PPOCR_SERVER_URLS = {
    "det.onnx": [
        "https://raw.githubusercontent.com/Scarab-11/s-claude-2/"
        "claude/image-pdf-text-selectable-pw4qg1/ppocr_server/onnx/det.onnx",
        "https://github.com/Scarab-11/s-claude-2/raw/"
        "claude/image-pdf-text-selectable-pw4qg1/ppocr_server/onnx/det.onnx",
    ],
    "rec.onnx": [
        "https://raw.githubusercontent.com/Scarab-11/s-claude-2/"
        "claude/image-pdf-text-selectable-pw4qg1/ppocr_server/onnx/rec.onnx",
        "https://github.com/Scarab-11/s-claude-2/raw/"
        "claude/image-pdf-text-selectable-pw4qg1/ppocr_server/onnx/rec.onnx",
    ],
}
PPOCR_MIN_BYTES = {"det.onnx": 50_000_000, "rec.onnx": 50_000_000}

_ppocr_engine_cache = {}
_ppocr_unavailable = {}
PPOCR_REQUIRED_MODULES = ("cv2", "onnxruntime", "pyclipper", "shapely")


def ppocr_model_root():
    """PP-OCRv5 の模型を置く場所（本体の隣の models フォルダ）。"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")


def ppocr_cache_dirs():
    """server の模型を取得して置く場所を、試す順に返す（tessdata と同じ考え方）。"""
    places = [os.path.join(ppocr_model_root(), "ppocrv5_server")]
    for name in ("LOCALAPPDATA", "ProgramData", "APPDATA", "HOME"):
        base = os.environ.get(name, "")
        if base and os.path.isdir(base):
            places.append(os.path.join(base, "pdf_ocr", "ppocrv5_server"))
    places.append(os.path.join(tempfile.gettempdir(), "pdf_ocr_ppocrv5_server"))
    seen = []
    for path in places:
        full = os.path.abspath(path)
        if full not in seen:
            seen.append(full)
    return seen


def ppocr_dict_path():
    path = os.path.join(ppocr_model_root(), "ppocrv5_dict.txt")
    return path if os.path.isfile(path) else None


def ppocr_model_ready(directory):
    dict_path = ppocr_dict_path()
    if not dict_path:
        return False
    det = os.path.join(directory, "det.onnx")
    rec = os.path.join(directory, "rec.onnx")
    return (os.path.isfile(det) and os.path.isfile(rec)
            and os.path.getsize(det) > 1_000_000
            and os.path.getsize(rec) > 1_000_000)


def find_ppocr_model(name):
    """使える模型の置き場を探す。無ければ None。"""
    if name == "mobile":
        directory = os.path.join(ppocr_model_root(), "ppocrv5_mobile")
        return directory if ppocr_model_ready(directory) else None
    for directory in ppocr_cache_dirs():
        if ppocr_model_ready(directory):
            return directory
    return None


def download_ppocr_server(target_dir, progress=None, quiet=False):
    """server の模型（det.onnx・rec.onnx）を取得する。

    progress(name, downloaded, total) を、取得の途中で繰り返し呼ぶ
    （GUI の進捗バー用。無ければ何もしない）。
    """
    import urllib.request

    if not writable_dir(target_dir):
        raise RuntimeError("%s に書き込めません" % target_dir)
    for filename, urls in PPOCR_SERVER_URLS.items():
        final_path = os.path.join(target_dir, filename)
        if (os.path.isfile(final_path)
                and os.path.getsize(final_path) >= PPOCR_MIN_BYTES[filename]):
            continue
        temp_path = final_path + ".part"
        if not quiet:
            sys.stdout.write("  %s を取得しています …\n" % filename)
            sys.stdout.flush()
        last_error = None
        for url in urls:
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "pdf_ocr"})
                with urllib.request.urlopen(request, timeout=180) as response:
                    total = int(response.headers.get("Content-Length", 0))
                    done = 0
                    with open(temp_path, "wb") as f:
                        while True:
                            chunk = response.read(1048576)
                            if not chunk:
                                break
                            f.write(chunk)
                            done += len(chunk)
                            if progress:
                                progress(filename, done, total)
                    # 途中で回線が切れても response.read() は静かに終わる
                    # ことがある。届いた大きさが Content-Length と違えば、
                    # 半端なまま「完了」扱いにしない。
                    if total and done != total:
                        raise RuntimeError(
                            "%d バイトのはずが %d バイトしか届かなかった"
                            % (total, done))
                last_error = None
                break
            except Exception as exc:                        # noqa: BLE001
                last_error = exc
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        if last_error is not None:
            raise RuntimeError(
                "%s を取得できませんでした（%s）" % (filename, last_error))
        if os.path.getsize(temp_path) < PPOCR_MIN_BYTES[filename]:
            os.remove(temp_path)
            raise RuntimeError("%s の中身が壊れています" % filename)
        os.replace(temp_path, final_path)
    return target_dir


def ensure_ppocr_model(name, confirm=None, progress=None, quiet=False):
    """使える模型の置き場を返す。無ければ用意を試みる。

    confirm() は「165 MB を取得してよいか」を利用者に確かめるための
    呼び出し。None なら確かめずに取得しない（自動では通信しない）。
    """
    found = find_ppocr_model(name)
    if found:
        return found
    if name != "server":
        return None
    if confirm is None or not confirm():
        return None
    for directory in ppocr_cache_dirs():
        try:
            download_ppocr_server(directory, progress=progress, quiet=quiet)
            return directory
        except RuntimeError:
            continue
    return None


def missing_ppocr_modules():
    """PP-OCRv5 を動かす部品（画像処理・推論・検出の後処理）のうち、
    この Python に入っていないものの一覧を返す（無ければ空）。
    """
    missing = []
    for module in PPOCR_REQUIRED_MODULES:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    return missing


def get_ppocr_engine(name, confirm=None, progress=None, quiet=False):
    """"ppocr_mobile" / "ppocr_server" の推論器を用意する（使い回す）。

    一度「用意できない」と分かったら（部品が足りない・確認で「いいえ」・
    取得に失敗など）、同じ実行の中では覚えておいて、以後は確認や取得を
    やり直さない（複数の PDF を続けて変換するとき、同じ確認ダイアログや
    大きな取得を毎回繰り返さないため）。
    """
    if name in _ppocr_unavailable:
        raise RuntimeError(_ppocr_unavailable[name])
    if name not in _ppocr_engine_cache:
        try:
            # 模型を取りに行く前に、部品が入っているか確かめる。ここで
            # 確かめないと、165MB の server 模型を取り終えてから 1 ページ
            # 目で初めて「pyclipper が無い」と分かり、通信が無駄になる。
            missing = missing_ppocr_modules()
            if missing:
                raise RuntimeError(
                    "PP-OCRv5 に必要な部品が入っていません（不足: %s）。"
                    "PDF文字認識.bat の [1] 準備 をもう一度実行してください。"
                    % "、".join(missing))
            import ppocr_onnx
            short = name.split("_", 1)[1]                  # mobile / server
            directory = ensure_ppocr_model(short, confirm, progress, quiet)
            if not directory:
                raise RuntimeError(
                    "PP-OCRv5 %s の模型が用意できません。tesseract で読みます。"
                    % short)
            dict_path = ppocr_dict_path()
            _ppocr_engine_cache[name] = ppocr_onnx.PPOCREngine(
                os.path.join(directory, "det.onnx"),
                os.path.join(directory, "rec.onnx"), dict_path,
                det_side=960, det_limit="max")
        except RuntimeError as exc:
            _ppocr_unavailable[name] = str(exc)
            raise
    return _ppocr_engine_cache[name]


def prepare_engines(settings, exe, quiet=False):
    """ENGINE1/ENGINE2 が PP-OCRv5・tesseract（速度重視）なら、ページ処理が
    始まる前に 1 回だけ用意する。PP-OCRv5 の確認や取得は
    `settings["_PPOCR_CONFIRM"]` / `settings["_PPOCR_PROGRESS"]`（GUI から
    渡す）を使う。用意できなければ普段の tesseract（精度重視）に戻し、
    その旨を settings["_ENGINE_FALLBACK"] に積む。
    """
    confirm = settings.get("_PPOCR_CONFIRM")
    progress = settings.get("_PPOCR_PROGRESS")
    fallback = []
    for key in ("ENGINE1", "ENGINE2"):
        name = settings.get(key, "tesseract")
        if name in PPOCR_ENGINES:
            try:
                get_ppocr_engine(name, confirm, progress, quiet)
            except RuntimeError as exc:
                settings[key] = "tesseract"
                message = "%s: %s" % (key, exc)
                fallback.append(message)
                if not quiet:
                    sys.stdout.write("  " + message + "\n")
        elif name == "tesseract_fast":
            needed = ["jpn", "eng", "jpn_vert"]
            tessdata = ensure_fast_tessdata(exe, needed,
                                            settings.get("_TESSDATA"), quiet)
            if tessdata:
                settings["_TESSDATA_FAST"] = tessdata
            else:
                settings[key] = "tesseract"
                message = ("%s: 速度重視版の言語データを用意できません"
                          "（精度重視版で読みます）" % key)
                fallback.append(message)
                if not quiet:
                    sys.stdout.write("  " + message + "\n")
    settings["_ENGINE_FALLBACK"] = fallback
    return fallback


def ppocr_words(name, image_path, confirm=None, progress=None, quiet=True):
    """PP-OCRv5 で 1 枚読み、tesseract と同じ Word の一覧にして返す。

    行ごとの枠を、そのまま 1 つの Word にする（tesseract の TSV と違い
    単語単位には割れていないため、merge_lines() は掛けない）。縦組みの
    列は angle=90 になり、pick_columns() がそのまま拾える。
    """
    engine = get_ppocr_engine(name, confirm, progress, quiet)
    results = engine.read_image(image_path)
    words = []
    for index, (box, text, conf, vertical) in enumerate(results):
        left = float(box[:, 0].min())
        top = float(box[:, 1].min())
        width = float(box[:, 0].max()) - left
        height = float(box[:, 1].max()) - top
        words.append(Word(text, left, top, width, height,
                          angle=90 if vertical else 0, line=index,
                          conf=conf * 100.0))
    return words


def run_tesseract(exe, args, timeout=600, env=None, tessdata=None):
    """tesseract を呼んで標準出力を返す。

    args は [画像, "stdout", …] の形。言語データの置き場を指定するときは、
    設定ファイル名（末尾の "tsv" など）より前に入れる必要がある。
    """
    if tessdata:
        args = args[:2] + ["--tessdata-dir", tessdata] + args[2:]
    creationflags = 0
    if os.name == "nt":  # 黒いウィンドウを開かせない
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run([exe] + args, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout, check=False,
                          creationflags=creationflags, env=env)
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError("tesseract が失敗しました: %s" % message)
    return proc.stdout.decode("utf-8", "replace")


def ocr_env(jobs):
    """複数ページを同時に読むときは、tesseract 自身の並列を止める。

    tesseract は内部でも複数スレッドを使うため、同時実行すると
    CPU の取り合いでかえって何十倍も遅くなる。
    """
    if jobs <= 1:
        return None
    return dict(os.environ, OMP_THREAD_LIMIT="1")


def detect_rotation(exe, image_path, min_confidence=1.5, env=None,
                    tessdata=None):
    """横倒し・上下逆のページを見つけ、立て直すのに必要な回転角を返す。

    戻り値は時計回りの度数（0 / 90 / 180 / 270）。判定できなければ 0。
    """
    try:
        out = run_tesseract(exe, [image_path, "stdout", "--psm", "0",
                                  "-l", "osd"], timeout=120, env=env,
                            tessdata=tessdata)
    except (RuntimeError, subprocess.TimeoutExpired, OSError):
        return 0
    rotate = 0
    confidence = 0.0
    for line in out.splitlines():
        if line.startswith("Rotate:"):
            rotate = as_int(line.split(":", 1)[1], 0) % 360
        elif line.startswith("Orientation confidence:"):
            try:
                confidence = float(line.split(":", 1)[1].strip())
            except ValueError:
                confidence = 0.0
    if rotate in (90, 180, 270) and confidence >= min_confidence:
        return rotate
    return 0


def unrotate_boxes(words, rotation, width, height):
    """立て直した画像の座標を、元の画像の座標に戻す。

    width / height は立て直したあとの画像の大きさ。
    """
    if rotation == 0:
        return words
    restored = []
    for word in words:
        if rotation == 90:      # 画像を時計回りに 90 度回して読んだ
            left = word.top
            top = width - word.left - word.width
        elif rotation == 180:
            left = width - word.left - word.width
            top = height - word.top - word.height
        else:                   # 270
            left = height - word.top - word.height
            top = word.left
        if rotation == 180:
            new_w, new_h = word.width, word.height
        else:
            new_w, new_h = word.height, word.width
        restored.append(Word(word.text, left, top, new_w, new_h,
                             (word.angle - rotation) % 360))
    return restored


def ocr_image(exe, image_path, image_size, settings, env=None, ink_path=None,
              retry=True):
    """1 ページ分の画像を OCR して、元の画像座標での単語一覧を返す。

    ink_path は「色の付いたインクを濃いまま残した」白黒画像。縦組みを
    読むときだけこちらを使う（ink_image() の説明を参照）。
    """
    lang = settings["LANG"]
    psm = settings["PSM"]
    min_conf = as_int(settings["MINCONF"], 30)
    tessdata = settings.get("_TESSDATA") or None
    rotation = 0
    engine1 = settings.get("ENGINE1", "tesseract")
    engine2 = settings.get("ENGINE2", "tesseract")
    # tesseract（速度重視）を選んだパスだけ、速度優先版の置き場に差し替える
    # （選んでいないパスは、いつもどおり精度重視版のまま）。
    tessdata_fast = settings.get("_TESSDATA_FAST") or None
    tessdata1 = tessdata_fast if engine1 == "tesseract_fast" else tessdata
    tessdata2 = tessdata_fast if engine2 == "tesseract_fast" else tessdata

    if as_bool(settings["AUTOROTATE"]) and settings.get("_HAS_OSD"):
        rotation = detect_rotation(exe, image_path, env=env, tessdata=tessdata)
    if rotation:
        image_path, image_size = rotate_image(image_path, rotation)
        if ink_path:
            ink_path = rotate_image(ink_path, rotation)[0]
    vertical_image = ink_path or image_path

    lang2 = settings.get("LANG2", "")
    # 縦書きで読む設定のときは、縦中横（縦組みの中で横に寝かせた数字）を
    # 拾い直すために、数字に強い読み方でもう一度だけ読んでおく。縦組みを
    # 受け持つほうのパス（ふつうは 2 回目＝lang2）の置き場を使う。
    numbers = None
    if as_bool(settings.get("NUMBERS", "yes")) and (
            "_vert" in lang or "_vert" in lang2):
        numbers_tessdata = tessdata1 if "_vert" in lang else tessdata2
        numbers = sparse_numbers(exe, vertical_image, env, numbers_tessdata)

    wants_numbers = numbers is not None
    first_vertical = "_vert" in lang

    if engine1 in PPOCR_ENGINES:
        # PP-OCRv5 はすでに行ごとにまとまった結果を返すので、tesseract
        # 専用の後処理（merge_lines・縦中横の拾い直しなど）は掛けない。
        words = ppocr_words(engine1, image_path)
        words = sort_reading_order(words, image_size[0])
    else:
        first_image = vertical_image if first_vertical else image_path
        tsv = run_tesseract(exe, [first_image, "stdout", "-l", lang,
                                  "--psm", str(psm)]
                            + upright_only(first_vertical) + ["tsv"],
                            env=env, tessdata=tessdata1)
        if first_vertical and wants_numbers:
            raw = parse_vertical(tsv, min_conf)
            fix_tatechuyoko(raw, numbers)
            fix_stacked_digits(raw, first_image, exe, env, tessdata1, min_conf)
            fill_vertical_gaps(raw, first_image, exe, env, tessdata1, lang, psm)
        else:
            raw = parse_tsv(tsv, min_conf)
            if wants_numbers:
                # 縦組みが混じる紙面では、横書きの設定で読んでも縦中横が
                # 1 文字に化ける。こちらも直しておかないと、この読みが
                # 採用されたページで数字ごと消える
                fix_tatechuyoko(raw, numbers, upright=False)
            fix_latin_runs(raw, first_image, exe, env, tessdata1)
            reread_weak_lines(raw, first_image, exe, env, tessdata1)
        words = merge_lines(raw)
        if not first_vertical:
            words = sort_reading_order(words, image_size[0])

    if lang2:
        if engine2 in PPOCR_ENGINES:
            words2 = ppocr_words(engine2, vertical_image)
        else:
            # 縦組みの所を拾い直すために、縦書き用の設定でもう一度読む
            second_vertical = "_vert" in lang2
            second_image = vertical_image if second_vertical else image_path
            tsv2 = run_tesseract(exe, [second_image, "stdout", "-l", lang2,
                                       "--psm", str(settings.get("PSM2", "5"))]
                                 + upright_only(second_vertical) + ["tsv"],
                                 env=env, tessdata=tessdata2)
            if second_vertical and wants_numbers:
                raw2 = parse_vertical(tsv2, min_conf)
                fix_tatechuyoko(raw2, numbers)
                fix_stacked_digits(raw2, second_image, exe, env, tessdata2,
                                   min_conf)
                fill_vertical_gaps(raw2, second_image, exe, env, tessdata2,
                                   lang2, settings.get("PSM2", "5"))
            else:
                raw2 = parse_tsv(tsv2, min_conf)
                if wants_numbers:
                    fix_tatechuyoko(raw2, numbers, upright=False)
            words2 = merge_lines(raw2)
        words = combine_passes(words, words2, page_width=image_size[0])

    # 図面や CAD 出力のように文字が散らばっているページは、文章として
    # 読む設定ではほとんど拾えない。取れた文字列が少ないページに限って
    # 散在向けの設定でもう一度読み、多いほうを採る。資料の種類を利用者に
    # 選ばせないための処理なので、ふつうの文書では二度読みは起きない。
    thin = as_int(settings.get("SPARSEUNDER", "0"), 0)
    sparse_psm = settings.get("SPARSEPSM", "")
    if thin and sparse_psm and len(words) < thin:
        tsv3 = run_tesseract(exe, [image_path, "stdout", "-l", lang,
                                   "--psm", str(sparse_psm), "tsv"],
                             env=env, tessdata=tessdata1)
        scattered = sort_reading_order(merge_lines(parse_tsv(tsv3, min_conf)),
                                       image_size[0])
        if len(scattered) > len(words):
            words = scattered

    # 精度重視版の言語データは横組みで強く、縦組みで弱い。うまく読めた
    # とは言えないページだけ、元から入っていた版でも読み直して、平均
    # 信頼度の高いほうを採る（in_doubt の説明を参照）。
    other = settings.get("_TESSDATA_ALT")
    if (retry and other is not None and in_doubt(words)
            and engine1 == "tesseract" and engine2 == "tesseract"):
        spare = dict(settings)
        spare["_TESSDATA"] = other
        try:
            again, again_rotation = ocr_image(exe, image_path, image_size,
                                              spare, env, ink_path,
                                              retry=False)
        except (RuntimeError, OSError):                 # noqa: BLE001
            again, again_rotation = None, 0
        # 向きの判定は読み直しでも改めて行うので、そのときの向きを一緒に
        # 返す。こちらの向きを返すと、二つが食い違ったページで透明文字が
        # 写っている文字からずれる（回した紙面で実際にそうなった）。
        if again and page_quality(again) > page_quality(words):
            return again, again_rotation

    return unrotate_boxes(words, rotation, image_size[0], image_size[1]), rotation


def page_quality(words):
    """読み取り結果の確からしさを 1 つの数にする（文字数で重み付けした平均）。

    短い断片ほど信頼度が高く出やすいので、字数で重みを付けないと
    「1 字ずつばらばらに化けた紙面」のほうが高く出てしまう。
    """
    total = sum(len(word.text) for word in words)
    if not total:
        return 0.0
    return sum(word.conf * len(word.text) for word in words) / float(total)


def in_doubt(words, floor=90.0, least=8):
    """この読み取りを、別の版の言語データでも読み直して比べるべきか。

    精度重視版の言語データは横組みで強く、縦組みで弱い。実測（狙った語）。

        紙面                精度重視版        速度優先版
        横組み二段（実物）  94.1 → 15/16     92.8 →  9/16   精度重視の勝ち
        縦組み（実物）      79.1 → 12/16     89.5 → 15/16   速度優先の勝ち
        表（縦の見出し）    56.9 → 壊れる    93.6 → 正しい  速度優先の勝ち
        縦組み（合成）      85.0 → 12/16     94.6 → 正しい  速度優先の勝ち

    **4 例とも、平均信頼度の高いほうが正しい**ので、読み直して比べれば
    両方の良いところを取れる。ただし精度重視版は 2 倍以上遅く（同じ紙面で
    77 秒 対 34 秒）、毎ページ二度読みすると割に合わない。

    そこで、はっきり良く読めたページ（90 以上）はそのまま採り、それ以外
    だけ読み直す。上の 4 例では、いちばん重い横組みのページだけが二度読み
    を免れ、残り 3 例は読み直して正しいほうに変わる。

    字数の少ないページは平均が揺れるので、ある程度の量があるときに限る。
    """
    return len(words) >= least and page_quality(words) < floor


def sparse_numbers(exe, image_path, env=None, tessdata=None, floor=80.0):
    """紙面に散らばっている数字だけを、数字に強い読み方で拾う。

    縦組みの中の数字は、二桁までなら横に寝かせて 1 文字分に収める組み方
    （縦中横）をする。縦書き用の言語データはこれを読めず、「(昭和25年)」が
    「(昭和お年)」のような一文字に化ける。横書きの設定で読ませても、
    ページ全体では周りの縦組みに引きずられて同じように化ける。

    PSM 11（文字が散在）は行の並びを推測しないので、縦組みの中に埋もれた
    数字のかたまりだけを素直に拾える。誤って拾ったものを本文に混ぜると
    かえって悪くなるので、はっきり読めたものだけを返す。
    """
    tsv = run_tesseract(exe, [image_path, "stdout", "-l", "eng",
                              "--psm", "11", "tsv"], env=env,
                        tessdata=tessdata)
    found = []
    # ここは行として読ませていない（PSM 11 は文字が散在している前提）ので、
    # 行を手掛かりにする keep_holes は効かない。はっきり読めたものだけ。
    for word in parse_tsv(tsv, floor, rescue=False):
        text = squeeze(word.text)
        if len(text) < 2 or not text.isdigit():
            continue
        # 横に寝かせた数字は、縦より横に長い。縦に積んだ数字とは違う
        if word.width < word.height * 0.8:
            continue
        found.append(word)
    return found


def fix_tatechuyoko(vertical, numbers, inside=0.3, upright=True):
    """縦中横を読み違えた所を数字に直す。

    **縦書きパスだけでなく、横書きパスにも効かせる。** 縦組みの紙面を
    横書きの設定で読んでも、縦中横の数字は同じように 1 文字に化ける。
    実測（利用者の縦組みの資料、横書きパスの生の読み）。

        43 → 「は」   56 → 「%」と「ぶ」   12 → 「D」

    利用者が報告した `(昭和%ぶ年)` はこの「%」と「ぶ」そのもの。以前は
    縦書きパスにしか掛けていなかったので、**横書きパスが採用された
    ページでは、信頼度 96 で見つけた数字ごと捨てていた。**

    upright は、その数字のまわりの文章が縦組みか横組みかを表す
    （1 文字分の大きさを、列の幅で測るか行の高さで測るかが変わる）。

    横に寝かせた数字は 1 文字分の枠に収まるので、読み違えると必ず
    「1 文字」に化ける（「(昭和25年)」→「(昭和お年)」の「お」）。
    数字の枠と重なっている 1 文字を探して置き換える。

    化けた先が数字のこともある（「(昭和25年)」→「(昭和1年)」）。
    二桁が一桁に潰れているので、数字だからといって正しいとは限らない。
    枠がひとつ分しかない所に数字が二つに割れて出ることもある
    （「56」→「5」と別の 1 文字）。残ったほうは消す。

    「近いもの」ではなく「重なっているもの」で選ぶ。近さだけで選ぶと、
    たまたま隣にある正しく読めた文字を消してしまう（数字が読み飛ばされて
    いて、化けた文字がそもそも無い場合）。

    置き換え先が見つからなかった数字は捨てる。紙面の数字を無条件に拾う
    読み取りなので、ノンブル（ページ番号）のような本文と関係のない数字も
    混ざっており、それを列に差し込むと本文の途中にページ番号が割り込む。
    縦組みに置かれた普通の大きさの数字は、もともと横書きのパスから
    拾い直す仕組み（combine_passes）があるので、そちらに任せる。

    行としてまとめる前に置き換えるので、直した数字はそのまま列の途中に
    収まる。あとから足すのと違い、コピーしたときの並びが崩れない。

    戻り値は、置き換えた数の合計。
    """
    # 行ごとの日本語の字数。どれが本文の列かの目安にする
    body_lines = {}
    for word in vertical:
        body_lines[word.line] = (body_lines.get(word.line, 0)
                                 + cjk_count(word.text))

    replaced = 0
    for number in numbers:
        # 縦中横は 1 文字分の枠に詰めて組むので、列の幅からはみ出さない。
        # はみ出す数字は、列の途中に普通の大きさで置かれたもので、読み違い
        # ではない（縦書きの読み取りはそこを読み飛ばしているだけ）。
        # 1 語ごとの枠は tesseract が上下左右に膨らませてしまうので、
        # 同じ列にある語の幅の中央値を「列の幅」として使う。
        # 1 文字分の枠に収まらない数字は、ふつうの大きさで置かれたもの。
        # ただし、**1 文字の語と枠がぴたり重なっているなら、それ自体が
        # 「1 文字分に収まっている」証拠**なので、大きさは問わない。
        # 実測（利用者の縦組みの資料）で「43」が幅 34、1 文字分の見積もり
        # 27 の 1.25 倍（33.75）を 0.25 画素超えて見送られていた。
        # 置き換え先の「は」は 34x28 で、数字とまったく同じ枠だった。
        snug = any(len(squeeze(word.text)) == 1
                   and overlap_ratio(number, word) >= 0.9
                   and overlap_ratio(word, number) >= 0.9
                   for word in vertical)
        if not snug and number.width > cell_size(number, vertical,
                                                 upright) * 1.25:
            continue
        digits = squeeze(number.text)
        if any(digits in squeeze(word.text) and overlap_ratio(number, word) > inside
               for word in vertical):
            continue              # そこはもう正しく読めている

        target = None
        best = (0, inside)
        matched = []
        for word in vertical:
            if len(squeeze(word.text)) != 1:
                continue          # 1 文字分の枠に化けるので、候補は 1 文字だけ
            share = overlap_ratio(number, word)
            if share <= inside:
                continue
            matched.append(word)
            # 本文の列にある候補を優先する。列から外れた 1 文字に数字を
            # 移すと、その字だけの行になり、日本語を含まない行として
            # あとで捨てられ、数字ごと消えてしまう。
            score = (body_lines.get(word.line, 0), share)
            if score > best:
                target, best = word, score
        if target is not None:
            # 枠ひとつ分の所に二つ以上に割れて出たときの、残りを消す。
            # 見方は 2 つあり、どちらかに当たれば片割れとみなす。
            #
            #   ・その字のほとんどが数字の枠に収まっている（word_inside）
            #   ・その字が数字の枠のかなりの部分を覆っている（covers）
            #
            # 前者だけでは足りなかった。実測（利用者の縦組みの資料）で
            # 「56」が「%」と「ぶ」に割れたとき、「ぶ」の枠は数字より
            # 下にずれていて、ぶ自身の 27% しか重なっていない。ところが
            # **数字のほうから見ると 42% を覆っている**。半分に割れた
            # 相手なので、こちらから見れば必ず大きく重なる。
            # 隣の字は端がかかるだけなので、どちらの見方でも小さい。
            for word in matched:
                if word is target:
                    continue
                word_inside = overlap_ratio(word, number) >= 0.6
                covers = overlap_ratio(number, word) >= 0.3
                if word_inside or covers:
                    vertical.remove(word)
            target.text = squeeze(number.text)
            if upright:
                # 縦書きパスでは、この語はもう数字そのものなので、数字の
                # 信頼度を持たせる。横書きパスでは持たせない。**そちらの
                # 信頼度は、そのページを縦横どちらの読みで採るかの判定
                # （pick_columns）に使われる。** 1 文字直しただけで判定を
                # 動かすと、関係のない語まで入れ替わる。実測（実物 4 つ、
                # 正解語 16 個ずつ）で、持たせると 52/64 が 50/64 に落ち、
                # 縦組みの見開きで「1950年」と「壁量計算に加」が消えた。
                target.conf = number.conf
            replaced += 1
        elif insert_number(vertical, number, upright):
            replaced += 1
    return replaced


def insert_number(words, number, upright=True, share=0.5):
    """読み飛ばされた縦中横の数字を、行（列）の途中に差し込む。

    縦中横は 1 文字に化けるとは限らず、**丸ごと読み飛ばされる**ことも
    ある。利用者の機械で変換された PDF から取り出した実物。

        1950年(昭和年)      ← 25 が 1 文字も無い
        1995年(平成年)      ← 7 が無い
        2000年(平成年)      ← 12 が無い
        2024月佐藤実        ← 年10 が無い

    化けていれば置き換える相手がいるが、無ければいない。以前はここで
    **信頼度 96 で見つけた数字を捨てていた**。捨てていた理由は、紙面の
    数字を無条件に拾う読み取りなので、ノンブル（ページ番号）のような
    本文と関係のない数字も混ざるため。列に差し込むと本文の途中に
    ページ番号が割り込む。

    そこで、`keep_holes()` と同じ考え方で分ける。**その行の語に前後を
    挟まれている数字だけを差し込む。** ノンブルは紙面の隅に 1 つで
    立っているので、挟む相手がいない。

    行の目印（line）は挟んだ語から引き継ぐので、あとで行としてまとめる
    ときに位置の順で並び、コピーしたときも列の途中に収まる。
    """
    if upright:
        low, high = number.left, number.left + number.width
        band = lambda word: (word.left, word.left + word.width)   # noqa: E731
        place = lambda word: word.top                             # noqa: E731
        size = lambda word: word.width                            # noqa: E731
        own = number.width
    else:
        low, high = number.top, number.top + number.height
        band = lambda word: (word.top, word.top + word.height)    # noqa: E731
        place = lambda word: word.left                            # noqa: E731
        size = lambda word: word.height                           # noqa: E731
        own = number.height

    lines = {}
    for word in words:
        start, stop = band(word)
        if min(stop, high) - max(start, low) > min(size(word), own) * share:
            lines.setdefault(word.line, []).append(word)

    here = place(number)
    best = None
    for key, items in lines.items():
        if not any(place(word) < here for word in items):
            continue
        if not any(place(word) > here for word in items):
            continue
        weight = sum(cjk_count(word.text) for word in items)
        if best is None or weight > best[0]:
            best = (weight, key)
    if best is None or not best[0]:
        return False

    spare = Word(squeeze(number.text), number.left, number.top,
                 number.width, number.height, conf=number.conf)
    spare.line = best[1]
    words.append(spare)
    return True


# 1 文字だけを読ませると、数字が形の似た英字に化けやすい
LOOKALIKE = {"l": "1", "i": "1", "I": "1", "|": "1", "]": "1", "[": "1",
             "!": "1", "/": "1", "\\": "1",
             "O": "0", "o": "0", "Q": "0", "D": "0", "U": "0",
             "S": "5", "s": "5", "Z": "2", "z": "2", "B": "8",
             "G": "6", "b": "6", "g": "9", "q": "9", "T": "7", "A": "4"}


def is_stacked_digits(word, least=2):
    """縦に 1 文字ずつ積まれた数字らしいか。"""
    body = squeeze(word.text)
    return (len(body) >= least and body.isdigit()
            and word.height > word.width * 1.5)


def parse_vertical(tsv_text, min_conf, digit_floor=10):
    """縦書きの読み取り結果を取り出す。

    西暦などの数字は、縦組みでも 1 文字ずつ縦に積んで組む。縦書き用の
    言語データはこれを 1 つの語として読もうとして外し、信頼度も低く出る
    （実測では「1950」を信頼度 24 で「1930」と読んだ）。そのままだと
    下限で捨てられて数字ごと消えるので、積まれた数字だけは下限を下げて
    拾っておき、あとで 1 文字ずつ読み直して直す。
    """
    # ここでは keep_holes を使わない。縦書きの結果は pick_columns が
    # 信頼度で横書きの結果と比べて採否を決めるので、自信のない語を足すと
    # その比較が動く。実測（実物 4 つ、正解語 16 個ずつ）で、縦書きにも
    # 足すと 51/64 が 48/64 に落ちた。落ちたのは縦組みの見開き 1 つで
    # (12/16 → 9/16)、正しく読めていた「1950年(昭和25年)」が、縦書きの
    # 読み違い「1930年(昭和お年)」に差し替わったため。
    words = []
    for word in parse_tsv(tsv_text, min(min_conf, digit_floor), rescue=False):
        if word.conf >= min_conf or is_stacked_digits(word):
            words.append(word)
    return words


def fix_stacked_digits(words, image_path, exe, env=None, tessdata=None,
                       min_conf=30, most=24):
    """縦に積まれた数字を、1 文字ずつ読み直して直す。

    まとめて読ませると外すが、1 文字ずつ切り出して読ませれば当たる。
    切れ目は、その列のインクの途切れで決める（枠を等分すると、数字の
    後ろに続く「年」まで巻き込んで位置がずれる）。

    信頼度の高いものも読み直す。tesseract は自信を持って間違えることが
    あり、Windows 版では「1950」を信頼度 87 で「1930」と読んでいた。
    信頼度で選り分けると、この一番直したいものが素通りする。
    代わりに、1 文字ずつの読みがすべてはっきりしていて、桁数も元と
    合ったときだけ差し替える。読み直せなかった低信頼度のものは捨てる。
    誤った数字を残すと、検索で誤って当たるようになる。
    """
    from PIL import Image

    targets = [word for word in words if is_stacked_digits(word)][:most]
    if not targets:
        return 0

    image = Image.open(image_path).convert("L")
    fixed = 0
    try:
        for word in targets:
            text = read_stacked(image, word, exe, env, tessdata)
            if text and len(text) == len(squeeze(word.text)):
                if squeeze(word.text) != text:
                    fixed += 1
                word.text = text
                word.conf = max(word.conf, float(min_conf))
            elif word.conf < min_conf:
                words.remove(word)
    finally:
        image.close()
    return fixed


def read_stacked(image, word, exe, env=None, tessdata=None, pad=3, most=8):
    """縦に積まれた数字を、上から 1 文字ずつ読んでつなげる。"""
    strip = image.crop((word.left, word.top,
                        word.left + word.width, word.top + word.height))
    try:
        bands = ink_bands(strip)
    finally:
        strip.close()

    digits = []
    for top, bottom in bands[:most]:
        cell = image.crop((word.left - pad, word.top + top - pad,
                           word.left + word.width + pad, word.top + bottom + pad))
        try:
            digit = read_digit(cell, exe, env, tessdata)
        finally:
            cell.close()
        if not digit:
            break              # 数字が途切れたら、そこから先は別の文字
        digits.append(digit)
    return "".join(digits)


def ink_bands(strip, level=150, least=4):
    """縦長の切り抜きを、インクのある行のかたまりに分ける。"""
    width, height = strip.size
    pixels = strip.load()
    bands = []
    start = None
    for y in range(height + 1):
        wet = y < height and any(pixels[x, y] < level for x in range(width))
        if wet and start is None:
            start = y
        elif not wet and start is not None:
            if y - start >= least:
                bands.append((start, y))
            start = None
    return bands


def read_digit(cell, exe, env=None, tessdata=None, pad=14, target=160,
               floor=60.0):
    """1 文字の切り抜きを数字として読む。読めなければ空文字。

    まわりに余白を足して正方形にしてから拡大する。ぎりぎりに切り出した
    ままだと、tesseract は 1 と 0 を読み落とす（実測で 4 桁中 2 桁）。

    はっきり読めたものだけを返す。読み直した結果で元を置き換えるので、
    自信のない読みを通すと、正しく読めていたものを壊しかねない。
    """
    from PIL import Image

    width, height = cell.size
    side = max(width, height) + pad * 2
    canvas = Image.new("L", (side, side), 255)
    canvas.paste(cell, ((side - width) // 2, (side - height) // 2))
    scale = max(1, target // side)
    if scale > 1:
        canvas = canvas.resize((side * scale, side * scale), Image.LANCZOS)

    handle, path = tempfile.mkstemp(prefix="pdf_ocr_cell_", suffix=".png")
    os.close(handle)
    try:
        canvas.save(path)
        canvas.close()
        tsv = run_tesseract(exe, [path, "stdout", "-l", "eng", "--psm", "10",
                                  "tsv"], env=env, tessdata=tessdata)
    except (RuntimeError, OSError):
        return ""
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    out = ""
    best = floor
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t",
                            quoting=csv.QUOTE_NONE)
    for row in reader:
        text = (row.get("text") or "").strip()
        try:
            conf = float(row.get("conf") or -1)
        except ValueError:
            continue
        if text and conf >= best:
            out, best = text, conf

    body = squeeze(out)
    if len(body) != 1:
        return ""
    return body if body.isdigit() else LOOKALIKE.get(body, "")


def fill_vertical_gaps(words, image_path, exe, env=None, tessdata=None,
                       lang="jpn_vert", psm=5, floor=50.0, span=3.0,
                       least=2.0, fill=0.35, most=120):
    """列の中にあいた不自然なすきまを、切り出して読み直す。

    縦組みを 1 枚まるごと読ませると、まわりの字は取れているのに 1〜2 字
    だけ落ちることがある。「(昭和25年)」の「昭和」が丸ごと消えるのが
    その例で、紙面には出ているのに読み取り結果には候補としても現れない。

    そこで、同じ列で上下に並ぶ語の間隔を見て、広く空いている所をその列の
    幅で切り出し、もう一度だけ読ませる。切り出すと候補が絞られるので、
    まわりに引きずられずに読めることが多い（実測で「昭和」を信頼度 90 で
    拾えた）。

    問い合わせを空振りさせないための条件が 2 つある。どちらか一方では
    足りず、両方いる。

      すきまが 2 文字分以上あること
          tesseract が返す枠はインクにぴったり沿っているので、字と字の
          間には常にすきまがある。1 文字分では、詰まって並んだ所まで
          読みに行って、無い字を作る。落ちた 1 文字は、上下のすきまを
          合わせて 2 文字分以上の穴になる
      読めた字が、そのすきまを 35% 以上埋めること
          何も無い所や図の隙間を読ませると、tesseract は小さな断片を
          自信を持って返す（実測で「局」を信頼度 81、「震」を 92）。
          穴の大きさに見合う字が返ってきたときだけ採る

    実測では、この 2 つで 5.3.4 と 5.5.1 の両方で誤りが 0 になり、
    「昭和」「そこ」「年」の 3 か所が正しく戻った。片方だけでは、
    どちらの版でも誤った字が入った。

    読めた字が漢字・かなであることも条件にする。図やけい線の間を
    読んでしまうと、記号の切れ端が本文に紛れ込むため。上下の相手が
    漢字・かなであることは条件にしない。直したい「(昭和25年)」自体が、
    かっこと数字に挟まれているため。
    """
    from PIL import Image

    lines = {}
    for word in words:
        lines.setdefault(word.line, []).append(word)

    shapes = {}
    for line, group in lines.items():
        if len(group) < 3:
            continue
        widths = sorted(word.width for word in group)
        rough = widths[len(widths) // 2]
        # 幅の広い語（横に寝た数字や、隣の列を巻き込んだ読み違い）は
        # 列の位置を測る当てにならないので、細いものだけで測る
        column = [word for word in group if word.width <= rough * 1.4]
        if len(column) < 3 or rough <= 0:
            continue
        widths = sorted(word.width for word in column)
        lefts = sorted(word.left for word in column)
        cell = widths[len(widths) // 2]
        if cell > 0:
            shapes[line] = (lefts[len(lefts) // 2], cell)
    if not shapes:
        return 0

    # 図やけい線の切れ端も「行」としてまとまってしまう。そこに開いた
    # すきまを読むと、記号の断片が本文に紛れ込む。紙面全体の字の大きさ
    # から外れた行は、本文の列ではないとみなして触らない。
    sizes = sorted(cell for _, cell in shapes.values())
    usual = sizes[len(sizes) // 2]

    holes = []
    for line, (left, cell) in shapes.items():
        if not usual * 0.5 <= cell <= usual * 2.0:
            continue
        column = sorted(lines[line], key=lambda word: word.top)
        for above, below in zip(column, column[1:]):
            gap = below.top - (above.top + above.height)
            if least * cell <= gap <= span * cell:
                holes.append((above, left, cell, above.top + above.height,
                              below.top))
    if not holes:
        return 0

    image = Image.open(image_path)
    added = 0
    try:
        for above, left, cell, top, bottom in holes[:most]:
            patch = image.crop((left, top, left + cell, bottom))
            found = read_patch(patch, exe, env, tessdata, lang, psm, floor)
            patch.close()
            # 穴の大きさに見合う字が返ってきたときだけ採る。何も無い所を
            # 読ませても、tesseract は小さな断片を自信を持って返すため
            covered = sum(height for _, _, _, height in found)
            if covered < (bottom - top) * fill:
                continue
            for text, conf, offset, height in found:
                word = Word(text, left, top + offset, cell, height,
                            angle=90, line=above.line, conf=conf)
                words.append(word)
                added += 1
    finally:
        image.close()
    return added


def fix_latin_runs(words, image_path, exe, env=None, tessdata=None,
                   floor=80.0, least=8, span=4, pad=6, most=40):
    """日本語の行に紛れた、自信のない英字だけの語を切り出して読み直す。

    日本語の語が英字として読まれることがある。利用者の資料での実測
    （tesseract 5.5.3、300dpi）。

        本書は、  →  AIS,   信頼度 57.9

    紙面全体を一度に読ませると、まわりの候補に引きずられてこうなります。
    **同じ場所を切り出して読み直すと、`本書は、` が信頼度 93 で返ります。**
    言語データを日本語だけにしても、`jpn+eng` のままでも、PSM を
    7 / 8 / 6 / 13 のどれにしても、余白を 2 / 6 / 12 画素のどれにしても、
    すべて `本書は、` の 93 でした。**切り出すこと自体が効きます。**

    これは版や解像度で表に出たり出なかったりする、際どい判定です。
    同じ資料を 500dpi で読むと正しく `本書は、` になり、300dpi では
    `AIS,` になりました。利用者の環境（Windows 版の tesseract）では
    500dpi でも英字側に倒れていました。**どちらに倒れても直るように
    しておくのが筋です。**

    ふつうの英字（`PDF`、`CAD`、図面番号）を壊さないための条件。

      ・その語が英字だけで、span 文字以内であること
      ・信頼度が floor 未満であること（正しく読めた英字は高く出る。
        実測で `AIS,` は 57.9、まわりの日本語は 93〜95）
      ・その行に日本語が least 文字以上あること
      ・読み直した結果が漢字・かなを含み、元より信頼度が高いこと

    最後の条件が最後の砦で、`PDF` を切り出して読み直しても日本語は
    返らないので、元のまま残ります。
    """
    from PIL import Image

    if not words:
        return 0
    lines = {}
    for word in words:
        lines.setdefault(word.line, []).append(word)

    def latin_only(text):
        """漢字・かなを含まず、英字を含む。

        is_latin() は使えない。あれは英字だけの語を見るもので、実際に
        化けた `AIS,` は読点が付いていて外れる。数字だけの語（`2025`）は
        英字を含まないので、ここには入らない。
        """
        body = squeeze(text)
        return (bool(body) and not has_cjk(body)
                and any("a" <= ch.lower() <= "z" for ch in body))

    targets = []
    for items in lines.values():
        if sum(cjk_count(word.text) for word in items) < least:
            continue
        for word in items:
            if (word.conf < floor and latin_only(word.text)
                    and len(squeeze(word.text)) <= span):
                targets.append(word)
    if not targets or len(targets) > most:
        return 0

    try:
        image = Image.open(image_path)
    except (OSError, ValueError):
        return 0
    fixed = 0
    try:
        for word in targets:
            box = (max(0, word.left - pad), max(0, word.top - pad),
                   min(image.width, word.left + word.width + pad),
                   min(image.height, word.top + word.height + pad))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            got = read_patch(image.crop(box), exe, env, tessdata,
                             lang="jpn", psm=7, floor=word.conf)
            if not got:
                continue
            text, conf = got[0][0], got[0][1]
            if len(got) > 1:
                text = "".join(item[0] for item in got)
                conf = min(item[1] for item in got)
            if conf > word.conf and has_cjk(text):
                word.text = text
                word.conf = conf
                fixed += 1
    finally:
        image.close()
    return fixed


def paper_bright(image, word, least=8):
    """その語の枠の明るさの中央値。地の色が明るいか暗いかを見る目安。"""
    box = (max(0, word.left), max(0, word.top),
           min(image.width, word.left + word.width),
           min(image.height, word.top + word.height))
    if box[2] - box[0] < 1 or box[3] - box[1] < 1:
        return 255
    patch = image.crop(box).convert("L")
    if patch.width * patch.height < least:
        return 255
    values = sorted(patch.getdata())
    return values[len(values) // 2]


def reread_column_runs(words, image_path, exe, env=None, tessdata=None,
                       paper=190, gain=0.0, pad=6, most=200, least=3):
    """縦組みの列を、地の明るさが揃っている所ごとに読み直す。

    列を丸ごと読み直すと、ひどいときは**何も返りません**。実測
    （利用者の縦組みの資料、500dpi、tesseract 5.5.3）。同じ列で、
    切り出す上端を 127 画素（約 2 字分）下げるだけで結果が変わります。

    | 切り出し | 信頼度 | 結果 |
    |---|---|---|
    | 列の全体（34 字） | **0** | `」` だけ |
    | 上端を 2 字分下げる | 76 | `の1981年に改正された耐震性能を「新耐震基準と呼ぶよ。` |

    **長さのせいではありません。** その列の上端には、オレンジ地に
    白抜きの大きな見出し（`★FILE 01` と誌面の題）がありました。
    見出しの領域を白で塗りつぶすと、同じ全体の切り出しが信頼度 87 で
    正しく読めます。

    tesseract は切り出した画像**全体を 1 つのしきい値**で白黒にします。
    地の明るさが違う領域が混ざると、しきい値がそちらに引かれて本文の
    黒文字が潰れます（実測の明るさの中央値は、見出しの領域 156・
    本文 230・混ぜた全体 209）。

    そこで、**語ごとに地の明るさを見て、明るい地が続く所だけ**を
    まとめて読み直します。見出しや色の付いた帯は、そこで切れます。

    語の数で機械的に区切る案は駄目でした（実測で 1 本改善・7 本悪化）。
    切れ目が語の途中に来て、余白に入った隣の字がもう 1 文字として
    読まれます（`がが`・`のの`・`おお`）。**切れ目は紙面の作りに
    合わせて決める必要があります。**

    **この関数も、いまは呼んでいません。** 明るさで区切ると壊滅的な
    失敗（信頼度 0）は防げますが、残りはやはり差し引きで負けました
    （実測で 1 本改善・3 本悪化）。

    | 差し替え | 判定 |
    |---|---|
    | `柱頭接合)が` → `柱頭柱脚の接合)が` | ○ |
    | `変わってきたの` → `わってきたのっ` | × `変` が落ちる |
    | `耐力壁の量` → `耐力力壁の量` | × `力` が重複 |
    | `倒壊した!` → `壊した.た!` | × |

    明るさが揃った本文だけを切り出しても、縦組みの列は 30 字ほどあり、
    その長さを一度に読ませると、元の読みと同じくらい間違えます
    （28 字の切り出しでも閉じかっこが落ちるのを実測）。**横書きの行
    （30 字）で効いて縦組みの列（30 字）で効かない理由は、まだ
    分かっていません。** 字数は同じなので、長さでは説明がつきません。

    残してあるのは、次に試す人が明るさの件から調べ直さずに済むように
    するためです。
    """
    from PIL import Image

    try:
        image = Image.open(image_path)
    except (OSError, ValueError):
        return 0

    fixed = 0
    try:
        lines = {}
        for word in words:
            lines.setdefault(word.line, []).append(word)

        runs = []
        for items in lines.values():
            if not line_is_vertical(items):
                continue
            items.sort(key=lambda word: word.top)
            piece = []
            for word in items:
                if paper_bright(image, word) >= paper:
                    piece.append(word)
                else:
                    if len(piece) >= 2:
                        runs.append(piece)
                    piece = []
            if len(piece) >= 2:
                runs.append(piece)
        if not runs or len(runs) > most:
            return 0

        for piece in runs:
            chars = sum(len(word.text) for word in piece)
            if chars < least:
                continue
            conf = sum(word.conf * len(word.text)
                       for word in piece) / float(chars)
            box = (max(0, min(w.left for w in piece) - pad),
                   max(0, min(w.top for w in piece) - pad),
                   min(image.width, max(w.left + w.width for w in piece) + pad),
                   min(image.height,
                       max(w.top + w.height for w in piece) + pad))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            got = read_line(image.crop(box), exe, env, tessdata,
                            lang="jpn_vert+jpn", psm=5)
            if not got:
                continue
            got.sort(key=lambda word: word.top)
            text = "".join(word.text for word in got)
            weight = sum(len(word.text) for word in got) or 1
            again = sum(word.conf * len(word.text)
                        for word in got) / float(weight)
            was = "".join(w.text for w in piece)
            if digit_count(text) < digit_count(was):
                continue
            if (again < conf + gain or not has_cjk(text)
                    or len(squeeze(text)) < chars):
                continue
            keep = piece[0]
            keep.text = text
            keep.conf = again
            keep.left, keep.top = box[0] + pad, box[1] + pad
            keep.width = max(1, box[2] - box[0] - pad * 2)
            keep.height = max(1, box[3] - box[1] - pad * 2)
            for extra in piece[1:]:
                words.remove(extra)
            fixed += 1
    finally:
        image.close()
    return fixed


def digit_count(text):
    """その文字列に入っている数字の個数。"""
    return sum(1 for ch in text if ch.isascii() and ch.isdigit())


def reread_weak_lines(words, image_path, exe, env=None, tessdata=None,
                      floor=200.0, gain=0.0, least=3, pad=6, most=400,
                      columns=False):
    """行を 1 本ずつ切り出して読み直す。

    紙面全体を一度に読ませると、まわりの候補に引きずられて 1 行だけ
    大きく崩れることがある。利用者の資料の署名の行での実測
    （tesseract 5.5.3、500dpi）。

    | 読ませ方 | 結果 | 信頼度 |
    |---|---|---|
    | 紙面全体 | `2024` … `月佐藤実`（`年10` が消える） | 31.5 |
    | その行だけ切り出す | `2024年10月佐藤実` | **92** |

    `fix_latin_runs()` と同じ理屈ですが、あちらは語 1 つを切り出すのに
    対し、こちらは**行ごと**切り出します。上の例では消えているのが
    `年`（漢字）と `10`（数字）の両方で、語 1 つでは足りません。

    **既定ではすべての行を読み直します。** 以前は「自信の低い行だけ」に
    絞っていましたが、実測（実物 4 つ、正解語 16 個ずつ）で全部を見る
    ほうが良く、**57/64 が 59/64** になりました。横組みの資料 1 つは
    16/16（全問正解）に届きました。悪くなった資料はありません。

    速さは 4 ページで 149 秒が 187 秒（+25%）。1 ページあたり 10 秒ほど
    増えます。**紙面全体を 1 回読むだけでは、まわりの候補に引きずられた
    読みがそのまま残ります。** 行ごとに読み直せば、その行だけの候補で
    決め直せます。

    行を丸ごと入れ替えるので、悪くする危険があります。次の条件で絞ります。

      ・読み直した結果が gain 以上高いこと（低ければ入れ替えない）
      ・読み直した結果が、元より短くならないこと（字を減らさない）
      ・読み直した結果が漢字・かなを含むこと
      ・横組みの行だけ（縦組みは fill_vertical_gaps が受け持つ）

    floor は「この信頼度未満の行だけを見る」という上限で、既定の 200 は
    実質すべての行を意味します。速さを優先したい場合に下げられるよう
    残してあります。
    """
    from PIL import Image

    # **行としてまとめる前に呼ぶ。** まとめたあとでは遅い。上の署名の行は
    # 「2024」と「月佐藤実」の 2 つに分かれてしまう（間が広く空いている
    # ので、離れた語として切られる）。**消えた `年10` はちょうどその
    # すきまにある**ので、片方だけを切り出しても拾えない。tesseract が
    # 付けた行番号で束ねれば、すきまごと切り出せる。
    lines = {}
    for word in words:
        lines.setdefault(word.line, []).append(word)

    targets = []
    for items in lines.values():
        upright = line_is_vertical(items)
        if upright and not columns:
            continue
        chars = sum(len(word.text) for word in items)
        # floor は既定で 200（＝すべての行を見る）。実測で、自信の低い行に
        # 絞るより全部を見るほうが良かった（57/64 対 59/64、実物 4 つ）。
        # 差し替えるかどうかは、下の条件で決める。
        if chars < least:
            continue
        conf = sum(word.conf * len(word.text) for word in items) / float(chars)
        if conf < floor:
            targets.append((items, conf, chars, upright))
    if not targets or len(targets) > most:
        return 0

    try:
        image = Image.open(image_path)
    except (OSError, ValueError):
        return 0
    fixed = 0
    try:
        for items, conf, chars, upright in targets:
            box = (max(0, min(w.left for w in items) - pad),
                   max(0, min(w.top for w in items) - pad),
                   min(image.width, max(w.left + w.width for w in items) + pad),
                   min(image.height,
                       max(w.top + w.height for w in items) + pad))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            if upright:
                got = read_line(image.crop(box), exe, env, tessdata,
                                lang="jpn_vert+jpn", psm=5)
                got.sort(key=lambda word: word.top)     # 縦は上から下へ読む
            else:
                got = read_line(image.crop(box), exe, env, tessdata)
                got.sort(key=lambda word: word.left)
            if not got:
                continue
            text = "".join(word.text for word in got)
            weight = sum(len(word.text) for word in got) or 1
            again = sum(word.conf * len(word.text)
                        for word in got) / float(weight)
            was = "".join(w.text for w in items)
            # 数字を減らさないこと。縦組みでは、この時点までに縦中横の
            # 数字を直してある（fix_tatechuyoko / fix_stacked_digits）。
            # 縦書き用の言語データは横に寝た数字を読めないので、列ごと
            # 読み直した結果には数字が入っていない。そのまま差し替えると
            # 直した数字を捨ててしまう。
            if digit_count(text) < digit_count(was):
                continue
            if (again < conf + gain or not has_cjk(text)
                    or len(squeeze(text)) < chars):
                continue
            # その行を 1 つの語に差し替える。枠は行を囲む大きさ。
            keep = items[0]
            keep.text = text
            keep.conf = again
            keep.left, keep.top = box[0] + pad, box[1] + pad
            keep.width = max(1, box[2] - box[0] - pad * 2)
            keep.height = max(1, box[3] - box[1] - pad * 2)
            for extra in items[1:]:
                words.remove(extra)
            fixed += 1
    finally:
        image.close()
    return fixed


def read_line(patch, exe, env=None, tessdata=None, lang="jpn", psm=13):
    """切り出した 1 行を読んで、単語の一覧を返す。

    `read_patch()` とは別に要ります。あちらは縦組みのすきま埋め用で、
    **漢字・かなを含まない語を捨てます**。行を読み直すときに数字を
    捨てられては困ります（`2024年10月` の `2024` と `10` が消えます）。

    PSM は 13（生の 1 行として読む）。実測で、同じ行を 3 通りの切り出し
    方で読ませたとき、返る文字はどれも `2024年10月佐藤実` で正しかった
    のに、**PSM 7 では信頼度が 31〜92 と切り出し方で大きく振れ**、
    PSM 13 は 92〜93 で安定しました。信頼度で採否を決めるので、
    振れないほうを使います。
    """
    handle, path = tempfile.mkstemp(prefix="pdf_ocr_line_", suffix=".png")
    os.close(handle)
    try:
        patch.save(path)
        tsv = run_tesseract(exe, [path, "stdout", "-l", lang, "--psm",
                                  str(psm), "tsv"], env=env, tessdata=tessdata)
    except (RuntimeError, OSError):
        return []
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return tsv_words(tsv)


def read_patch(patch, exe, env=None, tessdata=None, lang="jpn_vert", psm=5,
               floor=50.0):
    """切り出した小片を読んで、(文字, 信頼度, 上からの位置, 高さ) を返す。"""
    handle, path = tempfile.mkstemp(prefix="pdf_ocr_gap_", suffix=".png")
    os.close(handle)
    try:
        patch.save(path)
        tsv = run_tesseract(exe, [path, "stdout", "-l", lang, "--psm",
                                  str(psm), "tsv"], env=env, tessdata=tessdata)
    except (RuntimeError, OSError):
        return []
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    found = []
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t",
                            quoting=csv.QUOTE_NONE)
    for row in reader:
        text = clean_text(row.get("text") or "")
        try:
            conf = float(row.get("conf") or -1)
            top = int(row["top"])
            height = int(row["height"])
        except (KeyError, TypeError, ValueError):
            continue
        if not text or conf < floor or not has_cjk(text):
            continue
        found.append((text, conf, top, height))
    return found


def cell_size(number, words, upright=True):
    """その数字が収まるべき 1 文字分の大きさ。

    縦中横は 1 文字分の枠に詰めて組むので、この大きさに収まらない数字は
    「読み違えられた縦中横」ではなく、ふつうの大きさで置かれた数字。

    1 文字分にあたるのは、縦組みなら**列の幅**、横組みなら**行の高さ**。
    どちらも、その数字と同じ列（行）にある語の中央値で測る。1 語ごとの枠は
    tesseract が上下左右に膨らませるので、1 つでは当てにならない。
    """
    if upright:
        low, high, own = number.left, number.left + number.width, number.width
        span = lambda word: (word.left, word.left + word.width)   # noqa: E731
        size = lambda word: word.width                            # noqa: E731
    else:
        low, high, own = number.top, number.top + number.height, number.height
        span = lambda word: (word.top, word.top + word.height)    # noqa: E731
        size = lambda word: word.height                           # noqa: E731

    sizes = []
    for word in words:
        start, stop = span(word)
        overlap = min(stop, high) - max(start, low)
        if overlap > min(size(word), own) * 0.5:
            sizes.append(size(word))
    if not sizes:
        return own
    sizes.sort()
    middle = len(sizes) // 2
    if len(sizes) % 2:
        return float(sizes[middle])
    return (sizes[middle - 1] + sizes[middle]) / 2.0


def prefer_columns(columns, rivals, overlap=0.5, margin=0.0):
    """縦組みの列を、2 通りの読みのうち自信のあるほうに差し替える。

    横書きのパスで縦組みを探させるのをやめた（`upright_only()`）ぶん、
    **縦組みの列の読みが 1 通りだけになりました**。実測（利用者の縦組みの
    資料 `1ca57185-____1.pdf`、500dpi）で、横書きのパスはそれまで
    68 本の列を縦組みとして読んでいて、その中には縦書きのパスより
    上手く読めているものがありました。

    そこで、横書きの言語データのまま縦組みを探させる読みをもう 1 回
    足し、列ごとに信頼度の高いほうを採る、という案を試しました。

    **駄目でした。呼んでいません。** 実測（4 つの実資料、正解語 84 個、
    tesseract 5.5.1）。

    | 読み方 | 合計 |
    |---|---|
    | 3 回目 なし | 74/84 |
    | 3 回目 あり（信頼度が上なら差し替え） | **74/84** |
    | 3 回目 あり（8 ポイント以上の差で差し替え） | 74/84 |

    差し引きゼロです。中身も入れ替わるだけでした（`moto2.pdf` で
    `43年前の基準` が戻る代わりに `耐力壁の配置バランス` が落ちる）。
    8 ポイントの差を要求すると、そもそも差し替えが起きません。
    tesseract を 1 ページにつきもう 1 回呼ぶので、**読み取りの時間が
    5 割増える**のに、得るものがありません。

    **信頼度は、どちらの読みが正しいかの目安になりません。**これは
    1 文字ごとの読み直し・列ごとの読み直しでも同じ結論でした。
    """
    picked = list(columns)
    for rival in rivals:
        if (rival.angle != 90 or len(rival.text) <= 1
                or not has_cjk(rival.text)):
            continue
        best, score = None, overlap
        for index, word in enumerate(picked):
            if word.angle != 90:
                continue
            share = min(overlap_ratio(word, rival), overlap_ratio(rival, word))
            if share >= score:
                best, score = index, share
        if best is None:
            continue
        # 縦中横の直しで拾った数字を、数字の無い読みに戻さない
        if digit_count(rival.text) < digit_count(picked[best].text):
            continue
        if rival.conf > picked[best].conf + margin:
            picked[best] = rival
    return picked


def combine_passes(horizontal, vertical, overlap=0.5, page_width=0):
    """横書きで読んだ結果に、縦書きで読んだ結果の縦組みだけを差し込む。

    縦組みの所は、横書きとして読むと 1 文字ずつばらばらの読み違いになる。
    2 回目（縦書き設定）で縦に読めた行を採用し、その場所と重なっていた
    1 回目の結果は捨てる。捨てないと同じ場所に二重の文字が残る。

    ただし縦組みの中の数字は横向きに組まれることが多く（縦中横）、
    縦書きの設定では読めない。重なっていても、数字や英字だけで、まだ
    出ていない文字列なら残す。
    """
    columns = pick_columns(vertical, horizontal)
    if not columns:
        return horizontal

    column_text = squeeze("".join(word.text for word in columns))
    # ページ全体が縦組みなら、縦組みを先に置き（読む順がそうなる）、
    # 横書きで拾った絵の模様（英字の断片）は捨てる。
    # 「横書きより多いか」で決めていたが、縦組みの本の実測が 0.98 で、
    # わずかに届かず順序が入れ替わった。縦組みのページでも図表の横書きが
    # 同じくらいの量あるため、半分を境にする（実測は 0.98 と 0.16 で、
    # どちらからも遠い）。
    vertical_page = (cjk_count(column_text)
                     >= cjk_count("".join(w.text for w in horizontal)) * 0.5)

    kept = []
    found = list(columns)
    for word in horizontal:
        digits = is_number(word.text)
        # 数字は縦組みの列の中に、横向きのまま入る（縦中横）。
        # 列の並びに混ぜておくと、コピーしたときも列の途中に収まる。
        if (digits and squeeze(word.text) not in column_text
                and any(same_column(word, column) for column in found)):
            columns.append(word)
            continue
        covered = max((overlap_ratio(word, column) for column in found),
                      default=0.0)
        if covered >= overlap:
            continue                   # 縦組みを横書きとして読み違えたもの
        if vertical_page and not has_cjk(word.text) and not digits:
            continue                   # 絵を文字と読み違えたもの
        kept.append(word)

    # 置く順番＝コピーしたときに並ぶ順番になるビューアがあるので、
    # 読む順に並べる。縦組みは右の列から、横組みは上の行から。
    columns = sort_columns(columns)
    kept = sort_reading_order(kept, page_width)
    return columns + kept if vertical_page else kept + columns


def sort_reading_order(words, page_width=0):
    """横組みを、人が読む順（段ごとに、上から下へ）に並べ替える。

    上から下へ（同じ高さなら左から右へ）だけで並べると、二段組みや
    見開きのページで左の段の 1 行目・右の段の 1 行目・左の段の 2 行目…
    と交互になる。コピーすると文章が互い違いになって読めない。

    tesseract の段組みの判定は当てにできない。同じ紙面でも、描き出す
    解像度が違うだけで結果が変わる（150dpi では左右を別の block に
    分けたが、300dpi では 1 つの block にまとめ、1 行が左右にまたがった）。
    そこで、こちらで段の切れ目を探す。

    紙面のどの高さにも文字が無い縦の帯＝段の切れ目とみなす。行と行の
    すき間や、文の途中の空白では、他の行がその位置を覆うので残らない。
    """
    # 縦組みは右の列から読むので、この並べ替えは当てはまらない。
    # 列の並べ替えは sort_columns が受け持つ。
    flat = [word for word in words if word.angle not in (90, 270)]
    if len(flat) < 2 or len(flat) * 2 < len(words):
        return list(words)
    standing = [word for word in words if word.angle in (90, 270)]

    heights = sorted(word.height for word in flat)
    line_height = heights[len(heights) // 2]
    if not page_width:
        page_width = max(word.left + word.width for word in flat)
    # 段の切れ目は、1 文字分よりはっきり広い
    least = max(line_height * 1.5, page_width * 0.02)

    spans = []
    for word in sorted(flat, key=lambda w: w.left):
        left, right = word.left, word.left + word.width
        if spans and left <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], right)
        else:
            spans.append([left, right])

    edges = [spans[i][1] + (spans[i + 1][0] - spans[i][1]) / 2.0
             for i in range(len(spans) - 1)
             if spans[i + 1][0] - spans[i][1] >= least]
    if not edges:
        return by_rows(flat, line_height) + standing

    def band(word):
        middle = word.left + word.width / 2.0
        for index, edge in enumerate(edges):
            if middle < edge:
                return index
        return len(edges)

    # 切れ目の左右に文字がわずかしか無いときは、段ではなく余白や
    # ノンブル。段として扱うと、かえって並びが崩れる。
    counts = {}
    for word in flat:
        counts[band(word)] = counts.get(band(word), 0) + 1
    if min(counts.values()) < max(2, len(flat) * 0.1):
        return by_rows(flat, line_height) + standing

    ordered = []
    for index in sorted(counts):
        ordered.extend(by_rows([w for w in flat if band(w) == index],
                               line_height))
    return ordered + standing


def by_rows(words, line_height, share=0.6):
    """同じ行のものをまとめてから、行ごとに左から右へ並べる。

    枠の上端は同じ行でも数ピクセルずれる。上端の値だけで並べると、
    1 行の中の語順が入れ替わって「木造住宅に「なぜ、と思われるかも
    しれません。構造」のようになる。
    """
    rows = []
    for word in sorted(words, key=lambda w: (w.top, w.left)):
        if rows and word.top - rows[-1][0] <= line_height * share:
            rows[-1][1].append(word)
        else:
            rows.append((word.top, [word]))
    ordered = []
    for _top, row in rows:
        ordered.extend(sorted(row, key=lambda w: w.left))
    return ordered


def sort_columns(columns):
    """縦組みを読む順（右の列から、列の中は上から）に並べ替える。

    同じ列でも枠の左端は少しずつ違うので、まず「同じ縦線上のかたまり」
    にまとめてから、かたまりごとに右から並べる。
    """
    if not columns:
        return columns

    def center(word):
        return word.left + word.width / 2.0

    bands = []
    for word in sorted(columns, key=center, reverse=True):
        for band in bands:
            if abs(center(word) - band["center"]) <= band["width"] * 0.6:
                band["words"].append(word)
                break
        else:
            bands.append({"center": center(word), "width": max(word.width, 1),
                          "words": [word]})

    ordered = []
    for band in bands:
        ordered.extend(sorted(band["words"], key=lambda w: w.top))
    return ordered


def is_number(text):
    """縦中横で出てくる数字のかたまりか（1950、23.5 など）。"""
    body = squeeze(text)
    if not body:
        return False
    digits = sum(1 for ch in body if ch.isdigit())
    return digits and digits >= len(body) * 0.5


def pick_columns(vertical, horizontal=(), floor=75.0, margin=8.0, share=0.08):
    """縦書きで読んだ結果から、本当に縦組みだった行だけを選ぶ。

    縦書きの設定は、紙面のどこを読ませても縦組みとして読んでしまう。
    横組みの本文も、絵や罫線も、それらしい漢字の列に化ける。長さや形で
    は本物と見分けがつかないので、同じ場所を横書きで読んだ結果と
    確からしさを比べる。横書きのほうが自信を持って読めている場所は、
    もともと横組み（か、そもそも文字ではない）とみなして捨てる。

    どちらも読んでいない場所は比べようがないので、縦書き側がよほど
    自信を持って読めたものだけを残す。

    縦組みの列は、途中に横向きの数字が入ると分断され、残りが 1 文字だけに
    なることがある（「…できたのが 1950 年、」の「年」）。そういう 1 文字は、
    残った列の続きに見えるものだけ拾う。
    """
    columns = []
    for word in vertical:
        if word.angle != 90 or len(word.text) <= 1 or not has_cjk(word.text):
            continue
        rival, covered = rival_conf(word, horizontal)
        if covered < 0.2:
            if word.conf >= floor:
                columns.append(word)
        elif word.conf > rival + margin:
            # 差が僅かなら横書きを採る。横組みの本文を縦に読み違えた列は、
            # 信頼度が本物の横書きとほとんど並ぶ（実測で 94.5 対 93.5）。
            # 1 ポイントの差で縦組みと認めると、そこに 1 文字の読み違いが
            # 芋づる式にぶら下がり、重なった正しい横書きまで消える。
            columns.append(word)
    if not columns:
        return columns

    # 紙面のほとんどが横組みなら、わずかに残った「列」も読み違いとみなす。
    # 実測での割合は、横書きだけの紙面 4.6%・見出しだけ縦組み 16.1%・
    # 縦組みの本 104.6% で、はっきり分かれた。
    if horizontal:
        flat = cjk_count("".join(word.text for word in horizontal))
        standing = cjk_count("".join(word.text for word in columns))
        if flat and standing < flat * share:
            return []

    extras = []
    for word in vertical:
        if word.angle != 90 or len(word.text) > 1 or word.conf < floor:
            continue          # 1 文字は当てにならない。はっきり読めたものだけ
        if any(same_column(word, column) for column in columns):
            extras.append(word)
    return columns + extras


def rival_conf(column, horizontal):
    """その列の場所を、横書きの読み取りがどれだけ確かに読めているか。

    戻り値は (確からしさ, 列のうち横書きに覆われている割合)。
    重なった面積で重みを付ける。
    """
    area = float(column.width * column.height)
    if area <= 0:
        return 0.0, 0.0
    weighted = 0.0
    total = 0.0
    for word in horizontal:
        share = overlap_ratio(column, word) * area
        if share > 0:
            weighted += word.conf * share
            total += share
    if total <= 0:
        return 0.0, 0.0
    return weighted / total, min(1.0, total / area)


def same_column(word, column):
    """word が column と同じ列の続きに見えるか。"""
    center = word.left + word.width / 2.0
    if not (column.left - column.width * 0.5 <= center
            <= column.left + column.width * 1.5):
        return False
    gap = max(column.top - (word.top + word.height),
              word.top - (column.top + column.height))
    return gap <= max(column.width, word.height) * 3


def squeeze(text):
    return "".join(text.split())


def cjk_count(text):
    return sum(1 for ch in text if has_cjk(ch))


def overlap_ratio(word, other):
    """word の面積のうち、other と重なっている割合。"""
    left = max(word.left, other.left)
    top = max(word.top, other.top)
    right = min(word.left + word.width, other.left + other.width)
    bottom = min(word.top + word.height, other.top + other.height)
    if right <= left or bottom <= top:
        return 0.0
    area = float(word.width * word.height)
    if area <= 0:
        return 0.0
    return (right - left) * (bottom - top) / area


def rotate_image(image_path, rotation):
    """画像を時計回りに rotation 度だけ回して保存し直す。"""
    from PIL import Image

    root, ext = os.path.splitext(image_path)
    out_path = "%s_r%d%s" % (root, rotation, ext)
    with Image.open(image_path) as image:
        rotated = image.rotate(-rotation, expand=True)
    try:
        rotated.save(out_path)
        return out_path, rotated.size
    finally:
        rotated.close()


def tsv_words(tsv_text):
    """tesseract の TSV を、信頼度で切らずに全部そのまま単語にする。

    足切りは keep_holes() が行ごとに判断する。ここで先に落とすと、
    行の中で判断する材料そのものが無くなる。
    """
    words = []
    reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t",
                            quoting=csv.QUOTE_NONE)
    for row in reader:
        try:
            conf = float(row.get("conf") or -1)
        except ValueError:
            continue
        if conf < 0:
            continue           # 語ではなく、行や段落の区切りを表す行
        text = clean_text(row.get("text") or "")
        if not text:
            continue
        try:
            left = int(row["left"])
            top = int(row["top"])
            width = int(row["width"])
            height = int(row["height"])
        except (KeyError, TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        # 向き（縦書きかどうか）は行としてまとめるときに決める
        word = Word(text, left, top, width, height, conf=conf)
        word.line = (row.get("block_num"), row.get("par_num"),
                     row.get("line_num"))
        words.append(word)
    return words


def keep_holes(words, min_conf, floor=80.0, least=2):
    """自信のある字に挟まれた、自信のない字を捨てずに残す。

    tesseract は、正しく読んだ字にも信頼度 0 を付けることがある。実測
    （利用者の資料、500dpi）。

    | 正しい字 | 信頼度 | 捨てた結果 |
    |---|---|---|
    | 構造塾 の 塾 | 0.0 | 「構造」をご活用ください |
    | 地盤補強 の 盤 | 0.0 | 地補強工事業者 |
    | 震災による被害 の 震 | 0.0 | 災による被害 |
    | 言葉、数値が の 、数値 | 0.0 | 言葉が難しい |
    | 昭和25年 の 25 | 10 未満 | (昭和年) |

    **落ちた字は前後とつながって、別の読める語になる。** 誤読より
    始末が悪い。字が化けていれば見て気付けるが、消えた字は気付けない。

    かといって足切りをやめると、罫線やイラストを読み違えた文字列が
    大量に混ざる（同じ資料の図の領域で、罫線を「本」と読んだものが
    24 個続いた）。そこで、行として見て分ける。

    - その行の、自信のある字の平均信頼度が floor 以上（本文の行は
      実測 81〜95、図の領域のごみは 44〜72 だった）
    - 自信のある字が least 個以上ある
    - 拾う字が、その行の自信のある字に前後を挟まれている
    - 拾う字が、その行の幅からはみ出していない（列の横に離れた字まで
      拾うと、行の位置が動いて読む順が変わった）

    ごみは行の端に出るか、行ごとごみになる。挟まれた穴は本文にしか
    空かない。
    """
    lines = {}
    for word in words:
        lines.setdefault(word.line, []).append(word)

    spare = set()
    for items in lines.values():
        sure = [word for word in items if word.conf >= min_conf]
        chars = sum(len(word.text) for word in sure)
        if len(sure) < least or not chars:
            continue
        mean = sum(word.conf * len(word.text) for word in sure) / float(chars)
        if mean < floor:
            continue
        vertical = line_is_vertical(sure)
        along = (lambda w: w.top) if vertical else (lambda w: w.left)
        across = (lambda w: w.left) if vertical else (lambda w: w.top)
        thick = (lambda w: w.width) if vertical else (lambda w: w.height)
        first = min(along(word) for word in sure)
        last = max(along(word) for word in sure)
        near = min(across(word) for word in sure)
        far = max(across(word) + thick(word) for word in sure)
        for word in items:
            if word.conf >= min_conf:
                continue
            middle = across(word) + thick(word) // 2
            if first < along(word) < last and near <= middle <= far:
                spare.add(id(word))

    return [word for word in words
            if word.conf >= min_conf or id(word) in spare]


def parse_tsv(tsv_text, min_conf, rescue=True):
    """tesseract の TSV から、意味のある単語だけを取り出す。"""
    words = tsv_words(tsv_text)
    if rescue and min_conf > 0:
        return keep_holes(words, min_conf)
    return [word for word in words if word.conf >= min_conf]


def merge_lines(words, split_gap=1.5, space_gap=0.15):
    """同じ行の単語をつないで、1 本の文字列にまとめる。

    tesseract は 1 行を単語ごとに区切って返す。それをそのまま別々の
    文字列として置くと、単語ごとに文字の大きさとベースラインがずれ、
    ビューアが「別の行」と判断してしまう。その結果、選択して貼り付けると
    「建築」と「物省エネ法（概要）」のように分断され、通しでは検索も
    できなくなる。行としてつないでおけば、選択も検索も一続きになる。

    離れた単語（表の別の欄など）は split_gap を境につながない。
    """
    groups = {}
    order = []
    for word in words:
        if word.line not in groups:
            groups[word.line] = []
            order.append(word.line)
        groups[word.line].append(word)

    merged = []

    def flush(run, vertical):
        run = trim_latin(run) if vertical else run
        if run:
            merged.append(join_words(run, vertical, space_gap))

    for key in order:
        items = groups[key]
        vertical = line_is_vertical(items)
        items.sort(key=lambda w: w.top if vertical else w.left)
        run = [items[0]]
        for previous, current in zip(items, items[1:]):
            gap = word_gap(previous, current, vertical)
            size = min(word_size(previous, vertical), word_size(current, vertical))
            if gap > size * split_gap:
                flush(run, vertical)
                run = [current]
            else:
                run.append(current)
        flush(run, vertical)
    return merged


def trim_latin(run):
    """縦組みの行の前後に付いた、英字だけの断片を落とす。

    縦組みの列の上や下にイラストがあると、その模様が「St」「KHOY」の
    ような英字に読まれ、同じ行として本文につながってしまう。つながると
    見出しの先頭がずれ、コピーしたときにも余計な字が混じる。
    縦に組まれた日本語の中に、英単語が縦向きに現れることはまずないので、
    行の端にある英字だけの断片は落とす。間に挟まったものは残す
    （型番などの可能性があるため）。
    """
    start, end = 0, len(run)
    while start < end and is_latin(run[start].text):
        start += 1
    while end > start and is_latin(run[end - 1].text):
        end -= 1
    return run[start:end]


def is_latin(text):
    body = squeeze(text)
    return bool(body) and all("a" <= ch.lower() <= "z" for ch in body)


def line_is_vertical(items):
    """その行が縦書き（上から下へ読む）かどうかを、行全体の形で決める。

    1 文字ずつ見ると正方形に近くて判断できないので、行の外形で見る。
    """
    left = min(w.left for w in items)
    top = min(w.top for w in items)
    width = max(w.left + w.width for w in items) - left
    height = max(w.top + w.height for w in items) - top
    if height <= width * 1.5:
        return False
    return has_cjk("".join(w.text for w in items))


def word_gap(previous, current, vertical):
    if vertical:
        return current.top - (previous.top + previous.height)
    return current.left - (previous.left + previous.width)


def word_size(word, vertical):
    """文字の大きさ（読む向きに対する高さ）。"""
    return max(word.width if vertical else word.height, 1)


def join_words(run, vertical, space_gap):
    """1 本につないだ Word を作る。枠は全体を囲む大きさにする。"""
    text = run[0].text
    for previous, current in zip(run, run[1:]):
        gap = word_gap(previous, current, vertical)
        size = min(word_size(previous, vertical), word_size(current, vertical))
        # 日本語どうしは詰める。詰めておかないと通しで検索できない。
        if (gap > size * space_gap and not has_cjk(previous.text[-1])
                and not has_cjk(current.text[0])):
            text += " "
        text += current.text

    left = min(w.left for w in run)
    top = min(w.top for w in run)
    right = max(w.left + w.width for w in run)
    bottom = max(w.top + w.height for w in run)
    # 確からしさは文字数で重みを付ける（短い断片に引きずられないように）
    weight = sum(len(w.text) for w in run) or 1
    conf = sum(w.conf * len(w.text) for w in run) / float(weight)
    # 年月日の数字が丸数字に化けたものを、ここで戻す。前後の字を見て
    # 決めるので、語ごとではなく 1 本につないでから直す
    text = fix_open_bracket(uncircle_numbers(text))
    return Word(text, left, top, right - left, bottom - top,
                90 if vertical else 0, conf=conf)


def clean_text(text):
    """PDF に書けない制御文字を落とす。"""
    text = text.strip()
    if not text:
        return ""
    return "".join(ch for ch in text
                   if ch == " " or unicodedata.category(ch)[0] != "C")


def fix_open_bracket(text):
    """かぎかっこの始まりが「`」に化けたものを、「 に戻す。

    精度重視版の言語データにすると、開きのかぎかっこ 「 が
    バッククォート ` として返ってくることがある。実際の紙面では
    **17 個すべてがこれ**で、閉じの 」 は 17 個とも正しく、正しい 「 は
    1 つも無かった。つまり取りこぼしではなく、字の種類だけを一貫して
    間違えている。

        木造住宅の`構造」について   →  木造住宅の「構造」について

    日本語の本文にバッククォートが出てくることはまずないが、プログラムの
    コードを載せた資料では出てくる。そこで、**すぐ後ろが漢字・かなの
    ときだけ**直す。実際の紙面の 17 個はすべてこれに当てはまった。
    """
    mark = "`"
    if mark not in text:
        return text
    out = []
    length = len(text)
    for index, ch in enumerate(text):
        if ch == mark and index + 1 < length and has_cjk(text[index + 1]):
            out.append("\u300c")
        else:
            out.append(ch)
    return "".join(out)


def uncircle_numbers(text):
    """年月日の数字が丸数字に化けたものを、ふつうの数字に戻す。

    箇条書きに ①②③ が使われている紙面では、本文の数字まで丸数字として
    読まれることがある。実際の紙面（精度重視版の言語データ）ではこうなった。

        2025年4月   →  ②0②⑤年④月
        2024年10月  →  ⑳②④年①0月

    形は正しく取れていて、字の種類だけを間違えている（②=2、⑤=5、
    ⑳=20、④=4 と、4 か所すべて数字として正しい）。そこで丸数字を数字に
    直す。

    ただし箇条書きの ①②③ まで数字にしてはいけない。この紙面には
    「①構造の本を読んでも理解できない」という行があり、本文にも
    「さらに、①の構造の本を…」と出てくる。そこで、次のどちらかに
    当てはまる丸数字だけを直す。

      ・ふつうの数字と地続きに並んでいる（②0②⑤ の ② や、①0 の ①）
      ・すぐ後ろが 年・月・日 である（④月 の ④）

    箇条書きの ① は、後ろが「構」や「の」なので触らない。
    """
    if not any(ch in CIRCLED_DIGITS for ch in text):
        return text

    def plain_digit(ch):
        # "①".isdigit() は True になるので、ASCII の数字だけを見る
        return ch.isascii() and ch.isdigit()

    def digit_like(ch):
        return plain_digit(ch) or ch in CIRCLED_DIGITS

    out = []
    length = len(text)
    for index, ch in enumerate(text):
        if ch not in CIRCLED_DIGITS:
            out.append(ch)
            continue
        # 前後に digit_like が続くひとかたまりを取り出す
        start = index
        while start > 0 and digit_like(text[start - 1]):
            start -= 1
        stop = index + 1
        while stop < length and digit_like(text[stop]):
            stop += 1
        run = text[start:stop]
        after = text[stop] if stop < length else ""
        if any(plain_digit(c) for c in run) or (after and after in "年月日"):
            out.append(CIRCLED_DIGITS[ch])
        else:
            out.append(ch)
    return "".join(out)


def has_cjk(text):
    for ch in text:
        code = ord(ch)
        if (0x3040 <= code <= 0x30FF or 0x3400 <= code <= 0x9FFF
                or 0xF900 <= code <= 0xFAFF or 0xFF00 <= code <= 0xFF60):
            return True
    return False


# --------------------------------------------------------------------------
# 透明テキスト層
# --------------------------------------------------------------------------

def build_overlay(words, page_w, page_h, image_w, image_h, font_name):
    """見えない文字だけの 1 ページ PDF を作って bytes で返す。

    page_w / page_h は「表示されている向き」でのページの大きさ（ポイント）。
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    kx = page_w / float(image_w)
    ky = page_h / float(image_h)

    for word in words:
        x = word.left * kx
        box_w = word.width * kx
        box_h = word.height * ky
        y = page_h - (word.top + word.height) * ky
        if box_w <= 0.1 or box_h <= 0.1:
            continue

        angle = word.angle % 360
        sideways = angle in (90, 270)
        # 文字の高さ方向＝枠の短辺、文字の進む方向＝枠の長辺
        size = max(box_w if sideways else box_h, 0.5)
        run_length = box_h if sideways else box_w
        width = pdfmetrics.stringWidth(word.text, font_name, size)
        if width <= 0:
            continue
        scale = max(1.0, min(1000.0, 100.0 * run_length / width))

        # ベースラインを枠の中に収める（文字の下に出る分を DESCENT とみなす）
        descent = size * 0.12
        c.saveState()
        if angle == 90:            # 上から下へ
            c.translate(x + descent, y + box_h)
            c.rotate(-90)
        elif angle == 180:         # 上下逆
            c.translate(x + box_w, y + size - descent)
            c.rotate(180)
        elif angle == 270:         # 下から上へ
            c.translate(x + box_w - descent, y)
            c.rotate(90)
        else:                      # 左から右へ
            c.translate(x, y + descent)
        text_obj = c.beginText(0, 0)
        text_obj.setTextRenderMode(3)  # 描画しない（＝見えない文字）
        text_obj.setFont(font_name, size)
        text_obj.setHorizScale(scale)
        text_obj.textLine(word.text)
        c.drawText(text_obj)
        c.restoreState()

    c.showPage()
    c.save()
    return buf.getvalue()


def overlay_matrix(rotation, width, height):
    """表示されている向きの座標 → ページ本来の座標 に直す行列。

    /Rotate が付いたページは、画像に描画した向きと PDF の座標系がずれる。
    width / height はページ本来（回転前）の大きさ。
    """
    if rotation == 90:
        return (0, 1, -1, 0, width, 0)
    if rotation == 180:
        return (-1, 0, 0, -1, width, height)
    if rotation == 270:
        return (0, -1, 1, 0, 0, height)
    return (1, 0, 0, 1, 0, 0)


def count_text_chars(document):
    """元の PDF の各ページに入っている文字数を数える。

    重ね始める前に一度だけ数える。処理の途中で数えると、自分が重ねた
    文字まで「元から入っていた文字」として数えてしまう。
    """
    counts = []
    for index in range(len(document)):
        page = document[index]
        try:
            textpage = page.get_textpage()
            text = textpage.get_text_bounded()
            counts.append(len("".join(text.split())))
        except Exception:                               # noqa: BLE001
            counts.append(0)
        finally:
            page.close()
    return counts


# --------------------------------------------------------------------------
# 本体
# --------------------------------------------------------------------------

def ocr_pdf(src_path, dst_path, settings, exe, font_name, force, quiet=False,
            retext=False, on_progress=None, cancel=None):
    """on_progress(current, total, message) は、静かモードでも呼ばれる
    （GUI の進捗バー用）。cancel() が True を返すと、そこまでのページで
    打ち切って保存する（キャンセル）。
    """
    import pypdfium2 as pdfium
    from pypdf import PdfReader, PdfWriter, Transformation

    dpi = as_int(settings["DPI"], 300)
    max_dpi = as_int(settings["MAXDPI"], 600)
    max_pixels = as_int(settings["MAXPIXELS"], 40000000)
    grayscale = as_bool(settings["GRAYSCALE"])
    skip_text_pages = as_bool(settings["SKIPTEXTPAGES"]) and not (force or retext)
    jobs = as_int(settings["JOBS"], 0) or min(4, (os.cpu_count() or 1))
    env = ocr_env(jobs)
    # 縦組みを読むときだけ、色の付いたインクを濃く残した画像も用意する
    wants_ink = grayscale and ("_vert" in settings["LANG"]
                               or "_vert" in settings.get("LANG2", ""))

    # PP-OCRv5・tesseract（速度重視）を使う設定なら、ページごとに何度も
    # 呼ばれる前にここで一度だけ用意する（模型の読み込みは重く、確認
    # ダイアログも 1 回で済ませたい）。用意できなければ普段の tesseract
    # （精度重視）に戻す。
    prepare_engines(settings, exe, quiet)

    reader = PdfReader(src_path)
    if reader.is_encrypted:
        try:
            opened = reader.decrypt("")
        except Exception:                               # noqa: BLE001
            opened = 0
        if not opened:
            raise RuntimeError("パスワード付きの PDF は開けません。")

    # しおり・注釈・文書情報ごと引き継ぐ（ページだけ足すと落ちてしまう）
    writer = PdfWriter(clone_from=reader)

    # 内容ストリームを共有しているページは、重ねる前に切り離しておく
    shared = unshare_page_contents(writer)
    if shared and not quiet:
        sys.stdout.write("  %d ページが内容を共有していたので切り離しました\n"
                         % shared)

    if retext:
        # 元から入っている見えない文字を消してから入れ直す。
        # 二重のテキスト層が残ると、選択も検索もおかしくなるため。
        pages_cleared, removed = remove_existing_text(writer)
        if not quiet:
            if removed:
                sys.stdout.write("  元の見えない文字を %d ページ分（%d か所）"
                                 "消しました\n" % (pages_cleared, removed))
            else:
                sys.stdout.write("  元の見えない文字はありませんでした\n")

    document = pdfium.PdfDocument(src_path)
    total = len(writer.pages)
    done_pages = 0
    word_count = 0
    skipped = 0

    # ページ番号やハンコだけの薄いテキスト層は「文字入り」と見なさない。
    # ここで元の文字数を先に数えておく（重ね始めたあとでは数えられない）。
    text_chars = count_text_chars(document) if skip_text_pages else [0] * total
    text_page_chars = as_int(settings["TEXTPAGECHARS"], 100)

    try:
        with tempfile.TemporaryDirectory(prefix="pdf_ocr_") as tmpdir:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                for start in range(0, total, jobs):
                    if cancel and cancel():
                        break
                    chunk = list(range(start, min(start + jobs, total)))
                    tasks = []
                    for index in chunk:
                        if text_chars[index] >= text_page_chars:
                            skipped += 1
                            note = "すでに %d 字入っているため飛ばす" % text_chars[index]
                            if not quiet:
                                report(index + 1, total, note)
                            if on_progress:
                                on_progress(index + 1, total, note)
                            continue
                        image_path = os.path.join(tmpdir, "p%05d.png" % index)
                        ink_path = ink_path_for(image_path) if wants_ink else None
                        used_dpi = page_dpi(document, index, dpi, max_dpi)
                        size = render_page(document, index, used_dpi, grayscale,
                                           image_path, max_pixels, ink_path)
                        tasks.append((index, image_path, size, used_dpi))

                    futures = [
                        (index, size, used_dpi,
                         pool.submit(ocr_image, exe, image_path, size,
                                     settings, env,
                                     ink_path_for(image_path) if wants_ink
                                     else None))
                        for index, image_path, size, used_dpi in tasks
                    ]
                    for index, size, used_dpi, future in futures:
                        words, rotation = future.result()
                        word_count += len(words)
                        if words:
                            merge_overlay(writer.pages[index], words, size,
                                          font_name, PdfReader, Transformation)
                        done_pages += 1
                        note = "%d 個の文字列を認識" % len(words)
                        if used_dpi != dpi:
                            note += "（画像が細かいので %d dpi）" % used_dpi
                        if rotation:
                            note += "（%d 度回して読み取り）" % rotation
                        if not quiet:
                            report(index + 1, total, note)
                        if on_progress:
                            on_progress(index + 1, total, note)
                    for _index, image_path, _size, _dpi in tasks:
                        remove_page_images(image_path)
    finally:
        document.close()

    if skipped and not quiet:
        sys.stdout.write(
            "  ※ %d ページは元から文字が入っていたので飛ばしました。\n"
            "     その文字が古い OCR のもので検索・選択が乱れる場合は、\n"
            "     PDF文字認識.bat をダブルクリックして [3] を選んでください。\n"
            % skipped)

    # 透明テキストはページごとに作るので、同じフォントが何度も埋め込まれる。
    # 中身が同じものは 1 つにまとめてからファイルにする。
    if hasattr(writer, "compress_identical_objects"):
        writer.compress_identical_objects()
    writer.add_metadata({"/Producer": "pdf_ocr.py + Tesseract OCR"})
    # 途中で失敗しても、壊れた PDF を出力先に残さない
    tmp_out = dst_path + ".tmp"
    try:
        with open(tmp_out, "wb") as f:
            writer.write(f)
        os.replace(tmp_out, dst_path)
    except Exception:                                   # noqa: BLE001
        try:
            os.remove(tmp_out)
        except OSError:
            pass
        raise
    return done_pages, word_count


INVISIBLE_MODES = (3, 7)          # 描画しないテキスト表示モード
SHOW_TEXT_OPS = (b"Tj", b"TJ", b"'", b'"')


def filter_invisible_ops(operations):
    """命令列から見えない文字の表示だけを抜いて、(残った命令, 消した数)。"""
    from pypdf.generic import FloatObject

    kept = []
    removed = 0
    mode = 0
    stack = []
    for operands, operator in operations:
        if operator == b"q":
            stack.append(mode)
        elif operator == b"Q":
            mode = stack.pop() if stack else 0
        elif operator == b"Tr" and operands:
            try:
                mode = int(operands[0])
            except (TypeError, ValueError):
                mode = 0
        elif operator in SHOW_TEXT_OPS and mode in INVISIBLE_MODES:
            removed += 1
            # 文字を消しても、後ろの文字の位置がずれないように
            # 改行や文字間隔の指定だけは残す
            if operator == b"'":
                kept.append(([], b"T*"))
            elif operator == b'"' and len(operands) >= 2:
                kept.append(([FloatObject(operands[0])], b"Tw"))
                kept.append(([FloatObject(operands[1])], b"Tc"))
                kept.append(([], b"T*"))
            continue
        kept.append((operands, operator))
    return kept, removed


def remove_invisible_text(page):
    """ページに入っている「見えない文字」だけを消す。

    昔の OCR ソフトが付けたテキスト層が残っていると、新しく重ねた文字と
    二重になって、選択も検索も乱れる。消すのは見えない文字だけなので、
    ワープロで作った本文のような「見える文字」はそのまま残る。

    戻り値は消した文字表示命令の数。
    """
    from pypdf.generic import ContentStream

    removed = 0
    contents = page.get_contents()
    if contents is not None:
        stream = ContentStream(contents, page.pdf)
        kept, count = filter_invisible_ops(stream.operations)
        if count:
            stream.operations = kept
            page.replace_contents(stream)
            removed += count

    # 紙面まるごとが Form XObject に包まれている PDF がある（ページを
    # 抜き出すソフトの出力に多い）。中の文字も消さないと、消したつもりで
    # 二重のテキスト層が残ってしまう。
    removed += remove_invisible_in_forms(page.get("/Resources"), page.pdf, set())
    return removed


def remove_invisible_in_forms(resources, pdf, seen, depth=0):
    """Form XObject の中に入っている見えない文字を消す（入れ子もたどる）。"""
    from pypdf.generic import (ContentStream, DecodedStreamObject,
                               IndirectObject, NameObject)

    if resources is None or depth > 8:
        return 0
    xobjects = resources.get_object().get("/XObject")
    if xobjects is None:
        return 0
    xobjects = xobjects.get_object()

    removed = 0
    for name in list(xobjects.keys()):
        reference = xobjects.raw_get(name)
        form = reference.get_object()
        if form.get("/Subtype") != "/Form":
            continue
        mark = ((reference.idnum, reference.generation)
                if isinstance(reference, IndirectObject) else id(form))
        if mark in seen:
            continue
        seen.add(mark)

        removed += remove_invisible_in_forms(form.get("/Resources"), pdf,
                                             seen, depth + 1)
        stream = ContentStream(form, pdf)
        kept, count = filter_invisible_ops(stream.operations)
        if not count:
            continue
        stream.operations = kept

        # 元の Form は他のページも指しているかもしれないので、書き換えず
        # 中身を入れ替えた写しを作り、このページの参照だけを差し替える。
        replacement = DecodedStreamObject()
        for key, value in form.items():
            if key not in ("/Length", "/Filter", "/DecodeParms"):
                replacement[NameObject(key)] = value
        replacement.set_data(stream.get_data())
        xobjects[NameObject(name)] = pdf._add_object(replacement)
        removed += count
    return removed


def content_refs(page):
    """ページの内容ストリームが、どのオブジェクトを指しているかを返す。"""
    from pypdf.generic import IndirectObject

    try:
        raw = page.raw_get("/Contents")
    except KeyError:
        return set()
    if isinstance(raw, IndirectObject):
        return {(raw.idnum, raw.generation)}
    refs = set()
    for item in raw:
        if isinstance(item, IndirectObject):
            refs.add((item.idnum, item.generation))
    return refs


def unshare_page_contents(writer):
    """複数のページが同じ内容ストリームを共有していたら、ページごとに分ける。

    スキャナが作る PDF では、全ページが同じ内容ストリーム
    （画像を 1 枚貼るだけの短い命令列）を共有していることがある。
    pypdf は重ねた結果を「元と同じオブジェクト」に書き戻すため、
    共有されたままだと 1 ページに重ねた文字が全ページに現れてしまう。
    重ねる前に、共有しているページへ自分専用の複製を持たせる。
    """
    from pypdf.generic import ContentStream, NameObject

    if not hasattr(writer, "_add_object"):
        return 0

    seen = set()
    split = 0
    for page in writer.pages:
        refs = content_refs(page)
        if not refs:
            continue
        if refs & seen:
            contents = page.get_contents()
            if contents is None:
                continue
            stream = ContentStream(contents, page.pdf)
            page[NameObject("/Contents")] = writer._add_object(stream)
            split += 1
            refs = content_refs(page)
        seen |= refs
    return split


def remove_existing_text(writer):
    """全ページの見えない文字を消して、消した数とページ数を返す。"""
    pages = 0
    removed = 0
    for page in writer.pages:
        count = remove_invisible_text(page)
        if count:
            pages += 1
            removed += count
    return pages, removed


def ink_path_for(image_path):
    """その作業用画像に対応する、縦組み用の画像の置き場所。"""
    root, ext = os.path.splitext(image_path)
    return root + "_ink" + ext


def remove_page_images(image_path):
    """1 ページ分の作業用画像（回して読み直した分も）を消す。"""
    root, ext = os.path.splitext(image_path)
    paths = [image_path, ink_path_for(image_path)]
    for base in (root, root + "_ink"):
        paths += ["%s_r%d%s" % (base, r, ext) for r in (90, 180, 270)]
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass


def native_dpi(document, index, cover=0.4):
    """ページに貼られている画像そのものの細かさ（dpi）を返す。

    スキャンした PDF は、紙を高い解像度で撮った画像を 1 枚貼っただけの
    ことが多い。それより粗く描き出すと、元の画像を縮めてから読むことに
    なり、小さな文字を丸ごと取りこぼす。本のページを見開きで取り込んだ
    資料のように、紙面が小さく貼られているほど差が大きい。

    紙面そのものだけを見たいので、ページの大半を覆う画像だけを数える。
    ロゴやハンコのような小さな画像は無視する。
    """
    import pypdfium2.raw as pdfium_c

    page = document[index]
    try:
        width, height = page.get_size()
        if width <= 0 or height <= 0:
            return 0
        best = 0.0
        for obj in page.get_objects(max_depth=6):
            if obj.type != pdfium_c.FPDF_PAGEOBJ_IMAGE:
                continue
            try:
                px_width, px_height = obj.get_px_size()
                left, bottom, right, top = obj.get_bounds()
            except Exception:                           # noqa: BLE001
                continue
            box_width, box_height = right - left, top - bottom
            if box_width <= 1 or box_height <= 1:
                continue
            if box_width * box_height < cover * width * height:
                continue
            best = max(best, 72.0 * px_width / box_width,
                       72.0 * px_height / box_height)
        return int(round(best))
    except Exception:                                   # noqa: BLE001
        return 0
    finally:
        page.close()


def page_dpi(document, index, dpi, max_dpi):
    """そのページを描き出す解像度を決める。

    設定した値より画像のほうが細かければ、画像に合わせて上げる。
    下げることはしない（設定を無視して粗くしないため）。
    """
    if max_dpi <= 0:
        return dpi
    found = native_dpi(document, index)
    if found <= dpi:
        return dpi
    return min(found, max(dpi, max_dpi))


def render_scale(page_size, dpi, max_pixels):
    """解像度を決める。大判の図面で画像が巨大になりすぎないように抑える。"""
    scale = dpi / 72.0
    width, height = page_size
    pixels = (width * scale) * (height * scale)
    if max_pixels > 0 and pixels > max_pixels:
        scale *= (max_pixels / pixels) ** 0.5
    return scale


def ink_image(image):
    """色を捨てて白黒にするとき、色の付いたインクを濃いまま残す。

    ふつうの輝度によるグレー変換は、色の付いたインクを薄い灰色にして
    しまう。オレンジの見出し（RGB 196,110,50）は輝度では 129 まで
    明るくなり、白い紙との差が黒い文字の半分しかなくなる。実測でも、
    この見出しは輝度変換では信頼度 7 でしか読めず（＝捨てられる）、
    R/G/B のうち最も暗い値を取ると 91 で読めた。

    ただしこれを紙面全体に使うと、今度は薄い色の飾り罫や枠まで濃く
    なって文字として拾われる（見出しを囲む点線が「ーー」に化けて、
    見出し自体が読めなくなった）。図や表の多い横組みでは害のほうが
    大きいので、この画像は**縦組みを読むときだけ**使う。手元の
    見開き 1 ページでは、横＝輝度／縦＝この画像の組み合わせが最良だった
    （狙った 34 語のうち、両方輝度 32・両方この画像 32・組み合わせ 33）。

    なお GRAYSCALE=no（既定）では白黒に落とさないので、この画像は
    作らない。色をそのまま tesseract に渡すほうが、白黒に落としてから
    色を補うより成績がよかったため（DEFAULTS の GRAYSCALE を参照）。
    ここは GRAYSCALE=yes に戻したときのために残してある。
    """
    from PIL import ImageChops

    if image.mode != "RGB":
        image = image.convert("RGB")
    red, green, blue = image.split()
    return ImageChops.darker(ImageChops.darker(red, green), blue)


def render_page(document, index, dpi, grayscale, image_path, max_pixels=0,
                ink_path=None):
    """ページを画像にして保存し、(画像の幅, 高さ) を返す。

    ink_path を渡すと、縦組み用に「色の付いたインクを濃いまま残した」
    画像も同じ大きさで書き出す。
    """
    page = document[index]
    try:
        scale = render_scale(page.get_size(), dpi, max_pixels)
        image = page.render(scale=scale).to_pil()
        try:
            if ink_path:
                ink = ink_image(image)
                try:
                    ink.save(ink_path)
                finally:
                    ink.close()
            if grayscale:
                image = image.convert("L")
            image.save(image_path)
            return image.size
        finally:
            image.close()
    finally:
        page.close()


def merge_overlay(page, words, image_size, font_name, PdfReader, Transformation):
    """透明テキストのページを、元のページに重ねる。"""
    box = page.cropbox if page.cropbox is not None else page.mediabox
    width = float(box.width)
    height = float(box.height)
    rotation = (page.rotation or 0) % 360
    if rotation in (90, 270):
        visual_w, visual_h = height, width
    else:
        visual_w, visual_h = width, height

    overlay_bytes = build_overlay(words, visual_w, visual_h,
                                  image_size[0], image_size[1], font_name)
    overlay_page = PdfReader(io.BytesIO(overlay_bytes)).pages[0]
    matrix = overlay_matrix(rotation, width, height)
    transformation = Transformation(matrix).translate(float(box.left),
                                                      float(box.bottom))
    page.merge_transformed_page(overlay_page, transformation)


def report(current, total, message):
    sys.stdout.write("  %d/%d ページ … %s\n" % (current, total, message))
    sys.stdout.flush()


def output_path(src_path, settings, overwrite):
    outdir = settings["OUTDIR"] or os.path.dirname(os.path.abspath(src_path))
    if not os.path.isdir(outdir):
        os.makedirs(outdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(src_path))[0]
    dst = os.path.join(outdir, base + settings["SUFFIX"] + ".pdf")
    if overwrite or not os.path.exists(dst):
        return dst
    for n in range(2, 100):
        candidate = os.path.join(outdir,
                                 "%s%s_%d.pdf" % (base, settings["SUFFIX"], n))
        if not os.path.exists(candidate):
            return candidate
    return dst


def collect_inputs(paths, suffix):
    """ファイルとフォルダの両方を受け取れるようにする（ドラッグ＆ドロップ用）。"""
    files = []
    for path in paths:
        if os.path.isdir(path):
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                if os.path.isfile(full) and name.lower().endswith(".pdf"):
                    files.append(full)
        elif os.path.isfile(path):
            files.append(path)
        else:
            sys.stderr.write("見つかりません: %s\n" % path)
    result = []
    for path in files:
        base = os.path.splitext(os.path.basename(path))[0]
        if suffix and base.endswith(suffix):
            sys.stderr.write("変換済みのため飛ばします: %s\n"
                             % os.path.basename(path))
            continue
        result.append(path)
    return result


def check_imports():
    missing = []
    for module, package in (("pypdfium2", "pypdfium2"), ("pypdf", "pypdf"),
                            ("reportlab", "reportlab"), ("PIL", "pillow")):
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    return missing


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="pdf_ocr.py",
        description="画像PDFに透明なテキスト層を重ねて、選択・検索できるようにする。")
    parser.add_argument("inputs", nargs="*", help="PDF ファイルまたはフォルダ")
    parser.add_argument("--mode", choices=sorted(MODES), default=None,
                        help="読み取り方の初期値（既定: auto）")
    parser.add_argument("--lang", help="tesseract の言語（例 jpn+eng）")
    parser.add_argument("--psm", help="tesseract のページ分割モード")
    parser.add_argument("--dpi", type=int, help="ページを画像にするときの解像度")
    parser.add_argument("--maxdpi", type=int,
                        help="画像が細かいときに上げてよい上限（0 で固定）")
    parser.add_argument("--grayscale", dest="grayscale", action="store_true",
                        default=None, help="白黒にしてから読む（速いが色付きに弱い）")
    parser.add_argument("--no-grayscale", dest="grayscale",
                        action="store_false", help="色を残したまま読む")
    parser.add_argument("--minconf", type=int, help="採用する信頼度の下限(0-100)")
    parser.add_argument("--outdir", help="出力先フォルダ")
    parser.add_argument("--suffix", help="出力ファイル名に付ける文字（既定 _OCR）")
    parser.add_argument("--jobs", type=int, help="同時に OCR するページ数")
    parser.add_argument("--no-autorotate", dest="autorotate",
                        action="store_false", default=None,
                        help="横倒しページの自動立て直しをしない")
    parser.add_argument("--force", action="store_true",
                        help="すでに文字が入っているページも認識し直す")
    parser.add_argument("--retext", action="store_true",
                        help="元から入っている文字を消してから認識し直す"
                             "（質の悪いテキスト層を入れ替える）")
    parser.add_argument("--overwrite", action="store_true",
                        help="同名の出力ファイルを上書きする")
    parser.add_argument("--quiet", action="store_true", help="途中経過を出さない")
    parser.add_argument("--dumptext", action="store_true",
                        help="変換後の PDF から取り出せる文字を表示する")
    parser.add_argument("--install-langs", action="store_true",
                        help="日本語（縦書き含む）の言語データを用意して終わる")
    parser.add_argument("--no-download", action="store_true",
                        help="足りない言語データを取りに行かない")
    parser.add_argument("--selftest", action="store_true",
                        help="環境（tesseract・ライブラリ）だけ確認する")
    parser.add_argument("--check", action="store_true",
                        help="変換せずに、PDF の中身（文字数・画像・フォント）を調べる")
    parser.add_argument("--dumpocr", action="store_true",
                        help="変換せずに、縦組みの読み取りの中身を書き出す（不具合調べ用）")
    return parser.parse_args(argv)


def langs_in_use(exe, settings):
    """いま使っている言語データを、一行で説明する文字列にする。

    「直したはずなのに何も変わらない」を、その場で切り分けられるように
    するためのもの。実際に、精度重視版を用意できていないのに何も
    表示されず、利用者にも開発側にも区別がつかないことが起きた。
    どの版で読んでいるかは結果を大きく左右するので、毎回必ず出す。
    """
    tessdata = settings.get("_TESSDATA") or None
    path = find_traineddata(exe, "jpn", tessdata)
    if not path:
        return "日本語の言語データが見つかりません"
    try:
        size = os.path.getsize(path)
    except OSError:
        return path
    least = THIN_TRAINEDDATA.get("jpn", 0)
    kind = "速度優先版（精度が落ちます）" if size < least else "精度重視版"
    return "%s  %.1f MB  %s" % (kind, size / 1048576.0, path)


def prepare_conversion(mode=None, quiet=True, no_download=False):
    """変換の準備一式（tesseract・言語データ・フォント）を整える。

    main() の CLI 用の一連の処理と同じ手順を、GUI からも呼べる形にした
    もの（main() 自体は変えていない。CLI の挙動を壊さないため）。
    そろわなければ RuntimeError を投げる。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    ini = read_ini(os.path.join(here, INI_NAME))
    if mode is None:
        mode = "auto"
        if ini.has_section("settings"):
            wanted = dict(ini.items("settings")).get("mode", "").strip()
            if wanted in MODES:
                mode = wanted
    settings = build_settings(ini, mode)

    missing = check_imports()
    if missing:
        raise RuntimeError(
            "必要なライブラリが入っていません: %s\n"
            "PDF文字認識.bat をダブルクリックして [1] を選んでください。"
            % " ".join(missing))

    exe = find_tesseract(settings["TESSERACT"])
    if not exe:
        raise RuntimeError(TESSERACT_HELP)

    available = tesseract_langs(exe)
    needed = wanted_langs(settings, False)

    local = adopt_local_langs(exe, needed, quiet)
    if local:
        settings["_TESSDATA"] = local
        settings["_TESSDATA_ALT"] = ""
        available = langs_in_dir(local)

    if not no_download:
        missing = sorted(name for name in needed if name not in available)
        if missing:
            try:
                tessdata, _failed, _target = ensure_langs(exe, needed,
                                                          available, quiet)
            except RuntimeError:
                tessdata = None
            if tessdata:
                settings["_TESSDATA"] = tessdata
            available = tesseract_langs(exe, settings.get("_TESSDATA"))
        try:
            upgraded = upgrade_langs(exe, needed, quiet,
                                     settings.get("_TESSDATA"))
        except RuntimeError:
            upgraded = None
        if upgraded:
            settings["_TESSDATA_ALT"] = settings.get("_TESSDATA") or ""
            settings["_TESSDATA"] = upgraded
            available = langs_in_dir(upgraded)

    settings["_HAS_OSD"] = "osd" in available
    lang, _missing_langs = usable_lang(available, settings["LANG"])
    settings["LANG"] = lang
    if settings.get("LANG2"):
        lang2, _missing2 = usable_lang(available, settings["LANG2"])
        settings["LANG2"] = lang2

    font_path = find_font(settings["FONT"])
    font_name = register_font(font_path)

    return {"exe": exe, "settings": settings, "font_name": font_name,
           "available": available}


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not args.quiet:
        sys.stdout.write("%s 版 %s\n" % (PROG, VERSION))
    here = os.path.dirname(os.path.abspath(__file__))
    ini = read_ini(os.path.join(here, INI_NAME))
    # 読み取り方は auto（資料の種類を選ばせない）を既定にする。
    # 横書きだけの資料で速さを優先したい人のために、設定.ini の
    # [settings] MODE= でも変えられるようにしておく。
    mode = args.mode
    if mode is None:
        mode = "auto"
        if ini.has_section("settings"):
            wanted = dict(ini.items("settings")).get("mode", "").strip()
            if wanted in MODES:
                mode = wanted
    settings = build_settings(ini, mode)

    for name, value in (("LANG", args.lang), ("PSM", args.psm),
                        ("DPI", args.dpi), ("MAXDPI", args.maxdpi),
                        ("MINCONF", args.minconf),
                        ("OUTDIR", args.outdir), ("SUFFIX", args.suffix),
                        ("JOBS", args.jobs)):
        if value is not None:
            settings[name] = str(value)
    if args.autorotate is False:
        settings["AUTOROTATE"] = "no"
    if args.grayscale is not None:
        settings["GRAYSCALE"] = "yes" if args.grayscale else "no"

    missing = check_imports()
    if missing:
        sys.stderr.write(
            "必要なライブラリが入っていません: %s\n"
            "PDF文字認識.bat をダブルクリックして [1] を選ぶか、\n"
            "次を実行してください:\n"
            "    pip install %s\n" % (" ".join(missing), " ".join(missing)))
        return 2

    if args.check:
        # 調べるだけなので、tesseract が無くても動くようにここで処理する
        targets = collect_inputs(args.inputs, suffix="")
        if not targets:
            sys.stderr.write("調べる PDF がありません。\n")
            return 1
        for path in targets:
            try:
                check_pdf(path)
            except Exception as exc:                    # noqa: BLE001
                sys.stderr.write("  調べられませんでした: %s\n" % exc)
        return 0

    exe = find_tesseract(settings["TESSERACT"])
    if not exe:
        sys.stderr.write(TESSERACT_HELP)
        return 2

    available = tesseract_langs(exe)

    # 足りない言語データは自分で用意する（インストーラでの入れ忘れ対策）
    needed = wanted_langs(settings, args.install_langs)

    # 前にこのツールのフォルダへ言語データを入れていれば、そちらを使う。
    # tesseract 本体の置き場に書けない環境（Windows の Program Files が
    # まさにこれ）では、入れ替え先がこちらになる。ここで拾わないと、
    # 本体の置き場に残った速度優先版だけを見て「まだ速度優先版だ」と
    # 判断し、起動のたびに 50 MB 以上を取得し直すことになる。
    # 同梱の（または前に用意した）精度重視版があれば、取得せずにそれを使う
    local = adopt_local_langs(exe, needed, args.quiet)
    if local:
        settings["_TESSDATA"] = local
        # 元から入っていた版も残してある。精度重視版が苦手なページだけ、
        # そちらで読み直して比べるために覚えておく
        settings["_TESSDATA_ALT"] = ""
        # ここも tesseract に聞かない。聞いて失敗すると「言語が 1 つも
        # 使えない」と読み違え、日本語を外して読みにいってしまう
        available = langs_in_dir(local)

    if not args.no_download:
        missing = sorted(name for name in needed if name not in available)
        if missing:
            sys.stdout.write("言語データ %s がありません。取得します。\n"
                             % " ".join(missing))
            target = local_tessdata_dir()
            try:
                tessdata, failed, target = ensure_langs(exe, needed, available,
                                                        args.quiet)
            except RuntimeError as exc:
                sys.stderr.write("%s\n" % exc)
                tessdata = None
            if tessdata:
                settings["_TESSDATA"] = tessdata
            available = tesseract_langs(exe, settings.get("_TESSDATA"))
            still = [name for name in missing if name not in available]
            if still:
                sys.stderr.write(tessdata_help(still, target))

        # 速度優先版が入っていたら、精度重視版に入れ替える。Windows の
        # インストーラが入れるのは速度優先版で、そのままでは「足りて
        # いる」と見なされて上の処理が働かない。実際の紙面で、狙った
        # 16 語のうち取り出せた数が 9 から 13 に増えた（thin_traineddata
        # の説明を参照）。
        try:
            upgraded = upgrade_langs(exe, needed, args.quiet,
                                     settings.get("_TESSDATA"))
        except RuntimeError as exc:
            sys.stderr.write("%s\n" % exc)
            upgraded = None
        if upgraded:
            settings["_TESSDATA_ALT"] = settings.get("_TESSDATA") or ""
            settings["_TESSDATA"] = upgraded
            available = langs_in_dir(upgraded)

    settings["_HAS_OSD"] = "osd" in available
    lang, missing_langs = usable_lang(available, settings["LANG"])
    if missing_langs:
        sys.stderr.write("言語データ %s が使えないので %s で読み取ります。\n"
                         % ("+".join(missing_langs), lang))
    settings["LANG"] = lang

    if settings.get("LANG2"):
        lang2, missing2 = usable_lang(available, settings["LANG2"])
        if "jpn_vert" in missing2:
            sys.stderr.write("縦書き用の jpn_vert が使えないので、縦組みは"
                             "うまく読めません。\n")
        settings["LANG2"] = lang2

    if not args.quiet:
        sys.stdout.write("言語データ: %s\n" % langs_in_use(exe, settings))

    if args.install_langs:
        sys.stdout.write("使える言語データ: %s\n" % ", ".join(sorted(available)))
        return 0 if all(name in available for name in needed) else 2

    font_path = find_font(settings["FONT"])
    font_name = register_font(font_path)

    if args.selftest:
        sys.stdout.write("tesseract : %s\n" % exe)
        sys.stdout.write("使える言語: %s\n" % ", ".join(sorted(available)))
        sys.stdout.write("フォント  : %s\n" % (font_path or "（埋め込みなしで代用）"))
        sys.stdout.write("文字の取り出し: %s\n"
                         % ("OK" if font_round_trip(font_name)
                            else "NG（このフォントでは日本語を取り出せません）"))
        # ここから 2 つは、いつもの変換（tesseract）には要らない、画面
        # （GUI）専用の部品。入っていなくても失敗ではないが、黙って
        # 気づけないと「GUI で見て初めて壊れていると分かる」になるため、
        # 準備の最後にここでまとめて出す。
        try:
            import tkinterdnd2                              # noqa: F401
            dnd_reason = None
        except ImportError as exc:
            dnd_reason = str(exc)
        sys.stdout.write(
            "画面のドラッグ＆ドロップ: %s\n"
            % ("OK" if dnd_reason is None
               else "入っていません（%s）→ 画面の「PDF を選ぶ…」ボタンは使えます"
               % dnd_reason))
        missing_ppocr = missing_ppocr_modules()
        sys.stdout.write(
            "PP-OCRv5（縦書き・横書きで選べる読み取り）: %s\n"
            % ("OK" if not missing_ppocr
               else "入っていません（不足: %s）→ 選んでも tesseract で読みます"
               % "、".join(missing_ppocr)))
        sys.stdout.write("準備できています。\n")
        return 0

    targets = collect_inputs(args.inputs, settings["SUFFIX"])
    if not targets:
        sys.stderr.write("変換する PDF がありません。\n")
        return 1

    if args.dumpocr:
        for path in targets:
            dst = os.path.splitext(path)[0] + "_調査.txt"
            sys.stdout.write("\n%s\n" % os.path.basename(path))
            try:
                dump_ocr(path, dst, settings, exe)
            except Exception as exc:                    # noqa: BLE001
                sys.stderr.write("  書き出せませんでした: %s\n" % exc)
                continue
            sys.stdout.write("  → %s\n" % os.path.basename(dst))
        return 0

    failures = 0
    for path in targets:
        dst = output_path(path, settings, args.overwrite)
        sys.stdout.write("\n%s\n  → %s\n" % (os.path.basename(path),
                                             os.path.basename(dst)))
        started = time.time()
        try:
            pages, words = ocr_pdf(path, dst, settings, exe, font_name,
                                   args.force, args.quiet, args.retext)
        except Exception as exc:                        # noqa: BLE001
            failures += 1
            sys.stderr.write("  失敗しました: %s\n" % exc)
            continue
        sys.stdout.write("  完了 … %d ページ / %d 個の文字列 / %.1f 秒\n"
                         % (pages, words, time.time() - started))
        # 開くべきファイルを、置き場所と時刻まで書いて示す。別名で増えた
        # 古い出力を開いたまま「変わらない」と見えることがあったため。
        sys.stdout.write("  保存しました … %s\n"
                         % os.path.abspath(dst))
        try:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S",
                                  time.localtime(os.path.getmtime(dst)))
            sys.stdout.write("  このファイルを開いてください（%s 更新）\n"
                             % stamp)
        except OSError:
            pass
        if args.dumptext:
            dump_text(dst)

    # 速度優先版のままだと、実測で狙った 16 語のうち 9 語しか取れない
    # （精度重視版なら 15 語）。取りそこねたことを黙って続けると、
    # 「直したはずなのに何も変わらない」がそのまま起きるので、
    # 最後にもう一度、目立つ形で伝える。
    if not args.quiet and thin_traineddata(exe, "jpn",
                                           settings.get("_TESSDATA") or None):
        sys.stdout.write(
            "\n"
            "  ※ 日本語の言語データが速度優先版のままです。\n"
            "     精度重視版なら読めていたはずの字が読めません。\n"
            "     このバッチをダブルクリックして [1] 準備をやり直す を\n"
            "     実行すると、精度重視版を取りに行きます。\n"
            "     社内ネットワークで取得できない場合は、\n"
            "     https://github.com/tesseract-ocr/tessdata から\n"
            "     jpn.traineddata（35 MB ほど）を手で落として、\n"
            "     %s に置いてください。\n"
            % local_tessdata_dir())

    return 1 if failures else 0


def dump_ocr(src_path, dst_path, settings, exe, most=600):
    """縦組みの読み取りの中身を、そのまま書き出す（不具合調べ用）。

    tesseract は版によって読み方が変わるので、開発した環境では起きない
    読み違いがある。そこで、tesseract が返した生の結果と、こちらがそれを
    どう直したかを並べて残す。この控えを送ってもらえば、手元に同じ環境が
    無くても直せる。
    """
    import pypdfium2 as pdfium

    dpi = as_int(settings["DPI"], 300)
    max_dpi = as_int(settings["MAXDPI"], 600)
    max_pixels = as_int(settings["MAXPIXELS"], 40000000)
    grayscale = as_bool(settings["GRAYSCALE"])
    min_conf = as_int(settings["MINCONF"], 30)
    tessdata = settings.get("_TESSDATA") or None
    lang = settings["LANG"]
    lang2 = settings.get("LANG2", "")
    vertical_lang = lang2 if "_vert" in lang2 else lang
    vertical_psm = settings.get("PSM2", "5") if "_vert" in lang2 else settings["PSM"]
    env = ocr_env(1)

    report = []

    def out(text=""):
        report.append(text)

    out("PDF文字認識 調査ファイル")
    out("=" * 60)
    out("このツール: 版 %s" % VERSION)
    out("入力      : %s" % os.path.basename(src_path))
    out("tesseract : %s" % exe)
    try:
        version = subprocess.run([exe, "--version"], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, check=False)
        out("版        : %s" % version.stdout.decode("utf-8", "replace")
            .splitlines()[0].strip())
    except Exception:                                   # noqa: BLE001
        pass
    out("日本語の版: %s" % langs_in_use(exe, settings))
    out("読み取り  : LANG=%s PSM=%s / LANG2=%s PSM2=%s MINCONF=%d"
        % (lang, settings["PSM"], lang2 or "（なし）",
           settings.get("PSM2", ""), min_conf))
    out()

    document = pdfium.PdfDocument(src_path)
    try:
        with tempfile.TemporaryDirectory(prefix="pdf_ocr_dump_") as tmpdir:
            for index in range(len(document)):
                image_path = os.path.join(tmpdir, "p%05d.png" % index)
                ink_path = ink_path_for(image_path) if grayscale else None
                used_dpi = page_dpi(document, index, dpi, max_dpi)
                size = render_page(document, index, used_dpi, grayscale,
                                   image_path, max_pixels, ink_path)
                vertical_image = ink_path or image_path

                out("-" * 60)
                out("%d ページ目  %d dpi  画像 %dx%d"
                    % (index + 1, used_dpi, size[0], size[1]))
                out("-" * 60)

                tsv = run_tesseract(exe, [vertical_image, "stdout", "-l",
                                          vertical_lang, "--psm",
                                          str(vertical_psm), "tsv"],
                                    env=env, tessdata=tessdata)
                words = parse_vertical(tsv, min_conf)
                snapshot = dict((id(word), word.text) for word in words)

                numbers = sparse_numbers(exe, vertical_image, env, tessdata)
                out("[1] 数字だけを拾った結果（縦中横の直しに使う）")
                if numbers:
                    for number in numbers:
                        out("    %-8s conf%5.1f  x%5d y%5d %3dx%-3d"
                            % (number.text, number.conf, number.left,
                               number.top, number.width, number.height))
                else:
                    out("    （なし）")
                out()

                fix_tatechuyoko(words, numbers)
                fix_stacked_digits(words, vertical_image, exe, env, tessdata,
                                   min_conf)
                before_fill = set(id(word) for word in words)
                fill_vertical_gaps(words, vertical_image, exe, env, tessdata,
                                   vertical_lang, vertical_psm)

                out("[2] 縦書きで読んだ結果と、こちらが直した所")
                out("    text          conf   left   top   幅x高  行  直し")
                kept = set(id(word) for word in words)
                shown = 0
                for word in words:
                    if shown >= most:
                        out("    …（多いのでここまで）")
                        break
                    note = ""
                    was = snapshot.get(id(word))
                    if was is not None and was != word.text:
                        note = "← 「%s」から直した" % was
                    elif id(word) not in before_fill:
                        note = "← すきまから拾った"
                    out("    %-12s %5.1f %6d %5d %4dx%-4d %s %s"
                        % (word.text[:12], word.conf, word.left, word.top,
                           word.width, word.height, word.line, note))
                    shown += 1
                for key, text in snapshot.items():
                    if key not in kept:
                        out("    %-12s   ---                            消した"
                            % text[:12])
                out()

                out("[3] 縦書きで読んだものを、行としてつないだ結果")
                vertical_lines = merge_lines(words)
                for word in vertical_lines:
                    if word.angle == 90:
                        out("    x%5d y%5d  %s" % (word.left, word.top, word.text))
                out()

                # ここから先は、縦書きだけでは分からない所を見るために足す。
                # 実際にコピーされる文字は、横書きで読んだ結果と縦書きで
                # 読んだ結果を突き合わせて決まる。縦書きの控えだけを見て
                # いたために、利用者の手元の症状と食い違ったことがある。
                out("[4] 横書きで読んだ結果を、行としてつないだ結果")
                tsv_h = run_tesseract(exe, [image_path, "stdout", "-l", lang,
                                            "--psm", str(settings["PSM"]),
                                            "tsv"], env=env, tessdata=tessdata)
                horizontal = merge_lines(parse_tsv(tsv_h, min_conf))
                for word in horizontal[:most]:
                    out("    x%5d y%5d %s %s"
                        % (word.left, word.top,
                           "縦" if word.angle == 90 else "横", word.text))
                out()

                # ここは組み立て直さず、変換のときと同じ関数を呼ぶ。
                # 手で組み直すと、片方だけ直したときに調査ファイルと
                # 実際のコピー結果が食い違う（言語データを版ごとに読み
                # 分ける処理を入れたとき、実際にそうなった）。
                out("[5] 最終的に PDF に入る文字（実際にコピーされるのはこれ）")
                merged, _ = ocr_image(exe, image_path, size, settings, env,
                                      ink_path)
                if in_doubt(horizontal) or in_doubt(merged):
                    out("    ※ うまく読めたとは言えないページなので、"
                        "元の版の言語データでも読み直して比べています")
                out("    平均信頼度 %.1f" % page_quality(merged))
                for word in merged[:most]:
                    out("    x%5d y%5d %s %s"
                        % (word.left, word.top,
                           "縦" if word.angle == 90 else "横", word.text))
                out()
                remove_page_images(image_path)
    finally:
        document.close()

    with io.open(dst_path, "w", encoding="utf-8-sig", newline="\r\n") as handle:
        handle.write("\n".join(report) + "\n")
    return dst_path


def check_pdf(path):
    """PDF の中身を調べて表示する（うまくいかないときの原因さがし用）。

    ページごとに「取り出せる文字の数」「画像の有無」「使われている
    フォントが埋め込みか」を見れば、変換できていないのか、変換した
    文字が取り出せないのかを切り分けられる。
    """
    from pypdf import PdfReader

    reader = PdfReader(path)
    sys.stdout.write("\n%s\n" % os.path.basename(path))
    sys.stdout.write("  ページ数: %d\n" % len(reader.pages))
    if reader.is_encrypted:
        sys.stdout.write("  ※ 暗号化されています\n")

    for number, page in enumerate(reader.pages, 1):
        try:
            text = "".join((page.extract_text() or "").split())
        except Exception:                               # noqa: BLE001
            text = ""
        fonts = page_fonts(page)
        images = count_images(page)
        sys.stdout.write(
            "  %3d ページ: 文字 %5d 字 / 画像 %d / 回転 %d / フォント %s\n"
            % (number, len(text), images, (page.rotation or 0) % 360,
               ", ".join(fonts) if fonts else "なし"))
        if text:
            sys.stdout.write("            先頭: %s\n" % text[:40])

    sys.stdout.write(
        "\n  見かた: 画像があって文字が 0 字なら、まだ変換されていません。\n"
        "          文字があるのに検索できないときは、フォントの欄に\n"
        "          「埋込」と出ているかを確かめてください。\n")


def page_fonts(page):
    """ページで使われているフォントを「名前(埋込/非埋込)」の形で並べる。"""
    names = []
    try:
        resources = page.get("/Resources")
        fonts = resources.get("/Font") if resources else None
        if not fonts:
            return names
        for key in fonts:
            font = fonts[key].get_object()
            name = str(font.get("/BaseFont", key))
            embedded = font_is_embedded(font)
            unicode_map = "/ToUnicode" in font
            names.append("%s(%s%s)" % (name.lstrip("/"),
                                       "埋込" if embedded else "非埋込",
                                       ",ToUnicode有" if unicode_map else ""))
    except Exception:                                   # noqa: BLE001
        pass
    return names


def font_is_embedded(font):
    descriptors = []
    if "/FontDescriptor" in font:
        descriptors.append(font["/FontDescriptor"].get_object())
    for descendant in font.get("/DescendantFonts", []) or []:
        child = descendant.get_object()
        if "/FontDescriptor" in child:
            descriptors.append(child["/FontDescriptor"].get_object())
    for descriptor in descriptors:
        if any(key in descriptor
               for key in ("/FontFile", "/FontFile2", "/FontFile3")):
            return True
    return False


def count_images(page):
    try:
        resources = page.get("/Resources")
        xobjects = resources.get("/XObject") if resources else None
        if not xobjects:
            return 0
        return sum(1 for key in xobjects
                   if xobjects[key].get_object().get("/Subtype") == "/Image")
    except Exception:                                   # noqa: BLE001
        return 0


def dump_text(path):
    """変換した PDF から実際に取り出せる文字を表示する（動作確認用）。"""
    from pypdf import PdfReader

    sys.stdout.write("\n  ---- 取り出せた文字 ----\n")
    for number, page in enumerate(PdfReader(path).pages, 1):
        text = " ".join((page.extract_text() or "").split())
        sys.stdout.write("  [%d ページ] %s\n" % (number, text or "(なし)"))
    sys.stdout.write("  ------------------------\n")


if __name__ == "__main__":
    sys.exit(main())
