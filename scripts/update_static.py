import csv, io, json, statistics, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
HEADERS={'User-Agent':'Mozilla/5.0 FlowScope/1.0'}

def mean(xs): return sum(xs)/len(xs) if xs else 0.0
def stdev(xs):
    if len(xs)<2:return 1.0
    s=statistics.pstdev(xs); return s if s>1e-12 else 1.0
def z_last(xs):
    if len(xs)<10:return 0.0
    h=xs[:-1]; return (xs[-1]-mean(h))/stdev(h)
def get_json(url):
    r=requests.get(url,timeout=25,headers=HEADERS); r.raise_for_status(); return r.json()
def get_text(url):
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

def regime_engine(pm,sz,fz,oz,uz):
    r={'regime':'Mixed Market','confidence':'LOW','title':'Смешанный рынок','text':'Потоки пока не формируют чистую закономерность.','confirm':'Ждём согласования Spot / Futures / OI / Funding.','cancel':'—'}
    if pm>0 and sz>.45 and fz>-.45 and oz<1.5 and uz<1.5:r={'regime':'Healthy Spot Growth','confidence':'MEDIUM','title':'Здоровый спотовый рост','text':'Рост подтверждается спотовым спросом, а плечи пока не выглядят экстремально перегретыми.','confirm':'Spot остаётся сильным, OI не ускоряется экстремально.','cancel':'Spot слабеет, а Futures / OI начинают доминировать.'}
    if pm>0 and sz<.45 and fz>1.0 and oz>1.0 and uz>.6:r={'regime':'Futures-driven Rise','confidence':'HIGH','title':'Перегретый рост на фьючерсах','text':'Цена растёт преимущественно за счёт деривативов. Spot не подтверждает движение, OI и Funding повышают уязвимость структуры.','confirm':'Spot остаётся слабым, а импульс Futures начинает затухать.','cancel':'Появляется устойчивый сильный Spot-покупатель.'}
    if pm>=0 and sz<-.45 and oz>.7 and uz>.5:r={'regime':'Distribution','confidence':'MEDIUM','title':'Распределение','text':'Цена держится, но Spot ухудшается на фоне повышенного leverage. Риск разворота вниз растёт.','confirm':'Spot-поток продолжает снижаться, цена перестаёт обновлять хаи.','cancel':'Возвращается сильный Spot-спрос.'}
    if pm<0 and fz<-.7 and oz>.5:r={'regime':'Short Build-up','confidence':'MEDIUM','title':'Наращивание шортов','text':'Цена падает вместе с агрессивными продажами Futures и ростом OI. Новые позиции поддерживают снижение.','confirm':'OI продолжает расти на снижении.','cancel':'Spot абсорбирует продажи, OI перестаёт расти.'}
    if pm<0 and oz<-1.1:r={'regime':'Long Flush','confidence':'MEDIUM','title':'Вынос лонгов','text':'Цена падает вместе с резким снижением OI. Это очистка плеч, но ещё не LONG-сигнал.','confirm':'Цена стабилизируется, Spot-продажи ослабевают.','cancel':'OI снова растёт вместе с продажами.'}
    if pm<=0 and sz>.7 and oz<.3 and uz<.5:r={'regime':'Accumulation / Absorption','confidence':'MEDIUM','title':'Накопление / абсорбция','text':'Цена не растёт, но Spot показывает покупателя без перегрева плеч. Возможен сценарий накопления.','confirm':'Spot продолжает покупать, цена перестаёт обновлять лои.','cancel':'Spot разворачивается вниз.'}
    if pm>=0 and sz>.6 and oz<-.5 and uz<.3:r={'regime':'Healthy Deleveraging','confidence':'HIGH','title':'Здоровое снижение плеч','text':'Цена держится при сильном Spot, а OI / Funding охлаждаются. Плечи очищаются без потери спроса.','confirm':'Spot сохраняет спрос после снижения OI.','cancel':'Spot также начинает слабеть.'}
    return r

def fetch_etf():
    try:
        text=get_text('https://raw.githubusercontent.com/bykarantelicom/crypto-datasets/main/data/etf-flows.csv')
        rows=[]
        for r in csv.DictReader(io.StringIO(text)):
            if r.get('asset')=='BTC':
                rows.append((r['date'],float(r['net_inflow_usd'])/1_000_000.0))
        if not rows: raise RuntimeError('empty ETF dataset')
        vals=[v for _,v in rows]
        daily=vals[0]; d3=sum(vals[:3]); last5=mean(vals[:5]); prev5=mean(vals[5:10]) if len(vals)>=10 else 0.0; mom=last5-prev5
        status,cls=etf_class(daily,d3,mom)
        return {'status':status,'cls':cls,'daily':daily,'d3':d3,'momentum5':mom,'date':rows[0][0],'source':'bykaranteli/SoSoValue'}
    except Exception as e:
        return {'status':'Unavailable','cls':'off','daily':None,'d3':None,'momentum5':None,'date':None,'error':str(e)[:160]}

def aggregate(xs,n):
    if n<=1:return xs
    out=[]
    for i in range(0,len(xs),n):
        g=xs[i:i+n]
        if len(g)==n: out.append(sum(g))
    return out

def okx_taker_series(inst_type,tf):
    period='1H'; group=1
    if tf=='4h': group=4
    elif tf=='1d': period='1D'
    elif tf=='1w': period='1D'; group=7
    url=f'https://www.okx.com/api/v5/rubik/stat/taker-volume?ccy=BTC&instType={inst_type}&period={period}'
    j=get_json(url)
    rows=j.get('data') or []
    # OKX returns newest first: [ts, sellVol, buyVol]
    vals=[]
    for r in reversed(rows):
        try: vals.append(float(r[2])-float(r[1]))
        except: pass
    vals=aggregate(vals,group)
    if len(vals)<10: raise RuntimeError(f'not enough OKX {inst_type} taker data')
    return vals

def bybit_price(tf):
    iv={'1h':'60','4h':'240','1d':'D','1w':'W'}[tf]
    j=get_json(f'https://api.bybit.com/v5/market/kline?category=spot&symbol=BTCUSDT&interval={iv}&limit=120')
    rows=j['result']['list']
    if len(rows)<2: raise RuntimeError('Bybit price unavailable')
    p1=float(rows[0][4]); p0=float(rows[1][4]); return p1,(p1/p0-1)*100

def bybit_oi(tf):
    iv={'1h':'1h','4h':'4h','1d':'1d','1w':'1d'}[tf]
    j=get_json(f'https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime={iv}&limit=200')
    arr=list(reversed([float(x['openInterest']) for x in j['result']['list']]))
    if tf=='1w': arr=arr[::7]
    changes=[(arr[i]/arr[i-1]-1)*100 for i in range(1,len(arr)) if arr[i-1]]
    if len(changes)<3: raise RuntimeError('Bybit OI unavailable')
    oz=z_last(changes); och=changes[-1]; ost,ocl=oi_class(oz)
    return {'status':ost,'cls':ocl,'z':oz,'change':och}

def bybit_funding():
    j=get_json('https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=200')
    arr=list(reversed([float(x['fundingRate']) for x in j['result']['list']]))
    if len(arr)<3: raise RuntimeError('Bybit funding unavailable')
    uz=z_last(arr); rate=arr[-1]; ust,ucl=funding_class(uz)
    return {'status':ust,'cls':ucl,'z':uz,'rate':rate}

def fetch_state(tf,etf):
    errors=[]
    price,pm=bybit_price(tf)
    try:
        sdel=okx_taker_series('SPOT',tf); sz=z_last(sdel); sst,scl=flow_class(sz)
        spot={'status':sst,'cls':scl,'z':sz,'delta':sdel[-1],'source':'OKX taker volume'}
    except Exception as e:
        errors.append('Spot: '+str(e)[:120]); spot={'status':'Unavailable','cls':'off','z':0.0,'delta':None}
    try:
        fdel=okx_taker_series('CONTRACTS',tf); fz=z_last(fdel); fst,fcl=flow_class(fz)
        futures={'status':fst,'cls':fcl,'z':fz,'delta':fdel[-1],'source':'OKX taker volume'}
    except Exception as e:
        errors.append('Futures: '+str(e)[:120]); futures={'status':'Unavailable','cls':'off','z':0.0,'delta':None}
    try: oi=bybit_oi(tf)
    except Exception as e:
        errors.append('OI: '+str(e)[:120]); oi={'status':'Unavailable','cls':'off','z':0.0,'change':None}
    try: funding=bybit_funding()
    except Exception as e:
        errors.append('Funding: '+str(e)[:120]); funding={'status':'Unavailable','cls':'off','z':0.0,'rate':None}
    reg=regime_engine(pm,spot['z'],futures['z'],oi['z'],funding['z'])
    return {'ok':True,'ts':int(time.time()),'tf':tf,'price':price,'priceMove':pm,'spot':spot,'futures':futures,'oi':oi,'funding':funding,'etf':etf,'regime':reg,'errors':errors}

def main():
    etf=fetch_etf(); states={}
    for tf in ('1h','4h','1d','1w'):
        try: states[tf]=fetch_state(tf,etf)
        except Exception as e: states[tf]={'ok':False,'tf':tf,'errors':[str(e)[:220]],'etf':etf}
    payload={'generated_at':int(time.time()),'states':states}
    (DATA/'state.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    hp=DATA/'history.json'
    try: hist=json.loads(hp.read_text(encoding='utf-8'))
    except: hist=[]
    if states.get('4h',{}).get('ok'):
        d=states['4h']; hist.append({'ts':d['ts'],'price':d['price'],'spot_z':d['spot']['z'],'futures_z':d['futures']['z'],'oi_z':d['oi']['z'],'funding_z':d['funding']['z'],'etf_daily':d['etf'].get('daily'),'regime':d['regime']['regime']})
    hp.write_text(json.dumps(hist[-500:],ensure_ascii=False,separators=(',',':')),encoding='utf-8')
if __name__=='__main__': main()
