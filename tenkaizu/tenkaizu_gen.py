# -*- coding: utf-8 -*-
"""展開図ジェネレータ  平面図(通り芯)→ 展開図 A/B/C/D  → 外部変形データ / DXF / プレビュー

.jwc はバイナリ形式（DOS版 Jw_cad 由来）のため出力しない。
Jw_cad へは外部変形（gaibu/）で作図させ、.jww で保存する。

文字は文字種(cn1..cn10)ではなく任意サイズ文字(cn0 幅 高さ 間隔 色)で出す。
文字種の寸法は環境ごとの設定に依存するため。

単位に注意:
  座標・文字列の長さベクトル … 実寸 mm（1/100 なら用紙 mm × 100）
  cn0 の幅・高さ・間隔        … 用紙 mm（縮尺をかけない）
"""
import unicodedata, os

SCALE = 100                              # 1/100
PAPER_W, PAPER_H = 420.0, 297.0          # A3
HALF_W, HALF_H = PAPER_W/2*SCALE, PAPER_H/2*SCALE
WALL_T = 80                              # 基準線から壁仕上面までの寄り

# ---- 文字高（用紙 mm）----------------------------------------
TXT_DIM  = 2.0     # 寸法値
TXT_AXIS = 3.5     # 通り芯記号（X1・Y4 など）
TXT_NAME = 2.5     # 室名・面記号

# ---- 作図規約（実寸 mm）--------------------------------------
DIM_OFF, DIM_STEP, DIM_TXT_GAP = 375, 450, 30
VDIM_OFF, VDIM_EXT, DOT_R      = 760, 540, 25
AX_UP, AX_DN                   = 900, 1050
AX_CIR_R, AX_CIR_Y, AX_TICK    = 350, 1350, 250
NAMEBOX_TOP, NAMEBOX_H, NAMEBOX_PAD = 550, 350, 150

LT_SOLID, LT_CHAIN = 1, 5                # 線種 1=実線 5=一点鎖1

def tlen(s, mm):
    """文字列の実寸長さ。全角=1、半角=0.5 で数える（間隔0）。"""
    n = sum(1.0 if unicodedata.east_asian_width(c) in 'WFA' else 0.5 for c in s)
    return n * mm * SCALE
def theight(mm): return mm * SCALE

P = []   # ('line',ly,lt,x1,y1,x2,y2) ('circle',ly,lt,x,y,r) ('text',ly,mm,x1,y1,dx,dy,s)
def line(ly,lt,x1,y1,x2,y2): P.append(('line',ly,lt,x1,y1,x2,y2))
def circle(ly,lt,x,y,r):     P.append(('circle',ly,lt,x,y,r))
def text_h(ly,mm,cx,by,s):
    L=tlen(s,mm); P.append(('text',ly,mm,cx-L/2,by,L,0,s))
def text_v(ly,mm,bx,cy,s):
    L=tlen(s,mm); P.append(('text',ly,mm,bx,cy-L/2,0,L,s))

# ============ 1面ぶんの作図 ============
def draw_face(ox, oy, L, H, room, face, axis, steps, chain):
    t = WALL_T
    fl, fr = ox+t, ox+L-t

    # --- レイヤ3 枠線 ---
    line(3,LT_SOLID, fl,oy,   fr,oy  ); line(3,LT_SOLID, fr,oy,   fr,oy+H)
    line(3,LT_SOLID, fr,oy+H, fl,oy+H); line(3,LT_SOLID, fl,oy+H, fl,oy  )
    for s in steps:
        line(3,LT_SOLID, ox+s,oy, ox+s,oy+H)

    # --- レイヤ1 基準線（一点鎖線）＋通り芯記号（実線）---
    for pos, mk in axis:
        x = ox+pos
        line(1,LT_CHAIN, x, oy-AX_DN, x, oy+H+AX_UP)
        if mk:
            cy = oy+H+AX_CIR_Y
            circle(1,LT_SOLID, x, cy, AX_CIR_R)
            line(1,LT_SOLID, x-AX_CIR_R-AX_TICK/2, cy, x-AX_CIR_R+AX_TICK/2, cy)
            line(1,LT_SOLID, x+AX_CIR_R-AX_TICK/2, cy, x+AX_CIR_R+AX_TICK/2, cy)
            line(1,LT_SOLID, x, cy-AX_CIR_R-AX_TICK/2, x, cy-AX_CIR_R+AX_TICK/2)
            line(1,LT_SOLID, x, cy+AX_CIR_R-AX_TICK/2, x, cy+AX_CIR_R+AX_TICK/2)
            text_h(1,TXT_AXIS, x, cy-theight(TXT_AXIS)/2, mk)

    # --- レイヤ2 幅寸法（すべて芯々・基準線間）---
    def hdim(y, x1, x2, val):
        line(2,LT_SOLID, x1,y, x2,y)
        circle(2,LT_SOLID, x1,y, DOT_R); circle(2,LT_SOLID, x2,y, DOT_R)
        text_h(2,TXT_DIM, (x1+x2)/2, y+DIM_TXT_GAP, '{:,}'.format(int(round(val))))
    y_in = oy+H+DIM_OFF
    if chain:
        a = 0
        for s in chain:
            hdim(y_in, ox+a, ox+a+s, s); a += s
        hdim(y_in+DIM_STEP, ox, ox+L, L)
    else:
        hdim(y_in, ox, ox+L, L)

    # --- レイヤ2 高さ寸法（天井高）---
    xd = ox-VDIM_OFF
    line(2,LT_SOLID, xd,oy, xd,oy+H)
    circle(2,LT_SOLID, xd,oy, DOT_R); circle(2,LT_SOLID, xd,oy+H, DOT_R)
    line(2,LT_SOLID, xd,oy, xd+VDIM_EXT,oy); line(2,LT_SOLID, xd,oy+H, xd+VDIM_EXT,oy+H)
    text_v(2,TXT_DIM, xd-DIM_TXT_GAP, oy+H/2, '{:,}'.format(int(round(H))))

    # --- レイヤ4 室名 ---
    text_h(4,TXT_NAME, ox+L/2, oy+H/2-theight(TXT_NAME)/2, room)

    # --- 面記号（枠=レイヤ3／文字=レイヤ4）---
    bw = tlen(face,TXT_NAME)+NAMEBOX_PAD*2
    bx = ox+L/2-bw/2; bt = oy-NAMEBOX_TOP; bb = bt-NAMEBOX_H
    line(3,LT_SOLID, bx,bb, bx+bw,bb); line(3,LT_SOLID, bx+bw,bb, bx+bw,bt)
    line(3,LT_SOLID, bx+bw,bt, bx,bt); line(3,LT_SOLID, bx,bt, bx,bb)
    text_h(4,TXT_NAME, ox+L/2, bb+(NAMEBOX_H-theight(TXT_NAME))/2, face)

# ============ 室の定義 ============
ROOMS = [
    ('洋室-1', 2500, [
        ('Ａ　面', 3640, [(0,'X1'),(3640,'X2')],            [],     None),
        ('Ｂ　面', 2550, [(0,'Y2'),(980,None),(2550,None)],  [900],  [980,1570]),
        ('Ｃ　面', 3640, [(0,'X2'),(910,None),(3640,'X1')],  [990],  [910,2730]),
        ('Ｄ　面', 2550, [(0,None),(2550,'Y2')],             [],     None),
    ]),
    ('事務室', 2700, [
        ('Ａ　面', 3640, [(0,'X2'),(1540,None),(3640,'X3')], [1460], [1540,2100]),
        ('Ｂ　面', 4550, [(0,'Y4'),(1000,None),(4550,None)], [1080], [1000,3550]),
        ('Ｃ　面', 3640, [(0,'X3'),(3640,'X2')],             [],     None),
        ('Ｄ　面', 4550, [(0,None),(4550,'Y4')],             [],     None),
    ]),
]

# ============ A3 への割付 ============
PAD_L, PAD_R, PAD_T, PAD_B = 1150, 500, 1800, 1200
GAP_X, GAP_Y = 3000, 4500
rows=[]
for room,H,faces in ROOMS:
    rows.append((room,H,faces,
                 sum(f[1]+PAD_L+PAD_R for f in faces)+GAP_X*(len(faces)-1),
                 H+PAD_T+PAD_B))
y_top = sum(r[4] for r in rows)/2 + GAP_Y*(len(rows)-1)/2
for room,H,faces,rw,rh in rows:
    oy = y_top-rh+PAD_B; x = -rw/2
    for face,L,axis,steps,chain in faces:
        draw_face(x+PAD_L, oy, L, H, room, face, axis, steps, chain)
        x += PAD_L+L+PAD_R+GAP_X
    y_top -= rh+GAP_Y

xs=[];ys=[]
for e in P:
    if e[0]=='line': xs+=[e[3],e[5]]; ys+=[e[4],e[6]]
    elif e[0]=='circle': xs+=[e[3]-e[5],e[3]+e[5]]; ys+=[e[4]-e[5],e[4]+e[5]]
    else: xs+=[e[3],e[3]+e[5]]; ys+=[e[4],e[4]+e[6]+theight(e[2])]
BX0,BY0 = min(xs), min(ys)
print('要素数 %d   X %.0f..%.0f (用紙 ±%.0f)   Y %.0f..%.0f (用紙 ±%.0f)'
      % (len(P),min(xs),max(xs),HALF_W,min(ys),max(ys),HALF_H))
assert min(xs)>-HALF_W and max(xs)<HALF_W and min(ys)>-HALF_H and max(ys)<HALF_H

# ============ 出力 ============
LC={1:1,2:1,3:2,4:1}
def fm(v): return ('%.2f'%v).rstrip('0').rstrip('.')

def elements(dx=0.0, dy=0.0):
    o=[]
    for ly in (1,2,3,4):
        es=[e for e in P if e[1]==ly]
        if not es: continue
        o += ['ly%d'%ly, 'lc%d'%LC[ly]]
        lt=None; size=None
        for e in es:
            if e[0]=='line':
                if e[2]!=lt: lt=e[2]; o.append('lt%d'%lt)
                o.append('%s %s %s %s'%(fm(e[3]+dx),fm(e[4]+dy),fm(e[5]+dx),fm(e[6]+dy)))
            elif e[0]=='circle':
                if e[2]!=lt: lt=e[2]; o.append('lt%d'%lt)
                o.append('ci %s %s %s'%(fm(e[3]+dx),fm(e[4]+dy),fm(e[5])))
            else:
                if e[2]!=size:
                    size=e[2]
                    # cn0 幅 高さ 間隔 色（任意サイズ文字）
                    # 文字サイズは「用紙 mm」。座標と長さベクトルは実寸 mm。
                    o.append('cn0 %s %s 0 %d'%(fm(size),fm(size),LC[ly]))
                # ch 始点X 始点Y 長さX 長さY "文字列
                o.append('ch %s %s %s %s "%s'%(fm(e[3]+dx),fm(e[4]+dy),
                                               fm(e[5]),fm(e[6]),e[7]))
    return o

HEAD = ['# 展開図  洋室-1 / 事務室   A3  S=1/100',
        '# レイヤ1:基準線  レイヤ2:寸法線  レイヤ3:枠線  レイヤ4:文字']
def gaibu(): return '\r\n'.join(HEAD+elements(-BX0, -BY0))+'\r\n'

def dxf():
    o=[]; a=lambda c,v: o.extend([str(c),str(v)])
    a(0,'SECTION'); a(2,'TABLES')
    a(0,'TABLE'); a(2,'LTYPE'); a(70,2)
    a(0,'LTYPE'); a(2,'CONTINUOUS'); a(70,0); a(3,'Solid line'); a(72,65); a(73,0); a(40,0.0)
    a(0,'LTYPE'); a(2,'DASHDOT'); a(70,0); a(3,'Dash dot'); a(72,65); a(73,4); a(40,600.0)
    a(49,400.0); a(49,-100.0); a(49,0.0); a(49,-100.0)
    a(0,'ENDTAB')
    a(0,'TABLE'); a(2,'LAYER'); a(70,4)
    for ly in (1,2,3,4):
        a(0,'LAYER'); a(2,str(ly)); a(70,0); a(62,LC[ly]); a(6,'CONTINUOUS')
    a(0,'ENDTAB')
    a(0,'TABLE'); a(2,'STYLE'); a(70,1)
    a(0,'STYLE'); a(2,'STANDARD'); a(70,0); a(40,0.0); a(41,1.0); a(50,0.0)
    a(71,0); a(42,2.5); a(3,'txt'); a(4,'')
    a(0,'ENDTAB'); a(0,'ENDSEC')
    a(0,'SECTION'); a(2,'ENTITIES')
    for e in P:
        ly=str(e[1])
        if e[0]=='line':
            a(0,'LINE'); a(8,ly); a(6,'DASHDOT' if e[2]==LT_CHAIN else 'CONTINUOUS')
            a(10,e[3]); a(20,e[4]); a(30,0.0); a(11,e[5]); a(21,e[6]); a(31,0.0)
        elif e[0]=='circle':
            a(0,'CIRCLE'); a(8,ly); a(6,'CONTINUOUS')
            a(10,e[3]); a(20,e[4]); a(30,0.0); a(40,e[5])
        else:
            a(0,'TEXT'); a(8,ly); a(10,e[3]); a(20,e[4]); a(30,0.0); a(40,theight(e[2]))
            a(1,e[7]); a(50, 90 if abs(e[5])<1e-6 else 0); a(7,'STANDARD')
    a(0,'ENDSEC'); a(0,'EOF')
    return '\r\n'.join(o)+'\r\n'

D=os.path.dirname(os.path.abspath(__file__))+'/out/'
os.makedirs(D, exist_ok=True)
open(D+'tenkaizu.dxf','w',encoding='cp932',newline='').write(dxf())
open(D+'tenkaizu_data.txt','w',encoding='cp932',newline='').write(gaibu())
for f in ('tenkaizu.dxf','tenkaizu_data.txt'):
    print('  %-20s %6d bytes'%(f, os.path.getsize(D+f)))

# ============ プレビュー ============
import pymupdf
MM=72/25.4
doc=pymupdf.open(); pg=doc.new_page(width=PAPER_W*MM,height=PAPER_H*MM)
px=lambda x:(x/SCALE+PAPER_W/2)*MM
py=lambda y:(PAPER_H/2-y/SCALE)*MM
for e in P:
    ly=e[1]; w=0.5 if ly==3 else 0.15
    if e[0]=='line':
        sh=pg.new_shape(); sh.draw_line((px(e[3]),py(e[4])),(px(e[5]),py(e[6])))
        sh.finish(width=w,color=(0,0,0),dashes='[3 2] 0' if e[2]==LT_CHAIN else None); sh.commit()
    elif e[0]=='circle':
        sh=pg.new_shape(); sh.draw_circle((px(e[3]),py(e[4])),e[5]/SCALE*MM)
        sh.finish(width=w,color=(0,0,0),fill=(0,0,0) if e[5]<=DOT_R else None); sh.commit()
    else:
        pg.insert_text((px(e[3]),py(e[4])), e[7], fontname='japan',
                       fontsize=theight(e[2])/SCALE*MM, rotate=90 if abs(e[5])<1e-6 else 0)
doc.save(D+'preview.pdf')
pymupdf.open(D+'preview.pdf')[0].get_pixmap(dpi=200).save(D+'preview.png')
print('  preview ok')
