# -*- coding: utf-8 -*-
"""展開図ジェネレータ  平面図(通り芯)→ 展開図 A/B/C/D  → 外部変形データ / DXF / プレビュー

.jwc はバイナリ形式（DOS版 Jw_cad 由来）のため出力しない。
Jw_cad へは外部変形（gaibu/）で作図させ、.jww で保存する。

単位:
  座標・文字列の長さベクトル … 実寸 mm（1/100 なら用紙 mm × 100）
  文字サイズ(hcw/hch/cn0)     … 用紙 mm（縮尺をかけない）

寸法は Jw_cad の寸法図形として出力する:
  pn<色> / pt x y      端部の実点
  msg                  寸法図形の開始マーカー
  x1 y1 x2 y2          寸法線
  cn<n> / cs …         寸法値（書式は ch と同じ）
  #                    区切り（捨ててはいけない）
"""
import unicodedata, os

SCALE = 100                              # 1/100
PAPER_W, PAPER_H = 420.0, 297.0          # A3
HALF_W, HALF_H = PAPER_W/2*SCALE, PAPER_H/2*SCALE
WALL_T = 80                              # 基準線から壁仕上面までの寄り

# ---- 文字高（用紙 mm）----------------------------------------
TXT_DIM, TXT_AXIS, TXT_NAME = 2.0, 3.5, 2.5
# 文字種テーブル（用紙 mm）。実機の hcw/hch と一致（Jw_cad 既定値）
CHAR_TYPE = {1.5:1, 2.0:2, 2.5:3, 3.0:4, 3.5:5, 4.0:6, 4.5:7, 5.0:8, 6.0:9, 12.0:10}

# ---- 線色 ----------------------------------------------------
C_AXIS   = 1    # 基準線
C_MARK   = 4    # 通り芯記号（円・十字）
C_DIM    = 2    # 寸法線・寸法補助線・寸法値
C_POINT  = 6    # 寸法端部の実点
C_FRAME  = 5    # 部屋の外形線・段差線
C_BOX    = 2    # 面記号の囲み枠
C_TEXT   = 1    # 室名・面記号・通り芯記号の文字

LT_SOLID, LT_CHAIN = 1, 5                # 線種 1=実線 5=一点鎖1

# ---- 作図規約（実寸 mm）--------------------------------------
DIM_OFF, DIM_STEP, DIM_TXT_GAP = 375, 450, 30
VDIM_OFF, VDIM_EXT             = 760, 540
AX_UP, AX_DN                   = 900, 1050
AX_CIR_R, AX_CIR_Y, AX_TICK    = 350, 1350, 250
NAMEBOX_TOP, NAMEBOX_H, NAMEBOX_PAD = 550, 350, 150

def tlen(s, mm):
    """文字列の実寸長さ。全角=1、半角=0.5 で数える（文字間隔は 0）。"""
    n = sum(1.0 if unicodedata.east_asian_width(c) in 'WFA' else 0.5 for c in s)
    return n * mm * SCALE
def theight(mm): return mm * SCALE

# ('line',ly,lc,lt,x1,y1,x2,y2)   ('circle',ly,lc,lt,x,y,r)   ('point',ly,x,y)
# ('text',ly,lc,mm,x1,y1,dx,dy,s) ('dimfig',ly,lc,mm,x1,y1,x2,y2,tx,ty,tdx,tdy,s)
P = []
def line(ly,lc,lt,x1,y1,x2,y2): P.append(('line',ly,lc,lt,x1,y1,x2,y2))
def circle(ly,lc,lt,x,y,r):     P.append(('circle',ly,lc,lt,x,y,r))
def point(ly,x,y):              P.append(('point',ly,x,y))
def text_h(ly,lc,mm,cx,by,s):
    n=tlen(s,mm); P.append(('text',ly,lc,mm,cx-n/2,by,n,0,s))
def dimfig_h(ly,lc,mm,x1,y1,x2,y2,cx,by,s):
    n=tlen(s,mm); P.append(('dimfig',ly,lc,mm,x1,y1,x2,y2,cx-n/2,by,n,0,s))
def dimfig_v(ly,lc,mm,x1,y1,x2,y2,bx,cy,s):
    n=tlen(s,mm); P.append(('dimfig',ly,lc,mm,x1,y1,x2,y2,bx,cy-n/2,0,n,s))

# ============ 1面ぶんの作図 ============
def draw_face(ox, oy, L, H, room, face, axis, steps, chain):
    fl, fr = ox+WALL_T, ox+L-WALL_T

    # --- レイヤ3 枠線（部屋の外形線）---
    line(3,C_FRAME,LT_SOLID, fl,oy,   fr,oy  ); line(3,C_FRAME,LT_SOLID, fr,oy,   fr,oy+H)
    line(3,C_FRAME,LT_SOLID, fr,oy+H, fl,oy+H); line(3,C_FRAME,LT_SOLID, fl,oy+H, fl,oy  )
    for s in steps:
        line(3,C_FRAME,LT_SOLID, ox+s,oy, ox+s,oy+H)

    # --- レイヤ1 基準線＋通り芯記号 ---
    for pos, mk in axis:
        x = ox+pos
        line(1,C_AXIS,LT_CHAIN, x, oy-AX_DN, x, oy+H+AX_UP)
        if mk:
            cy = oy+H+AX_CIR_Y
            circle(1,C_MARK,LT_SOLID, x, cy, AX_CIR_R)
            line(1,C_MARK,LT_SOLID, x-AX_CIR_R-AX_TICK/2, cy, x-AX_CIR_R+AX_TICK/2, cy)
            line(1,C_MARK,LT_SOLID, x+AX_CIR_R-AX_TICK/2, cy, x+AX_CIR_R+AX_TICK/2, cy)
            line(1,C_MARK,LT_SOLID, x, cy-AX_CIR_R-AX_TICK/2, x, cy-AX_CIR_R+AX_TICK/2)
            line(1,C_MARK,LT_SOLID, x, cy+AX_CIR_R-AX_TICK/2, x, cy+AX_CIR_R+AX_TICK/2)
            text_h(1,C_TEXT,TXT_AXIS, x, cy-theight(TXT_AXIS)/2, mk)

    # --- レイヤ2 幅寸法（芯々・基準線間）---
    def hdim(y, x1, x2, val):
        point(2, x1,y); point(2, x2,y)
        dimfig_h(2,C_DIM,TXT_DIM, x1,y, x2,y, (x1+x2)/2, y+DIM_TXT_GAP,
                 '{:,}'.format(int(round(val))))
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
    line(2,C_DIM,LT_SOLID, xd,oy,   xd+VDIM_EXT,oy)
    line(2,C_DIM,LT_SOLID, xd,oy+H, xd+VDIM_EXT,oy+H)
    point(2, xd,oy); point(2, xd,oy+H)
    dimfig_v(2,C_DIM,TXT_DIM, xd,oy, xd,oy+H, xd-DIM_TXT_GAP, oy+H/2,
             '{:,}'.format(int(round(H))))

    # --- レイヤ4 室名（枠内中央）---
    text_h(4,C_TEXT,TXT_NAME, ox+L/2, oy+H/2-theight(TXT_NAME)/2, room)

    # --- 面記号（枠=レイヤ3／文字=レイヤ4）---
    bw = tlen(face,TXT_NAME)+NAMEBOX_PAD*2
    bx = ox+L/2-bw/2; bt = oy-NAMEBOX_TOP; bb = bt-NAMEBOX_H
    line(3,C_BOX,LT_SOLID, bx,bb, bx+bw,bb); line(3,C_BOX,LT_SOLID, bx+bw,bb, bx+bw,bt)
    line(3,C_BOX,LT_SOLID, bx+bw,bt, bx,bt); line(3,C_BOX,LT_SOLID, bx,bt, bx,bb)
    text_h(4,C_TEXT,TXT_NAME, ox+L/2, bb+(NAMEBOX_H-theight(TXT_NAME))/2, face)

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

# ============ 検証：中心振り分けが崩れていないか ============
def check():
    ng=[]
    for room,H,faces in ROOMS:
        for face,L,axis,steps,chain in faces:
            pass
    # 室名/面記号の中心が枠線の中心と一致するか
    frames=[e for e in P if e[0]=='line' and e[1]==3 and e[2]==C_FRAME
            and abs(e[5]-e[7])<1e-6 and abs(e[4]-e[6])>1]   # 水平な枠線
    names=[e for e in P if e[0]=='text' and e[1]==4]
    cent_f=sorted({round((e[4]+e[6])/2,1) for e in frames})
    cent_t=sorted({round(e[4]+e[6]/2,1) for e in names})
    for c in cent_t:
        if not any(abs(c-f)<0.5 for f in cent_f): ng.append(c)
    return cent_f, cent_t, ng
cf,ct,ng = check()
print('枠線の中心 :', [int(v) for v in cf])
print('文字の中心 :', [int(v) for v in ct])
print('不一致     :', ng if ng else 'なし')
assert not ng, '室名/面記号の中心が枠線と合っていません'

xs=[];ys=[]
for e in P:
    if e[0]=='line': xs+=[e[4],e[6]]; ys+=[e[5],e[7]]
    elif e[0]=='circle': xs+=[e[4]-e[6],e[4]+e[6]]; ys+=[e[5]-e[6],e[5]+e[6]]
    elif e[0]=='point': xs+=[e[2]]; ys+=[e[3]]
    elif e[0]=='dimfig':
        xs+=[e[4],e[6],e[8],e[8]+e[10]]; ys+=[e[5],e[7],e[9],e[9]+e[11]+theight(e[3])]
    else: xs+=[e[4],e[4]+e[6]]; ys+=[e[5],e[5]+e[7]+theight(e[3])]
BX0,BY0 = min(xs), min(ys)
print('要素数 %d   X %.0f..%.0f (用紙 ±%.0f)   Y %.0f..%.0f (用紙 ±%.0f)'
      % (len(P),min(xs),max(xs),HALF_W,min(ys),max(ys),HALF_H))
assert min(xs)>-HALF_W and max(xs)<HALF_W and min(ys)>-HALF_H and max(ys)<HALF_H

# ============ 外部変形データ ============
def fm(v): return ('%.2f'%v).rstrip('0').rstrip('.')
def elements(dx=0.0, dy=0.0, skip=()):
    o=[]
    for ly in (1,2,3,4):
        es=[e for e in P if e[1]==ly]
        if not es or ly in skip: continue
        o.append('ly%d'%ly)
        lc=None; lt=None; size=None; pn=None
        def setlc(v):
            nonlocal lc
            if v!=lc: lc=v; o.append('lc%d'%v)
        def setlt(v):
            nonlocal lt
            if v!=lt: lt=v; o.append('lt%d'%v)
        def setcn(v):
            nonlocal size
            if v!=size: size=v; o.append('cn%d'%CHAR_TYPE[v])
        for e in es:
            if e[0]=='point':
                if pn is None: pn=C_POINT; o.append('pn%d'%pn)
                o.append('pt %s %s'%(fm(e[2]+dx),fm(e[3]+dy)))
            elif e[0]=='dimfig':
                setlc(e[2]); setlt(LT_SOLID)
                o.append('msg')
                o.append('%s %s %s %s'%(fm(e[4]+dx),fm(e[5]+dy),fm(e[6]+dx),fm(e[7]+dy)))
                setcn(e[3])
                o.append('cs %s %s %s %s "%s'%(fm(e[8]+dx),fm(e[9]+dy),
                                               fm(e[10]),fm(e[11]),e[12]))
                o.append('#')
            elif e[0]=='line':
                setlc(e[2]); setlt(e[3])
                o.append('%s %s %s %s'%(fm(e[4]+dx),fm(e[5]+dy),fm(e[6]+dx),fm(e[7]+dy)))
            elif e[0]=='circle':
                setlc(e[2]); setlt(e[3])
                o.append('ci %s %s %s'%(fm(e[4]+dx),fm(e[5]+dy),fm(e[6])))
            else:
                setlc(e[2]); setcn(e[3])
                o.append('ch %s %s %s %s "%s'%(fm(e[4]+dx),fm(e[5]+dy),
                                               fm(e[6]),fm(e[7]),e[8]))
    return o
def gaibu(skip=()): return '\r\n'.join(elements(-BX0,-BY0,skip))+'\r\n'

# ============ DXF (R12) ============
def dxf():
    o=[]; a=lambda c,v: o.extend([str(c),str(v)])
    a(0,'SECTION'); a(2,'TABLES')
    a(0,'TABLE'); a(2,'LTYPE'); a(70,2)
    a(0,'LTYPE'); a(2,'CONTINUOUS'); a(70,0); a(3,'Solid line'); a(72,65); a(73,0); a(40,0.0)
    a(0,'LTYPE'); a(2,'DASHDOT'); a(70,0); a(3,'Dash dot'); a(72,65); a(73,4); a(40,600.0)
    a(49,400.0); a(49,-100.0); a(49,0.0); a(49,-100.0)
    a(0,'ENDTAB')
    a(0,'TABLE'); a(2,'LAYER'); a(70,4)
    for ly,col in ((1,C_AXIS),(2,C_DIM),(3,C_FRAME),(4,C_TEXT)):
        a(0,'LAYER'); a(2,str(ly)); a(70,0); a(62,col); a(6,'CONTINUOUS')
    a(0,'ENDTAB')
    a(0,'TABLE'); a(2,'STYLE'); a(70,1)
    a(0,'STYLE'); a(2,'STANDARD'); a(70,0); a(40,0.0); a(41,1.0); a(50,0.0)
    a(71,0); a(42,2.5); a(3,'txt'); a(4,'')
    a(0,'ENDTAB'); a(0,'ENDSEC')
    a(0,'SECTION'); a(2,'ENTITIES')
    for e in P:
        ly=str(e[1])
        if e[0]=='point':
            a(0,'POINT'); a(8,ly); a(62,C_POINT); a(10,e[2]); a(20,e[3]); a(30,0.0)
        elif e[0]=='dimfig':
            a(0,'LINE'); a(8,ly); a(62,e[2]); a(6,'CONTINUOUS')
            a(10,e[4]); a(20,e[5]); a(30,0.0); a(11,e[6]); a(21,e[7]); a(31,0.0)
            a(0,'TEXT'); a(8,ly); a(62,e[2]); a(10,e[8]); a(20,e[9]); a(30,0.0)
            a(40,theight(e[3])); a(1,e[12]); a(50, 90 if abs(e[10])<1e-6 else 0); a(7,'STANDARD')
        elif e[0]=='line':
            a(0,'LINE'); a(8,ly); a(62,e[2]); a(6,'DASHDOT' if e[3]==LT_CHAIN else 'CONTINUOUS')
            a(10,e[4]); a(20,e[5]); a(30,0.0); a(11,e[6]); a(21,e[7]); a(31,0.0)
        elif e[0]=='circle':
            a(0,'CIRCLE'); a(8,ly); a(62,e[2]); a(6,'CONTINUOUS')
            a(10,e[4]); a(20,e[5]); a(30,0.0); a(40,e[6])
        else:
            a(0,'TEXT'); a(8,ly); a(62,e[2]); a(10,e[4]); a(20,e[5]); a(30,0.0)
            a(40,theight(e[3])); a(1,e[8]); a(50, 90 if abs(e[6])<1e-6 else 0); a(7,'STANDARD')
    a(0,'ENDSEC'); a(0,'EOF')
    return '\r\n'.join(o)+'\r\n'

D=os.path.dirname(os.path.abspath(__file__))+'/out/'
os.makedirs(D, exist_ok=True)
open(D+'tenkaizu.dxf','w',encoding='cp932',newline='').write(dxf())
open(D+'tenkaizu_data.txt','w',encoding='cp932',newline='').write(gaibu())
open(D+'tenkaizu_data_nodim.txt','w',encoding='cp932',newline='').write(gaibu(skip=(2,)))
for f in ('tenkaizu.dxf','tenkaizu_data.txt','tenkaizu_data_nodim.txt'):
    print('  %-24s %6d bytes'%(f, os.path.getsize(D+f)))

# ============ プレビュー ============
import pymupdf
MM=72/25.4
PEN={1:(0,0,1),2:(0,0.6,0),4:(0.6,0,0.6),5:(0.8,0,0),6:(0.8,0.5,0)}
doc=pymupdf.open(); pg=doc.new_page(width=PAPER_W*MM,height=PAPER_H*MM)
px=lambda x:(x/SCALE+PAPER_W/2)*MM
py=lambda y:(PAPER_H/2-y/SCALE)*MM
for e in P:
    if e[0]=='point':
        sh=pg.new_shape(); sh.draw_circle((px(e[2]),py(e[3])), 0.25*MM)
        sh.finish(width=0.1,color=PEN[C_POINT],fill=PEN[C_POINT]); sh.commit()
    elif e[0]=='dimfig':
        col=PEN.get(e[2],(0,0,0))
        sh=pg.new_shape(); sh.draw_line((px(e[4]),py(e[5])),(px(e[6]),py(e[7])))
        sh.finish(width=0.15,color=col); sh.commit()
        pg.insert_text((px(e[8]),py(e[9])), e[12], fontname='japan', color=col,
                       fontsize=theight(e[3])/SCALE*MM, rotate=90 if abs(e[10])<1e-6 else 0)
    elif e[0]=='line':
        sh=pg.new_shape(); sh.draw_line((px(e[4]),py(e[5])),(px(e[6]),py(e[7])))
        sh.finish(width=0.5 if e[2]==C_FRAME else 0.15, color=PEN.get(e[2],(0,0,0)),
                  dashes='[3 2] 0' if e[3]==LT_CHAIN else None); sh.commit()
    elif e[0]=='circle':
        sh=pg.new_shape(); sh.draw_circle((px(e[4]),py(e[5])),e[6]/SCALE*MM)
        sh.finish(width=0.15,color=PEN.get(e[2],(0,0,0))); sh.commit()
    else:
        pg.insert_text((px(e[4]),py(e[5])), e[8], fontname='japan', color=PEN.get(e[2],(0,0,0)),
                       fontsize=theight(e[3])/SCALE*MM, rotate=90 if abs(e[6])<1e-6 else 0)
doc.save(D+'preview.pdf')
pymupdf.open(D+'preview.pdf')[0].get_pixmap(dpi=200).save(D+'preview.png')
print('  preview ok')
