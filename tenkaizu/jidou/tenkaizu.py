# -*- coding: utf-8 -*-
"""Jw_cad 外部変形 : 平面図から展開図を自動作図する

  平面図を範囲選択すると、壁芯線（一点鎖線・専用レイヤ）から室を検出し、
  各室の Ａ～Ｄ面の展開図を作図する。

  jwc_temp.txt の書式
    座標・文字列の長さベクトル … 実寸 mm
    文字サイズ(hcw/hch)        … 用紙 mm
    ch 始点X 始点Y 長さX 長さY "文字列      文字
    msg / 線 / cs …  / #                    寸法図形
    pn<色> / pt x y                          実点
    先頭に hd を出すと選択図形が削除される → 出さない（平面図を残すため）
"""
import sys, os, re, math, unicodedata

EPS = 1.0
HERE = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 設定
# ============================================================
CFG = {
    '壁芯線レイヤ':'f', '室名レイヤ':'c', '天井高レイヤ':'e', '通り芯レイヤ':'1',
    '天井高の接頭辞':'ch=',
    '作図レイヤグループ':'1',
    '壁の寄り':'80',
    '文字高_寸法':'2.0', '文字高_室名':'2.5', '文字高_通り芯記号':'3.5',
    '線色_基準線':'1', '線色_通り芯記号':'4', '線色_寸法':'2', '線色_実点':'6',
    '線色_外形線':'5', '線色_段差線':'1', '線色_面記号枠':'2', '線色_文字':'1',
    'レイヤ_基準線':'1', 'レイヤ_寸法':'2', 'レイヤ_外形線':'3',
    'レイヤ_文字':'4', 'レイヤ_段差線':'5',
    '用紙幅':'420', '用紙高':'297', '縮尺':'100',
    '面の間隔_横':'1500', '面の間隔_縦':'1500', '室ごとに改行':'しない',
    '面の記号':'Ａ　面,Ｂ　面,Ｃ　面,Ｄ　面',
}
def load_cfg():
    p = os.path.join(HERE, 'tenkaizu_setting.txt')
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
SCALE = I('縮尺')
WALL_T = F('壁の寄り')
FACE_MARK = [s.strip() for s in CFG['面の記号'].split(',')]

# 作図規約（実寸 mm）
DIM_OFF, DIM_STEP, DIM_TXT_GAP = 375, 450, 30
VDIM_OFF, VDIM_EXT             = 760, 540
AX_UP, AX_DN                   = 900, 1050
AX_CIR_R, AX_CIR_Y, AX_TICK    = 350, 1350, 250
NAMEBOX_TOP, NAMEBOX_H, NAMEBOX_PAD = 550, 350, 150
PAD_L, PAD_R, PAD_T, PAD_B = 1150, 500, 1800, 1200
CHAR_TYPE = {1.5:1, 2.0:2, 2.5:3, 3.0:4, 3.5:5, 4.0:6, 4.5:7, 5.0:8, 6.0:9, 12.0:10}

def tlen(s, mm):
    n = sum(1.0 if unicodedata.east_asian_width(c) in 'WFA' else 0.5 for c in s)
    return n * mm * SCALE
def theight(mm): return mm * SCALE

# ============================================================
# jwc_temp.txt の読み込み
# ============================================================
NUM = re.compile(r'^-?\d+(\.\d+)?$')
def read_temp(path):
    ly = lc = lt = cn = None
    lines, texts, raws = [], [], []
    for raw in open(path, encoding='cp932', errors='replace').read().splitlines():
        t = raw.strip()
        if not t: continue
        if t[0] == 'h':                      # 図面情報は出力しない
            continue
        raws.append(raw)                     # 元図形（そのまま返す用）
        m = re.match(r'^ly([0-9a-fA-F])$', t)
        if m: ly = m.group(1).lower(); continue
        m = re.match(r'^lc(\d+)$', t)
        if m: lc = int(m.group(1)); continue
        m = re.match(r'^lt(\d+)$', t)
        if m: lt = int(m.group(1)); continue
        m = re.match(r'^cn(\d+)', t)
        if m: cn = int(m.group(1)); continue
        if t[:3] in ('ch ', 'cs '):
            p = t.split(None, 5)
            if len(p) >= 6:
                texts.append(dict(ly=ly, cn=cn, x=float(p[1]), y=float(p[2]),
                                  dx=float(p[3]), dy=float(p[4]), s=p[5][1:]))
            continue
        p = t.split()
        if len(p) == 4 and all(NUM.match(v) for v in p):
            lines.append(dict(ly=ly, lc=lc, lt=lt,
                              x1=float(p[0]), y1=float(p[1]),
                              x2=float(p[2]), y2=float(p[3])))
    return lines, texts, raws
def txt_center(t):
    return (t['x'] + t['dx']/2, t['y'] + t['dy']/2)

# ============================================================
# 壁芯線 → 閉領域（室）
# ============================================================
def detect_rooms(walls):
    pts = set()
    for w in walls:
        pts.add((w['x1'], w['y1'])); pts.add((w['x2'], w['y2']))
    def inter(a, b):
        x1,y1,x2,y2 = a['x1'],a['y1'],a['x2'],a['y2']
        x3,y3,x4,y4 = b['x1'],b['y1'],b['x2'],b['y2']
        d = (x2-x1)*(y4-y3) - (y2-y1)*(x4-x3)
        if abs(d) < 1e-9: return None
        t = ((x3-x1)*(y4-y3) - (y3-y1)*(x4-x3)) / d
        u = ((x3-x1)*(y2-y1) - (y3-y1)*(x2-x1)) / d
        if -1e-9 <= t <= 1+1e-9 and -1e-9 <= u <= 1+1e-9:
            return (round(x1+t*(x2-x1), 3), round(y1+t*(y2-y1), 3))
        return None
    for i in range(len(walls)):
        for j in range(i+1, len(walls)):
            p = inter(walls[i], walls[j])
            if p: pts.add(p)
    uniq = []
    for p in pts:
        for q in uniq:
            if abs(p[0]-q[0]) < EPS and abs(p[1]-q[1]) < EPS: break
        else: uniq.append(p)
    def snap(p):
        for q in uniq:
            if abs(p[0]-q[0]) < EPS and abs(p[1]-q[1]) < EPS: return q
        return p
    def on_seg(p, w):
        x1,y1,x2,y2 = w['x1'],w['y1'],w['x2'],w['y2']; x,y = p
        L = math.hypot(x2-x1, y2-y1)
        if abs((x2-x1)*(y-y1) - (y2-y1)*(x-x1)) > EPS*L: return False
        return (min(x1,x2)-EPS <= x <= max(x1,x2)+EPS and
                min(y1,y2)-EPS <= y <= max(y1,y2)+EPS)
    edges = set()
    for w in walls:
        a = snap((w['x1'], w['y1']))
        on = [p for p in uniq if on_seg(p, w)]
        on.sort(key=lambda p: (p[0]-a[0])**2 + (p[1]-a[1])**2)
        for u, v in zip(on, on[1:]):
            if u != v: edges.add((u, v) if u < v else (v, u))
    adj = {}
    for u, v in edges:
        adj.setdefault(u, []).append(v); adj.setdefault(v, []).append(u)
    for k in adj:
        adj[k].sort(key=lambda p, k=k: math.atan2(p[1]-k[1], p[0]-k[0]))
    used, faces = set(), []
    for u, v in list(edges) + [(v, u) for u, v in edges]:
        if (u, v) in used: continue
        face, a, b = [], u, v
        while (a, b) not in used:
            used.add((a, b)); face.append(a)
            lst = adj[b]; a, b = b, lst[(lst.index(a)-1) % len(lst)]
            if len(face) > 20000: break
        if len(face) >= 3: faces.append(face)
    def area(poly):
        s = 0
        for (x1,y1),(x2,y2) in zip(poly, poly[1:]+poly[:1]): s += x1*y2 - x2*y1
        return s/2
    rooms = [f for f in faces if area(f) > 1000]
    rooms.sort(key=lambda f: -area(f))
    return rooms, area

def inside(p, poly):
    x, y = p; c = False
    for (x1,y1),(x2,y2) in zip(poly, poly[1:]+poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2-x1)*(y-y1)/(y2-y1) + x1: c = not c
    return c

# ============================================================
# 多角形 → Ａ～Ｄ面
# ============================================================
REV = {0:False, 1:True, 2:True, 3:False}      # Ａ:X昇 Ｂ:Y降 Ｃ:X降 Ｄ:Y昇
def faces_of(poly):
    edge = {0:[], 1:[], 2:[], 3:[]}
    for (x1,y1),(x2,y2) in zip(poly, poly[1:]+poly[:1]):
        if abs(y1-y2) < EPS:
            (edge[2] if x2 > x1 else edge[0]).append((min(x1,x2), max(x1,x2), y1))
        elif abs(x1-x2) < EPS:
            (edge[1] if y2 > y1 else edge[3]).append((min(y1,y2), max(y1,y2), x1))
    out = {}
    for k, es in edge.items():
        if not es: continue
        es.sort(key=lambda e: e[0], reverse=REV[k])
        segs, planes = [], []
        for a, b, pl in es:
            if planes and abs(pl - planes[-1]) < EPS: segs[-1] += b - a
            else: segs.append(b - a); planes.append(pl)
        ends = (es[0][1] if REV[k] else es[0][0], es[-1][0] if REV[k] else es[-1][1])
        out[k] = dict(total=sum(segs), segs=segs, ends=ends, planes=planes)
    return out

# ============================================================
# 通り芯の名前
# ============================================================
def axis_names(lines, texts):
    lyA = CFG['通り芯レイヤ'].lower()
    # 通り芯は一点鎖線（lt5/6）で、記号の十字（実線・短い）と区別する
    def isaxis(l):
        return (l['ly'] == lyA and l['lt'] in (5, 6) and
                math.hypot(l['x2']-l['x1'], l['y2']-l['y1']) > 1000)
    vs = [l for l in lines if isaxis(l) and abs(l['x1']-l['x2']) < EPS]
    hs = [l for l in lines if isaxis(l) and abs(l['y1']-l['y2']) < EPS]
    xn, yn = {}, {}
    for t in texts:
        if t['ly'] != lyA: continue
        s = t['s'].strip()
        cx, cy = txt_center(t)
        if re.match(r'^[XxＸｘ]\d+$', s) and vs:
            best = min(vs, key=lambda l: abs(l['x1'] - cx))
            if abs(best['x1'] - cx) < 500: xn[best['x1']] = s
        elif re.match(r'^[YyＹｙ]\d+$', s) and hs:
            best = min(hs, key=lambda l: abs(l['y1'] - cy))
            if abs(best['y1'] - cy) < 500: yn[best['y1']] = s
    return xn, yn
def name_at(tbl, v):
    for k, s in tbl.items():
        if abs(k - v) < 5: return s
    return None

# ============================================================
# 作図データの生成
# ============================================================
P = []   # ('line',ly,lc,lt,x1,y1,x2,y2) ('circle',..) ('point',ly,x,y)
         # ('text',ly,lc,mm,x,y,dx,dy,s) ('dimfig',ly,lc,mm,x1,y1,x2,y2,tx,ty,tdx,tdy,s)
LT_SOLID, LT_CHAIN = 1, 5
def line(ly,lc,lt,x1,y1,x2,y2): P.append(('line',ly,lc,lt,x1,y1,x2,y2))
def circle(ly,lc,lt,x,y,r):     P.append(('circle',ly,lc,lt,x,y,r))
def point(ly,x,y):              P.append(('point',ly,x,y))
def text_h(ly,lc,mm,cx,by,s):
    n=tlen(s,mm); P.append(('text',ly,lc,mm,cx-n/2,by,n,0,s))
def dimfig_h(ly,lc,mm,x1,y1,x2,y2,cx,by,s):
    n=tlen(s,mm); P.append(('dimfig',ly,lc,mm,x1,y1,x2,y2,cx-n/2,by,n,0,s))
def dimfig_v(ly,lc,mm,x1,y1,x2,y2,bx,cy,s):
    n=tlen(s,mm); P.append(('dimfig',ly,lc,mm,x1,y1,x2,y2,bx,cy-n/2,0,n,s))

def draw_face(ox, oy, L, H, room, mark, axis, steps, chain):
    LY_A,LY_D,LY_F,LY_T,LY_S = (I('レイヤ_基準線'),I('レイヤ_寸法'),I('レイヤ_外形線'),
                                I('レイヤ_文字'),I('レイヤ_段差線'))
    C_A,C_M,C_D,C_F,C_S,C_B,C_T = (I('線色_基準線'),I('線色_通り芯記号'),I('線色_寸法'),
                                   I('線色_外形線'),I('線色_段差線'),I('線色_面記号枠'),
                                   I('線色_文字'))
    TD,TN,TX = F('文字高_寸法'),F('文字高_室名'),F('文字高_通り芯記号')
    fl, fr = ox+WALL_T, ox+L-WALL_T
    # 外形線
    line(LY_F,C_F,LT_SOLID, fl,oy,   fr,oy  ); line(LY_F,C_F,LT_SOLID, fr,oy,   fr,oy+H)
    line(LY_F,C_F,LT_SOLID, fr,oy+H, fl,oy+H); line(LY_F,C_F,LT_SOLID, fl,oy+H, fl,oy  )
    # 段差線
    for s in steps:
        line(LY_S,C_S,LT_SOLID, ox+s,oy, ox+s,oy+H)
    # 基準線＋通り芯記号
    for pos, mk in axis:
        x = ox+pos
        line(LY_A,C_A,LT_CHAIN, x, oy-AX_DN, x, oy+H+AX_UP)
        if mk:
            cy = oy+H+AX_CIR_Y
            circle(LY_A,C_M,LT_SOLID, x, cy, AX_CIR_R)
            line(LY_A,C_M,LT_SOLID, x-AX_CIR_R-AX_TICK/2, cy, x-AX_CIR_R+AX_TICK/2, cy)
            line(LY_A,C_M,LT_SOLID, x+AX_CIR_R-AX_TICK/2, cy, x+AX_CIR_R+AX_TICK/2, cy)
            line(LY_A,C_M,LT_SOLID, x, cy-AX_CIR_R-AX_TICK/2, x, cy-AX_CIR_R+AX_TICK/2)
            line(LY_A,C_M,LT_SOLID, x, cy+AX_CIR_R-AX_TICK/2, x, cy+AX_CIR_R+AX_TICK/2)
            text_h(LY_A,C_T,TX, x, cy-theight(TX)/2, mk)
    # 幅寸法（芯々）
    def hdim(y, x1, x2, val):
        point(LY_D, x1,y); point(LY_D, x2,y)
        dimfig_h(LY_D,C_D,TD, x1,y, x2,y, (x1+x2)/2, y+DIM_TXT_GAP,
                 '{:,}'.format(int(round(val))))
    y_in = oy+H+DIM_OFF
    if len(chain) > 1:
        a = 0
        for s in chain: hdim(y_in, ox+a, ox+a+s, s); a += s
        hdim(y_in+DIM_STEP, ox, ox+L, L)
    else:
        hdim(y_in, ox, ox+L, L)
    # 高さ寸法
    xd = ox-VDIM_OFF
    line(LY_D,C_D,LT_SOLID, xd,oy,   xd+VDIM_EXT,oy)
    line(LY_D,C_D,LT_SOLID, xd,oy+H, xd+VDIM_EXT,oy+H)
    point(LY_D, xd,oy); point(LY_D, xd,oy+H)
    dimfig_v(LY_D,C_D,TD, xd,oy, xd,oy+H, xd-DIM_TXT_GAP, oy+H/2,
             '{:,}'.format(int(round(H))))
    # 室名
    text_h(LY_T,C_T,TN, ox+L/2, oy+H/2-theight(TN)/2, room)
    # 面記号
    bw = tlen(mark,TN)+NAMEBOX_PAD*2
    bx = ox+L/2-bw/2; bt = oy-NAMEBOX_TOP; bb = bt-NAMEBOX_H
    line(LY_F,C_B,LT_SOLID, bx,bb, bx+bw,bb); line(LY_F,C_B,LT_SOLID, bx+bw,bb, bx+bw,bt)
    line(LY_F,C_B,LT_SOLID, bx+bw,bt, bx,bt); line(LY_F,C_B,LT_SOLID, bx,bt, bx,bb)
    text_h(LY_T,C_T,TN, ox+L/2, bb+(NAMEBOX_H-theight(TN))/2, mark)

# ============================================================
# 出力
# ============================================================
def fm(v):
    s = ('%.2f' % v).rstrip('0').rstrip('.')
    return s if s not in ('', '-') else '0'
def emit(dx=0.0, dy=0.0):
    o = ['lg%s' % CFG['作図レイヤグループ']]
    for ly in sorted({e[1] for e in P}):
        es = [e for e in P if e[1] == ly]
        o.append('ly%x' % ly)
        lc = lt = size = pn = None
        for e in es:
            if e[0] == 'point':
                if pn is None: pn = I('線色_実点'); o.append('pn%d' % pn)
                o.append('pt %s %s' % (fm(e[2]+dx), fm(e[3]+dy)))
            elif e[0] == 'dimfig':
                if e[2] != lc: lc = e[2]; o.append('lc%d' % lc)
                if lt != LT_SOLID: lt = LT_SOLID; o.append('lt%d' % lt)
                o.append('msg')
                o.append('%s %s %s %s' % (fm(e[4]+dx),fm(e[5]+dy),fm(e[6]+dx),fm(e[7]+dy)))
                if e[3] != size: size = e[3]; o.append('cn%d' % CHAR_TYPE[size])
                o.append('cs %s %s %s %s "%s' % (fm(e[8]+dx),fm(e[9]+dy),
                                                 fm(e[10]),fm(e[11]),e[12]))
                o.append('#')
            elif e[0] == 'line':
                if e[2] != lc: lc = e[2]; o.append('lc%d' % lc)
                if e[3] != lt: lt = e[3]; o.append('lt%d' % lt)
                o.append('%s %s %s %s' % (fm(e[4]+dx),fm(e[5]+dy),fm(e[6]+dx),fm(e[7]+dy)))
            elif e[0] == 'circle':
                if e[2] != lc: lc = e[2]; o.append('lc%d' % lc)
                if e[3] != lt: lt = e[3]; o.append('lt%d' % lt)
                o.append('ci %s %s %s' % (fm(e[4]+dx),fm(e[5]+dy),fm(e[6])))
            else:
                if e[2] != lc: lc = e[2]; o.append('lc%d' % lc)
                if e[3] != size: size = e[3]; o.append('cn%d' % CHAR_TYPE[size])
                o.append('ch %s %s %s %s "%s' % (fm(e[4]+dx),fm(e[5]+dy),
                                                 fm(e[6]),fm(e[7]),e[8]))
    return o

# ============================================================
# 本体
# ============================================================
def main():
    temp = None
    for c in (os.path.join(os.getcwd(),'jwc_temp.txt'), os.path.join(HERE,'jwc_temp.txt')):
        if os.path.exists(c): temp = c; break
    if temp is None:
        sys.stderr.write('jwc_temp.txt が見つかりません。\n'); return 1
    lines, texts, raws = read_temp(temp)

    lyW = CFG['壁芯線レイヤ'].lower()
    lyN = CFG['室名レイヤ'].lower()
    lyH = CFG['天井高レイヤ'].lower()
    walls = [l for l in lines if l['ly'] == lyW]
    names = [t for t in texts if t['ly'] == lyN]
    chs   = [t for t in texts if t['ly'] == lyH]
    msg = []
    if not walls:
        msg.append('壁芯線レイヤ「%s」に線がありません。' % CFG['壁芯線レイヤ'])
    if not chs:
        msg.append('天井高レイヤ「%s」に文字がありません。' % CFG['天井高レイヤ'])
    if msg:
        sys.stderr.write('\n'.join(msg) + '\n設定は tenkaizu_setting.txt で変更できます。\n')
        return 1

    polys, area = detect_rooms(walls)
    xn, yn = axis_names(lines, texts)
    pre = CFG['天井高の接頭辞']

    rooms = []
    for poly in polys:
        nm = [t for t in names if inside(txt_center(t), poly)]
        ch = [t for t in chs   if inside(txt_center(t), poly)]
        if not nm or not ch: continue
        c = txt_center(ch[0])
        nm.sort(key=lambda t: math.hypot(txt_center(t)[0]-c[0], txt_center(t)[1]-c[1]))
        h = re.sub(r'[^\d.]', '', ch[0]['s'].replace(pre, ''))
        if not h: continue
        rooms.append((nm[0]['s'].strip(), float(h), poly))

    if not rooms:
        sys.stderr.write('室名と天井高が揃った室が見つかりませんでした。\n')
        return 1

    # ---- 面の組み立て ----
    plan = []                      # (室名, 天井高, 面記号, 芯々幅, 基準線, 段差, 内訳)
    for nm, H, poly in rooms:
        fs = faces_of(poly)
        for k in range(4):
            if k not in fs: continue
            f = fs[k]; L = f['total']; segs = f['segs']
            a0, a1 = f['ends']
            tbl = xn if k in (0,2) else yn
            m0, m1 = name_at(tbl, a0), name_at(tbl, a1)
            axis = [(0.0, m0)]
            acc = 0.0
            for s in segs[:-1]:
                acc += s; axis.append((acc, None))
            axis.append((L, m1))
            # 段差線は壁「面」の位置。奥行が深い側へ壁厚半分ぶん食い込む
            deeper_is_larger = k in (0, 1)
            pl = f['planes']; steps = []; acc = 0.0
            for i in range(len(segs)-1):
                acc += segs[i]
                near_side_deeper = (pl[i] > pl[i+1]) == deeper_is_larger
                steps.append(acc - WALL_T if near_side_deeper else acc + WALL_T)
            plan.append((nm, H, FACE_MARK[k], L, axis, steps, segs, poly, k))

    # ---- 割付 ----
    total_w = F('用紙幅')*SCALE
    GAP_X, GAP_Y = F('面の間隔_横'), F('面の間隔_縦')
    per_room = CFG['室ごとに改行'].strip() in ('する','はい','yes','1')
    x = 0.0; y = 0.0; rowh = 0.0; placed = []
    prev = None
    for item in plan:
        nm,H,mark,L,axis,steps,segs,poly,k = item
        w = L + PAD_L + PAD_R
        h = H + PAD_T + PAD_B
        if x > 0 and (x + w > total_w or (per_room and nm != prev)):
            x = 0.0; y -= rowh + GAP_Y; rowh = 0.0
        placed.append((x + PAD_L, y - h + PAD_B, item))
        x += w + GAP_X; rowh = max(rowh, h); prev = nm
    for ox, oy, item in placed:
        nm,H,mark,L,axis,steps,segs,poly,k = item
        draw_face(ox, oy, L, H, nm, mark, axis, steps, segs)

    xs=[];ys=[]
    for e in P:
        if e[0]=='line': xs+=[e[4],e[6]]; ys+=[e[5],e[7]]
        elif e[0]=='circle': xs+=[e[4]-e[6],e[4]+e[6]]; ys+=[e[5]-e[6],e[5]+e[6]]
        elif e[0]=='point': xs+=[e[2]]; ys+=[e[3]]
        elif e[0]=='dimfig': xs+=[e[4],e[6],e[8],e[8]+e[10]]; ys+=[e[5],e[7],e[9],e[9]+e[11]+theight(e[3])]
        else: xs+=[e[4],e[4]+e[6]]; ys+=[e[5],e[5]+e[7]+theight(e[3])]
    bx0, by0 = min(xs), min(ys)

    # 配置基準点（REM #1 の hp1）。無ければ原点
    ox = oy = 0.0
    for raw in open(temp, encoding='cp932', errors='replace').read().splitlines():
        t = raw.strip()
        if t.startswith('hp1 '):
            p = t.split()
            if len(p) >= 3: ox, oy = float(p[1]), float(p[2])
            break

    out = emit(ox - bx0, oy - by0)
    with open(temp, 'w', encoding='cp932', newline='') as f:
        f.write('\r\n'.join(out) + '\r\n')
    sys.stderr.write('%d室 %d面を作図しました（%s）\n'
                     % (len({r[0] for r in rooms}), len(plan),
                        '／'.join('%s(CH=%d)' % (n, h) for n, h, _ in rooms)))
    return 0

if __name__ == '__main__':
    sys.exit(main())
