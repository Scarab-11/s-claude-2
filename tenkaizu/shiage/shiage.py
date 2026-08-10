# -*- coding: utf-8 -*-
"""Jw_cad 外部変形 : 内部仕上概要表から室別の縦組み仕上表を作図する

  横長の「内部仕上概要表」を範囲選択すると、罫線から表の格子を復元し、
  1室ぶんずつ縦組みの仕上表（床・巾木・腰壁・壁・天井・備考）を作図する。

  jwc_temp.txt の書式
    座標・文字列の長さベクトル … 実寸 mm（用紙mm × 縮尺）
    cn0 幅 高さ 間隔 色                     任意サイズ文字（幅・高さは用紙mm）
    ch 始点X 始点Y 長さX 長さY "文字列      文字
    先頭に hd を出すと選択図形が削除される → 出さない（元の表を残すため）
"""
import sys, os, re, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- 動作の記録（必ず shiage_log.txt に残す）------------------
LOG = []
def log(*a):
    LOG.append(' '.join(str(x) for x in a))
def write_log():
    try:
        with open(os.path.join(HERE, 'shiage_log.txt'), 'w',
                  encoding='cp932', errors='replace', newline='') as f:
            f.write('\r\n'.join(LOG) + '\r\n')
    except Exception:
        pass

# ============================================================
# 設定
# ============================================================
CFG = {
    '表レイヤ':'すべて',
    '作図レイヤグループ':'e', '縮尺':'100',
    '用紙幅':'420', '用紙高':'297',
    '1枚の枠数':'5', '枠ピッチ_縦':'52.0', '枠のすきま':'2.9', '用紙ピッチ_縦':'297',
    '枠の左余白':'22.0', '枠の上余白':'14.3',
    '枠幅':'67.5', '見出し列幅':'8.0',
    '行高_室名':'5.5', '行高_1行':'3.5', '行高_1行_備考':'2.85',
    '文字高':'2.5', '文字の余白':'1.9',
    '項目':'床,巾木,腰壁,壁,天井,備考',
    '項目の行数':'2,2,2,2,2,3',
    '仕切りのある項目':'床,巾木',
    '備考の項目':'備考',
    '腰壁の取り出し元':'壁',
    'レイヤ_枠':'0', 'レイヤ_文字':'1',
    '線色_外枠':'5', '線色_内部線':'2', '線色_文字':'6',
    '用紙枠':'しない', '線色_用紙枠':'8',
    '覆い率':'0.5',
}
def load_cfg():
    p = os.path.join(HERE, 'shiage_setting.txt')
    if not os.path.exists(p): return
    raw_bytes = open(p, 'rb').read()
    for enc in ('utf-8-sig', 'cp932', 'utf-8'):
        try:
            body = raw_bytes.decode(enc); break
        except UnicodeDecodeError:
            continue
    else:
        body = raw_bytes.decode('cp932', 'replace')
    for raw in body.splitlines():
        t = raw.split('#')[0].strip()
        if '=' in t:
            k, v = t.split('=', 1)
            k = k.strip()
            if k in CFG: CFG[k] = v.strip()
load_cfg()
def I(k): return int(CFG[k])
def F(k): return float(CFG[k])
def yes(k): return CFG[k].strip() in ('する', 'はい', 'yes', '1')
def csv(k): return [s.strip() for s in CFG[k].split(',') if s.strip()]

SCALE = F('縮尺')
TOL   = 0.3 * SCALE          # 罫線をまとめる許容差（実寸mm）

def S(mm):  return mm * SCALE            # 用紙mm → 実寸mm
def tlen(s, mm):
    """文字列の長さ（実寸mm）。全角＝幅、半角＝幅/2"""
    n = sum(1.0 if unicodedata.east_asian_width(c) in 'WFA' else 0.5 for c in s)
    return n * mm * SCALE

# ============================================================
# jwc_temp.txt の読み込み
# ============================================================
NUM = re.compile(r'^-?\d+(\.\d+)?$')
def read_temp(path):
    ly = None
    lines, texts = [], []
    for raw in open(path, encoding='cp932', errors='replace').read().splitlines():
        t = raw.strip()
        if not t or t[0] == 'h': continue
        m = re.match(r'^ly([0-9a-fA-F])$', t)
        if m: ly = m.group(1).lower(); continue
        if re.match(r'^(lc|lt|cn|pn|lg)', t): continue
        if t[:3] in ('ch ', 'cs '):
            p = t.split(None, 5)
            if len(p) >= 6:
                texts.append(dict(ly=ly, x=float(p[1]), y=float(p[2]),
                                  dx=float(p[3]), dy=float(p[4]), s=p[5][1:]))
            continue
        p = t.split()
        if len(p) == 4 and all(NUM.match(v) for v in p):
            lines.append(dict(ly=ly, x1=float(p[0]), y1=float(p[1]),
                              x2=float(p[2]), y2=float(p[3])))
    return lines, texts

# ============================================================
# 罫線 → 表の格子
# ============================================================
def cluster(vals, tol):
    """近い値をまとめて代表値にする"""
    out = []
    for v in sorted(vals):
        if out and v - out[-1][-1] <= tol: out[-1].append(v)
        else: out.append([v])
    return [sum(g)/len(g) for g in out]

def coverage(segs, tol):
    """区間の和集合の長さ"""
    segs = sorted((min(a,b), max(a,b)) for a, b in segs)
    tot, ca, cb = 0.0, None, None
    for a, b in segs:
        if ca is None: ca, cb = a, b
        elif a <= cb + tol: cb = max(cb, b)
        else: tot += cb - ca; ca, cb = a, b
    if ca is not None: tot += cb - ca
    return tot

def build_grid(lines):
    """罫線から行境界・列境界を求める。
       部分的にしか無い罫線（結合セルの仕切り）は境界にしない。"""
    hs = [l for l in lines if abs(l['y1']-l['y2']) <= TOL]   # 横線
    vs = [l for l in lines if abs(l['x1']-l['x2']) <= TOL]   # 縦線
    if not hs or not vs: return None
    xs = [v for l in hs+vs for v in (l['x1'], l['x2'])]
    ys = [v for l in hs+vs for v in (l['y1'], l['y2'])]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    W, H = x1-x0, y1-y0
    need = F('覆い率')
    rows, cols = [], []
    for y in cluster([l['y1'] for l in hs], TOL):
        segs = [(l['x1'], l['x2']) for l in hs if abs(l['y1']-y) <= TOL]
        if coverage(segs, TOL) >= W*need: rows.append(y)
    for x in cluster([l['x1'] for l in vs], TOL):
        segs = [(l['y1'], l['y2']) for l in vs if abs(l['x1']-x) <= TOL]
        if coverage(segs, TOL) >= H*need: cols.append(x)
    rows.sort(reverse=True)          # 上から下へ
    cols.sort()                      # 左から右へ
    return dict(rows=rows, cols=cols, box=(x0, y0, x1, y1))

def join_row(ts):
    """同じ高さに並ぶ文字を左から右へつなぐ。すきまがあれば空白を1つ入れる"""
    ts = sorted(ts, key=lambda t: t['x'])
    s = ts[0]['s'].strip()
    end = ts[0]['x'] + ts[0]['dx']
    for t in ts[1:]:
        if t['x'] - end > 0.5*SCALE: s += ' '
        s += t['s'].strip()
        end = max(end, t['x'] + t['dx'])
    return s

def cell_texts(texts, grid):
    """文字を (行,列) のセルに割り当てる。セル内は上の行から順に並べる"""
    rows, cols = grid['rows'], grid['cols']
    cells = {}
    for t in texts:
        cx = t['x'] + t['dx']/2
        cy = t['y'] + t['dy']/2 + TOL          # 文字の下端が罫線に乗らないよう少し上へ
        r = c = None
        for i in range(len(rows)-1):
            if rows[i+1] - TOL <= cy <= rows[i] + TOL: r = i; break
        for j in range(len(cols)-1):
            if cols[j] - TOL <= cx <= cols[j+1] + TOL: c = j; break
        if r is None or c is None: continue
        cells.setdefault((r, c), []).append(t)
    out = {}
    for k, v in cells.items():
        bands = []                             # 高さの近い文字は同じ行にまとめる
        for t in sorted(v, key=lambda t: -t['y']):
            if bands and abs(bands[-1][0]['y'] - t['y']) <= TOL: bands[-1].append(t)
            else: bands.append([t])
        out[k] = [join_row(b) for b in bands]
    return out

# ============================================================
# 見出し行から列の意味を決める
# ============================================================
def map_columns(cells, ncol):
    """先頭行の文字から、どの列が何かを決める。長い語を先に見る"""
    keys = ['天井高', '廻り縁', '腰壁', '巾木', '備考', '床', '壁', '天井']
    col = {}
    for c in range(ncol):
        s = ''.join(cells.get((0, c), [])).replace(' ', '').replace('　', '')
        for k in keys:
            if k in s and k not in col:
                col[k] = c; break
    return col

# ============================================================
# 作図データ
# ============================================================
P = []      # ('line',ly,lc,x1,y1,x2,y2) / ('text',ly,lc,mm,x,y,dx,dy,s)
def line(ly, lc, x1, y1, x2, y2): P.append(('line', ly, lc, x1, y1, x2, y2))
def text_l(ly, lc, mm, x, by, s):
    P.append(('text', ly, lc, mm, x, by, tlen(s, mm), 0.0, s))
def text_c(ly, lc, mm, cx, by, s):
    n = tlen(s, mm); P.append(('text', ly, lc, mm, cx-n/2, by, n, 0.0, s))
def rect(ly, lc, x, ytop, w, h):
    line(ly,lc, x,ytop, x+w,ytop);       line(ly,lc, x+w,ytop, x+w,ytop-h)
    line(ly,lc, x+w,ytop-h, x,ytop-h);   line(ly,lc, x,ytop-h, x,ytop)

def wrap(s, width, mm):
    """用紙 width mm に収まるよう折り返す。空白があればそこで切る"""
    lim = S(width)
    out, cur = [], ''
    for ch in s:
        if cur and tlen(cur+ch, mm) > lim:
            cut = -1
            for i in range(len(cur)-1, 0, -1):
                if cur[i] in ' 　': cut = i; break
            if cut > 0 and tlen(cur[:cut], mm) > lim*0.4:
                out.append(cur[:cut].rstrip()); cur = cur[cut+1:].lstrip() + ch
            else:
                out.append(cur); cur = ch
        else:
            cur += ch
    if cur.strip(): out.append(cur.rstrip())
    return out or ['']

def draw_block(bx, bytop, room, items):
    """1室ぶんの縦組み仕上表を描く。戻り値は枠の高さ（用紙mm）"""
    LY_F, LY_T = I('レイヤ_枠'), I('レイヤ_文字')
    C_O, C_I, C_T = I('線色_外枠'), I('線色_内部線'), I('線色_文字')
    TH  = F('文字高')
    W   = S(F('枠幅')); LW = S(F('見出し列幅')); PAD = S(F('文字の余白'))
    H0  = S(F('行高_室名'))
    # ---- 室名（見出し行）----
    # 室名と床の間の線は、外枠と同じ線色にする
    text_c(LY_T, C_T, TH, bx+W/2, bytop-H0+(H0-S(TH))/2, room)
    y = bytop - H0
    line(LY_F, C_O, bx, y, bx+W, y)
    # ---- 各項目 ----
    for idx, (name, ndef, lh_mm, split, body) in enumerate(items):
        lh = S(lh_mm)
        n  = max(ndef, len(body))
        h  = n * lh
        text_c(LY_T, C_T, TH, bx+LW/2, y-h/2-S(TH)/2, name)
        if split:                                  # 床・巾木は段ごとに仕切る
            for k in range(1, n):
                line(LY_F, C_I, bx+LW, y-k*lh, bx+W, y-k*lh)
            off = 0.0                              # 上の段から順に入れる
        else:
            off = (n - len(body)) / 2.0            # 行のまん中に寄せる
        for k, s in enumerate(body):
            if not s: continue
            top = y - (off+k)*lh
            text_l(LY_T, C_T, TH, bx+LW+PAD, top-lh+(lh-S(TH))/2, s)
        y -= h
        if idx < len(items)-1: line(LY_F, C_I, bx, y, bx+W, y)
    # ---- 外枠と見出し列の縦線 ----
    rect(LY_F, C_O, bx, bytop, W, bytop-y)
    line(LY_F, C_I, bx+LW, bytop-H0, bx+LW, y)
    return (bytop - y) / SCALE

# ============================================================
# 出力
# ============================================================
CHAR_TYPE = {1.5:1, 2.0:2, 2.5:3, 3.0:4, 3.5:5, 4.0:6, 4.5:7, 5.0:8, 6.0:9, 12.0:10}
def fm(v):
    s = ('%.2f' % v).rstrip('0').rstrip('.')
    return s if s not in ('', '-') else '0'
def emit(dx=0.0, dy=0.0):
    o = ['lg%s' % CFG['作図レイヤグループ'].strip().lower()]
    for ly in sorted({e[1] for e in P}):
        o.append('ly%x' % ly)
        lc = size = None
        for e in [e for e in P if e[1] == ly]:
            if e[0] == 'line':
                if e[2] != lc: lc = e[2]; o.append('lc%d' % lc)
                o.append('%s %s %s %s' % (fm(e[3]+dx), fm(e[4]+dy),
                                          fm(e[5]+dx), fm(e[6]+dy)))
            else:
                if e[2] != lc: lc = e[2]; o.append('lc%d' % lc)
                # 折り返しの計算どおりの幅で描くため、文字は任意サイズで出す
                if e[3] != size:
                    size = e[3]; o.append('cn0 %s %s 0 %d' % (fm(size), fm(size), lc))
                o.append('ch %s %s %s %s "%s' % (fm(e[4]+dx), fm(e[5]+dy),
                                                 fm(e[6]), fm(e[7]), e[8]))
    return o

# ============================================================
# 本体
# ============================================================
def main():
    import datetime
    log('仕上表 縦組み  %s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    log('Python %s' % sys.version.split()[0])
    log('スクリプト位置 : %s' % HERE)
    temp = None
    for c in (os.path.join(os.getcwd(), 'jwc_temp.txt'),
              os.path.join(HERE, 'jwc_temp.txt')):
        log('  探索 : %s  → %s' % (c, '有' if os.path.exists(c) else '無'))
        if os.path.exists(c) and temp is None: temp = c
    if temp is None:
        log('!! jwc_temp.txt が見つかりません。')
        sys.stderr.write('jwc_temp.txt が見つかりません。\n'); write_log(); return 1

    lines, texts = read_temp(temp)
    lyT = CFG['表レイヤ'].strip().lower()
    if lyT not in ('すべて', '', '*'):
        lines = [l for l in lines if l['ly'] == lyT]
        texts = [t for t in texts if t['ly'] == lyT]
    log('')
    log('---- 受け取ったデータ ----')
    log('  線 %d本 / 文字 %d個  （表レイヤ = %s）' % (len(lines), len(texts), CFG['表レイヤ']))
    from collections import Counter
    cl = Counter(l['ly'] for l in lines); ct = Counter(t['ly'] for t in texts)
    for k in sorted(set(cl) | set(ct), key=lambda v: (v is None, str(v))):
        log('    レイヤ%-3s 線%4d本  文字%3d個' % (k, cl.get(k, 0), ct.get(k, 0)))

    grid = build_grid(lines)
    if not grid or len(grid['rows']) < 2 or len(grid['cols']) < 2:
        log('!! 罫線から表の格子を作れませんでした。')
        log('   縦横の罫線が引かれた表を範囲選択してください。')
        sys.stderr.write('罫線から表を読み取れませんでした。\n'
                         '縦横の罫線がある表を範囲選択してください。\n')
        write_log(); return 1
    rows, cols = grid['rows'], grid['cols']
    log('')
    log('---- 表の格子 ----')
    log('  %d行 × %d列' % (len(rows)-1, len(cols)-1))
    log('  行の境界(Y) : %s' % ' '.join('%.1f' % v for v in rows))
    log('  列の境界(X) : %s' % ' '.join('%.1f' % v for v in cols))

    cells = cell_texts(texts, grid)
    col = map_columns(cells, len(cols)-1)
    log('')
    log('---- 見出し行から読み取った列 ----')
    for c in range(len(cols)-1):
        log('    第%2d列  %s' % (c+1, ' / '.join(cells.get((0, c), [])) or '(空)'))
    log('  対応 : %s' % (' '.join('%s=第%d列' % (k, v+1) for k, v in sorted(
        col.items(), key=lambda kv: kv[1])) or '(なし)'))
    if '床' not in col:
        log('!! 見出し行に「床」の列が見つかりません。')
        log('   表の見出し行ごと範囲選択できているか確認してください。')
        sys.stderr.write('見出し行に「床」の列が見つかりません。\n'
                         '表の見出し行ごと範囲選択してください。\n')
        write_log(); return 1
    cN = col['床'] - 1                      # 室名列は「床」の左どなり
    if cN < 0:
        log('!! 「床」の列の左に室名の列がありません。')
        sys.stderr.write('「床」の左に室名の列がありません。\n'); write_log(); return 1
    log('  室名列 = 第%d列（「床」の左どなり）' % (cN+1))

    # ---- 行 → 室 ----
    names  = csv('項目')
    ndefs  = [int(v) for v in csv('項目の行数')]
    splits = csv('仕切りのある項目')
    notes  = csv('備考の項目')
    if len(ndefs) < len(names): ndefs += [2]*(len(names)-len(ndefs))
    KOSHI, KABE = '腰壁', CFG['腰壁の取り出し元'].strip()
    W_TXT = F('枠幅') - F('見出し列幅') - F('文字の余白')*2

    def src(r, key):
        c = col.get(key)
        return list(cells.get((r, c), [])) if c is not None else []

    rooms = []
    log('')
    log('---- 室ごとの読み取り ----')
    for r in range(1, len(rows)-1):
        room = ' '.join(cells.get((r, cN), [])).strip()
        if not room: continue
        raw = {}
        for k in names:
            if k == KOSHI and KOSHI not in col:
                raw[k] = []                       # あとで「壁」から取り出す
            else:
                raw[k] = src(r, k)
        # 「壁」の欄に腰壁と壁が同居している表に対応する
        if KOSHI not in col and KABE in col:
            koshi, kabe = [], []
            for s in src(r, KABE):
                head = re.split(r'[：:]', s, 1)
                if len(head) == 2 and head[0].strip().startswith(KOSHI):
                    koshi.append(head[1].strip())
                elif len(head) == 2 and head[0].strip() in (KABE, ''):
                    kabe.append(head[1].strip())
                else:
                    kabe.append(s)
            raw[KOSHI] = koshi
            if KABE in raw: raw[KABE] = kabe
        items = []
        for k, nd in zip(names, ndefs):
            lh = F('行高_1行_備考') if k in notes else F('行高_1行')
            body = []
            for s in raw.get(k, []): body += wrap(s, W_TXT, F('文字高'))
            items.append((k, nd, lh, k in splits, body))
        rooms.append((room, items))
        log('  ■ %s' % room)
        for k, nd, lh, sp, body in items:
            log('      %-4s %s' % (k, ' ／ '.join(body) or '(なし)'))
            if len(body) > nd:
                log('        ※ %d行に増えたため、この枠は縦に伸びます' % len(body))
    if not rooms:
        log('!! 室名の入った行が見つかりませんでした。')
        sys.stderr.write('室名の入った行が見つかりませんでした。\n'); write_log(); return 1

    # ---- 割付（A3用紙に縦一列。枠が増えたら用紙を下へ足す）----
    per   = I('1枚の枠数')
    pitch = F('枠ピッチ_縦'); gap = F('枠のすきま'); sheet_pitch = F('用紙ピッチ_縦')
    ml, mt = F('枠の左余白'), F('枠の上余白')
    nsheet = (len(rooms) + per - 1) // per
    if yes('用紙枠'):
        for s in range(nsheet):
            rect(I('レイヤ_枠'), I('線色_用紙枠'),
                 0.0, -S(sheet_pitch*s), S(F('用紙幅')), S(F('用紙高')))
    over, spill = [], []
    for sh in range(nsheet):
        y, bottom = mt, mt
        for room, items in rooms[sh*per:(sh+1)*per]:
            h = draw_block(S(ml), -S(sheet_pitch*sh + y), room, items)
            bottom = y + h
            # 記述が長くて枠が高くなった室は、以降を押し下げて重なりを防ぐ
            step = pitch if h <= pitch - gap else h + gap
            if step > pitch: over.append((room, h, step - pitch))
            y += step
        if bottom > F('用紙高'): spill.append((sh+1, bottom))

    # ---- 配置基準点（REM #1 の hp1）。指示点は1枚目の用紙の左上 ----
    ox = oy = 0.0
    for raw in open(temp, encoding='cp932', errors='replace').read().splitlines():
        t = raw.strip()
        if t.startswith('hp1 '):
            p = t.split()
            if len(p) >= 3: ox, oy = float(p[1]), float(p[2])
            break
    out = emit(ox, oy)
    with open(temp, 'w', encoding='cp932', errors='replace', newline='') as f:
        f.write('\r\n'.join(out) + '\r\n')

    log('')
    log('---- 作図 ----')
    log('  配置基準点(用紙の左上) : %.1f, %.1f' % (ox, oy))
    log('  %d室 → %d枠 / 用紙 %d枚（1枚に%d枠）' % (len(rooms), len(rooms), nsheet, per))
    for s in range(nsheet):
        log('    %d枚目 : %s' % (s+1, ' , '.join(
            r for r, _ in rooms[s*per:(s+1)*per])))
    for room, h, d in over:
        log('  ※ %s : 記述が長く枠の高さが %.1fmm（標準 %.1fmm）になったため、'
            'この室から下を %.1fmm 押し下げました。' % (room, h, pitch-gap, d))
        log('    そろえたいときは 枠幅 を広げるか 文字高 を小さくしてください。')
    for sh, b in spill:
        log('  ※ %d枚目 : 枠の下端が用紙の下 %.1fmm を %.1fmm はみ出しました。'
            % (sh, F('用紙高'), b - F('用紙高')))
        log('    1枚の枠数 を減らすか、枠の上余白 を詰めてください。')
    log('  出力 %d行 を %s に書き出しました' % (len(out), temp))
    write_log()
    sys.stderr.write('%d室ぶんの仕上表を作図しました（用紙%d枚）\n' % (len(rooms), nsheet))
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        import traceback
        log(''); log('!! 予期しないエラー'); log(traceback.format_exc())
        write_log()
        sys.stderr.write(traceback.format_exc())
        sys.exit(1)
