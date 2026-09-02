import json, math, re, statistics, time
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)

def mean(xs): return sum(xs)/len(xs) if xs else 0.0
def stdev(xs):
    if len(xs) < 2: return 1.0
    s=statistics.pstdev(xs)
    return s if s > 1e-12 else 1.0
def z_last(xs):
    if len(xs) < 10: return 0.0
    h=xs[:-1]
    return (xs[-1]-mean(h))/stdev(h)
def kline_delta(k):
    vol=float(k[5]); taker=float(k[9]); return 2*taker-vol

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
    if pm>=0 and sz<-.45 and oz>.7 and uz>.5:r={'regime':'Distribution','confidence':'MEDIUM','title':'Распределение','text':'Цена держится, но Spot ухудшается на фоне повышенного leverage. Риск разворота вниз растёт.','confirm':'Spot CVD продолжает снижаться, цена перестаёт обновлять хаи.','cancel':'Возвращается сильный Spot-спрос.'}
    if pm<0 and fz<-.7 and oz>.5:r={'regime':'Short Build-up','confidence':'MEDIUM','title':'Наращивание шортов','text':'Цена падает вместе с агрессивными продажами Futures и ростом OI. Новые позиции поддерживают снижение.','confirm':'OI продолжает расти на снижении.','cancel':'Spot абсорбирует продажи, OI перестаёт расти.'}
    if pm<0 and oz<-1.1:r={'regime':'Long Flush','confidence':'MEDIUM','title':'Вынос лонгов','text':'Цена падает вместе с резким снижением OI. Это очистка плеч, но ещё не LONG-сигнал.','confirm':'Цена стабилизируется, Spot-продажи ослабевают.','cancel':'OI снова растёт вместе с продажами.'}
    if pm<=0 and sz>.7 and oz<.3 and uz<.5:r={'regime':'Accumulation / Absorption','confidence':'MEDIUM','title':'Накопление / абсорбция','text':'Цена не растёт, но Spot показывает покупателя без перегрева плеч. Возможен сценарий накопления.','confirm':'Spot продолжает покупать, цена перестаёт обновлять лои.','cancel':'Spot разворачивается вниз.'}
    if pm>=0 and sz>.6 and oz<-.5 and uz<.3:r={'regime':'Healthy Deleveraging','confidence':'HIGH','title':'Здоровое снижение плеч','text':'Цена держится при сильном Spot, а OI / Funding охлаждаются. Плечи очищаются без потери спроса.','confirm':'Spot сохраняет спрос после снижения OI.','cancel':'Spot также начинает слабеть.'}
    return r

def get(url):
    r=requests.get(url,timeout=20,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status();return r.json()

def fetch_etf():
    try:
        r=requests.get('https://farside.co.uk/btc/',timeout=20,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status()
        soup=BeautifulSoup(r.text,'html.parser'); rows=[]
        for tr in soup.find_all('tr'):
            cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'])]
            if cells and re.match(r'^\d{2}\s+[A-Za-z]{3}\s+\d{4}$',cells[0]):
                raw=cells[-1].replace(',','').strip()
                if raw in {'','-'}:continue
                neg=raw.startswith('(') and raw.endswith(')'); raw=raw.strip('()$ ')
                try:
                    v=float(raw); rows.append((cells[0],-v if neg else v))
                except:pass
        if not rows:return {'status':'Unavailable','cls':'off','daily':None,'d3':None,'momentum5':None,'date':None}
        vals=[v for _,v in rows]; daily=vals[-1]; d3=sum(vals[-3:]); last5=mean(vals[-5:]); prev5=mean(vals[-10:-5]) if len(vals)>=10 else 0.0; mom=last5-prev5; status,cls=etf_class(daily,d3,mom)
        return {'status':status,'cls':cls,'daily':daily,'d3':d3,'momentum5':mom,'date':rows[-1][0]}
    except Exception as e:return {'status':'Unavailable','cls':'off','daily':None,'d3':None,'momentum5':None,'date':None,'error':str(e)[:160]}

def fetch_state(tf,etf):
    spot=get(f'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={tf}&limit=120')
    fut=get(f'https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval={tf}&limit=120')
    bytf={'1h':'1h','4h':'4h','1d':'1d','1w':'1d'}[tf]
    oi=get(f'https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime={bytf}&limit=60')
    funding=get('https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=100')
    sdel=[kline_delta(k) for k in spot]; fdel=[kline_delta(k) for k in fut]; sz,fz=z_last(sdel),z_last(fdel); sst,scl=flow_class(sz); fst,fcl=flow_class(fz)
    p0,p1=float(spot[-2][4]),float(spot[-1][4]); pm=(p1/p0-1)*100
    arr=list(reversed([float(x['openInterest']) for x in oi['result']['list']])); changes=[(arr[i]/arr[i-1]-1)*100 for i in range(1,len(arr))]; oz=z_last(changes); och=changes[-1]; ost,ocl=oi_class(oz)
    fr=list(reversed([float(x['fundingRate']) for x in funding['result']['list']])); uz=z_last(fr); rate=fr[-1]; ust,ucl=funding_class(uz)
    reg=regime_engine(pm,sz,fz,oz,uz)
    return {'ok':True,'ts':int(time.time()),'tf':tf,'price':p1,'priceMove':pm,'spot':{'status':sst,'cls':scl,'z':sz,'delta':sdel[-1]},'futures':{'status':fst,'cls':fcl,'z':fz,'delta':fdel[-1]},'oi':{'status':ost,'cls':ocl,'z':oz,'change':och},'funding':{'status':ust,'cls':ucl,'z':uz,'rate':rate},'etf':etf,'regime':reg,'errors':[]}

def main():
    etf=fetch_etf(); states={}
    for tf in ('1h','4h','1d','1w'):
        try: states[tf]=fetch_state(tf,etf)
        except Exception as e: states[tf]={'ok':False,'tf':tf,'errors':[str(e)[:200]],'etf':etf}
    payload={'generated_at':int(time.time()),'states':states}
    (DATA/'state.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    hp=DATA/'history.json'
    try: hist=json.loads(hp.read_text(encoding='utf-8'))
    except: hist=[]
    if states.get('4h',{}).get('ok'):
        d=states['4h']; hist.append({'ts':d['ts'],'price':d['price'],'spot_z':d['spot']['z'],'futures_z':d['futures']['z'],'oi_z':d['oi']['z'],'funding_z':d['funding']['z'],'etf_daily':d['etf'].get('daily'),'regime':d['regime']['regime']})
    hist=hist[-500:]
    hp.write_text(json.dumps(hist,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
if __name__=='__main__':main()
