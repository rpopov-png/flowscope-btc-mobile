import csv, io, json, statistics, time
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
HEADERS={'User-Agent':'Mozilla/5.0 FlowScope/1.0'}

def mean(x): return sum(x)/len(x) if x else 0.0
def sd(x):
    if len(x)<2:return 1.0
    s=statistics.pstdev(x); return s if s>1e-12 else 1.0
def zlast(x):
    if len(x)<10:return 0.0
    h=x[:-1]; return (x[-1]-mean(h))/sd(h)
def getj(url):
    r=requests.get(url,timeout=25,headers=HEADERS); r.raise_for_status(); j=r.json()
    if isinstance(j,dict) and j.get('code') not in (None,'0',0): raise RuntimeError(j.get('msg') or str(j.get('code')))
    return j
def gett(url):
    r=requests.get(url,timeout=25,headers=HEADERS); r.raise_for_status(); return r.text

def flow_class(z):
    if z>1.5:return 'Strong Buy','pos'
    if z>.45:return 'Buy','pos'
    if z<-1.5:return 'Strong Sell','neg'
    if z<-.45:return 'Sell','neg'
    return 'Neutral','neu'
def oi_class(z):
    if z>1.5:return 'Sharp Rise','warn'
    if z>.4:return 'Rising','warn'
    if z<-1.5:return 'Sharp Drop','pos'
    if z<-.4:return 'Falling','pos'
    return 'Stable','neu'
def funding_class(z):
    if z>1.5:return 'High','warn'
    if z>.4:return 'Positive','warn'
    if z<-1.5:return 'Strong Negative','neg'
    if z<-.4:return 'Negative','neg'
    return 'Neutral','neu'
def etf_class(d,d3,m):
    if d is None:return 'Unavailable','off'
    if d>0 and d3>0 and m>0:return 'Strong Inflow','pos'
    if d>0 or d3>0:return 'Inflow','pos'
    if d<0 and d3<0 and m<0:return 'Strong Outflow','neg'
    if d<0 or d3<0:return 'Outflow','neg'
    return 'Neutral','neu'

def regime(pm,sz,fz,oz,uz):
    r={'regime':'Mixed Market','confidence':'LOW','title':'Смешанный рынок','text':'Потоки пока не формируют чистую закономерность.','confirm':'Ждём согласования Spot / Futures / OI / Funding.','cancel':'—'}
    if pm>0 and sz>.45 and fz>-.45 and oz<1.5 and uz<1.5:r={'regime':'Healthy Spot Growth','confidence':'MEDIUM','title':'Здоровый спотовый рост','text':'Рост подтверждается спотовым спросом, а плечи пока не выглядят экстремально перегретыми.','confirm':'Spot остаётся сильным, OI не ускоряется экстремально.','cancel':'Spot слабеет, а Futures / OI начинают доминировать.'}
    if pm>0 and sz<.45 and fz>1.0 and oz>1.0 and uz>.6:r={'regime':'Futures-driven Rise','confidence':'HIGH','title':'Перегретый рост на фьючерсах','text':'Цена растёт преимущественно за счёт деривативов. Spot не подтверждает движение, OI и Funding повышают уязвимость структуры.','confirm':'Spot остаётся слабым, а импульс Futures начинает затухать.','cancel':'Появляется устойчивый сильный Spot-покупатель.'}
    if pm>=0 and sz<-.45 and oz>.7 and uz>.5:r={'regime':'Distribution','confidence':'MEDIUM','title':'Распределение','text':'Цена держится, но Spot ухудшается на фоне повышенного leverage. Риск разворота вниз растёт.','confirm':'Spot-поток продолжает снижаться, цена перестаёт обновлять хаи.','cancel':'Возвращается сильный Spot-спрос.'}
    if pm<0 and fz<-.7 and oz>.5:r={'regime':'Short Build-up','confidence':'MEDIUM','title':'Наращивание шортов','text':'Цена падает вместе с агрессивными продажами Futures и ростом OI. Новые позиции поддерживают снижение.','confirm':'OI продолжает расти на снижении.','cancel':'Spot абсорбирует продажи, OI перестаёт расти.'}
    if pm<0 and oz<-1.1:r={'regime':'Long Flush','confidence':'MEDIUM','title':'Вынос лонгов','text':'Цена падает вместе с резким снижением OI. Это очистка плеч, но ещё не LONG-сигнал.','confirm':'Цена стабилизируется, Spot-продажи ослабевают.','cancel':'OI снова растёт вместе с продажами.'}
    if pm<=0 and sz>.7 and oz<.3 and uz<.5:r={'regime':'Accumulation / Absorption','confidence':'MEDIUM','title':'Накопление / абсорбция','text':'Цена не растёт, но Spot показывает покупателя без перегрева плеч. Возможен сценарий накопления.','confirm':'Spot продолжает покупать, цена перестаёт обновлять лои.','cancel':'Spot разворачивается вниз.'}
    if pm>=0 and sz>.6 and oz<-.5 and uz<.3:r={'regime':'Healthy Deleveraging','confidence':'HIGH','title':'Здоровое снижение плеч','text':'Цена держится при сильном Spot, а OI / Funding охлаждаются. Плечи очищаются без потери спроса.','confirm':'Spot сохраняет спрос после снижения OI.','cancel':'Spot также начинает слабеть.'}
    return r

def etf():
    try:
        rows=[]
        for r in csv.DictReader(io.StringIO(gett('https://raw.githubusercontent.com/bykarantelicom/crypto-datasets/main/data/etf-flows.csv'))):
            if r.get('asset')=='BTC': rows.append((r['date'],float(r['net_inflow_usd'])/1_000_000))
        vals=[v for _,v in rows]; d=vals[0]; d3=sum(vals[:3]); m=mean(vals[:5])-mean(vals[5:10]); st,cl=etf_class(d,d3,m)
        return {'status':st,'cls':cl,'daily':d,'d3':d3,'momentum5':m,'date':rows[0][0],'source':'SoSoValue dataset'}
    except Exception as e:return {'status':'Unavailable','cls':'off','daily':None,'d3':None,'momentum5':None,'date':None,'error':str(e)[:160]}

def agg(xs,n):
    if n<=1:return xs
    out=[]
    for i in range(0,len(xs),n):
        g=xs[i:i+n]
        if len(g)==n: out.append(sum(g))
    return out

def taker(inst_type,tf):
    period='1H'; group=1
    if tf=='4h':group=4
    elif tf=='1d':period='1D'
    elif tf=='1w':period='1D'; group=7
    j=getj(f'https://www.okx.com/api/v5/rubik/stat/taker-volume?ccy=BTC&instType={inst_type}&period={period}')
    vals=[]
    for r in reversed(j.get('data') or []):
        try: vals.append(float(r[2])-float(r[1]))
        except: pass
    vals=agg(vals,group)
    if len(vals)<10: raise RuntimeError('insufficient taker history')
    return vals

def price(tf):
    bar={'1h':'1H','4h':'4H','1d':'1D','1w':'1W'}[tf]
    j=getj(f'https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar={bar}&limit=100')
    rows=j.get('data') or []
    if len(rows)<2: raise RuntimeError('OKX price unavailable')
    p1=float(rows[0][4]); p0=float(rows[1][4]); return p1,(p1/p0-1)*100

def oi(tf):
    period='1H'; group=1
    if tf=='4h':group=4
    elif tf=='1d':period='1D'
    elif tf=='1w':period='1D'; group=7
    j=getj(f'https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume?ccy=BTC&period={period}')
    arr=[float(r[1]) for r in reversed(j.get('data') or []) if len(r)>1]
    if group>1: arr=arr[::group]
    ch=[(arr[i]/arr[i-1]-1)*100 for i in range(1,len(arr)) if arr[i-1]]
    if len(ch)<3: raise RuntimeError('OKX OI unavailable')
    z=zlast(ch); st,cl=oi_class(z); return {'status':st,'cls':cl,'z':z,'change':ch[-1],'source':'OKX'}

def funding():
    j=getj('https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=100')
    vals=[]
    for r in reversed(j.get('data') or []):
        try: vals.append(float(r.get('realizedRate') or r.get('fundingRate')))
        except: pass
    if len(vals)<3: raise RuntimeError('OKX funding unavailable')
    z=zlast(vals); st,cl=funding_class(z); return {'status':st,'cls':cl,'z':z,'rate':vals[-1],'source':'OKX'}

def state(tf,e):
    errors=[]
    p,pm=price(tf)
    try:
        x=taker('SPOT',tf); z=zlast(x); st,cl=flow_class(z); spot={'status':st,'cls':cl,'z':z,'delta':x[-1],'source':'OKX'}
    except Exception as ex: errors.append('Spot: '+str(ex)[:100]); spot={'status':'Unavailable','cls':'off','z':0.0,'delta':None}
    try:
        x=taker('CONTRACTS',tf); z=zlast(x); st,cl=flow_class(z); fut={'status':st,'cls':cl,'z':z,'delta':x[-1],'source':'OKX'}
    except Exception as ex: errors.append('Futures: '+str(ex)[:100]); fut={'status':'Unavailable','cls':'off','z':0.0,'delta':None}
    try:o=oi(tf)
    except Exception as ex:errors.append('OI: '+str(ex)[:100]); o={'status':'Unavailable','cls':'off','z':0.0,'change':None}
    try:f=funding()
    except Exception as ex:errors.append('Funding: '+str(ex)[:100]); f={'status':'Unavailable','cls':'off','z':0.0,'rate':None}
    return {'ok':True,'ts':int(time.time()),'tf':tf,'price':p,'priceMove':pm,'spot':spot,'futures':fut,'oi':o,'funding':f,'etf':e,'regime':regime(pm,spot['z'],fut['z'],o['z'],f['z']),'errors':errors}

def main():
    e=etf(); states={}
    for tf in ('1h','4h','1d','1w'):
        try:states[tf]=state(tf,e)
        except Exception as ex:states[tf]={'ok':False,'tf':tf,'errors':[str(ex)[:220]],'etf':e}
    (DATA/'state.json').write_text(json.dumps({'generated_at':int(time.time()),'states':states},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    hp=DATA/'history.json'
    try:h=json.loads(hp.read_text(encoding='utf-8'))
    except:h=[]
    if states.get('4h',{}).get('ok'):
        d=states['4h']; h.append({'ts':d['ts'],'price':d['price'],'spot_z':d['spot']['z'],'futures_z':d['futures']['z'],'oi_z':d['oi']['z'],'funding_z':d['funding']['z'],'etf_daily':d['etf'].get('daily'),'regime':d['regime']['regime']})
    hp.write_text(json.dumps(h[-500:],ensure_ascii=False,separators=(',',':')),encoding='utf-8')
if __name__=='__main__':main()
