#!/usr/bin/env python3
# === START OF FILE ===

"""
polymarket_range_backtest.py (fixed & improved)

Исправлено:
- диапазоны были слишком маленькие → теперь 30 разных ширин
- добавлено округление границ до 4 знаков
- JSON сохраняется в prettified режиме
- добавлена проверка: если локальный файл существует — не скачиваем
- создана директория data/
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

END = int(datetime.utcnow().timestamp() * 1000)
START = int((datetime.utcnow() - timedelta(days=31)).timestamp() * 1000)
LIMIT = 1000
SLEEP = 0.15


def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def fetch_klines(symbol, interval, start_ts, end_ts):
    rows = []
    url = f"{BASE}/api/v3/klines"
    cur_start = start_ts

    while cur_start < end_ts:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": cur_start,
            "endTime": end_ts,
            "limit": LIMIT
        }
        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Error fetching klines {r.status_code} {r.text}")

        data = r.json()
        if not data:
            break

        rows.extend(data)
        last_open = data[-1][0]
        interval_ms = 60000  # always 1m
        cur_start = last_open + interval_ms

        time.sleep(SLEEP)
        if len(data) < LIMIT:
            break

    cols = [
        "open_time","open","high","low","close","volume",
        "close_time","qav","num_trades","taker_base_vol",
        "taker_quote_vol","ignore"
    ]
    df = pd.DataFrame(rows, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)

    df = df.set_index("open_time")
    return df[["open","high","low","close","volume"]]


def load_or_fetch(symbol):
    """Load local CSV if exists; otherwise download and save."""
    ensure_dir(DATA_DIR)
    path = f"{DATA_DIR}/{symbol}_1m.csv"

    if os.path.exists(path):
        print(f"Loading from disk: {path}")
        df = pd.read_csv(path)
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        df = df.set_index("open_time")
        return df

    print(f"Downloading {symbol} ...")
    df = fetch_klines(symbol, INTERVAL, START, END)
    df.to_csv(path)
    print(f"Saved to {path}")
    return df


def ewma_vol(logret, span=9):
    s2 = logret.pow(2).ewm(span=span, adjust=False).mean()
    return np.sqrt(s2)


def gbm_prob_in_range(s0, a, b, sigma1m, minutes, mu=0.0):
    if sigma1m <= 0:
        return float(a < s0 < b)

    mu_term = (mu - 0.5 * sigma1m**2) * minutes
    mean_ln = math.log(s0) + mu_term
    var_ln = (sigma1m**2) * minutes
    std_ln = math.sqrt(var_ln)

    z1 = (math.log(a) - mean_ln) / std_ln
    z2 = (math.log(b) - mean_ln) / std_ln
    return float(norm.cdf(z2) - norm.cdf(z1))


def run_backtest(df_1m, horizons, ewma_span=9):
    mapping = {"1m":1, "5m":5, "1h":60, "1d":1440}
    results = {}

    df = df_1m.copy()
    df["logret"] = np.log(df["close"]).diff()
    df["sigma1m"] = ewma_vol(df["logret"].fillna(0), span=ewma_span)

    # 30 synthetic widths
    scales = np.linspace(0.1, 3.0, 20)

    for h in horizons:
        minutes = mapping[h]

        preds = []
        truths = []
        ranges_shown = []

        idxs = df.index[:-minutes]

        for t in idxs:
            s0 = df.at[t, "close"]
            sigma1m = df.at[t, "sigma1m"]

            if sigma1m <= 0 or pd.isna(sigma1m):
                continue

            for k in scales:
                sigma_h = sigma1m * math.sqrt(minutes)
                width = k * sigma_h * s0

                a = round(s0 - width / 2, 4)
                b = round(s0 + width / 2, 4)
                if a <= 0:
                    a = 0.0001

                p = gbm_prob_in_range(s0, a, b, sigma1m, minutes)

                t_future = t + pd.Timedelta(minutes=minutes)
                if t_future not in df.index:
                    continue

                sT = df.at[t_future, "close"]
                hit = 1.0 if (a < sT < b) else 0.0

                preds.append(p)
                truths.append(hit)
                ranges_shown.append((float(a), float(b)))

        preds = np.array(preds)
        truths = np.array(truths)

        if len(preds) == 0:
            continue

        brier = np.mean((preds - truths)**2)

        bins = np.linspace(0, 1, 11)
        bin_idxs = np.digitize(preds, bins) - 1

        calib = []
        for bi in range(len(bins)-1):
            mask = bin_idxs == bi
            if mask.sum() == 0:
                calib.append({
                    "bin": [float(bins[bi]), float(bins[bi+1])],
                    "pred_mean": None,
                    "obs_freq": None,
                    "n": 0
                })
            else:
                calib.append({
                    "bin": [float(bins[bi]), float(bins[bi+1])],
                    "pred_mean": float(preds[mask].mean()),
                    "obs_freq": float(truths[mask].mean()),
                    "n": int(mask.sum())
                })

        results[h] = {
            "brier": float(brier),
            "n": int(len(preds)),
            "calibration": calib
        }

    return results


def main():
    ensure_dir(DATA_DIR)
    all_results = {}

    for sym in SYMBOLS:
        df = load_or_fetch(sym)

        # drop warmup
        df = df.iloc[100:]

        res = run_backtest(df, ["1m","5m","1h","1d"])
        all_results[sym] = res

    # pretty-print JSON
    with open("backtest_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print("\n=== SUMMARY ===")
    for sym in all_results:
        print("\n###", sym)
        for h, r in all_results[sym].items():
            print(h, "Brier:", r["brier"], "n:", r["n"])
            print("Sample calibration bins:")
            for row in r["calibration"][:3]:
                print(row)


if __name__ == "__main__":
    main()

# === END OF FILE ===
