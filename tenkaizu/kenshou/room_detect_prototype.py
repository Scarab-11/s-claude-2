# -*- coding: utf-8 -*-
"""壁芯線から室（閉領域）を検出する試作"""
import re, math
from collections import defaultdict

DUMP='/root/.claude/uploads/9ed4d5cc-1e7d-598f-9a7c-a24aa8e5dd7a/1f3fbe14-jwc_dumpA.txt'
WALL_LAYER='f'          # 壁芯レイヤ
NAME_LAYER='2'          # 室名レイヤ
CH_LAYER  ='e'          # 天井高レイヤ
EPS=1.0

num=re.compile(r'^-?\d+(\.\d+)?$')
ly=lc=lt=cn=None
walls=[]; texts=[]
for raw in open(DUMP,encoding='cp932').read().splitlines():
    t=raw.strip()
    if not t: continue
    m=re.match(r'^ly([0-9a-fA-F])$',t)
    if m: ly=m.group(1); continue
    m=re.match(r'^lc(\d+)$',t)
    if m: lc=int(m.group(1)); continue
    m=re.match(r'^lt(\d+)$',t)
    if m: lt=int(m.group(1)); continue
    m=re.match(r'^cn(\d+)',t)
    if m: cn=int(m.group(1)); continue
    if t.startswith('ch ') or t.startswith('cs '):
        p=t.split(None,5)
        if len(p)>=6: texts.append((ly,cn,float(p[1]),float(p[2]),float(p[3]),float(p[4]),p[5][1:]))
        continue
    p=t.split()
    if len(p)==4 and all(num.match(v) for v in p) and ly==WALL_LAYER:
        walls.append(tuple(map(float,p)))

print('壁芯線 %d本 / 文字 %d個' % (len(walls), len(texts)))

# ---- 交点で分割 ----------------------------------------------
def seg_pts(s):
    return (s[0],s[1]),(s[2],s[3])
pts=set()
for s in walls:
    a,b=seg_pts(s); pts.add(a); pts.add(b)
def on_seg(p,s):
    (x1,y1),(x2,y2)=seg_pts(s); x,y=p
    cross=(x2-x1)*(y-y1)-(y2-y1)*(x-x1)
    if abs(cross) > EPS*math.hypot(x2-x1,y2-y1): return False
    return min(x1,x2)-EPS<=x<=max(x1,x2)+EPS and min(y1,y2)-EPS<=y<=max(y1,y2)+EPS
def inter(s1,s2):
    (x1,y1),(x2,y2)=seg_pts(s1); (x3,y3),(x4,y4)=seg_pts(s2)
    d=(x2-x1)*(y4-y3)-(y2-y1)*(x4-x3)
    if abs(d)<1e-9: return None
    t=((x3-x1)*(y4-y3)-(y3-y1)*(x4-x3))/d
    u=((x3-x1)*(y2-y1)-(y3-y1)*(x2-x1))/d
    if -1e-9<=t<=1+1e-9 and -1e-9<=u<=1+1e-9:
        return (x1+t*(x2-x1), y1+t*(y2-y1))
    return None
for i in range(len(walls)):
    for j in range(i+1,len(walls)):
        p=inter(walls[i],walls[j])
        if p: pts.add((round(p[0],3),round(p[1],3)))
def snap(p):
    for q in pts:
        if abs(p[0]-q[0])<EPS and abs(p[1]-q[1])<EPS: return q
    return p
pts={snap(p) for p in pts}
edges=set()
for s in walls:
    a,b=seg_pts(s)
    on=[p for p in pts if on_seg(p,s)]
    on.sort(key=lambda p:(p[0]-a[0])**2+(p[1]-a[1])**2)
    for u,v in zip(on,on[1:]):
        if u!=v: edges.add((u,v) if u<v else (v,u))
print('節点 %d / 辺 %d' % (len(pts), len(edges)))

# ---- 面（閉領域）の探索 --------------------------------------
adj=defaultdict(list)
for u,v in edges: adj[u].append(v); adj[v].append(u)
for k in adj: adj[k].sort(key=lambda p,k=k: math.atan2(p[1]-k[1],p[0]-k[0]))
def nxt(u,v):
    """有向辺 u→v の次の辺。v で (v→u) の時計回り直後を選ぶ"""
    lst=adj[v]; i=lst.index(u)
    return v, lst[(i-1)%len(lst)]
faces=[]; used=set()
for u,v in list(edges)+[(v,u) for u,v in edges]:
    if (u,v) in used: continue
    face=[]; a,b=u,v
    while (a,b) not in used:
        used.add((a,b)); face.append(a)
        a,b=nxt(a,b)
        if len(face)>10000: break
    if len(face)>=3: faces.append(face)
def area(poly):
    s=0
    for (x1,y1),(x2,y2) in zip(poly,poly[1:]+poly[:1]): s+=x1*y2-x2*y1
    return s/2
rooms=[f for f in faces if area(f)>1000]        # 反時計回り＝内側の面
rooms.sort(key=lambda f:-area(f))
print('検出した閉領域 %d個（面積>0.001㎡）' % len(rooms))

# ---- 文字の割り当て ------------------------------------------
def inside(p,poly):
    x,y=p; c=False
    for (x1,y1),(x2,y2) in zip(poly,poly[1:]+poly[:1]):
        if (y1>y)!=(y2>y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1: c=not c
    return c
names=[t for t in texts if t[0]==NAME_LAYER]
chs  =[t for t in texts if t[0]==CH_LAYER]
def txt_center(t):
    return (t[2]+t[4]/2, t[3]+t[5]/2)
print()
print('%-4s %10s  %-28s %-10s'%('No','面積(㎡)','室名','天井高'))
print('-'*62)
for i,f in enumerate(rooms,1):
    A=area(f)/1e6
    nm=[t[6] for t in names if inside(txt_center(t),f)]
    ch=[t[6] for t in chs   if inside(txt_center(t),f)]
    print('%-4d %10.2f  %-28s %-10s'%(i,A,' / '.join(nm) if nm else '(なし)',' / '.join(ch) if ch else '(なし)'))

# ============ 多角形 → Ａ〜Ｄ面 ============
def faces_of(poly):
    """反時計回り多角形（Y上向き）から4面を作る。
       進行方向 -X=北壁(Ａ面) / +Y=東壁(Ｂ面) / +X=南壁(Ｃ面) / -Y=西壁(Ｄ面)"""
    edge={'Ａ':[], 'Ｂ':[], 'Ｃ':[], 'Ｄ':[]}
    for (x1,y1),(x2,y2) in zip(poly,poly[1:]+poly[:1]):
        if abs(y1-y2)<EPS:
            (edge['Ｃ'] if x2>x1 else edge['Ａ']).append((min(x1,x2),max(x1,x2),y1))
        elif abs(x1-x2)<EPS:
            (edge['Ｂ'] if y2>y1 else edge['Ｄ']).append((min(y1,y2),max(y1,y2),x1))
    out={}
    # 見る向きに応じた左→右の並び順
    #   Ａ(北を見る)=X昇順  Ｂ(東)=Y降順  Ｃ(南)=X降順  Ｄ(西)=Y昇順
    REV={'Ａ':False, 'Ｂ':True, 'Ｃ':True, 'Ｄ':False}
    for k,es in edge.items():
        if not es: continue
        es.sort(key=lambda e:e[0], reverse=REV[k])
        segs=[]; planes=[]
        for a,b,pl in es:
            L=round(b-a); pl=round(pl)
            if planes and abs(pl-planes[-1])<EPS:
                segs[-1]+=L                      # 同一面はつなぐ（T字接合の分割を解消）
            else:
                segs.append(L); planes.append(pl)
        out[k]=(sum(segs), segs, planes)
    return out

print()
print('='*70)
print('各室の展開面（芯々寸法）')
print('='*70)
for i,f in enumerate(rooms,1):
    nm=[t[6] for t in names if inside(txt_center(t),f)]
    ch=[t[6] for t in chs   if inside(txt_center(t),f)]
    if not nm or not ch: continue
    fs=faces_of(f)
    h=ch[0].split('=')[-1]
    print('\n■ %s  天井高 %s   （検出面積 %.2f㎡・頂点%d）'%(' / '.join(nm), h, area(f)/1e6, len(f)))
    for k in ('Ａ','Ｂ','Ｃ','Ｄ'):
        if k not in fs: continue
        tot,segs,_=fs[k]
        det = ' ＝ '+' ＋ '.join(str(s) for s in segs) if len(segs)>1 else ''
        print('   %s面  幅 %5d%s'%(k,tot,det))
