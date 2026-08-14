#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""天井伏図生成の回帰テスト。

これまでに出た不具合を 1 件ずつ確かめる。直したものが次の変更で
壊れていないかを、毎回まとめて見るためのもの。

    python3 tools/test.py          全部走らせる
    python3 tools/test.py 壁線     名前に「壁線」を含むものだけ

新しい不具合を直したら、必ずここに 1 件足すこと。
"""

import io
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
SCRIPT = os.path.join(SRC, 'jww_ceiling_plan.py')
NUM = r'[-+]?(?:\d+\.?\d*|\.\d+)'


def read(path):
    return io.open(path, encoding='utf-8').read()


PLAN_1F = read(os.path.join(SRC, 'テスト', 'sample_平面図.txt'))
PLAN_HEX = read(os.path.join(SRC, 'テスト', 'sample_16進レイヤ.txt'))
RULES = read(os.path.join(SRC, '天伏図ルール.txt'))

# 2階の図面を模したもの。行の高さがまちまちで、室名が欄からはみ出し、
# 1 つのセルに 2 室まとめて書いてある表を持つ。
_V = '石膏ﾎﾞｰﾄﾞt=9.5の上ﾋﾞﾆﾙｸﾛｽ貼り'
_ROOMS_2F = [('LDK', 1800, 1800), ('洋室-2', 6000, 6000), ('洋室-3', 6000, 1800),
             ('UB1616', 900, 6300), ('脱衣・洗濯', 2600, 6300), ('WC', 4200, 6300),
             ('廊下', 4200, 5000), ('収納', 2600, 4200), ('ｸﾛｰｾﾞｯﾄ', 4200, 4200),
             ('収納1', 5600, 4200), ('収納2', 7000, 4200), ('ﾊﾞﾙｺﾆｰ', 1800, -800)]
_TABLE_2F = [('LDK', ['木軸下地', _V], '2,500'),
             ('洋室-2', ['木軸下地', _V], '2,500'),
             ('洋室-3', ['木軸下地', _V], '2,500'),
             ('UB1616', [], ''),                       # 天井欄が空（斜線）
             ('脱衣・洗濯', ['木軸下地', '耐水' + _V], '2,500'),
             ('ＷＣ', ['木軸下地', _V], '2,500'),       # 全角
             ('収納1・収納2', ['木軸下地ﾗﾜﾝ合板 t=4.0貼'], '2,500'),
             ('ｸﾛｰｾﾞｯﾄ', ['木軸下地' + _V], '2,500'),   # 空白なしの表記ゆれ
             ('廊下', ['木軸下地', _V], '2,500')]


def plan_2f(with_table=True):
    out = PLAN_1F.split('#\n')[0] + '#\n'
    out += 'lg0\nlyf\nlc2\nlt5\n'
    out += '0 0 8190 0\n8190 0 8190 7280\n8190 7280 0 7280\n0 7280 0 0\n'
    out += '0 3460 8190 3460\n'
    out += 'ly2\nlc2\nlt1\ncn3\n'
    for name, x, y in _ROOMS_2F:
        out += f'ch {x} {y} {len(name) * 300} 0 "{name}\n'
    if not with_table:
        return out
    out += 'ly9\nlc2\nlt1\ncn3\n'
    out += 'ch -12000 9000 1600 0 "内部仕上概要表\n'
    out += 'ch -13000 6000 600 0 "2階\n'
    out += ('ch -10000 8300 800 0 "室　名\nch -7500 8300 800 0 "天　井\n'
            'ch -1500 8300 1000 0 "天井高\n')
    y = 7600
    for name, finish, height in _TABLE_2F:
        tall = len(finish) == 2
        # 室名は欄からはみ出す長さで書く
        out += f'ch -10000 {y} {len(name) * 400} 0 "{name}\n'
        if tall:
            out += f'ch -7500 {y + 150} 4000 0 "{finish[0]}\n'
            out += f'ch -7500 {y - 150} 4000 0 "{finish[1]}\n'
        elif finish:
            out += f'ch -7500 {y} 4000 0 "{finish[0]}\n'
        if height:
            out += f'ch -1500 {y} 600 0 "{height}\n'
        y -= 700 if tall else 400
    return out


# 3枚目の図面を模したもの。用途区分の欄が左にあり、室名は欄の中で
# 中央寄せ（書き出し位置がまちまち）。表が2つに分かれていて、図面に
# 無い室の行も混ざっている。
_ROOMS_3F = [('正面玄関', 1000, 6000), ('事務室', 4000, 6000), ('多目的室', 7000, 6000),
             ('厨房・食堂', 10000, 6000), ('救急消毒室', 13000, 6000),
             ('洗面・洗濯室', 1000, 3000), ('更衣室', 4000, 3000), ('男子WC', 7000, 3000),
             ('廊下', 10000, 3000), ('浴室', 13000, 3000), ('車庫', 16000, 3000)]
# (区分, 室名, 天井の行, 天井高)。室名の書き出し位置は名前の長さで変える
_TABLE_3A = [('1階', '正面玄関', ['軽天下地', '岩綿吸音板t=9.5'], '2,700'),
             ('', '事務室', ['軽天下地', '岩綿吸音板t=9.5'], '2,700'),
             ('', '更衣室', ['軽天下地', '化粧石膏ﾎﾞｰﾄﾞt=9.5貼'], '2,500'),
             ('', '多目的室', ['軽天下地', '岩綿吸音板t=9.5'], '2,700'),
             ('', '厨房・食堂', ['軽天下地', '岩綿吸音板t=9.5'], '2,500'),
             ('', '裏玄関', ['軽天下地', '化粧石膏ﾎﾞｰﾄﾞt=9.5貼'], '2,500'),  # 図面に無い
             ('', '廊下', ['軽天下地', '化粧石膏ﾎﾞｰﾄﾞt=9.5貼'], '2,500'),
             ('', '男子WC', ['軽天下地', '化粧石膏ﾎﾞｰﾄﾞt=9.5貼'], '2,500')]
_TABLE_3B = [('2階', '浴室', ['軽天下地', '化粧石膏ﾎﾞｰﾄﾞt=9.5貼'], '2,500'),
             ('', '洗面・洗濯室', ['軽天下地', '化粧石膏ﾎﾞｰﾄﾞt=9.5貼'], '2,500'),
             ('', '救急消毒室', ['軽天下地', 'ｹｲ酸ｶﾙｼｳﾑ板t=6.0 目透かし貼りEP-G'], '2,500'),
             ('', '車庫', ['木毛ｾﾒﾝﾄ板表し'], ''),
             ('', 'ﾘﾈﾝ庫', ['軽天下地', '化粧石膏ﾎﾞｰﾄﾞt=9.5貼'], '2,500')]  # 図面に無い


def _schedule(rows, top, title):
    """概要表を 1 つ書き出す。室名は欄の中で中央寄せにする。"""
    out = f'ch -20000 {top + 900} 1600 0 "{title}\n'
    out += (f'ch -19000 {top + 300} 800 0 "区　分\n'
            f'ch -16000 {top + 300} 800 0 "室　名\n'
            f'ch -12000 {top + 300} 800 0 "天　井\n'
            f'ch -3000 {top + 300} 1000 0 "天井高\n')
    y = top - 400
    for zone, name, finish, height in rows:
        if zone:
            out += f'ch -19000 {y} 600 0 "{zone}\n'
        # 中央寄せ: 短い室名ほど右から始まる
        x = -16000 + (6 - min(len(name), 6)) * 150
        out += f'ch {x} {y} {len(name) * 300} 0 "{name}\n'
        if len(finish) == 2:
            out += f'ch -12000 {y + 150} 4000 0 "{finish[0]}\n'
            out += f'ch -12000 {y - 150} 4000 0 "{finish[1]}\n'
        else:
            out += f'ch -12000 {y} 4000 0 "{finish[0]}\n'
        if height:
            out += f'ch -3000 {y} 600 0 "{height}\n'
        y -= 700
    return out, y


def plan_3f():
    out = PLAN_1F.split('#\n')[0] + '#\n'
    out += 'lg0\nlyf\nlc2\nlt5\n'
    out += '0 0 18000 0\n18000 0 18000 9000\n18000 9000 0 9000\n0 9000 0 0\n'
    out += '0 4500 18000 4500\n'
    out += 'ly2\nlc2\nlt1\ncn3\n'
    for name, x, y in _ROOMS_3F:
        out += f'ch {x} {y} {len(name) * 300} 0 "{name}\n'
    out += 'ly9\nlc2\nlt1\ncn3\n'
    a, y = _schedule(_TABLE_3A, 20000, '内部仕上概要表')
    b, _ = _schedule(_TABLE_3B, y - 2000, '内部仕上概要表')
    return out + a + b


def run(plan, rules=RULES):
    """外部変形を 1 回走らせて (終了コード, 書き出し, ログ) を返す。"""
    with tempfile.TemporaryDirectory() as work:
        temp = os.path.join(work, 'jwc_temp.txt')
        rpath = os.path.join(work, '天伏図ルール.txt')
        for path, text in ((temp, plan), (rpath, rules)):
            with open(path, 'wb') as f:
                f.write(text.replace('\n', '\r\n').encode('cp932'))
        proc = subprocess.run([sys.executable, SCRIPT, temp, rpath],
                              capture_output=True, cwd=work)
        raw = open(temp, 'rb').read()
        log = os.path.join(SRC, 'jww_ceiling_plan.log')
        text = io.open(log, encoding='cp932').read() if os.path.exists(log) else ''
        if os.path.exists(log):
            os.remove(log)
        # 書き出しは必ず CP932 / CRLF で読めること
        return proc.returncode, raw.decode('cp932'), text, raw


def symbols(out):
    """書き出しに入っている記号の一覧。"""
    return {m.group(1) for m in re.finditer(r'ch .*"(C-[\w?]+)\r?$', out, re.M)}


def in_plan(out):
    """仕上表より前、図面の中だけの書き出し。仕上表の記号欄と混ざらないように。"""
    i = out.find('"記号')
    return out if i < 0 else out[:i]


def attrs_before(out, needle):
    """その行より前に効いている属性。"""
    state = {}
    for line in out.splitlines():
        if line == needle:
            return dict(state)
        if m := re.fullmatch(r'(lg|ly|lc|lt|cn)([0-9a-fA-F]+)', line):
            state[m.group(1)] = m.group(2)
    return None


CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


# ---------------------------------------------------------------- バッチ
@case('バッチ: 範囲選択の制御行')
def _():
    bat = read(os.path.join(SRC, '天井伏図生成.bat'))
    assert 'REM #h2' in bat, '#h2 が無い（#h0 だと範囲選択に入らない）'
    assert not re.search(r'(?m)^REM #h0\b', bat), '#h0 が残っている'
    assert 'REM #jww' in bat, '#jww が無いと外部変形の一覧に出ない'
    assert 'REM #hc' in bat and 'REM #1 ' in bat


# ---------------------------------------------------------------- 基本
@case('元の平面図を消さない')
def _():
    rc, out, log, _ = run(PLAN_1F)
    assert rc == 0, log
    assert not re.search(r'(?m)^hd\b', out), 'hd を書くと元の平面図が消える'


@case('書き出しが CP932 / CRLF')
def _():
    rc, out, log, raw = run(PLAN_1F)
    assert rc == 0
    assert raw.endswith(b'\r\n')
    assert b'\r\n' in raw and raw.count(b'\n') == raw.count(b'\r\n')


@case('縮尺: 図寸を実寸に直す')
def _():
    rc, out, log, _ = run(PLAN_1F)
    assert '1/100' in log, log
    # 仕上表の罫線の間隔は LEGEND_RH(6図寸mm) × 100 = 600
    rules_ = [l for l in out.splitlines()
              if re.fullmatch(rf'({NUM}) ({NUM}) ({NUM}) \2', l)]
    x0 = max(float(l.split()[0]) for l in rules_)     # 仕上表は図の右にある
    ys = sorted({float(l.split()[1]) for l in rules_
                 if float(l.split()[0]) >= x0})
    gaps = {round(b - a) for a, b in zip(ys, ys[1:])}
    assert gaps == {600}, f'仕上表の行の高さが 600 にならない: {sorted(gaps)}'


@case('縮尺: SET SCALE で固定できる')
def _():
    rc, out, log, _ = run(PLAN_1F, RULES.replace('SET SCALE auto', 'SET SCALE 50'))
    assert rc == 0
    assert '1/50' in log


# ---------------------------------------------------------------- レイヤ
@case('レイヤ: 16進(a〜f)を読む')
def _():
    rules = (RULES.replace('KEEP 0:f ', 'KEEP 0:f ').replace('KEEP 0:1 ', 'KEEP 0:d ')
                  .replace('KEEP 0:2 ', 'KEEP 0:e ').replace('KEEP 0:d ', 'KEEP 0:d '))
    rc, out, log, _ = run(PLAN_HEX, rules)
    assert rc == 0, log
    assert re.search(r'(?m)^  0:f ', log), f'0:f が内訳に出ない\n{log}'
    assert re.search(r'(?m)^  0:a ', log), '0:a が内訳に出ない'


@case('レイヤ: 建具などを落とす')
def _():
    rc, out, log, _ = run(PLAN_1F)
    assert rc == 0
    assert re.search(r'(?m)^  0:5 .*除外', log), f'建具レイヤが残っている\n{log}'
    assert 'ly5' not in out.split('\n'), '除外したレイヤが書き出されている'


@case('レイヤ: KEEP が空振りしたら番号を知らせる')
def _():
    rc, out, log, _ = run(PLAN_1F, RULES.replace('KEEP 0:', 'KEEP 1:'))
    assert rc == 1
    assert out.startswith('he '), out[:80]
    assert '0:f' in out and '0:2' in out, f'実際のレイヤ番号が出ていない: {out}'


@case('レイヤ: ソリッドやブロックを属性と誤認しない')
def _():
    plan = PLAN_1F + 'ly9\nsl 100 100 200 200 300 300\nbl 1 0 0 1 0 0 "図形\n'
    rc, out, log, _ = run(plan)
    assert rc == 0, log
    for bad in ('sl 100', 'bl 1'):
        assert bad not in out, f'{bad} がそのまま書き出されている'
    assert 'sl' in log and 'bl' in log, f'扱えない要素として数えていない\n{log}'


# ---------------------------------------------------------------- 壁線
@case('壁線: 中心線から W120 を作る')
def _():
    rc, out, log, _ = run(PLAN_1F)
    assert rc == 0
    assert re.search(r'作った壁線\s*:\s*(\d+)', log)
    n = int(re.search(r'作った壁線\s*:\s*(\d+)', log).group(1))
    assert n > 0, '壁線が 1 本もできていない'


@case('壁線: 端数が出ない（内側判定のはみ出し）')
def _():
    rc, out, log, _ = run(PLAN_1F)
    lines = [l for l in out.splitlines()
             if re.fullmatch(rf'{NUM} {NUM} {NUM} {NUM}', l)]
    bad = [l for l in lines if re.search(r'\.\d*[19]\d*\b', l)]
    assert not bad, f'0.01 のはみ出しが残っている: {bad[:3]}'


@case('壁線: 交差部で線が突き抜けない')
def _():
    # 十字に交わる 2 本の中心線だけを与える
    plan = (PLAN_1F.split('#\n')[0] + '#\n'
            + 'lg0\nlyf\nlc2\nlt5\n0 0 4000 0\n2000 -2000 2000 2000\n'
            + 'ly2\nlc2\nlt1\ncn3\nch 500 500 600 0 "室\n')
    rc, out, log, _ = run(plan, RULES.replace('SET LEGEND_MODE all',
                                              'SET LEGEND_MODE no'))
    assert rc == 0, log
    walls = [tuple(float(v) for v in l.split())
             for l in out.splitlines()
             if re.fullmatch(rf'{NUM} {NUM} {NUM} {NUM}', l)]
    # 交差部の内側（±60 の四角の中）を通る線があってはいけない
    inside = [w for w in walls
              if abs(w[0] - w[2]) > 1 and abs(w[1] - w[3]) < 1
              and w[1] in (min(y for _, y, _, _ in [(0, w[1], 0, 0)]),)
              and min(w[0], w[2]) < 1940 < max(w[0], w[2])
              and min(w[0], w[2]) < 2060 < max(w[0], w[2])]
    assert not inside, f'交差部を横切る壁線がある: {inside[:2]}'


@case('壁線: off にできる')
def _():
    rc, out, log, _ = run(PLAN_1F, RULES.replace('SET WALL_FROM 0:f',
                                                 'SET WALL_FROM off'))
    assert rc == 0
    assert re.search(r'作った壁線\s*:\s*0', log)


@case('壁線: 見つからなくても作図は続ける')
def _():
    rc, out, log, _ = run(PLAN_1F, RULES.replace('SET WALL_FROM 0:f',
                                                 'SET WALL_FROM 0:7'))
    assert rc == 0, '壁線が作れないだけで止まってはいけない'
    assert '壁線を作れませんでした' in log
    assert symbols(out), '記号は書かれているはず'


# ---------------------------------------------------------------- 室名と記号
@case('記号: 室名を登録しなくても付く')
def _():
    rc, out, log, _ = run(PLAN_1F)
    assert rc == 0
    assert re.search(r'置いた記号\s*:\s*(\d+)', log)
    assert int(re.search(r'置いた記号\s*:\s*(\d+)', log).group(1)) >= 10


@case('記号: 図面の仕上表から同じ仕上をまとめる')
def _():
    rc, out, log, _ = run(PLAN_1F)
    assert '図面の仕上表を' in log, f'概要表を読めていない\n{log}'
    # 10 室が 4 記号にまとまる
    assert len(symbols(out)) == 4, f'{sorted(symbols(out))}'


@case('記号: 表記ゆれ（空白の有無）でも同じ記号')
def _():
    rc, out, log, _ = run(plan_2f())
    assert rc == 0, log
    # ｸﾛｰｾﾞｯﾄ は「木軸下地石膏…」（空白なし）だが LDK と同じ仕上
    m = re.search(r'(?m)^\s*ｸﾛｰｾﾞｯﾄ\s+(\S+)', log)
    n = re.search(r'(?m)^\s*LDK\s+(\S+)', log)
    assert m and n, log
    assert m.group(1) == n.group(1), f'ｸﾛｰｾﾞｯﾄ={m.group(1)} LDK={n.group(1)}'


@case('記号: 1セルに2室（収納1・収納2）')
def _():
    rc, out, log, _ = run(plan_2f())
    got = {r: re.search(rf'(?m)^\s*{r}\s+(\S+)', log).group(1)
           for r in ('収納', '収納1', '収納2')}
    assert len(set(got.values())) == 1, f'ばらけている: {got}'


@case('記号: 枝番の食い違い（表が「倉庫」図面が「倉庫①」）')
def _():
    rc, out, log, _ = run(PLAN_1F)
    a = re.search(r'(?m)^\s*倉庫①\s+(\S+)', log)
    b = re.search(r'(?m)^\s*倉庫②\s+(\S+)', log)
    assert a and b, log
    assert a.group(1) == b.group(1), f'{a.group(1)} と {b.group(1)}'


@case('記号: 表の見出しを行に取り込まない')
def _():
    rc, out, log, _ = run(plan_2f())
    assert '天　井' not in log.split('室名と記号の対応')[1].split('\n\n')[0], \
        f'見出しが仕上として読まれている\n{log}'


@case('記号: 仕上表に空の行を作らない')
def _():
    rc, out, log, _ = run(plan_2f())
    rows = re.findall(r'(?m)^ch .* "(C-\d+)\r?$', out)
    assert rows, out[:200]
    # 天井欄が空の UB1616 も、室名が入って空行にならない
    assert '（UB1616）' in out, '仕上が読めない記号の行が空になっている'


@case('記号: 室名が仕上の文字に混ざらない')
def _():
    rc, out, log, _ = run(plan_3f())
    assert rc == 0, log
    body = log.split('室名と記号の対応')[1].split('\n\n')[0]
    finishes = re.findall(r'仕上表: (.+)$', body, re.M)
    assert finishes, body
    for room in ('正面玄関', '事務室', '多目的室', '厨房・食堂', '救急消毒室',
                 '洗面・洗濯室', '更衣室', '男子WC', '廊下', '浴室', '車庫'):
        for f in finishes:
            assert room not in f, f'仕上に室名が入っている: {room} / {f}'


@case('記号: 図面に無い室の行を巻き込まない')
def _():
    rc, out, log, _ = run(plan_3f())
    body = log.split('室名と記号の対応')[1].split('\n\n')[0]
    for ghost in ('裏玄関', 'ﾘﾈﾝ庫'):
        assert ghost not in body, f'表にしか無い室が混ざっている: {ghost}'


@case('記号: 表が2つに分かれていても読む')
def _():
    rc, out, log, _ = run(plan_3f())
    body = log.split('室名と記号の対応')[1].split('\n\n')[0]
    # 上の表の「正面玄関」も、下の表の「車庫」も読めていること
    assert re.search(r'正面玄関\s+\S+\s+レイヤ \S+\s+仕上表:', body), body
    assert re.search(r'車庫\s+\S+\s+レイヤ \S+\s+仕上表:', body), body


@case('記号: 中央寄せの室名でも仕上を取りこぼさない')
def _():
    rc, out, log, _ = run(plan_3f())
    body = log.split('室名と記号の対応')[1].split('\n\n')[0]
    lines = [l for l in body.splitlines() if l.strip()]
    blank = [l for l in lines if '仕上表:' not in l and '同じ天井仕上' not in l]
    assert not blank, f'仕上が読めていない室がある: {blank}'


@case('記号: 仕上が読めない室があれば表の読み取り結果を出す')
def _():
    plan = plan_3f().replace('ch 1000 6000 1200 0 "正面玄関',
                             'ch 1000 6000 1200 0 "正面玄関\nch 16000 6000 600 0 "US')
    rc, out, log, _ = run(plan)
    assert rc == 0, log
    assert '仕上が読めなかった室があります: US' in log, log
    # 表の各行について、見出しと読み取れた仕上が並ぶこと
    assert re.search(r'(?m)^  多目的室\s+軽天下地 岩綿吸音板', log), log


@case('記号: 表の行が1つ欠けても隣の行を汚さない')
def _():
    # 概要表の「多目的室」の行の見出しだけが読めなかった状況を作る
    # （実機で、その行だけ要素として読めていない例があった）
    plan, n = re.subn(r'(?m)^ch -\d+ \d+ \d+ 0 "多目的室$', '多目的室', plan_3f())
    assert n == 1, f'置き換えられていない: {n}'
    rc, out, log, _ = run(plan)
    assert rc == 0, log
    body = log.split('表からはこう読めています')[1]
    # 上下の行（更衣室・厨房・食堂）に多目的室の仕上が混ざっていないこと
    for row, want in (('更衣室', '軽天下地 化粧石膏ﾎﾞｰﾄﾞt=9.5貼'),
                      ('厨房・食堂', '軽天下地 岩綿吸音板t=9.5')):
        m = re.search(rf'(?m)^  {re.escape(row)}\s+(.+)$', body)
        assert m, f'{row} の行が無い\n{body}'
        assert m.group(1).strip() == want, f'{row} に余計な文字: {m.group(1)}'


@case('診断: 読めなかった行の中身をログに出す')
def _():
    plan = PLAN_1F + 'ly9\n多目的室\n'
    rc, out, log, _ = run(plan)
    assert rc == 0, log
    assert re.search(r'多 … 1 個.*例: 多目的室', log), log


@case('記号: NOROOM は ROOM より強い')
def _():
    rules = RULES.replace('# ROOM 事務室    C-1', 'ROOM UP C-9')
    rc, out, log, _ = run(PLAN_1F + 'ly2\ncn3\nch 3000 3000 350 0 "UP\n', rules)
    assert rc == 0, log
    assert 'C-9' not in symbols(out), 'NOROOM の文字に記号が付いている'


@case('記号: ROOM で固定できる')
def _():
    rules = RULES.replace('# ROOM 事務室    C-1', 'ROOM 事務室 C-9')
    rc, out, log, _ = run(PLAN_1F, rules)
    assert rc == 0, log
    assert re.search(r'(?m)^\s*事務室\s+C-9\s', log), log


@case('記号: 部屋名レイヤを off にすると付かない')
def _():
    rc, out, log, _ = run(PLAN_1F, RULES.replace('SET ROOM_LAYER 0:2',
                                                 'SET ROOM_LAYER off'))
    assert rc == 0
    assert not symbols(out), f'{sorted(symbols(out))}'


# ---------------------------------------------------------------- 見た目
@case('枠: 記号を四角で囲む')
def _():
    rc, out, log, _ = run(PLAN_1F)
    n = int(re.search(r'記号の枠\s*:\s*(\d+)', log).group(1))
    m = int(re.search(r'置いた記号\s*:\s*(\d+)', log).group(1))
    assert n == m * 4 // 4 and n == m, f'枠 {n} 個 / 記号 {m} 個'


@case('枠: 線色6・すき間0.5')
def _():
    rc, out, log, _ = run(PLAN_1F)
    lines = out.splitlines()
    i = next(i for i, l in enumerate(lines) if l.startswith('ch ') and '"C-' in l)
    box = [l for l in lines[max(0, i - 6):i]
           if re.fullmatch(rf'{NUM} {NUM} {NUM} {NUM}', l)]
    assert len(box) == 4, f'枠の 4 本が記号の直前に無い: {box}'
    xs = sorted({float(v) for l in box for v in (l.split()[0], l.split()[2])})
    ys = sorted({float(v) for l in box for v in (l.split()[1], l.split()[3])})
    # 文字高 3 図寸 × 100 ＝ 300、すき間 0.5 × 100 ＝ 50 ずつ
    assert round(ys[-1] - ys[0]) == 400, f'枠の高さ {ys[-1] - ys[0]}'
    assert 'lc6' in lines[max(0, i - 8):i], '枠の線色が 6 になっていない'


@case('枠: off にできる')
def _():
    rc, out, log, _ = run(PLAN_1F, RULES.replace('SET SYMBOL_BOX on',
                                                 'SET SYMBOL_BOX off'))
    assert re.search(r'記号の枠\s*:\s*0', log)


@case('仕上表: 外枠5・罫線2')
def _():
    rc, out, log, _ = run(PLAN_1F)
    assert 'lc5' in out.splitlines(), '外枠の線色 5 が無い'
    i = out.splitlines().index('lc5')
    rest = out.splitlines()[i:]
    assert 'lc2' in rest, '罫線の線色 2 が無い'


@case('レイヤ分け: 記号ごとに別レイヤ')
def _():
    rc, out, log, _ = run(PLAN_1F)
    seen = {}
    for m in re.finditer(r'(?m)^ch .* "(C-\d+)\r?$', in_plan(out)):
        at = attrs_before(out, m.group(0).rstrip('\r'))
        seen.setdefault(m.group(1), set()).add((at.get('lg'), at.get('ly')))
    assert len(seen) >= 3, seen
    for sym, at in seen.items():
        assert len(at) == 1, f'{sym} が複数のレイヤに散っている: {at}'
    flat = [next(iter(v)) for v in seen.values()]
    assert len(set(flat)) == len(flat), f'記号が同じレイヤに載っている: {seen}'


@case('レイヤ分け: 使うレイヤを並べて指定できる')
def _():
    rules = RULES.replace('SET SYMBOL_LAYERS\n', 'SET SYMBOL_LAYERS 0:4 0:6 0:7 0:b\n')
    rc, out, log, _ = run(PLAN_1F, rules)
    assert rc == 0, log
    for want in ('レイヤ 0:4', 'レイヤ 0:6', 'レイヤ 0:7'):
        assert want in log, f'{want} が使われていない\n{log}'


@case('レイヤ分け: off で 1 枚にまとまる')
def _():
    rules = RULES.replace('SET LAYER_PER_SYMBOL on', 'SET LAYER_PER_SYMBOL off')
    rc, out, log, _ = run(PLAN_1F, rules)
    seen = set()
    for m in re.finditer(r'(?m)^ch .* "(C-\d+)\r?$', in_plan(out)):
        at = attrs_before(out, m.group(0).rstrip('\r'))
        seen.add((at.get('lg'), at.get('ly')))
    assert len(seen) == 1, seen


@case('レイヤ分け: 足りないときは知らせる')
def _():
    rc, out, log, _ = run(PLAN_1F, RULES.replace('SET SYMBOL_LAYER 0:3',
                                                 'SET SYMBOL_LAYER 0:e'))
    assert rc == 0
    assert 'しかありません' in log, log


# ---------------------------------------------------------------- その他
@case('作図位置: hp1 が無くても動く')
def _():
    rc, out, log, _ = run(PLAN_1F.replace('hp1 20000 0\n', ''))
    assert rc == 0, log
    assert '作図位置の指示がなかった' in log


@case('図面名: 平面図 → 天井伏図')
def _():
    rc, out, log, _ = run(PLAN_1F)
    assert '"１階天井伏図' in out, '図面名が書き換わっていない'


@case('面積表記を消す')
def _():
    rc, out, log, _ = run(PLAN_1F)
    assert '㎡' not in out, '面積表記が残っている'


@case('空の選択はエラーにする')
def _():
    rc, out, log, _ = run(PLAN_1F.split('#\n')[0] + '#\n')
    assert rc == 1
    assert '図形が選択されていません' in out


@case('ルールファイルの誤りを知らせる')
def _():
    rc, out, log, _ = run(PLAN_1F, RULES + '\nROOM\n')
    assert rc == 1
    assert 'ルールファイルに誤りがあります' in out


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else ''
    cases = [(n, f) for n, f in CASES if only in n]
    width = max(len(n) for n, _ in cases)
    failed = []
    for name, fn in cases:
        try:
            fn()
            print(f'  ok   {name}')
        except AssertionError as exc:
            print(f'  NG   {name.ljust(width)}  {exc}')
            failed.append(name)
        except Exception as exc:                       # noqa: BLE001
            print(f'  ERR  {name.ljust(width)}  {type(exc).__name__}: {exc}')
            failed.append(name)
    print()
    print(f'{len(cases) - len(failed)} / {len(cases)} 件 通過')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
