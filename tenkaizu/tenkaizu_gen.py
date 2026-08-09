# -*- coding: utf-8 -*-
"""展開図ジェネレータ  平面図(通り芯)→ 展開図 A/B/C/D  → JWC / DXF / 外部変形 / プレビュー"""
import unicodedata, os

SCALE = 100                              # 1/100
PAPER_W, PAPER_H = 420.0, 297.0          # A3
HALF_W, HALF_H = PAPER_W/2*SCALE, PAPER_H/2*SCALE
WALL_T = 80                              # 基準線から壁仕上面までの寄り（壁厚の半分程度）

# ---- 参考図から実測した作図規約（実寸 mm）--------------------
DIM_OFF, DIM_STEP, DIM_TXT_GAP = 375, 450, 30
VDIM_OFF, VDIM_EXT, DOT_R      = 760, 540, 25
AX_UP, AX_DN                   = 900, 1050
AX_CIR_R, AX_CIR_Y, AX_TICK    = 250, 1250, 190
NAMEBOX_TOP, NAMEBOX_H, NAMEBOX_PAD = 550, 350, 150

CH_W = {1: 2.0, 2: 2.5}                  # 文字種1=2.0mm / 文字種2=2.5mm（Jw_cad 既定）
CH_D = {1: 0.0, 2: 0.0}

def tlen(s, cn):
    n = sum(1.0 if unicodedata.east_asian_width(c) in 'WFA' else 0.5 for c in s)
    return (n*CH_W[cn] + (len(s)-1)*CH_D[cn]) * SCALE
def theight(cn): return CH_W[cn]*SCALE

P = []
def line(ly,x1,y1,x2,y2): P.append(('line',ly,x1,y1,x2,y2))
def circle(ly,x,y,r):     P.append(('circle',ly,x,y,r))
def text_h(ly,cx,by,cn,s):
    L=tlen(s,cn); P.append(('text',ly,cx-L/2,by,cx+L/2,by,cn,s))
def text_v(ly,bx,cy,cn,s):
    L=tlen(s,cn); P.append(('text',ly,bx,cy-L/2,bx,cy+L/2,cn,s))

# ============ 1面ぶんの作図 ============
def draw_face(ox, oy, L, H, room, face, axis, steps, chain):
    """(ox,oy)=左端の基準線の下端。L=芯々の幅。axis=[(位置,記号 or None),..]
       steps=枠線内の段差線位置（面基準）  chain=内訳寸法（芯々）"""
    t  = WALL_T
    fl, fr = ox+t, ox+L-t                      # 枠線の左右（基準線より内側）

    # --- レイヤ3 枠線 ---
    line(3, fl, oy,   fr, oy  ); line(3, fr, oy,   fr, oy+H)
    line(3, fr, oy+H, fl, oy+H); line(3, fl, oy+H, fl, oy  )
    for s in steps:                            # 壁面が切り替わる位置
        line(3, ox+s, oy, ox+s, oy+H)

    # --- レイヤ1 基準線＋通り芯記号 ---
    for pos, mk in axis:
        x = ox+pos
        line(1, x, oy-AX_DN, x, oy+H+AX_UP)
        if mk:
            cy = oy+H+AX_CIR_Y
            circle(1, x, cy, AX_CIR_R)
            line(1, x-AX_CIR_R-AX_TICK/2, cy, x-AX_CIR_R+AX_TICK/2, cy)
            line(1, x+AX_CIR_R-AX_TICK/2, cy, x+AX_CIR_R+AX_TICK/2, cy)
            line(1, x, cy-AX_CIR_R-AX_TICK/2, x, cy-AX_CIR_R+AX_TICK/2)
            line(1, x, cy+AX_CIR_R-AX_TICK/2, x, cy+AX_CIR_R+AX_TICK/2)
            text_h(1, x, cy-theight(1)/2, 1, mk)

    # --- レイヤ2 幅寸法（すべて芯々・基準線間）---
    def hdim(y, x1, x2, val):
        line(2, x1, y, x2, y)
        circle(2, x1, y, DOT_R); circle(2, x2, y, DOT_R)
        text_h(2, (x1+x2)/2, y+DIM_TXT_GAP, 1, '{:,}'.format(int(round(val))))
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
    line(2, xd, oy, xd, oy+H)
    circle(2, xd, oy, DOT_R); circle(2, xd, oy+H, DOT_R)
    line(2, xd, oy, xd+VDIM_EXT, oy); line(2, xd, oy+H, xd+VDIM_EXT, oy+H)
    text_v(2, xd-DIM_TXT_GAP, oy+H/2, 1, '{:,}'.format(int(round(H))))

    # --- レイヤ4 室名 ---
    text_h(4, ox+L/2, oy+H/2-theight(2)/2, 2, room)

    # --- 面記号（枠=レイヤ3／文字=レイヤ4）---
    bw = tlen(face,2)+NAMEBOX_PAD*2
    bx = ox+L/2-bw/2; bt = oy-NAMEBOX_TOP; bb = bt-NAMEBOX_H
    line(3, bx,bb, bx+bw,bb); line(3, bx+bw,bb, bx+bw,bt)
    line(3, bx+bw,bt, bx,bt); line(3, bx,bt, bx,bb)
    text_h(4, ox+L/2, bb+(NAMEBOX_H-theight(2))/2, 2, face)

# ============ 室の定義 ============
# (面記号, 芯々幅L, 基準線[(位置,記号)], 段差線位置, 内訳寸法)
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
PAD_L, PAD_R, PAD_T, PAD_B = 1150, 350, 1600, 1200
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
    if e[0]=='line': xs+=[e[2],e[4]]; ys+=[e[3],e[5]]
    elif e[0]=='circle': xs+=[e[2]-e[4],e[2]+e[4]]; ys+=[e[3]-e[4],e[3]+e[4]]
    else: xs+=[e[2],e[4]]; ys+=[e[3],e[5]+theight(e[6])]
BX0,BY0 = min(xs), min(ys)
print('要素数 %d   X %.0f..%.0f (用紙 ±%.0f)   Y %.0f..%.0f (用紙 ±%.0f)'
      % (len(P),min(xs),max(xs),HALF_W,min(ys),max(ys),HALF_H))
assert min(xs)>-HALF_W and max(xs)<HALF_W and min(ys)>-HALF_H and max(ys)<HALF_H

# ============ 出力 ============
LT={1:5,2:1,3:1,4:1}; LC={1:1,2:1,3:2,4:1}
def fm(v): return ('%.2f'%v).rstrip('0').rstrip('.')

def elements(dx=0.0, dy=0.0):
    """レイヤ順に並べた JWC 属性行＋データ行"""
    o=[]
    for ly in (1,2,3,4):
        es=[e for e in P if e[1]==ly]
        if not es: continue
        o += ['ly%d'%ly, 'lc%d'%LC[ly], 'lt%d'%LT[ly]]
        cn=None
        for e in es:
            if e[0]=='line':
                o.append('%s %s %s %s'%(fm(e[2]+dx),fm(e[3]+dy),fm(e[4]+dx),fm(e[5]+dy)))
            elif e[0]=='circle':
                o.append('ci %s %s %s'%(fm(e[2]+dx),fm(e[3]+dy),fm(e[4])))
            else:
                if e[6]!=cn: cn=e[6]; o.append('cn%d'%cn)
                o.append('ch %s %s %s %s "%s'%(fm(e[2]+dx),fm(e[3]+dy),
                                               fm(e[4]+dx),fm(e[5]+dy),e[7]))
    return o

HEAD = ['# 展開図  洋室-1 / 事務室   A3  S=1/100',
        '# レイヤ1:基準線  レイヤ2:寸法線  レイヤ3:枠線  レイヤ4:文字']
def jwc():   return '\r\n'.join(['hs %d'%SCALE]+elements())+'\r\n'
def jwc_b():
    hdr=['hq','hv 0',
         'hcw 2 2.5 3 4 5 6 7 8 9 10',
         'hch 2 2.5 3 4 5 6 7 8 9 10',
         'hcd 0 0 0.5 0.5 0.5 1 1 1 1 1',
         'hs %d'%SCALE,'#']
    return '\r\n'.join(hdr+elements())+'\r\n'
def gaibu(): return '\r\n'.join(HEAD+elements(-BX0, -BY0))+'\r\n'   # 左下を原点に

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
        a(0,'LAYER'); a(2,str(ly)); a(70,0); a(62,LC[ly])
        a(6,'DASHDOT' if ly==1 else 'CONTINUOUS')
    a(0,'ENDTAB')
    a(0,'TABLE'); a(2,'STYLE'); a(70,1)
    a(0,'STYLE'); a(2,'STANDARD'); a(70,0); a(40,0.0); a(41,1.0); a(50,0.0)
    a(71,0); a(42,2.5); a(3,'txt'); a(4,'')
    a(0,'ENDTAB'); a(0,'ENDSEC')
    a(0,'SECTION'); a(2,'ENTITIES')
    for e in P:
        ly=str(e[1])
        if e[0]=='line':
            a(0,'LINE'); a(8,ly); a(10,e[2]); a(20,e[3]); a(30,0.0); a(11,e[4]); a(21,e[5]); a(31,0.0)
        elif e[0]=='circle':
            a(0,'CIRCLE'); a(8,ly); a(10,e[2]); a(20,e[3]); a(30,0.0); a(40,e[4])
        else:
            a(0,'TEXT'); a(8,ly); a(10,e[2]); a(20,e[3]); a(30,0.0); a(40,theight(e[6]))
            a(1,e[7]); a(50, 90 if abs(e[4]-e[2])<1e-6 else 0); a(7,'STANDARD')
    a(0,'ENDSEC'); a(0,'EOF')
    return '\r\n'.join(o)+'\r\n'

D=os.path.dirname(os.path.abspath(__file__))+'/out/'
os.makedirs(D, exist_ok=True)
open(D+'tenkaizu.jwc','w',encoding='cp932',newline='').write(jwc())
open(D+'tenkaizu_b.jwc','w',encoding='cp932',newline='').write(jwc_b())
open(D+'tenkaizu.dxf','w',encoding='cp932',newline='').write(dxf())
open(D+'tenkaizu_data.txt','w',encoding='cp932',newline='').write(gaibu())
for f in ('tenkaizu.jwc','tenkaizu_b.jwc','tenkaizu.dxf','tenkaizu_data.txt'):
    print('  %-20s %6d bytes' % (f, os.path.getsize(D+f)))

# ============ プレビュー ============
import pymupdf
MM=72/25.4
doc=pymupdf.open(); pg=doc.new_page(width=PAPER_W*MM,height=PAPER_H*MM)
px=lambda x:(x/SCALE+PAPER_W/2)*MM
py=lambda y:(PAPER_H/2-y/SCALE)*MM
for e in P:
    ly=e[1]; w=0.5 if ly==3 else 0.15
    if e[0]=='line':
        sh=pg.new_shape(); sh.draw_line((px(e[2]),py(e[3])),(px(e[4]),py(e[5])))
        sh.finish(width=w,color=(0,0,0),dashes='[3 2] 0' if ly==1 else None); sh.commit()
    elif e[0]=='circle':
        sh=pg.new_shape(); sh.draw_circle((px(e[2]),py(e[3])),e[4]/SCALE*MM)
        sh.finish(width=w,color=(0,0,0),fill=(0,0,0) if e[4]<=DOT_R else None); sh.commit()
    else:
        pg.insert_text((px(e[2]),py(e[3])), e[7], fontname='japan',
                       fontsize=theight(e[6])/SCALE*MM,
                       rotate=90 if abs(e[4]-e[2])<1e-6 else 0)
doc.save(D+'preview.pdf')
pymupdf.open(D+'preview.pdf')[0].get_pixmap(dpi=200).save(D+'preview.png')
print('  preview ok')
