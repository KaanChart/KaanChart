"""Fetch BTC/USDT 1H candles and draw the KaanChart market-structure chart.

Usage: python scripts/update_chart.py assets/btc-1h.png
"""
import json,sys,datetime as d,urllib.request
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.dates as md
def fetch():
    urls=[
        "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=240",
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=240",
    ]
    for u in urls:
        try:
            with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"kaanchart-bot"}),timeout=30) as r:
                data=json.load(r)
            if isinstance(data,list) and data: return data,"Binance"
        except Exception as e:
            print("fetch failed:",u,e)
    # Fallback: OKX (newest first; columns ts,o,h,l,c,vol)
    u="https://www.okx.com/api/v5/market/history-candles?instId=BTC-USDT&bar=1H&limit=100"
    rows=[]; after=""
    for _ in range(3):
        with urllib.request.urlopen(u+(f"&after={after}" if after else ""),timeout=30) as r:
            page=json.load(r)["data"]
        if not page: break
        rows+=page; after=page[-1][0]
    rows=sorted(rows,key=lambda x:int(x[0]))[-240:]
    return [[int(x[0]),x[1],x[2],x[3],x[4],x[5]] for x in rows],"OKX"

k,SRC=fetch()
T=[d.datetime.fromtimestamp(r[0]/1000,d.UTC)+d.timedelta(minutes=30) for r in k]
O,H,L,C,V=[[float(r[i]) for r in k] for i in (1,2,3,4,5)]
N=len(k); n=4
piv=[]  # (idx,type,price)
for i in range(n,N-n):
    if H[i]==max(H[i-n:i+n+1]): piv.append((i,'H',H[i]))
    if L[i]==min(L[i-n:i+n+1]): piv.append((i,'L',L[i]))
# alternate: keep extreme when same type repeats
alt=[]
for p in piv:
    if alt and alt[-1][1]==p[1]:
        if (p[1]=='H' and p[2]>alt[-1][2]) or (p[1]=='L' and p[2]<alt[-1][2]): alt[-1]=p
    else: alt.append(p)
lab=[];lastH=lastL=None
for p in alt:
    if p[1]=='H': lab.append((p,'' if lastH is None else ('HH' if p[2]>lastH else 'LH'))); lastH=p[2]
    else: lab.append((p,'' if lastL is None else ('HL' if p[2]>lastL else 'LL'))); lastL=p[2]
# BOS / CHoCH by close breaks of last confirmed swing
ev=[];trend=0;sH=sL=None;j=0;confirmed=[]
for i in range(N):
    while j<len(alt) and alt[j][0]+n<=i: 
        if alt[j][1]=='H': sH=alt[j]
        else: sL=alt[j]
        j+=1
    if sH and C[i]>sH[2]:
        ev.append((sH,i,'BOS' if trend==1 else 'CHoCH','up')); trend=1; sH=None
    elif sL and C[i]<sL[2]:
        ev.append((sL,i,'BOS' if trend==-1 else 'CHoCH','dn')); trend=-1; sL=None
cut=N-168
BG,FG,MU,GR='#0e1117','#e6e9ef','#8a93a6','#232a36'; UP,DN,GOLD='#26a69a','#ef5350','#f2b84b'
plt.rcParams.update({'font.size':11,'text.color':FG,'xtick.color':MU,'ytick.color':MU})
fig,ax=plt.subplots(figsize=(15,8.5),facecolor=BG); ax.set_facecolor(BG); ax.grid(color=GR,lw=.6); ax.yaxis.tick_right()
[s.set_visible(False) for s in ax.spines.values()]
w=0.7/24
for i in range(cut,N):
    col=UP if C[i]>=O[i] else DN
    ax.vlines(T[i],L[i],H[i],color=col,lw=1); ax.bar(T[i],abs(C[i]-O[i]) or 5,bottom=min(O[i],C[i]),width=w,color=col)
pts=[p for p in alt if p[0]>=cut]
ax.plot([T[p[0]] for p in pts],[p[2] for p in pts],color=MU,lw=1,alpha=.6)
for p,t in lab:
    if p[0]<cut or not t: continue
    good=t in('HH','HL'); ax.annotate(t,(T[p[0]],p[2]),xytext=(0,10 if p[1]=='H' else -18),textcoords='offset points',ha='center',fontsize=10,fontweight='bold',color=UP if good else DN)
for s,i,name,dr in ev:
    if i<cut: continue
    col=UP if dr=='up' else DN; x0=T[max(s[0],cut)]
    ax.hlines(s[2],x0,T[i],color=col,lw=1.2,ls='--')
    ax.text(x0+(T[i]-x0)/2,s[2],name,color=col,ha='center',va='bottom' if dr=='up' else 'top',fontsize=10,fontweight='bold')
ax.set_title(f'BTC/USDT · 1H · Market Structure · {SRC} spot · to {T[-1]-d.timedelta(minutes=30):%d %b %H:00} UTC   |   Last {C[-1]:,.0f}',loc='left',color=FG,fontsize=13)
ax.xaxis.set_major_formatter(md.DateFormatter('%d %b',tz=d.UTC))
fig.text(.47,.5,'KaanChart',fontsize=120,fontweight='bold',color=GOLD,alpha=.10,ha='center',va='center',rotation=12)
fig.text(.01,.01,'KaanChart',fontsize=16,fontweight='bold',color=GOLD)
fig.text(.99,.01,f'Source: {SRC} · swings = 4-bar fractals · BOS/CHoCH on candle close',ha='right',color=MU,fontsize=9)
fig.savefig(sys.argv[1],dpi=150,facecolor=BG,bbox_inches='tight')
print("saved",sys.argv[1],"last",C[-1])
