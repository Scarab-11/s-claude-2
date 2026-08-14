#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jw_cad 外部変形 : 天井伏図生成   jww_ceiling_plan.py

  範囲選択した平面図から、天井伏図のたたき台を作ります。

  ・バッチファイル(*.bat)から python で呼び出されます。
  ・単体では動きません(jwc_temp.txt が必要)。

  やること
    1. ルールファイルに従って、不要なレイヤの要素を落とす
    2. 室名の文字を見つけて、その下に天井仕上記号を書く
    3. 面積表記などの不要な文字を消す / 図面名を書き換える
    4. 仕上表(凡例)を作図する
    5. 以上を、指示した点を左下として作図する(元の平面図は残る)

  引数
    第1引数  jwc_temp.txt のパス
             (省略時 カレントフォルダの jwc_temp.txt)
    第2引数  ルールファイルのパス
             (省略時 このスクリプトと同じ場所の 天伏図ルール.txt)

  Python 3.8 以上 / Jw_cad Version 8.20 で使用する想定
"""

import math
import os
import re
import sys
import unicodedata
from datetime import datetime

APPTITLE = '天井伏図生成'
EPS = 1.0e-9

# jwc_temp.txt / ルールファイル / ログはすべて Shift_JIS(CP932)。
# Python の cp932 コーデックは NEC/IBM 拡張(①や㎡)も通す。
CP932 = 'cp932'

NUM = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'


# --------------------------------------------------------------
# 文字コードまわり
# --------------------------------------------------------------
def read_cp932(path):
    with open(path, 'rb') as f:
        data = f.read()
    # ルールファイルをうっかり UTF-8 で保存してしまった場合の逃げ道。
    # BOM が付いていれば UTF-8 として読む。
    if data.startswith(b'\xef\xbb\xbf'):
        return data[3:].decode('utf-8', errors='replace')
    return data.decode(CP932, errors='replace')


def write_cp932(path, text):
    with open(path, 'wb') as f:
        f.write(text.encode(CP932, errors='replace'))


def script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def fmt(v):
    """数値の書き出し。指数表記や不要な 0 を付けない。"""
    if abs(v) < EPS:
        return '0'
    s = f'{v:.6f}'.rstrip('0').rstrip('.')
    return '0' if s == '-0' else s


def to_num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def normalize_key(s):
    """室名の照合用に正規化する。

    空白(全角含む)を取り除き、全角英数を半角に寄せる。
    「事　務　室」「洋室－１」のような書き方でも拾えるようにする。
    """
    t = re.sub(r'[\s　]', '', s)
    return unicodedata.normalize('NFKC', t)


# --------------------------------------------------------------
# ルールファイル
# --------------------------------------------------------------
class Rules:
    DEFAULTS = {
        # 既定の採否。keep = 指定が無いレイヤは残す / drop = 落とす
        'DEFAULT':      'keep',
        # 室名照合  exact = 完全一致のみ / prefix = 前方一致も見る
        'ROOM_MATCH':   'prefix',
        # 部屋名が入っているレイヤ  off = ROOM に書いた室名だけを拾う
        'ROOM_LAYER':   'off',
        # ROOM に無い室名の扱い  on = 記号を自動で割り当てる / off = ROOM_DEFAULT を置く
        'ROOM_AUTO':    'on',
        # 自動で割り当てる記号の頭
        'SYMBOL_PREFIX': 'C-',
        # 図面の中の仕上表(内部仕上概要表)を読む  auto / off / 例 0:9
        'FINISH_TABLE': 'auto',
        # ROOM_AUTO が off のとき、ROOM に無い室名に置く記号  no = 置かない
        'ROOM_DEFAULT': 'C-?',
        # 記号の文字種(1-10)
        'SYMBOL_CN':    '3',
        # 室名の基準線から記号の基準線までの距離(図寸mm)
        'SYMBOL_DY':    '4.0',
        # 記号を書くレイヤ  same = 室名と同じ / 例 0:5
        'SYMBOL_LAYER': 'same',
        # 記号の線色  same = 室名と同じ / 例 2
        'SYMBOL_COLOR': 'same',
        # 壁の中心線があるレイヤ  off = 壁線を作らない
        'WALL_FROM':    '0:0',
        # 壁の厚さ(実寸mm)
        'WALL_WIDTH':   '120',
        # 壁線を書くレイヤ  same = 中心線と同じ
        'WALL_LAYER':   'same',
        # 壁線の線色
        'WALL_COLOR':   '5',
        # 記号を四角の枠で囲む  on / off
        'SYMBOL_BOX':   'on',
        # 枠と文字とのすき間(図寸mm)
        'SYMBOL_BOX_PAD': '0.5',
        # 枠の線色  same = 記号と同じ / 例 5
        'SYMBOL_BOX_COLOR': 'same',
        # 凡例の書き出し  all = 全部 / used = 使った記号だけ / no = 書かない
        'LEGEND_MODE':  'all',
        # 凡例の位置  auto = 図の右上 / 例 12000,8000 (図面の座標＝実寸mm)
        'LEGEND_POS':   'auto',
        'LEGEND_W1':    '12',      # 記号欄の最小幅(図寸mm)
        'LEGEND_W2':    '70',      # 仕上欄の最小幅(図寸mm)
        'LEGEND_RH':    '6',       # 行の高さ(図寸mm)
        'LEGEND_CN':    '3',       # 凡例の文字種
        'LEGEND_LAYER': 'same',
        'LEGEND_COLOR': 'same',    # 文字の線色  same = 罫線に合わせる
        'LEGEND_BORDER_COLOR': '5',  # 外枠の線色
        'LEGEND_LINE_COLOR':   '2',  # 中の罫線の線色
        'LEGEND_TITLE': '仕上表',
        # 文字データの解釈  auto / rel(長さ成分) / abs(終点座標)
        'CHFORMAT':     'auto',
        # 図寸mm を座標値に直す倍率  auto = hs(縮尺の分母)を使う / 例 100
        'SCALE':        'auto',
    }

    def __init__(self):
        self.keep = []            # [lg, ly]  None = ワイルドカード
        self.drop = []
        self.rooms = {}           # 正規化した室名 => 記号
        self.room_bases = {}      # 枝番を取った室名 => 記号
        self.legend = []          # [記号, 説明] 記述順
        self.colors = []          # [(lg, ly), 線番号]
        self.droptext = []        # 正規表現
        self.noroom = []          # 部屋名レイヤにあっても室名でないもの
        self.retext = []          # [正規表現, 置換後]
        self.settings = dict(self.DEFAULTS)
        self.errors = []

    # 室名の末尾に付く枝番。NFKC 済みなので ① は 1 になっている。
    BRANCH = re.compile(r'[0-9A-Za-z\-‐ー－_]+\Z')

    @classmethod
    def load(cls, path):
        r = cls()
        r.parse(read_cp932(path))
        r.build_room_bases()
        return r

    def build_room_bases(self):
        """「倉庫①」「倉庫②」から枝番を取った「倉庫」を引けるようにする。

        図面の室名が「倉庫」だけで、丸数字が別の要素として描かれている
        ことがあるため。記号が食い違う枝番があるときは、取り違えると
        まずいので登録しない。
        """
        found = {}
        for name, sym in self.rooms.items():
            base = self.BRANCH.sub('', name)
            if not base or base == name or base in self.rooms:
                continue
            found.setdefault(base, set()).add(sym)
        self.room_bases = {b: s.pop() for b, s in found.items() if len(s) == 1}

    @staticmethod
    def is_directive(line):
        """項目として読むのは、行のあたま(桁下げなし)が英大文字だけの語で
        始まる行に限る。それ以外は説明文とみなす。
        こうしておくと、説明文にわざわざ # を付けなくてよい。
        """
        return re.match(r'[A-Z_]+(?:\s|\Z)', line) is not None

    def parse(self, text):
        handlers = {
            'KEEP':     lambda rest, no: self.add_layer(self.keep, rest, no),
            'DROP':     lambda rest, no: self.add_layer(self.drop, rest, no),
            'ROOM':     self.add_room,
            'LEGEND':   self.add_legend,
            'DROPTEXT': lambda rest, no: self.add_regexp(self.droptext, rest, no),
            'NOROOM':   lambda rest, no: self.add_regexp(self.noroom, rest, no),
            'RETEXT':   self.add_retext,
            'COLOR':    self.add_color,
            'SET':      self.add_setting,
        }
        for no, line in enumerate(text.splitlines(), 1):
            if not self.is_directive(line):
                continue
            parts = line.strip().split(None, 1)
            key = parts[0].upper()
            rest = parts[1] if len(parts) > 1 else None
            handler = handlers.get(key)
            if handler is None:
                self.errors.append(f'{no}行目: 知らない項目です ({key})')
            else:
                handler(rest, no)

    def add_layer(self, target, rest, no):
        """「0:3」「*:5」「3」(グループ省略)を [lg, ly] にする。None = 何でも可"""
        if not rest:
            self.errors.append(f'{no}行目: レイヤの指定がありません')
            return
        spec = rest.split()[0]
        lg, ly = spec.split(':', 1) if ':' in spec else ('*', spec)
        target.append((self.parse_layer_no(lg), self.parse_layer_no(ly)))

    @staticmethod
    def parse_layer_no(s):
        """Jw_cad のレイヤ番号は 0-f の16進。10進の 0-15 も受け付ける。"""
        if not s or s == '*':
            return None
        if re.fullmatch(r'[0-9a-fA-F]', s):
            return int(s, 16)
        if re.fullmatch(r'1[0-5]|\d', s):
            return int(s)
        return None

    def add_color(self, rest, no):
        """COLOR 0:3 5 … そのレイヤの線色を書き換えて写す"""
        parts = rest.split() if rest else []
        if len(parts) < 2 or not re.fullmatch(r'\d+', parts[1]):
            self.errors.append(f'{no}行目: COLOR は「レイヤ 線番号」の形で書きます')
            return
        spec = self.layer_spec(parts[0])
        if spec is None:
            self.errors.append(f'{no}行目: レイヤの指定が読めません ({parts[0]})')
            return
        self.colors.append((spec, parts[1]))

    def add_room(self, rest, no):
        parts = rest.split() if rest else []
        if len(parts) < 2:
            self.errors.append(f'{no}行目: ROOM は「室名 記号」の形で書きます')
            return
        sym = parts.pop()
        self.rooms[normalize_key(''.join(parts))] = sym

    def add_legend(self, rest, no):
        if not rest:
            self.errors.append(f'{no}行目: LEGEND は「記号 説明」の形で書きます')
            return
        parts = rest.split(None, 1)
        self.legend.append((parts[0], parts[1] if len(parts) > 1 else ''))

    def add_regexp(self, target, rest, no):
        if not rest:
            return
        try:
            target.append(re.compile(rest))
        except re.error as e:
            self.errors.append(f'{no}行目: 検索文字の書き方が不正です ({e})')

    def add_retext(self, rest, no):
        """RETEXT 平面図 => 天井伏図"""
        if not rest:
            return
        pat, sep, rep = rest.partition('=>')
        if not sep or not pat.strip():
            self.errors.append(f'{no}行目: RETEXT は「検索 => 置換後」の形で書きます')
            return
        try:
            self.retext.append((re.compile(pat.strip()), rep.strip()))
        except re.error as e:
            self.errors.append(f'{no}行目: 検索文字の書き方が不正です ({e})')

    def add_setting(self, rest, no):
        parts = rest.split(None, 1) if rest else []
        key = parts[0].upper() if parts else None
        if key is None or key not in self.settings:
            self.errors.append(f'{no}行目: 知らない設定です ({parts[0] if parts else ""})')
            return
        self.settings[key] = parts[1].strip() if len(parts) > 1 else ''

    def __getitem__(self, key):
        return self.settings[key]

    def num(self, key):
        return to_num(self.settings[key]) or 0.0

    def int(self, key):
        try:
            return int(self.settings[key])
        except ValueError:
            return 0

    @property
    def whitelist(self):
        return bool(self.keep)

    def keep_layer(self, lg, ly):
        """レイヤを残すか。KEEP が1つでもあれば、書いたものだけを残す。"""
        if self.match_any(self.drop, lg, ly):
            return False
        if self.whitelist:
            return self.match_any(self.keep, lg, ly)
        return self['DEFAULT'].lower() != 'drop'

    @classmethod
    def layer_spec(cls, spec):
        """SET に書いた「0:0」「*:5」「3」を [lg, ly] にする。"""
        spec = (spec or '').strip()
        if not spec:
            return None
        lg, ly = spec.split(':', 1) if ':' in spec else ('*', spec)
        return (cls.parse_layer_no(lg), cls.parse_layer_no(ly))

    @staticmethod
    def match_any(rules, lg, ly):
        return any((rlg is None or rlg == lg) and (rly is None or rly == ly)
                   for rlg, rly in rules)


# --------------------------------------------------------------
# jwc_temp.txt の読み込み
#
#   座標は実寸(mm)。1/100 の図面なら 7280 と書いてあれば 7.28m。
#   一方 hcw/hch/hcd(文字の幅・高さ・間隔)は図寸(紙の上のmm)なので、
#   座標として使うには hs(縮尺の分母)を掛ける必要がある。
#   要素
#     x1 y1 x2 y2                線
#     x  y                       点
#     pt x y                     点
#     ci cx cy r [開始角 終了角 …]  円・円弧
#     ch x y f3 f4 "文字列        文字
#   属性
#     lg? ly? lc? lt? cn? …      直前までの状態が要素に効く
#   図面情報
#     h で始まる行
# --------------------------------------------------------------
RE_CH = re.compile(rf'ch\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+(.*)\Z', re.S)
RE_CI = re.compile(r'ci\s+(.*)\Z')
RE_PT = re.compile(rf'pt\s+({NUM})\s+({NUM})\s*\Z')
RE_LINE = re.compile(rf'({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s*\Z')
RE_POINT = re.compile(rf'({NUM})\s+({NUM})\s*\Z')


class Reader:
    def __init__(self):
        self.elements = []
        self.hcw = [3.0] * 11
        self.hch = [3.0] * 11
        self.hcd = [0.5] * 11
        self.hs = [1.0] * 16      # レイヤグループ 0-15 ごとの縮尺の分母
        self.hp1 = None
        self.skipped = {}
        self.skipped_at = {}      # (lg, ly) => 対応していない要素の数
        self.state = {}

    def parse(self, text):
        for raw in text.splitlines():
            s = raw.strip()
            if not s or s.startswith('#'):
                continue
            if s.startswith('h'):
                self.read_header(s)
                continue
            el = self.read_element(s)
            if el is not None:
                self.elements.append(el)
            elif self.ATTR_LINE.match(s):
                self.read_attribute(s)
            else:
                self.skip(s)
        return self

    # 属性として扱う行。これ以外の小文字始まりの行(ソリッド sl、
    # ブロック bl など)は、属性ではなく「対応していない要素」として数える。
    # 属性のつもりで取り込むと、書き出しのときにそのまま出てしまう。
    ATTR_LINE = re.compile(r'(?:lg|ly|lc|lt|cn)[0-9a-fA-F]')

    def skip(self, s):
        key = re.match(r'[A-Za-z]{1,3}|.', s).group(0)
        self.skipped[key] = self.skipped.get(key, 0) + 1
        at = (self.layer_no('lg'), self.layer_no('ly'))
        self.skipped_at[at] = self.skipped_at.get(at, 0) + 1

    def read_header(self, s):
        if m := re.match(r'hcw\s+(.*)\Z', s):
            self.hcw = self.char_table(m.group(1), self.hcw)
        elif m := re.match(r'hch\s+(.*)\Z', s):
            self.hch = self.char_table(m.group(1), self.hch)
        elif m := re.match(r'hcd\s+(.*)\Z', s):
            self.hcd = self.char_table(m.group(1), self.hcd)
        elif m := re.match(r'hs\s+(.*)\Z', s):
            self.hs = self.scale_table(m.group(1), self.hs)
        elif m := re.match(rf'hp1\s+({NUM})\s+({NUM})', s):
            self.hp1 = (float(m.group(1)), float(m.group(2)))

    @staticmethod
    def char_table(text, fallback):
        """文字種 1-10 の値。添字を文字種番号に合わせるため先頭に1つ詰める。"""
        vals = [v for v in (to_num(t) for t in text.split()) if v is not None]
        if not vals:
            return fallback
        table = ([vals[0]] + vals)[:11]
        while len(table) < 11:
            table.append(table[-1])
        return table

    @staticmethod
    def scale_table(text, fallback):
        """hs はレイヤグループ 0-15 の縮尺の分母が並ぶ。足りない分は先頭で埋める。"""
        vals = [v for v in (to_num(t) for t in text.split()) if v and v > 0]
        if not vals:
            return fallback
        return (vals + [vals[0]] * 16)[:16]

    def read_attribute(self, s):
        # lg0 / ly3 / lc2 / lt1 / cn3 / cn0 4 4 0.5 2 など。
        # 属性名は先頭2文字だけを見る。ここを [a-z]+ にすると、
        # レイヤ a〜f の「lyf」が丸ごと属性名になってしまい、
        # レイヤ番号が変わらないまま次の要素に持ち越されてしまう。
        # 状態は要素ごとに写しを持たせるため、毎回新しい辞書にする。
        key = s[:2]
        self.state = {**self.state, key: s}

    def read_element(self, s):
        if m := RE_CH.match(s):
            nums = [float(m.group(i)) for i in range(1, 5)]
            return self.make('text', nums, str=m.group(5).lstrip('"'))
        if m := RE_CI.match(s):
            nums = [to_num(t) for t in m.group(1).split()]
            if len(nums) < 3 or any(v is None for v in nums[:3]):
                return None
            return self.make('arc', [v if v is not None else 0.0 for v in nums])
        if m := RE_PT.match(s):
            return self.make('point', [float(m.group(1)), float(m.group(2))])
        if m := RE_LINE.match(s):
            return self.make('line', [float(m.group(i)) for i in range(1, 5)])
        if m := RE_POINT.match(s):
            return self.make('point', [float(m.group(1)), float(m.group(2))])
        return None

    def make(self, type_, nums, str=None):
        return {'type': type_, 'nums': nums, 'str': str, 'attr': self.state,
                'lg': self.layer_no('lg'), 'ly': self.layer_no('ly'),
                'cn': self.cn_no(), 'span': None}

    def layer_no(self, key):
        """lg0〜lgf / ly0〜lyf を 0〜15 にする。a〜f は16進の桁。"""
        line = self.state.get(key)
        if line is None:
            return 0
        m = re.fullmatch(r'[a-z]{2}([0-9a-fA-F])', line.strip())
        return int(m.group(1), 16) if m else 0

    def cn_no(self):
        line = self.state.get('cn')
        if line is None:
            return 3
        m = re.match(r'cn(\d+)', line)
        return int(m.group(1)) if m else 3


# --------------------------------------------------------------
# 読み込んだ図面
# --------------------------------------------------------------
class Doc:
    def __init__(self, reader, rules):
        self.elements = reader.elements
        self.hcw = reader.hcw
        self.hch = reader.hch
        self.hcd = reader.hcd
        self.hs = reader.hs
        self.hp1 = reader.hp1
        self.skipped = reader.skipped
        self.skipped_at = reader.skipped_at
        self.rel_ch = self.detect_ch_format(rules['CHFORMAT'])

    def scale(self, lg):
        """レイヤグループ lg の縮尺の分母。図寸(mm)にこれを掛けると座標値になる。"""
        if isinstance(lg, int) and 0 <= lg < len(self.hs):
            return self.hs[lg]
        return self.hs[0]

    def detect_ch_format(self, mode):
        """文字データ「ch 始点X 始点Y ○ ○ "文字列」の第3・第4フィールドは
        「文字列の長さ成分」と「終点座標」の2通りの説明がある。
        水平な文字なら、前者は第4=0、後者は第4=始点Y になるので、
        読み込んだデータから多数決で決める。
        """
        mode = (mode or '').lower()
        if mode == 'rel':
            return True
        if mode == 'abs':
            return False

        rel = abs_ = 0
        for el in self.elements:
            if el['type'] != 'text':
                continue
            x, y, f3, f4 = el['nums']
            if abs(y) < EPS:          # 判定に使えない
                continue
            if abs(f4) < EPS:
                rel += 1
            if abs(f4 - y) < EPS:
                abs_ += 1
            # 長さ成分なら第3フィールドは文字列の長さぶんしかない
            if abs(f3) < abs(x) * 0.5:
                rel += 1
        return not abs_ > rel        # 判断がつかなければ長さ成分


# --------------------------------------------------------------
# 天井伏図をつくる
# --------------------------------------------------------------
class CeilingPlan:
    def __init__(self, doc, rules):
        self.doc = doc
        self.rules = rules      # ログでも参照する
        self.log = []
        self.used = []            # 実際に置いた記号
        self.unknown = []         # ROOM に無かった室名
        self.assign = {}          # 室名 => 記号
        self.auto_legend = []     # 自動で作った仕上表の行
        self.assign_note = []     # ログ用の内訳
        self.counts = {}
        spec = (rules['SCALE'] or '').strip().lower()
        self.scale_fixed = None if spec in ('', 'auto') else to_num(spec)

    def bump(self, key, n=1):
        self.counts[key] = self.counts.get(key, 0) + n

    def build(self):
        kept = self.filter_layers(self.doc.elements)
        kept = self.recolor(kept)
        kept = self.process_texts(kept)
        self.build_assignment(kept)
        body = kept + self.make_walls(kept) + self.place_symbols(kept)
        if not body:
            raise ValueError('天井伏図にする要素がありません。選択したデータの'
                             f'レイヤは {self.layer_list()} です。'
                             '天伏図ルール.txt の KEEP をこの番号に'
                             '合わせてください。')

        dx, dy = self.offset(body)
        out = [self.move(el, dx, dy) for el in body]
        return out + self.legend(out)

    # --- 1. レイヤで残す/落とす --------------------------------
    def filter_layers(self, elements):
        kept = []
        for el in elements:
            if self.rules.keep_layer(el['lg'], el['ly']):
                kept.append(el)
            else:
                self.bump('layer_dropped')
        return kept

    def recolor(self, elements):
        """COLOR で指定したレイヤの線色を差し替える。すでに壁線が描いてある
        図面で、その線色だけを変えたいときに使う。"""
        if not self.rules.colors:
            return elements
        out = []
        for el in elements:
            for spec, color in self.rules.colors:
                if Rules.match_any([spec], el['lg'], el['ly']):
                    el = {**el, 'attr': {**el['attr'], 'lc': f'lc{color}'}}
                    self.bump('recolored')
                    break
            out.append(el)
        return out

    # --- 1b. 壁の中心線から壁線をつくる ------------------------
    #
    #   壁を「中心線を軸とする長方形」の集まりと考え、その集まりの
    #   外周だけを描く。長方形の内側に入った線は落とすので、
    #   交差部や T 字部で線が突き抜けたり、角に隙間ができたりしない。
    # -----------------------------------------------------------
    WALL_TOL = 0.01           # 内側判定のあそび(実寸mm)
    WALL_JOIN = 1.0           # 中心線どうしが取り付いているとみなす距離(実寸mm)
    WALL_MIN = 0.5            # これより短い切れ端は捨てる(実寸mm)

    def make_walls(self, elements):
        spec = self.rules['WALL_FROM'].strip()
        width = self.rules.num('WALL_WIDTH')
        target = Rules.layer_spec(spec)
        if spec.lower() in ('off', 'no') or width <= 0 or target is None:
            return []

        src = [el for el in elements if el['type'] == 'line'
               and Rules.match_any([target], el['lg'], el['ly'])]
        segs = [list(el['nums'][:4]) for el in src
                if math.hypot(el['nums'][2] - el['nums'][0],
                              el['nums'][3] - el['nums'][1]) > EPS]
        if not segs:
            # ここで止めると天井伏図そのものが作られなくなるので、
            # 壁線だけ諦めてログに理由を残す。
            where = ' '.join(f'{lg:x}:{ly:x}({t["fig"]}本)'
                             for (lg, ly), t in sorted(self.layer_tally().items())
                             if t['fig']) or 'なし'
            self.log.append('')
            self.log.append(f'※ 壁線を作れませんでした。SET WALL_FROM {spec} の'
                            'レイヤに線が 1 本もありません。')
            self.log.append(f'   線が入っているレイヤ: {where}')
            if hint := self.dashed_layers():
                self.log.append(f'   このうち一点鎖線が多いのは {hint} です。'
                                '壁の中心線はたいていこれです。')
            self.log.append('   WALL_FROM をこの中の番号に直し、KEEP にも同じ'
                            '番号を入れてください。')
            return []

        half = width / 2.0
        rects = [self.wall_rect(s, segs, half) for s in segs]
        pieces = []
        for i, r in enumerate(rects):
            for p, q in self.rect_edges(r):
                pieces += self.trim_edge(p, q, rects, i)
        pieces = self.merge_collinear(pieces)

        attr = self.wall_attr(src[0])
        lg, ly = self.wall_layer(src[0])
        out = [{'type': 'line', 'nums': [p[0], p[1], q[0], q[1]], 'str': None,
                'attr': attr, 'lg': lg, 'ly': ly, 'cn': src[0]['cn'],
                'span': None} for p, q in pieces]
        self.bump('walls', len(out))
        return out

    @classmethod
    def wall_rect(cls, seg, segs, half):
        """中心線を長方形にする。他の線が取り付く端は、角を塞ぐため half 伸ばす。"""
        x1, y1, x2, y2 = seg
        length = math.hypot(x2 - x1, y2 - y1)
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        if cls.joined(seg, (x1, y1), segs):
            x1, y1 = x1 - ux * half, y1 - uy * half
        if cls.joined(seg, (x2, y2), segs):
            x2, y2 = x2 + ux * half, y2 + uy * half
        return (x1, y1, x2, y2, half)

    @classmethod
    def joined(cls, seg, pt, segs):
        return any(other is not seg and cls.point_seg_dist(pt, other) <= cls.WALL_JOIN
                   for other in segs)

    @staticmethod
    def point_seg_dist(pt, seg):
        x1, y1, x2, y2 = seg
        dx, dy = x2 - x1, y2 - y1
        d2 = dx * dx + dy * dy
        if d2 < EPS:
            return math.hypot(pt[0] - x1, pt[1] - y1)
        t = ((pt[0] - x1) * dx + (pt[1] - y1) * dy) / d2
        t = max(0.0, min(1.0, t))
        return math.hypot(pt[0] - (x1 + t * dx), pt[1] - (y1 + t * dy))

    @staticmethod
    def rect_edges(rect):
        x1, y1, x2, y2, half = rect
        length = math.hypot(x2 - x1, y2 - y1)
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        nx, ny = -uy * half, ux * half
        c = [(x1 + nx, y1 + ny), (x2 + nx, y2 + ny),
             (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)]
        return [(c[i], c[(i + 1) % 4]) for i in range(4)]

    @classmethod
    def trim_edge(cls, p, q, rects, skip):
        length = math.hypot(q[0] - p[0], q[1] - p[1])
        if length < EPS:
            return []
        # 内側判定では長方形を tol だけ小さく見ているので、隠れる範囲は
        # その分だけ広げ直す。しないと端が tol だけはみ出して残る。
        margin = cls.WALL_TOL / length
        blocked = []
        for j, r in enumerate(rects):
            if j == skip:
                continue
            span = cls.clip_to_rect(p, q, r)
            if span:
                blocked.append((span[0] - margin, span[1] + margin))
        return cls.subtract(p, q, blocked)

    @classmethod
    def clip_to_rect(cls, p, q, rect):
        """線分 pq のうち、長方形の内側に入っている範囲を [0,1] の媒介変数で返す。"""
        x1, y1, x2, y2, half = rect
        length = math.hypot(x2 - x1, y2 - y1)
        tol = cls.WALL_TOL
        if length <= tol * 2 or half <= tol:
            return None
        ux, uy = (x2 - x1) / length, (y2 - y1) / length

        def local(pt):
            dx, dy = pt[0] - x1, pt[1] - y1
            return (dx * ux + dy * uy, -dx * uy + dy * ux)

        (u0, v0), (u1, v1) = local(p), local(q)
        lo, hi = 0.0, 1.0
        for a, d, mn, mx in ((u0, u1 - u0, tol, length - tol),
                             (v0, v1 - v0, -half + tol, half - tol)):
            if abs(d) < EPS:
                if a < mn or a > mx:
                    return None
                continue
            t0, t1 = (mn - a) / d, (mx - a) / d
            lo, hi = max(lo, min(t0, t1)), min(hi, max(t0, t1))
            if lo >= hi:
                return None
        return (lo, hi) if hi - lo > EPS else None

    @staticmethod
    def subtract(p, q, blocked):
        """線分 pq から、隠れる範囲を差し引いて残りを返す。"""
        keep, cur = [], 0.0
        for a, b in sorted(blocked):
            if a > cur:
                keep.append((cur, min(a, 1.0)))
            cur = max(cur, b)
            if cur >= 1.0:
                break
        if cur < 1.0:
            keep.append((cur, 1.0))

        def at(t):
            return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)

        length = math.hypot(q[0] - p[0], q[1] - p[1])
        return [(at(a), at(b)) for a, b in keep
                if (b - a) * length > CeilingPlan.WALL_MIN]

    @classmethod
    def merge_collinear(cls, pieces):
        """同じ直線に乗る切れ端をつなぐ。長い壁面が細切れのまま出るのを防ぐ。"""
        buckets = {}
        for p, q in pieces:
            dx, dy = q[0] - p[0], q[1] - p[1]
            length = math.hypot(dx, dy)
            if length <= cls.WALL_MIN:
                continue
            ux, uy = dx / length, dy / length
            if ux < -EPS or (abs(ux) < EPS and uy < 0):   # 向きをそろえる
                ux, uy = -ux, -uy
            c = -uy * p[0] + ux * p[1]
            key = (round(ux, 9), round(uy, 9), round(c, 3))
            t = sorted((ux * p[0] + uy * p[1], ux * q[0] + uy * q[1]))
            buckets.setdefault(key, []).append(tuple(t))

        out = []
        for (ux, uy, c), spans in buckets.items():
            t0, t1 = None, None
            for a, b in sorted(spans):
                if t0 is None:
                    t0, t1 = a, b
                elif a <= t1 + cls.WALL_MIN:
                    t1 = max(t1, b)
                else:
                    out.append((t0, t1, ux, uy, c))
                    t0, t1 = a, b
            if t0 is not None:
                out.append((t0, t1, ux, uy, c))

        def at(t, ux, uy, c):
            return (ux * t - uy * c, uy * t + ux * c)

        return [(at(t0, ux, uy, c), at(t1, ux, uy, c))
                for t0, t1, ux, uy, c in out]

    def wall_layer(self, src):
        spec = Rules.layer_spec(self.rules['WALL_LAYER'])
        if self.rules['WALL_LAYER'].strip().lower() == 'same' or spec is None:
            return src['lg'], src['ly']
        lg, ly = spec
        return (src['lg'] if lg is None else lg, src['ly'] if ly is None else ly)

    def wall_attr(self, src):
        a = {'lt': 'lt1'}
        lg, ly = self.wall_layer(src)
        a['lg'], a['ly'] = f'lg{lg:x}', f'ly{ly:x}'
        if self.rules['WALL_COLOR'].lower() != 'same':
            a['lc'] = f"lc{self.rules['WALL_COLOR']}"
        return a

    def layer_tally(self):
        """レイヤごとに 線の数 / 文字の数 / 線の長さの幅 / 文字の例 を集める。

        線の長さを見ると、壁の中心線(長い)・基準線(通り芯なので図より長い)・
        建具や柱(短い)の区別がつく。文字の例を見れば部屋名のレイヤが分かる。
        """
        def blank():
            return {'fig': 0, 'txt': 0, 'other': 0, 'len': [], 'sample': [],
                    'lt': {}}

        tally = {}
        for key, n in self.doc.skipped_at.items():
            tally.setdefault(key, blank())['other'] = n
        for el in self.doc.elements:
            t = tally.setdefault((el['lg'], el['ly']), blank())
            if el['type'] == 'text':
                t['txt'] += 1
                if len(t['sample']) < 3 and el['str'].strip():
                    t['sample'].append(el['str'].strip())
            else:
                t['fig'] += 1
                lt = (el['attr'].get('lt') or 'lt1')[2:]
                t['lt'][lt] = t['lt'].get(lt, 0) + 1
                if el['type'] == 'line':
                    n = el['nums']
                    t['len'].append(math.hypot(n[2] - n[0], n[3] - n[1]))
        return tally

    def layer_summary(self):
        """選択したデータのレイヤ別内訳。KEEP / DROP に書く番号はこれで調べる。"""
        lines = []
        for (lg, ly), t in sorted(self.layer_tally().items()):
            mark = '残す' if self.rules.keep_layer(lg, ly) else '除外'
            row = f"  {lg:x}:{ly:x}   線 {t['fig']:4d}   文字 {t['txt']:4d}   {mark}"
            if t['other']:
                row += f"   ★扱えない要素 {t['other']}"
            if t['lt']:
                order = sorted(t['lt'].items(), key=lambda kv: -kv[1])
                row += '   線種 ' + ' '.join(f'{k}x{v}' for k, v in order[:3])
            if t['len']:
                row += f"   長さ {fmt(min(t['len']))}〜{fmt(max(t['len']))}"
            if t['sample']:
                row += f"   文字の例 {' / '.join(t['sample'])}"
            lines.append(row)
        if lines:
            lines.append('')
            lines.append('  線種 1=実線 2〜4=点線 5〜6=一点鎖線 7〜8=二点鎖線。'
                         '壁の中心線や基準線は 5〜8 に入ります。')
            lines.append('  ★扱えない要素 … ソリッドやブロック図形。そのレイヤの'
                         '中身は写せません。')
            lines.append('    Jw_cad の [編集]-[図形分解] でばらすと扱えるように'
                         'なります。')
        return lines

    def dashed_layers(self):
        """鎖線(線種5〜8)が半分以上のレイヤ。壁の中心線・基準線の候補。"""
        out = []
        for (lg, ly), t in sorted(self.layer_tally().items()):
            dashed = sum(v for k, v in t['lt'].items() if k in '5678')
            if t['fig'] and dashed * 2 > t['fig']:
                out.append(f'{lg:x}:{ly:x}')
        return ' '.join(out)

    def layer_list(self):
        """1行で並べたレイヤ番号と要素数。エラーの文面に入れる。"""
        return ' '.join(f'{lg:x}:{ly:x}({t["fig"] + t["txt"]})'
                        for (lg, ly), t in sorted(self.layer_tally().items())
                        if t['fig'] or t['txt'])

    # --- 2. 文字の削除と置換 -----------------------------------
    def process_texts(self, elements):
        out = []
        for el in elements:
            if el['type'] != 'text':
                out.append(el)
                continue
            s = before = el['str']
            if any(rx.search(s) for rx in self.rules.droptext):
                self.bump('text_dropped')
                continue
            for rx, rep in self.rules.retext:
                s = rx.sub(rep, s)
            if not s.strip():
                self.bump('text_dropped')
                continue
            if s == before:
                out.append(el)
            else:
                # 文字列が変わったので、文字データが持つ長さも取り直す。
                # そのままだと Jw_cad 側で文字が引き伸ばされる。
                self.bump('text_replaced')
                ux, uy, _ = self.direction(el)
                w = self.text_width(s, el['cn'], el['lg'])
                out.append({**el, 'str': s, 'span': (ux * w, uy * w)})
        return out

    # --- 3a. 室名ごとの記号を決める ----------------------------
    #
    #   実務では室名がその都度変わるので、ルールファイルに室名を
    #   登録しておく方式では追いつかない。図面にある室名を全部拾い、
    #   次の順で記号を決める。
    #     1. ROOM に登録があればそれ（手で決めたものが最優先）
    #     2. 図面の仕上表に同じ天井仕上が載っている室と同じ記号
    #     3. 新しい番号を振る
    # -----------------------------------------------------------
    def build_assignment(self, elements):
        self.assign = {}          # 正規化した室名 => 記号
        self.auto_legend = []     # 自動で作った仕上表の行
        self.assign_note = []     # ログ用の内訳

        names, display = [], {}
        for el in elements:
            if el['type'] != 'text' or not self.on_room_layer(el):
                continue
            text = el['str'].strip()
            if not text or any(p.search(text) for p in self.rules.noroom):
                continue
            key = normalize_key(text)
            if key not in display:
                display[key] = text
                names.append(key)
        if not names:
            return

        auto = self.rules['ROOM_AUTO'].lower() in ('on', 'yes', '1')
        finishes = self.finish_table(names) if auto else {}
        prefix = self.rules['SYMBOL_PREFIX'].strip()
        number = self.next_symbol_no(prefix)
        by_finish = {}

        for key in names:
            sym = self.lookup_room(display[key])
            if sym is not None:
                self.assign[key] = sym
                self.assign_note.append((display[key], sym, 'ルールの ROOM'))
                continue
            if not auto:
                continue
            finish = finishes.get(key)
            # 突き合わせは空白を取ってから。同じ仕上でも「木軸下地　石膏…」
            # 「木軸下地石膏…」のように書き方が揺れるため。
            fkey = re.sub(r'[\s　]', '', finish) if finish else ''
            if fkey and fkey in by_finish:
                self.assign[key] = by_finish[fkey]
                self.assign_note.append(
                    (display[key], by_finish[fkey], '同じ天井仕上'))
                continue
            sym = f'{prefix}{number}'
            number += 1
            self.assign[key] = sym
            if finish:
                by_finish[fkey] = sym
                self.assign_note.append((display[key], sym, f'仕上表: {finish}'))
            else:
                self.assign_note.append((display[key], sym, '自動採番'))
            # 仕上が読めなかった行は空欄にせず室名を入れておく。空の行が
            # 並ぶと表が壊れて見えるうえ、どの室の行か分からなくなる。
            self.auto_legend.append((sym, finish or f'（{display[key]}）'))
            self.unknown.append(display[key])

    def next_symbol_no(self, prefix):
        """空いている番号の先頭。ルールに書いた記号とぶつからないようにする。"""
        used = [s for s, _ in self.rules.legend] + list(self.rules.rooms.values())
        nums = [int(m.group(1)) for s in used
                if (m := re.fullmatch(re.escape(prefix) + r'(\d+)', s.strip()))]
        return max(nums, default=0) + 1

    def finish_table(self, names):
        """図面に描いてある仕上表から「室名 => 天井仕上」を読む。

        表の作りは物件ごとに違うので、罫線ではなく文字の位置で読む。
        室名レイヤ以外に室名と同じ文字が並んでいるところを表とみなし、
        その右側にある文字を仕上とする。天井高のような数字だけの
        文字は読み飛ばす。
        """
        spec = self.rules['FINISH_TABLE'].strip()
        if spec.lower() in ('off', 'no', ''):
            return {}

        want = Rules.layer_spec(spec) if spec.lower() != 'auto' else None
        hits = {}
        for el in self.doc.elements:
            if el['type'] != 'text' or self.on_room_layer(el):
                continue
            if want and not Rules.match_any([want], el['lg'], el['ly']):
                continue
            exact, loose = self.match_names(el['str'], names)
            if exact or loose:
                hits.setdefault((el['lg'], el['ly']), []).append(
                    (exact, loose, el))

        if not hits:
            return {}
        layer, cells = max(hits.items(), key=lambda kv: len(kv[1]))
        if len(cells) < 3:            # 表と呼べるだけの行数がないなら諦める
            return {}

        texts = self.cells_by_row(layer, [el for _, _, el in cells])
        table = {}
        # 室名がそのまま一致する行を先に入れる。枝番違いの行に上書き
        # されないようにするため。
        for use_exact in (True, False):
            for exact, loose, el in cells:
                targets = exact if use_exact else loose
                text = texts.get(id(el), '')
                if text:
                    for name in targets:
                        table.setdefault(name, text)
        if table:
            self.log.append('')
            self.log.append(f'図面の仕上表をレイヤ {layer[0]:x}:{layer[1]:x} から'
                            f'読みました（{len(table)}室）。')
        return table

    @staticmethod
    def match_names(text, names):
        """表のセルの文字が、図面のどの室名を指しているかを返す。

        「収納1・収納2」のように 1 つのセルに 2 室まとめて書いてあることが
        あるので、中黒などで切った分も見る。表が「倉庫」で図面が「倉庫①」、
        その逆もあるので、頭の一致は双方向に見る。
        """
        exact, loose = [], []
        keys = [normalize_key(text)]
        keys += [normalize_key(p) for p in re.split(r'[・･/／、,]', text)]
        for key in keys:
            if not key:
                continue
            for n in names:
                if n == key and n not in exact:
                    exact.append(n)
                elif n != key and (n.startswith(key) or key.startswith(n)) \
                        and n not in loose:
                    loose.append(n)
        return exact, [n for n in loose if n not in exact]

    def cells_by_row(self, layer, name_cells):
        """室名セルごとに、その行の右側にある文字をつないで返す。

        行の高さは表によって違う（2行書きの行と1行の行が混ざる）ので、
        帯の幅を決め打ちにせず、いちばん近い室名セルの行に振り分ける。
        また、右側かどうかは文字の「書き出し位置」で見る。文字の末尾で
        見ると、長い室名が欄からはみ出したときに右の欄を取りこぼす。
        """
        if not name_cells:
            return {}
        margin = self.doc.hcw[3] * self.scale(layer[0])   # 1文字分だけ余裕を見る
        left = min(el['nums'][0] for el in name_cells)
        rows = sorted(((el['nums'][1], el) for el in name_cells),
                      key=lambda t: -t[0])              # 上から下へ
        bounds = self.row_bounds([y for y, _ in rows])
        found = {id(el): [] for el in name_cells}

        for other in self.doc.elements:
            if other['type'] != 'text' or (other['lg'], other['ly']) != layer:
                continue
            ox, oy = other['nums'][0], other['nums'][1]
            if ox < left + margin:
                continue          # 室名の欄より左（用途区分など）は見ない
            s = other['str'].strip()
            if not s or re.fullmatch(r'[\d,.\-〜~ 　]+', s):
                continue          # 天井高などの数字だけの欄は仕上ではない
            for (top, bottom), (_, el) in zip(bounds, rows):
                if bottom <= oy < top:
                    found[id(el)].append((-oy, ox, s))
                    break         # 表の外（見出しなど）はどの行にも入らない

        return {k: ' '.join(s for _, _, s in sorted(v)) for k, v in found.items()}

    @staticmethod
    def row_bounds(ys):
        """行の上下の境目。隣の行との中間で切る。

        いちばん近い行に入れるだけだと、表の見出しや表題まで最初の行に
        吸い込まれてしまうので、上端と下端も 1 行分で打ち切る。
        """
        if len(ys) == 1:
            return [(ys[0] + 1e9, ys[0] - 1e9)]
        mids = [(a + b) / 2.0 for a, b in zip(ys, ys[1:])]
        out = []
        for i, y in enumerate(ys):
            top = mids[i - 1] if i else y + (ys[0] - ys[1]) / 2.0
            bottom = mids[i] if i < len(mids) else y - (ys[-2] - ys[-1]) / 2.0
            out.append((top, bottom))
        return out

    # --- 3. 室名の下に天井仕上記号を置く -----------------------
    def place_symbols(self, elements):
        scn = max(1, min(10, self.rules.int('SYMBOL_CN')))
        dy_zusun = self.rules.num('SYMBOL_DY')
        out = []

        for el in elements:
            if el['type'] != 'text':
                continue
            sym = self.room_symbol(el)
            if sym is None:
                continue

            x, y = el['nums'][0], el['nums'][1]
            ux, uy, length = self.direction(el)
            # 文字の基準線に対して右まわり 90 度が「下」
            px, py = uy, -ux

            dy = dy_zusun * self.scale(el['lg'])
            w = self.text_width(sym, scn, el['lg'])
            cx = x + ux * length / 2.0 + px * dy
            cy = y + uy * length / 2.0 + py * dy

            bx, by = cx - ux * w / 2.0, cy - uy * w / 2.0
            out += self.symbol_box(el, scn, bx, by, w, ux, uy)
            out.append({'type': 'text', 'nums': [bx, by, 0, 0],
                        'str': sym, 'attr': self.symbol_attr(el, scn),
                        'lg': el['lg'], 'ly': el['ly'], 'cn': scn,
                        'span': (ux * w, uy * w)})
            if sym not in self.used:
                self.used.append(sym)
            self.bump('symbols')
        return out

    def room_symbol(self, el):
        """この文字に置く記号。ROOM に無くても、部屋名レイヤの文字なら
        仮記号を置く。室が増えるたびにルールファイルを直さずに済ませ、
        書き漏らしを図面上で見つけられるようにするため。"""
        text = el['str'].strip()
        # NOROOM は「そもそも室名ではない」の意味なので ROOM より優先する。
        if not text or any(p.search(text) for p in self.rules.noroom):
            return None
        sym = self.assign.get(normalize_key(text))
        if sym is not None:
            return sym
        sym = self.lookup_room(text)
        if sym is not None:
            return sym
        if not self.on_room_layer(el):
            return None
        default = self.rules['ROOM_DEFAULT'].strip()
        if not default or default.lower() in ('no', 'off'):
            return None
        if text not in self.unknown:
            self.unknown.append(text)
        return default

    def similar_rooms(self, text):
        """惜しい登録を挙げる。「倉庫」に対する「倉庫①」のような取り違えは
        気づきにくいので、ログで指摘する。"""
        key = normalize_key(text)
        if len(key) < 2:
            return ''
        near = [k for k in self.rules.rooms
                if k != key and (k.startswith(key[:2]) or key.startswith(k[:2]))]
        return ' / '.join(sorted(near)[:4])

    def on_room_layer(self, el):
        spec = self.rules['ROOM_LAYER'].strip()
        if spec.lower() in ('off', 'no', ''):
            return False
        target = Rules.layer_spec(spec)
        return target is not None and Rules.match_any([target], el['lg'], el['ly'])

    def lookup_room(self, text):
        key = normalize_key(text)
        if key in self.rules.rooms:
            return self.rules.rooms[key]
        if self.rules['ROOM_MATCH'].lower() != 'prefix':
            return None
        # 「事務室(14.46㎡)」のように後ろに何か付いている場合。
        # 取り違えを避けるため、長い室名から順に見る。
        hits = [k for k in self.rules.rooms if key.startswith(k)]
        if hits:
            return self.rules.rooms[max(hits, key=len)]
        # 逆に、図面が「倉庫」で登録が「倉庫①」「倉庫②」の場合。
        # 枝番を取った名前で引く。記号が割れているときは引かない。
        return self.rules.room_bases.get(key)

    def direction(self, el):
        """文字の向き。単位ベクトルと文字列の長さを返す。"""
        x, y, f3, f4 = el['nums']
        if el.get('span'):
            dx, dy = el['span']
        elif self.doc.rel_ch:
            dx, dy = f3, f4
        else:
            dx, dy = f3 - x, f4 - y
        length = math.hypot(dx, dy)
        if length < EPS:
            return 1.0, 0.0, self.text_width(el['str'], el['cn'])
        return dx / length, dy / length, length

    @staticmethod
    def is_halfwidth(c):
        """Shift_JIS で1バイトになる文字。半角英数記号と半角カナ。"""
        return c.isascii() or '｡' <= c <= 'ﾟ'

    def text_width(self, text, cn, lg=0):
        """文字列の長さを図面の座標値(実寸mm)で返す。半角は全角の半分で数える。

        hcw/hcd は図寸なので、縮尺の分母を掛けて座標値に直す。これを忘れると
        1/100 の図面で長さが 1/100 になり、文字が潰れて重なる。
        """
        if not text:
            return 0.0
        w = self.doc.hcw[cn]
        d = self.doc.hcd[cn]
        han = sum(1 for c in text if self.is_halfwidth(c))
        zen = len(text) - han
        return (w * zen + w / 2.0 * han + d * (len(text) - 1)) * self.scale(lg)

    def scale(self, lg):
        """図寸(mm)を図面の座標値に直す倍率。SET SCALE で固定もできる。"""
        if self.scale_fixed is not None:
            return self.scale_fixed
        return self.doc.scale(lg)

    def symbol_box(self, el, scn, bx, by, w, ux, uy):
        """記号を囲む四角。文字が傾いていれば枠も一緒に傾ける。

        (bx, by) は文字の左下。文字の並ぶ向きが (ux, uy)、
        その左まわり 90 度 (-uy, ux) が文字の高さの向きになる。
        """
        if self.rules['SYMBOL_BOX'].lower() not in ('on', 'yes', '1'):
            return []
        s = self.scale(el['lg'])
        pad = self.rules.num('SYMBOL_BOX_PAD') * s
        h = self.doc.hch[scn] * s
        attr = self.symbol_box_attr(el)

        def pt(along, up):
            return (bx + ux * along - uy * up, by + uy * along + ux * up)

        corners = [pt(-pad, -pad), pt(w + pad, -pad),
                   pt(w + pad, h + pad), pt(-pad, h + pad)]
        box = []
        for i in range(4):
            x1, y1 = corners[i]
            x2, y2 = corners[(i + 1) % 4]
            box.append({'type': 'line', 'nums': [x1, y1, x2, y2], 'str': None,
                        'attr': attr, 'lg': el['lg'], 'ly': el['ly'],
                        'cn': scn, 'span': None})
        self.bump('symbol_boxes')
        return box

    def symbol_box_attr(self, el):
        a = self.symbol_attr(el, None)
        a.pop('cn', None)
        a['lt'] = 'lt1'           # 枠は実線で描く
        if self.rules['SYMBOL_BOX_COLOR'].lower() != 'same':
            a['lc'] = f"lc{self.rules['SYMBOL_BOX_COLOR']}"
        return a

    def symbol_attr(self, el, scn):
        a = dict(el['attr'])
        if scn is not None:
            a['cn'] = f'cn{scn}'
        spec = self.rules['SYMBOL_LAYER']
        if spec.lower() != 'same':
            lg, ly = spec.split(':', 1) if ':' in spec else ('*', spec)
            if lg != '*':
                a['lg'] = f'lg{lg}'
            if ly != '*':
                a['ly'] = f'ly{ly}'
        if self.rules['SYMBOL_COLOR'].lower() != 'same':
            a['lc'] = f"lc{self.rules['SYMBOL_COLOR']}"
        return a

    # --- 4. 指示点へ移す ---------------------------------------
    def offset(self, elements):
        if self.doc.hp1 is None:
            self.log.append('作図位置の指示がなかったので、'
                            '元の平面図と同じ位置に作図します。')
            return 0.0, 0.0
        x0, y0, _, _ = self.bbox(elements)
        return self.doc.hp1[0] - x0, self.doc.hp1[1] - y0

    def bbox(self, elements):
        xs, ys = [], []
        for el in elements:
            n = el['nums']
            if el['type'] == 'line':
                xs += [n[0], n[2]]
                ys += [n[1], n[3]]
            elif el['type'] == 'point':
                xs.append(n[0])
                ys.append(n[1])
            elif el['type'] == 'arc':
                cx, cy, r = n[0], n[1], n[2]
                xs += [cx - r, cx + r]
                ys += [cy - r, cy + r]
            elif el['type'] == 'text':
                ux, uy, length = self.direction(el)
                xs += [n[0], n[0] + ux * length]
                ys += [n[1], n[1] + uy * length]
        if not xs:
            return 0.0, 0.0, 0.0, 0.0
        return min(xs), min(ys), max(xs), max(ys)

    def move(self, el, dx, dy):
        if abs(dx) < EPS and abs(dy) < EPS:
            return el
        n = list(el['nums'])
        if el['type'] == 'line':
            n[0] += dx
            n[1] += dy
            n[2] += dx
            n[3] += dy
        elif el['type'] in ('point', 'arc'):
            n[0] += dx
            n[1] += dy
        elif el['type'] == 'text':
            n[0] += dx
            n[1] += dy
            # 終点座標で持っている書式なら、終点も動かす
            if not self.doc.rel_ch and not el.get('span'):
                n[2] += dx
                n[3] += dy
        return {**el, 'nums': n}

    # --- 5. 仕上表(凡例) ---------------------------------------
    def legend(self, placed):
        mode = self.rules['LEGEND_MODE'].lower()
        if mode == 'no':
            return []
        rows = list(self.rules.legend)
        if mode == 'used':
            rows = [r for r in rows if r[0] in self.used]
        # 自動で割り当てた記号の行を足す。仕上が読めていなければ空欄にし、
        # 図面の上で書き込めるようにする。
        known = {r[0] for r in rows}
        rows += [r for r in self.auto_legend
                 if r[0] not in known and r[0] in self.used]
        if not rows:
            return []

        cn = max(1, min(10, self.rules.int('LEGEND_CN')))
        lg = self.legend_lg(placed)
        # 設定はすべて図寸mm。座標に使うので縮尺の分母を掛けておく。
        s = self.scale(lg)
        rh = self.rules.num('LEGEND_RH') * s
        th = self.doc.hch[cn] * s
        pad = 2.0 * s

        # 設定した幅は最小値として扱い、文字がはみ出すときは広げる。
        def fit(strings, minimum):
            return max(minimum * s,
                       max(self.text_width(t, cn, lg) for t in strings) + pad * 2)

        w1 = fit(['記号'] + [r[0] for r in rows], self.rules.num('LEGEND_W1'))
        w2 = fit([self.rules['LEGEND_TITLE']] + [r[1] for r in rows],
                 self.rules.num('LEGEND_W2'))
        w = w1 + w2
        h = rh * (len(rows) + 1)
        x0, y0 = self.legend_origin(placed, w, h, s)
        out = []

        def add(type_, nums, kind, text=None):
            out.append({'type': type_, 'nums': nums, 'str': text,
                        'attr': self.legend_attr(kind),
                        'lg': lg, 'ly': 0, 'cn': cn, 'span': None})

        # 外枠。中の罫線とは線色を変えられる。
        add('line', [x0, y0, x0 + w, y0], 'border')
        add('line', [x0, y0 + h, x0 + w, y0 + h], 'border')
        add('line', [x0, y0, x0, y0 + h], 'border')
        add('line', [x0 + w, y0, x0 + w, y0 + h], 'border')
        # 中の罫線
        add('line', [x0 + w1, y0, x0 + w1, y0 + h], 'line')
        for i in range(1, len(rows) + 1):
            add('line', [x0, y0 + rh * i, x0 + w, y0 + rh * i], 'line')

        # 見出し(最上段)と各行。上から順に並べる。
        def ty(i):
            return y0 + h - rh * (i + 1) + (rh - th) / 2.0

        add('text', [x0 + pad, ty(0), 0, 0], 'text', '記号')
        add('text', [x0 + w1 + pad, ty(0), 0, 0], 'text', self.rules['LEGEND_TITLE'])
        for i, (sym, desc) in enumerate(rows, 1):
            add('text', [x0 + pad, ty(i), 0, 0], 'text', sym)
            add('text', [x0 + w1 + pad, ty(i), 0, 0], 'text', desc)

        for el in out:
            if el['type'] == 'text':
                el['span'] = (self.text_width(el['str'], cn, lg), 0.0)
        self.counts['legend_rows'] = len(rows)
        return out

    def legend_lg(self, placed):
        """仕上表を置くレイヤグループ。縮尺はグループごとに違うので要る。"""
        spec = self.rules['LEGEND_LAYER']
        if spec.lower() != 'same' and ':' in spec:
            g = spec.split(':', 1)[0]
            if re.fullmatch(r'[0-9a-fA-F]', g):
                return int(g, 16)
        # same のときは図の大半が乗っているグループに合わせる。
        groups = [el['lg'] for el in placed if isinstance(el['lg'], int)]
        return max(set(groups), key=groups.count) if groups else 0

    def legend_origin(self, placed, w, h, s):
        # LEGEND_POS は図面の座標(実寸mm)。図とのすき間だけ図寸で持つ。
        pos = self.rules['LEGEND_POS'].strip()
        if pos.lower() != 'auto':
            if m := re.fullmatch(rf'({NUM})\s*,\s*({NUM})', pos):
                return float(m.group(1)), float(m.group(2)) - h
        _, _, x1, y1 = self.bbox(placed)
        return x1 + 10.0 * s, y1 - h

    def legend_attr(self, kind):
        """仕上表の属性。kind は border(外枠) / line(中の罫線) / text(文字)。"""
        a = {}
        spec = self.rules['LEGEND_LAYER']
        if spec.lower() != 'same':
            lg, ly = spec.split(':', 1) if ':' in spec else ('*', spec)
            if lg != '*':
                a['lg'] = f'lg{lg}'
            if ly != '*':
                a['ly'] = f'ly{ly}'
        color = {'border': 'LEGEND_BORDER_COLOR',
                 'line': 'LEGEND_LINE_COLOR'}.get(kind, 'LEGEND_COLOR')
        if self.rules[color].lower() != 'same':
            a['lc'] = f"lc{self.rules[color]}"
        if kind == 'text':
            a['cn'] = f"cn{max(1, min(10, self.rules.int('LEGEND_CN')))}"
        else:
            a['lt'] = 'lt1'
        return a


# --------------------------------------------------------------
# 書き出し
# --------------------------------------------------------------
class Writer:
    ATTR_ORDER = ['lg', 'ly', 'lc', 'lt', 'cn']

    def __init__(self, rel_ch):
        self.rel = rel_ch
        self.cur = {}
        self.out = []

    def add(self, el):
        self.attrs(el.get('attr') or {})
        self.out.append(self.element_line(el))

    def attrs(self, a):
        keys = self.ATTR_ORDER + [k for k in a if k not in self.ATTR_ORDER]
        for k in keys:
            v = a.get(k)
            if v is None or self.cur.get(k) == v:
                continue
            self.cur[k] = v
            self.out.append(v)

    def element_line(self, el):
        n = el['nums']
        if el['type'] == 'line':
            return ' '.join(fmt(v) for v in n[:4])
        if el['type'] == 'point':
            return f'pt {fmt(n[0])} {fmt(n[1])}'
        if el['type'] == 'arc':
            return 'ci ' + ' '.join(fmt(v) for v in n)
        return self.text_line(el)

    def text_line(self, el):
        x, y = el['nums'][0], el['nums'][1]
        if el.get('span'):
            f3, f4 = el['span']
            if not self.rel:
                f3, f4 = x + f3, y + f4
        else:
            f3, f4 = el['nums'][2], el['nums'][3]
        return f'ch {fmt(x)} {fmt(y)} {fmt(f3)} {fmt(f4)} "{el["str"]}'

    def text(self):
        """先頭に hd を書かないので、範囲選択した元の平面図は消えずに残る。"""
        return '\r\n'.join(self.out) + '\r\n'


# --------------------------------------------------------------
# メイン
# --------------------------------------------------------------
def abort_with(temp_path, message):
    if temp_path and os.path.exists(temp_path):
        write_cp932(temp_path, f'he {message}\r\n')
    print(f'{APPTITLE}: {message}', file=sys.stderr)
    sys.exit(1)


def find_temp():
    """jwc_temp.txt を探す。

    Jw_cad はカレントディレクトリに作成するが、環境によって
    バッチファイルのフォルダになることもあるので両方を見る。
    """
    for path in (os.path.join(os.getcwd(), 'jwc_temp.txt'),
                 os.path.join(script_dir(), 'jwc_temp.txt')):
        if os.path.exists(path):
            return path
    return None


def main():
    temp = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else find_temp()
    rpath = (sys.argv[2] if len(sys.argv) > 2 and sys.argv[2]
             else os.path.join(script_dir(), '天伏図ルール.txt'))

    if not temp or not os.path.exists(temp):
        print(f'{APPTITLE}: jwc_temp.txt が見つかりません。バッチファイルと '
              'jww_ceiling_plan.py が同じフォルダにあるか確認してください。',
              file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(rpath):
        abort_with(temp, f'ルールファイルが見つかりません。{os.path.basename(rpath)} '
                         'をスクリプトと同じ場所に置いてください。')

    rules = Rules.load(rpath)
    if rules.errors:
        abort_with(temp, f'ルールファイルに誤りがあります。 {rules.errors[0]}')

    reader = Reader().parse(read_cp932(temp))
    if not reader.elements:
        abort_with(temp, '図形が選択されていません。')

    doc = Doc(reader, rules)
    plan = CeilingPlan(doc, rules)

    if '--layers' in sys.argv:
        # レイヤ調査だけして終わる。作図はしない。
        write_log(rpath, doc, plan, 0)
        abort_with(temp, 'レイヤ別の内訳を jww_ceiling_plan.log に'
                         '書き出しました。メモ帳で開きます。')

    try:
        elements = plan.build()
    except ValueError as e:
        # レイヤの内訳を見れば直せることが多いので、失敗時もログは残す。
        write_log(rpath, doc, plan, 0)
        abort_with(temp, str(e))

    writer = Writer(doc.rel_ch)
    for el in elements:
        writer.add(el)
    write_cp932(temp, writer.text())

    write_log(rpath, doc, plan, len(elements))


def pad(text, width):
    """全角を2桁と数えて右に空白を足す。ログの桁を揃えるため。"""
    w = sum(1 if CeilingPlan.is_halfwidth(c) else 2 for c in text)
    return text + ' ' * max(0, width - w)


def disp_width(text):
    return sum(1 if CeilingPlan.is_halfwidth(c) else 2 for c in text)


def write_log(rpath, doc, plan, written):
    c = plan.counts
    lines = [
        f"{APPTITLE}  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f'ルールファイル : {rpath}',
        f'縮尺           : 1/{fmt(plan.scale(0))}'
        + ('' if plan.scale_fixed is None else '  (SET SCALE で固定)'),
        f"文字データ書式 : {'rel(長さ成分)' if doc.rel_ch else 'abs(終点座標)'}",
        f'読み込んだ要素 : {len(doc.elements)}',
        f"レイヤで除外   : {c.get('layer_dropped', 0)}",
        f"作った壁線     : {c.get('walls', 0)}",
        f"文字を削除     : {c.get('text_dropped', 0)}",
        f"文字を置換     : {c.get('text_replaced', 0)}",
        f"置いた記号     : {c.get('symbols', 0)}"
        + (f"  （うち仮記号 {len(plan.unknown)}）" if plan.unknown else ''),
        f"記号の枠       : {c.get('symbol_boxes', 0)}",
        f"凡例の行数     : {c.get('legend_rows', 0)}",
        f'書き出した要素 : {written}',
        '',
        'レイヤ別の内訳（KEEP / DROP に書く番号はここで調べます）',
    ]
    lines += plan.layer_summary()
    if plan.assign_note:
        lines.append('')
        lines.append('室名と記号の対応')
        width = max(disp_width(n) for n, _, _ in plan.assign_note)
        lines += [f'  {pad(n, width)}  {s:6} {why}'
                  for n, s, why in plan.assign_note]
    if plan.unknown:
        default = plan.rules['ROOM_DEFAULT'].strip()
        lines.append('')
        lines.append('ルールに登録が無く、記号を自動で割り当てた室名です。')
        lines.append('この割り当てで固定したいときは、下の行を 天伏図ルール.txt の')
        lines.append('ROOM の並びに貼り付けてください（記号は変えてかまいません）。')
        lines.append('')
        width = max(disp_width(n) for n in plan.unknown)
        for n in plan.unknown:
            sym = plan.assign.get(normalize_key(n), default)
            row = f'ROOM {pad(n, width)}  {sym}'
            if near := plan.similar_rooms(n):
                row += f'      ← 似た登録があります: {near}'
            lines.append(row)
    if doc.skipped:
        lines.append('')
        lines.append('対応していない要素があったため、複写されませんでした:')
        lines += [f'  {k} … {v} 個' for k, v in doc.skipped.items()]
    lines += plan.log
    try:
        write_cp932(os.path.join(script_dir(), 'jww_ceiling_plan.log'),
                    '\r\n'.join(lines) + '\r\n')
    except OSError:
        pass          # ログが書けなくても作図は成立させる


if __name__ == '__main__':
    main()
