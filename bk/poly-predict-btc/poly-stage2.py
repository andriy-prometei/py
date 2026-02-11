#!/usr/bin/env python3
import os, json, math, time
import numpy as np
import pandas as pd
import requests
from pathlib import Path
from sklearn.metrics import brier_score_loss
from scipy.stats import norm
from datetime import datetime, timedelta

BASE = "https://api.binance.com"
SYMBOLS = ["BTCUSDT"]#,"ETHUSDT","SOLUSDT"]
START_DAYS=31
INTERVAL="1m"
CACHE_DIR = Path("klines_cache")
STAGE2_FILE = Path("stage2.json")

EWMA_SEARCH_GRID=np.linspace(0.01,0.5,20)
BLEND_GRID=np.linspace(0.0,1.0,21)
N_BINS=20
HORIZONS={"1m":1,"5m":5,"1h":60,"1d":1440}
SLEEP=0.15

def log(msg): print("[poly]", msg)
def ensure_dir(p): p.mkdir(exist_ok=True)

def fetch_klines(symbol,start_ts,end_ts):
    url=f"{BASE}/api/v3/klines"
    rows=[]
    cur=start_ts
    limit=1000
    while cur<end_ts:
        params={"symbol":symbol,"interval":INTERVAL,"startTime":cur,"endTime":end_ts,"limit":limit}
        r=requests.get(url,params=params,timeout=30)
        if r.status_code!=200: raise RuntimeError(f"{r.status_code} {r.text}")
        data=r.json()
        if not data: break
        rows.extend(data)
        last_open=data[-1][0]
        cur=last_open+60000
        time.sleep(SLEEP)
    cols=["open_time","open","high","low","close","volume","close_time","qav","num_trades","taker_base_vol","taker_quote_vol","ignore"]
    df=pd.DataFrame(rows,columns=cols)
    df["open_time"]=pd.to_datetime(df["open_time"],unit="ms",utc=True)
    for c in ["open","high","low","close","volume"]: df[c]=df[c].astype(float)
    df=df.set_index("open_time")
    return df[["open","high","low","close","volume"]]

def get_klines_cached(symbol):
    ensure_dir(CACHE_DIR)
    fname=CACHE_DIR/f"{symbol}_{INTERVAL}.csv"
    if fname.exists():
        log(f"{symbol}: загружено из CSV")
        return pd.read_csv(fname,parse_dates=["open_time"],index_col="open_time")
    log(f"{symbol}: скачиваем с Binance...")
    end=int(datetime.utcnow().timestamp()*1000)
    start=int((datetime.utcnow()-timedelta(days=START_DAYS)).timestamp()*1000)
    df=fetch_klines(symbol,start,end)
    df.to_csv(fname)
    log(f"{symbol}: сохранено в {fname}")
    return df

def resample_df(df,minutes):
    if minutes==1: return df
    rule=f"{minutes}T"
    agg={"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
    return df.resample(rule).agg(agg).dropna()

def evma_from_end(arr,alpha):
    arr=np.array(arr)
    if len(arr)==0: return np.nan
    w=np.array([(1-alpha)**i for i in range(len(arr))])[::-1]
    w/=w.sum()
    return float(np.sum(arr*w))

def gbm_prob_in_range(s0,a,b,sigma,minutes,mu=0):
    if sigma<=0: return float(a<s0<b)
    mean_ln=math.log(s0)+(mu-0.5*sigma*sigma)*minutes
    var_ln=sigma*sigma*minutes
    sd=math.sqrt(var_ln)
    z1=(math.log(a)-mean_ln)/sd
    z2=(math.log(b)-mean_ln)/sd
    return float(norm.cdf(z2)-norm.cdf(z1))

def generate_stage1(df,minutes):
    df["logret"]=np.log(df["close"]).diff()
    preds,truths,windows=[],[],[]
    idx=df.index[:-minutes]
    for t in idx:
        past=df.loc[:t]["logret"].tail(200).dropna().tolist()
        if len(past)<20: continue
        sigma1m=np.std(past)
        s0=df.at[t,"close"]
        sigma_h=sigma1m*math.sqrt(minutes)
        w=sigma_h*s0*0.5
        a=max(0.0001,s0-w/2)
        b=s0+w/2
        p_raw=gbm_prob_in_range(s0,a,b,sigma1m,minutes)
        tf=t+pd.Timedelta(minutes=minutes)
        if tf not in df.index: continue
        hit=1.0 if a<df.at[tf,"close"]<b else 0.0
        preds.append(p_raw)
        truths.append(hit)
        windows.append(past)
    return preds,truths,windows

def apply_correction(p,k):
    idx=min(int(p*len(k)),len(k)-1)
    return float(max(0.0,min(1.0,p*k[idx])))

def compute_bins(preds,truths,n_bins=N_BINS):
    if len(preds)==0: return [],[]
    preds=np.array(preds)
    truths=np.array(truths)
    edges=np.quantile(preds,np.linspace(0,1,n_bins+1))
    bins_out=[]
    k_new=[]
    for i in range(n_bins):
        low,high=edges[i],edges[i+1]
        mask=(preds>=low)&(preds<high) if i<n_bins-1 else (preds>=low)&(preds<=high)
        arr_p=preds[mask]
        arr_y=truths[mask]
        if len(arr_p)==0:
            bins_out.append({"bin":i,"range":[round(low,4),round(high,4)],"pred":None,"obs":None,"count":0})
            k_new.append(1.0)
        else:
            pred=arr_p.mean()
            obs=arr_y.mean()
            bins_out.append({"bin":i,"range":[round(low,4),round(high,4)],"pred":float(pred),"obs":float(obs),"count":len(arr_p)})
            k_new.append(float(obs/pred if pred>0 else 1.0))
    return bins_out,k_new

def main():
    ensure_dir(CACHE_DIR)
    all_results={}
    for sym in SYMBOLS:
        df=get_klines_cached(sym)
        all_results[sym]={}
        for h,minutes in HORIZONS.items():
            df_r=resample_df(df,minutes)
            p,y,w=generate_stage1(df_r,minutes)
            if len(p)==0: continue
            # EWMA α оптимизация
            best_alpha=max(EWMA_SEARCH_GRID,key=lambda a: -brier_score_loss(y,[min(1.0,max(0.0,evma_from_end(wi,a))) for wi in w]))
            p_evma=np.array([min(1.0,max(0.0,evma_from_end(wi,best_alpha))) for wi in w])
            # Blend α оптимизация
            best_blend=max(BLEND_GRID,key=lambda a: -brier_score_loss(y,[min(1.0,max(0.0,a*pr+(1-a)*pe)) for pr,pe in zip(p,p_evma)]))
            p_blend=np.array([min(1.0,max(0.0,best_blend*pr+(1-best_blend)*pe)) for pr,pe in zip(p,p_evma)])
            # Бины и калибровка
            bins_out,k_new=compute_bins(p_blend,y)
            # Brier score
            brier={"raw":float(brier_score_loss(y,p)),
                   "evma":float(brier_score_loss(y,p_evma)),
                   "blend":float(brier_score_loss(y,p_blend)),
                   "final":float(brier_score_loss(y,p_blend))}
            all_results[sym][h]={"best_alpha":best_alpha,"blend_alpha":best_blend,"brier":brier,"bins":bins_out,"k":k_new}
    STAGE2_FILE.write_text(json.dumps(all_results,indent=2))
    log(f"stage2.json записан.")

if __name__=="__main__":
    main()
