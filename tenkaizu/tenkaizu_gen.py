# -*- coding: utf-8 -*-
"""展開図ジェネレータ  平面図(通り芯)→ 展開図 A/B/C/D  → JWC / DXF / プレビュー"""
import unicodedata, os

SCALE   = 100          # 1/100
PAPER_W, PAPER_H = 420.0, 297.0        # A3
HALF_W, HALF_H  = PAPER_W/2*SCALE, PAPER_H/2*SCALE   # 実寸 21000 / 14850

# ---- 参考図から実測した作図規約（実寸 mm）--------------------
DIM_OFF      = 375     # 枠線から幅寸法線までの距離
DIM_STEP     = 450     # 内訳寸法 → 全体寸法の追い出し
DIM_TXT_GAP  = 30      # 寸法線から寸法値までのすき間
VDIM_OFF     = 760     # 基準線から高さ寸法線までの距離
VDIM_EXT     = 540     # 寸法補助線の長さ
DOT_R        = 25      # 寸法端部の点の半径
AX_UP        = 900     # 枠線上端から基準線上端まで
AX_DN        = 1050    # 枠線下端から基準線下端まで
AX_CIR_R     = 250     # 通り芯記号の円 半径
AX_CIR_Y     = 1250    # 枠線上端から円中心まで
AX_TICK      = 190     # 通り芯記号の十字ティック長さ
NAMEBOX_TOP  = 550     # 枠線下端から面記号枠の上端まで
NAMEBOX_H    = 350     # 面記号枠の高さ
NAMEBOX_PAD  = 150     # 面記号枠の左右余白

CH_W = {1: 2.0, 2: 2.5}     # 文字種1=2.0mm / 文字種2=2.5mm（Jw_cad 既定）
CH_D = {1: 0.0, 2: 0.0}     # 文字間隔

def tlen(s, cn):
    """文字列の実寸長さ(mm)。全角=1、半角=0.5 で数える。"""
    n = sum(1.0 if unicodedata.east_asian_width(c) in 'WFA' else 0.5 for c in s)
    return (n*CH_W[cn] + (len(s)-1)*CH_D[cn]) * SCALE
def theight(cn):
    return CH_W[cn]*SCALE

# ============ プリミティブ ============
P = []   # ('line',ly,x1,y1,x2,y2) ('circle',ly,x,y,r) ('text',ly,x1,y1,x2,y2,cn,s)
def line(ly,x1,y1,x2,y2): P.append(('line',ly,x1,y1,x2,y2))
def circle(ly,x,y,r):     P.append(('circle',ly,x,y,r))
def text_h(ly,cx,by,cn,s):      # 水平・中央振り分け
    L=tlen(s,cn); P.append(('text',ly,cx-L/2,by,cx+L/2,by,cn,s))
def text_v(ly,bx,cy,cn,s):      # 下から上へ読む縦書き・中央振り分け
    L=tlen(s,cn); P.append(('text',ly,bx,cy-L/2,bx,cy+L/2,cn,s))

# ============ 1面ぶんの作図 ============
def draw_face(ox, oy, W, H, room, face, seglist, mark_l, mark_r):
    """(ox,oy)=枠線の左下。seglist=左からの内訳寸法（段差なしなら[W]）"""
    # --- レイヤ3 枠線 ---
    line(3, ox,   oy,   ox+W, oy  )
    line(3, ox+W, oy,   ox+W, oy+H)
    line(3, ox+W, oy+H, ox,   oy+H)
    line(3, ox,   oy+H, ox,   oy  )
    acc = 0
    for s in seglist[:-1]:                      # 段差の縦線
        acc += s
        line(3, ox+acc, oy, ox+acc, oy+H)

    # --- レイヤ1 基準線＋通り芯記号 ---
    for x, mk in ((ox, mark_l), (ox+W, mark_r)):
        line(1, x, oy-AX_DN, x, oy+H+AX_UP)
        if mk:
            cy = oy+H+AX_CIR_Y
            circle(1, x, cy, AX_CIR_R)
            line(1, x-AX_CIR_R-AX_TICK/2, cy, x-AX_CIR_R+AX_TICK/2, cy)
            line(1, x+AX_CIR_R-AX_TICK/2, cy, x+AX_CIR_R+AX_TICK/2, cy)
            line(1, x, cy-AX_CIR_R-AX_TICK/2, x, cy-AX_CIR_R+AX_TICK/2)
            line(1, x, cy+AX_CIR_R-AX_TICK/2, x, cy+AX_CIR_R+AX_TICK/2)
            text_h(1, x, cy-theight(1)/2, 1, mk)

    # --- レイヤ2 幅寸法（段差があるときは内訳＋全体の2段）---
    def hdim(y, x1, x2, val):
        line(2, x1, y, x2, y)
        circle(2, x1, y, DOT_R); circle(2, x2, y, DOT_R)
        text_h(2, (x1+x2)/2, y+DIM_TXT_GAP, 1, '{:,}'.format(int(round(val))))
    y_in = oy+H+DIM_OFF
    if len(seglist) > 1:
        acc = 0
        for s in seglist:
            hdim(y_in, ox+acc, ox+acc+s, s); acc += s
        hdim(y_in+DIM_STEP, ox, ox+W, W)
    else:
        hdim(y_in, ox, ox+W, W)

    # --- レイヤ2 高さ寸法（天井高）---
    xd = ox-VDIM_OFF
    line(2, xd, oy, xd, oy+H)
    circle(2, xd, oy, DOT_R); circle(2, xd, oy+H, DOT_R)
    line(2, xd, oy,   xd+VDIM_EXT, oy  )
    line(2, xd, oy+H, xd+VDIM_EXT, oy+H)
    text_v(2, xd-DIM_TXT_GAP, oy+H/2, 1, '{:,}'.format(int(round(H))))

    # --- レイヤ4 室名（枠内中央）---
    text_h(4, ox+W/2, oy+H/2-theight(2)/2, 2, room)

    # --- 面記号（枠=レイヤ3／文字=レイヤ4）---
    s  = face
    L  = tlen(s,2); bw = L+NAMEBOX_PAD*2
    bx = ox+W/2-bw/2; bt = oy-NAMEBOX_TOP; bb = bt-NAMEBOX_H
    line(3, bx,    bb, bx+bw, bb); line(3, bx+bw, bb, bx+bw, bt)
    line(3, bx+bw, bt, bx,    bt); line(3, bx,    bt, bx,    bb)
    text_h(4, ox+W/2, bb+(NAMEBOX_H-theight(2))/2, 2, s)

# ============ 室の定義 ============
# 各面: (面記号, 幅, 内訳, 左端の通り芯記号, 右端の通り芯記号)
ROOMS = [
    ('洋室-1', 2500, [
        ('Ａ　面', 3640, [3640],       'X1', 'X2'),
        ('Ｂ　面', 2550, [980, 1570],  'Y2', None),
        ('Ｃ　面', 3640, [910, 2730],  'X2', 'X1'),
        ('Ｄ　面', 2550, [2550],       None, 'Y2'),
    ]),
    ('事務室', 2700, [
        ('Ａ　面', 3640, [1540, 2100], 'X2', 'X3'),
        ('Ｂ　面', 4550, [1000, 3550], 'Y4', None),
        ('Ｃ　面', 3640, [3640],       'X3', 'X2'),
        ('Ｄ　面', 4550, [4550],       None, 'Y4'),
    ]),
]

# ============ A3 への割付 ============
PAD_L, PAD_R = 1150, 350        # 枠線を基準にした1面ぶんの左右余白
PAD_T, PAD_B = 1600, 1200       # 　　　　　　　　　　　　　上下余白
GAP_X, GAP_Y = 3000, 4500

rows = []
for room, H, faces in ROOMS:
    w = sum(f[1]+PAD_L+PAD_R for f in faces) + GAP_X*(len(faces)-1)
    rows.append((room, H, faces, w, H+PAD_T+PAD_B))
total_h = sum(r[4] for r in rows) + GAP_Y*(len(rows)-1)

y_top = total_h/2
for room, H, faces, rw, rh in rows:
    oy = y_top - rh + PAD_B          # 枠線の下端
    x  = -rw/2
    for face, W, segs, ml, mr in faces:
        draw_face(x+PAD_L, oy, W, H, room, face, segs, ml, mr)
        x += PAD_L+W+PAD_R+GAP_X
    y_top -= rh + GAP_Y

# ============ 収まり確認 ============
xs=[];ys=[]
for e in P:
    if e[0]=='line':   xs+=[e[2],e[4]]; ys+=[e[3],e[5]]
    elif e[0]=='circle': xs+=[e[2]-e[4],e[2]+e[4]]; ys+=[e[3]-e[4],e[3]+e[4]]
    else:
        xs+=[e[2],e[4]]; ys+=[e[3],e[5]+theight(e[6])]
print('要素数 %d   X %.0f..%.0f (用紙 ±%.0f)   Y %.0f..%.0f (用紙 ±%.0f)'
      % (len(P), min(xs), max(xs), HALF_W, min(ys), max(ys), HALF_H))
assert min(xs)>-HALF_W and max(xs)<HALF_W and min(ys)>-HALF_H and max(ys)<HALF_H, '用紙からはみ出し'

# ============ JWC 出力 ============
LT = {1:5, 2:1, 3:1, 4:1}      # 線種 (5=一点鎖1)
LC = {1:1, 2:1, 3:2, 4:1}      # 線色
def fm(v):
    return ('%.2f' % v).rstrip('0').rstrip('.')
def jwc():
    o = ['# 展開図  洋室-1 / 事務室   A3  S=1/100',
         '# レイヤ1:基準線  レイヤ2:寸法線  レイヤ3:枠線  レイヤ4:文字',
         'hq', 'hp 3', 'hs %d' % SCALE, 'lg0']
    for ly in (1,2,3,4):
        es = [e for e in P if e[1]==ly]
        if not es: continue
        o += ['ly%d' % ly, 'lc%d' % LC[ly], 'lt%d' % LT[ly]]
        cn = None
        for e in es:
            if e[0]=='line':
                o.append(' '.join(fm(v) for v in e[2:6]))
            elif e[0]=='circle':
                o.append('ci %s %s %s' % (fm(e[2]), fm(e[3]), fm(e[4])))
            else:
                if e[6]!=cn: cn=e[6]; o.append('cn%d' % cn)
                o.append('ch %s %s %s %s "%s' % (fm(e[2]),fm(e[3]),fm(e[4]),fm(e[5]),e[7]))
    return '\r\n'.join(o) + '\r\n'

# ============ DXF 出力 (R12) ============
def dxf():
    o=[]; a=lambda c,v: o.extend([str(c), str(v)])
    a(0,'SECTION'); a(2,'TABLES')
    a(0,'TABLE'); a(2,'LTYPE'); a(70,2)
    a(0,'LTYPE'); a(2,'CONTINUOUS'); a(70,0); a(3,'Solid line'); a(72,65); a(73,0); a(40,0.0)
    a(0,'LTYPE'); a(2,'DASHDOT');    a(70,0); a(3,'Dash dot');   a(72,65); a(73,4); a(40,600.0)
    a(49,400.0); a(49,-100.0); a(49,0.0); a(49,-100.0)
    a(0,'ENDTAB')
    a(0,'TABLE'); a(2,'LAYER'); a(70,4)
    for ly in (1,2,3,4):
        a(0,'LAYER'); a(2,str(ly)); a(70,0); a(62,LC[ly]); a(6,'DASHDOT' if ly==1 else 'CONTINUOUS')
    a(0,'ENDTAB')
    a(0,'TABLE'); a(2,'STYLE'); a(70,1)
    a(0,'STYLE'); a(2,'STANDARD'); a(70,0); a(40,0.0); a(41,1.0); a(50,0.0)
    a(71,0); a(42,2.5); a(3,'txt'); a(4,'')
    a(0,'ENDTAB'); a(0,'ENDSEC')
    a(0,'SECTION'); a(2,'ENTITIES')
    for e in P:
        ly=str(e[1])
        if e[0]=='line':
            a(0,'LINE'); a(8,ly); a(10,e[2]); a(20,e[3]); a(11,e[4]); a(21,e[5])
        elif e[0]=='circle':
            a(0,'CIRCLE'); a(8,ly); a(10,e[2]); a(20,e[3]); a(40,e[4])
        else:
            x1,y1,x2,y2,cn,s = e[2],e[3],e[4],e[5],e[6],e[7]
            rot = 90 if abs(x2-x1) < 1e-6 else 0
            a(0,'TEXT'); a(8,ly); a(10,x1); a(20,y1); a(30,0.0); a(40,theight(cn))
            a(1,s); a(50,rot); a(7,'STANDARD')
    a(0,'ENDSEC'); a(0,'EOF')
    return '\r\n'.join(o)+'\r\n'

D=os.path.dirname(os.path.abspath(__file__))+'/out/'
open(D+'tenkaizu.jwc','w',encoding='cp932',newline='').write(jwc())
open(D+'tenkaizu.dxf','w',encoding='cp932',newline='').write(dxf())
print('JWC %d bytes / DXF %d bytes' % (os.path.getsize(D+'tenkaizu.jwc'), os.path.getsize(D+'tenkaizu.dxf')))

# ============ プレビュー PDF/PNG ============
import pymupdf
MM=72/25.4
doc=pymupdf.open(); pg=doc.new_page(width=PAPER_W*MM, height=PAPER_H*MM)
def px(x): return (x/SCALE + PAPER_W/2)*MM
def py(y): return (PAPER_H/2 - y/SCALE)*MM
DASH={1:'[3 2] 0'}
for e in P:
    ly=e[1]; w=(0.5 if ly==3 else 0.15)
    if e[0]=='line':
        sh=pg.new_shape(); sh.draw_line((px(e[2]),py(e[3])),(px(e[4]),py(e[5])))
        sh.finish(width=w,color=(0,0,0),dashes=DASH.get(ly)); sh.commit()
    elif e[0]=='circle':
        sh=pg.new_shape(); sh.draw_circle((px(e[2]),py(e[3])), e[4]/SCALE*MM)
        sh.finish(width=w,color=(0,0,0),fill=(0,0,0) if e[4]<=DOT_R else None); sh.commit()
    else:
        h=theight(e[6])/SCALE*MM
        rot = 90 if abs(e[4]-e[2])<1e-6 else 0
        pg.insert_text((px(e[2]),py(e[3])), e[7], fontname='japan', fontsize=h*1.0, rotate=rot)
doc.save(D+'preview.pdf')
pymupdf.open(D+'preview.pdf')[0].get_pixmap(dpi=200).save(D+'preview.png')
print('preview ok')
