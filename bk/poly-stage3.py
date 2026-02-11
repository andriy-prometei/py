#!/usr/bin/env python3
# === START OF FILE ===

"""
poly-stage3.py

Изменения:
- EWMA span = 9
- После калибрации новые предсказания на реальных данных сохраняются в отдельный JSON
"""

import os
import time
import math
import json
import requests
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from tqdm import tqdm
from scipy.stats import norm

BASE = "https://api.binance.com"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTERVAL = "1m"
DATA_DIR = "data"
RESULT_FILE = "backtest_results.json"
RESULT_STAGE2_FILE = "backtest_results_stage2.json"

END = int(datetime.utcnow().timestamp() * 1000)
START = int((datetime.utcnow() - timedelta(days=31)).timestamp() * 1000)
LIMIT = 1000
SLEEP = 0.15

EWMA_SPAN = 9  # span уменьшен с 60 до 9

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

# ----------------------------------------------------------
# FETCH / LOAD KLINES
# ----------------------------------------------------------

def fetch_klines(symbol, interval, start_ts, end_ts):
    rows = []
    url = f"{BASE}/api/v3/klines"
    cur_start = start_ts

    while cur_start < end_ts:
        params = {"symbol": symbol,"interval": interval,"startTime": cur_start,"endTime": end_ts,"limit": LIMIT}
        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Error fetching klines {r.status_code} {r.text}")

        data = r.json()
        if not data: break

        rows.extend(data)
        last_open = data[-1][0]
        cur_start = last_open + 60000  # 1m
        time.sleep(SLEEP)
        if len(data) < LIMIT: break

    cols = ["open_time","open","high","low","close","volume","close_time","qav","num_trades","taker_base_vol","taker_quote_vol","ignore"]
    df = pd.DataFrame(rows, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)
    df = df.set_index("open_time")
    return df[["open","high","low","close","volume"]]

def load_or_fetch(symbol):
    ensure_dir(DATA_DIR)
    path = f"{DATA_DIR}/{symbol}_1m.csv"
    if os.path.exists(path):
        df = pd.read_csv(path)
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        df = df.set_index("open_time")
        return df
    df = fetch_klines(symbol, INTERVAL, START, END)
    df.to_csv(path)
    return df

# ----------------------------------------------------------
# VOLATILITY, GBM & BACKTEST
# ----------------------------------------------------------

def ewma_vol(logret, span=EWMA_SPAN):
    s2 = logret.pow(2).ewm(span=span, adjust=False).mean()
    return np.sqrt(s2)

def gbm_prob_in_range(s0, a, b, sigma1m, minutes, mu=0.0):
    if sigma1m <= 0: return float(a < s0 < b)
    mu_term = (mu - 0.5 * sigma1m**2) * minutes
    mean_ln = math.log(s0) + mu_term
    var_ln = (sigma1m**2) * minutes
    std_ln = math.sqrt(var_ln)
    z1 = (math.log(a) - mean_ln) / std_ln
    z2 = (math.log(b) - mean_ln) / std_ln
    return float(norm.cdf(z2) - norm.cdf(z1))

def run_backtest(df_1m, horizons):
    mapping = {"1m":1,"5m":5,"1h":60,"1d":1440}
    results = {}
    df = df_1m.copy()
    df["logret"] = np.log(df["close"]).diff()
    df["sigma1m"] = ewma_vol(df["logret"].fillna(0))
    scales = np.linspace(0.1, 3.0, 30)

    for h in horizons:
        minutes = mapping[h]
        preds, truths = [], []
        idxs = df.index[:-minutes]

        for t in idxs:
            s0 = df.at[t,"close"]
            sigma1m = df.at[t,"sigma1m"]
            if sigma1m <= 0 or pd.isna(sigma1m): continue

            for k in scales:
                sigma_h = sigma1m * math.sqrt(minutes)
                width = k * sigma_h * s0
                a = round(s0 - width/2,4)
                b = round(s0 + width/2,4)
                if a <= 0: a = 0.0001
                p = gbm_prob_in_range(s0,a,b,sigma1m,minutes)
                t_future = t + pd.Timedelta(minutes=minutes)
                if t_future not in df.index: continue
                sT = df.at[t_future,"close"]
                hit = 1.0 if (a < sT < b) else 0.0
                preds.append(p)
                truths.append(hit)
        preds = np.array(preds)
        truths = np.array(truths)
        brier = np.mean((preds-truths)**2)
        bins = np.linspace(0,1,11)
        bin_idx = np.digitize(preds,bins)-1
        calib=[]
        for bi in range(10):
            m=(bin_idx==bi)
            if m.sum()==0:
                calib.append({"bin":[bins[bi],bins[bi+1]],"pred_mean":None,"obs_freq":None,"n":0})
            else:
                calib.append({"bin":[bins[bi],bins[bi+1]],"pred_mean":float(preds[m].mean()),"obs_freq":float(truths[m].mean()),"n":int(m.sum())})
        results[h]={"brier":float(brier),"n":len(preds),"calibration":calib}
    return results

# ----------------------------------------------------------
# CALIBRATION
# ----------------------------------------------------------

def load_calibration():
    if not os.path.exists(RESULT_FILE): return None
    with open(RESULT_FILE,"r") as f:
        return json.load(f)

def build_correction_functions(calib_data):
    corr = {}
    bins = np.linspace(0,1,11)
    for sym, hdict in calib_data.items():
        corr[sym]={}
        for h, block in hdict.items():
            arr=[]
            for binrow in block["calibration"]:
                pmean=binrow["pred_mean"]
                ofreq=binrow["obs_freq"]
                if pmean is None or ofreq is None or pmean<=0: k=1.0
                else: k=ofreq/pmean
                arr.append(k)
            corr[sym][h]={"bins":bins,"k":np.array(arr)}
    return corr

def apply_correction(p,bins,kfactors):
    bi=np.digitize([p],bins)[0]-1
    bi=max(0,min(bi,len(kfactors)-1))
    return p*kfactors[bi]

# ----------------------------------------------------------
# MAIN
# ----------------------------------------------------------

def main():
    ensure_dir(DATA_DIR)
    calib_old = load_calibration()
    if calib_old is None:
        print("=== STAGE 1: Performing full backtest (EWMA span=9) ===")
        all_results={}
        for sym in SYMBOLS:
            df = load_or_fetch(sym)
            df=df.iloc[100:]
            res = run_backtest(df, ["1m","5m","1h","1d"])
            all_results[sym]=res
        with open(RESULT_FILE,"w") as f:
            json.dump(all_results,f,indent=2)
        print("Saved calibration to",RESULT_FILE)
        return

    print("=== STAGE 2: Calibration file found, applying corrections ===")
    corr = build_correction_functions(calib_old)
    all_corrected={}
    for sym in SYMBOLS:
        df = load_or_fetch(sym)
        df=df.iloc[100:]
        res_stage2={}
        for h in ["1m","5m","1h","1d"]:
            minutes = {"1m":1,"5m":5,"1h":60,"1d":1440}[h]
            scales = np.linspace(0.1,3.0,30)
            preds, truths=[],[]
            idxs = df.index[:-minutes]
            bins_kf = corr[sym][h]["bins"]
            kfactors = corr[sym][h]["k"]
            
            # Перед циклом по idxs:
            df["logret"] = np.log(df["close"]).diff()
            df["sigma1m"] = df["logret"].fillna(0).ewm(span=EWMA_SPAN, adjust=False).std()
            
            for t in idxs:
                s0=df.at[t,"close"]
                
                # Внутри цикла просто:
                sigma1m = df.at[t, "sigma1m"]
                if sigma1m <= 0 or pd.isna(sigma1m):
                    continue
                
#                sigma1m=df.at[t,"close"].ewm(span=EWMA_SPAN).std()[-1]
#                if sigma1m<=0 or pd.isna(sigma1m): continue
                for k in scales:
                    sigma_h=sigma1m*math.sqrt(minutes)
                    width=k*sigma_h*s0
                    a=round(s0-width/2,4)
                    b=round(s0+width/2,4)
                    if a<=0: a=0.0001
                    p=gbm_prob_in_range(s0,a,b,sigma1m,minutes)
                    p_corr=apply_correction(p,bins_kf,kfactors)
                    t_future=t+pd.Timedelta(minutes=minutes)
                    if t_future not in df.index: continue
                    sT=df.at[t_future,"close"]
                    hit=1.0 if (a<sT<b) else 0.0
                    preds.append(p_corr)
                    truths.append(hit)
            preds=np.array(preds)
            truths=np.array(truths)
            if len(preds)==0: continue
            brier=np.mean((preds-truths)**2)
            bins = np.linspace(0,1,11)
            bin_idx = np.digitize(preds,bins)-1
            calib=[]
            for bi in range(10):
                m=(bin_idx==bi)
                if m.sum()==0:
                    calib.append({"bin":[bins[bi],bins[bi+1]],"pred_mean":None,"obs_freq":None,"n":0})
                else:
                    calib.append({"bin":[bins[bi],bins[bi+1]],
                                  "pred_mean":float(preds[m].mean()),
                                  "obs_freq":float(truths[m].mean()),
                                  "n":int(m.sum())})
            res_stage2[h]={"brier":float(brier),"n":len(preds),"calibration":calib}
        all_corrected[sym]=res_stage2

    with open(RESULT_STAGE2_FILE,"w") as f:
        json.dump(all_corrected,f,indent=2)
    print("Saved corrected stage2 results to",RESULT_STAGE2_FILE)

if __name__=="__main__":
    main()

# === END OF FILE ===
